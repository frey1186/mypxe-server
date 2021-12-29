#!/usr/bin/env python3
import struct
import socket
import logging
import os
import threading
import datetime
import urllib.parse
import json

# config file loading 
try:
    f = open('config.json', 'r')
    settings = json.load(f)
    f.close()
except Exception as e:
    print("Loading config file failed: ",e)
    print("Use the default config file:")
    settings = {
        "Server": "192.168.100.1",
        "Offer_addr_start": "192.168.100.120",
        "Offer_addr_counts": 50,
        "Netmask": "255.255.255.0",
        "Boardcast": "192.168.100.255",
        "Filename": {
            "x86_64": "boot/ipxe/boot.ipxe",
            "ppc64le": "boot/grub2/powerpc-ieee1275/core.elf"
        },
        "TFTProot": "./tftpboot"
    }
    print("Server   : ",settings.get("Server"))
    print("TFTProot : ",settings.get("TFTProot"))

# leases file loading     
try:
    f = open('leases.json', 'r')
    USED_IPADDR_DICT = json.load(f)
    f.close()
except  Exception as e:
    USED_IPADDR_DICT ={}     # MAC : IP ,


class DHCPServer(object):
    def __init__(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)    # reuse the addr
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)   # can use boardcast
        # self.sock.setsockopt(socket.SOL_IP, socket.SO_BINDTODEVICE, "eth1".encode())
        self.sock.bind(('', 67))

    def start(self):
        while True:
            message, client_addr = self.sock.recvfrom(1024)
            print("[dhcp] recv message ok. from client: ", client_addr)
            dhcp_offer = DHCPOffer(message)
            # print("USED_IPADDR_DICT", USED_IPADDR_DICT)
            # if dhcp_offer.flags == b'\x80\x00':
            #     client_addr = ('255.255.255.255', 68)
            # elif client_addr[0] == '0.0.0.0':
            #     client_addr = (dhcp_offer.your_ip, 68)
            client_addr = (dhcp_offer.boardcast_ip, 68)
            ret = dhcp_offer.make_offer_ack()
            self.sock.sendto(ret, client_addr)
            print("[dhcp] send dhcp offer/ack ok ; client addr:", client_addr)

class DHCPOffer(object):
    def __init__(self, client_message):
        self.message = client_message   # the message from client DISCOVER and REQUEST
        self.message_type_header = b'\x02\x01\x06\x00'
        self.xid, self.secs, self.flags, self.chaddr = \
            struct.unpack('!4x4s2s2s16x16s', self.message[:44])
        self.client_ip = b'\x00'*4   # 0.0.0.0
        self.your_ip = self._prepare_your_ip()
        self.next_server_ip = settings.get("Server")      # server ip from settings
        self.boardcast_ip = settings.get("Boardcast")
        self.giaddr = b'\x00'*4   # 0.0.0.0
        self.magic_cookie = 0x63825363
        self.opt53 = (53, 1, 2)  # opt:53, len:1, value: ack=5, offer=2
        self.opt54 = (54, 4, settings.get("Server"))
        self.opt51 = (51, 4, 86400)  # lease time 1 day  maybe not nessary
        self.opt58 = (58, 4, 43200)  # renew time   可以不发送
        self.opt59 = (59, 4, 86300)  # rebuild time   可以不发送
        self.opt01 = (1, 4, settings.get("Netmask")) # netmask  255.255.255.0
        self.opt28 = (28, 4, self.boardcast_ip)  # boardcast address 192.168.56.255
        self.opt03 = (3, 4, self.next_server_ip)
        self.opt66 = (66, 4, self.next_server_ip)   # opt 66 tftp server
        self.client_opt_dict = self._client_opts_unpack()


    def _prepare_your_ip(self):
        your_ip = ""
        if USED_IPADDR_DICT.get(self.chaddr[:6]):
            your_ip = USED_IPADDR_DICT[self.chaddr[:6]]
        else:
            start_ip = struct.unpack('!I', socket.inet_aton(settings.get("Offer_addr_start")))[0]
            for ip in range(start_ip, start_ip + settings.get("Offer_addr_counts")):
                your_ip = socket.inet_ntoa(struct.pack('!I', ip))
                if your_ip in USED_IPADDR_DICT.values():
                    continue
                else:
                    USED_IPADDR_DICT[self.chaddr[:6]] = your_ip    # IPV4 MAC
                    break
        return your_ip

    def _client_opts_unpack(self):
        """
        从 client message 240 之后的字节流中提取出option相关信息到一个字典中
        :return:
        """
        opt_msg = self.message[240:]
        opts_dict = {}    # tag:[len, raw_value]
        while opt_msg:
            (tag,) = struct.unpack('!B', opt_msg[0:1])
            if tag == 255:
                break
            (len,) = struct.unpack('!B', opt_msg[1:2])
            raw_value = opt_msg[2: 2 + len]
            opts_dict[tag] = [len, raw_value]
            opt_msg = opt_msg[2 + len:]
        return opts_dict

    def _make_head(self):
        self.offer_heaher = self.message_type_header
        self.offer_heaher += self.xid
        self.offer_heaher += self.secs + self.flags
        self.offer_heaher += self.client_ip
        self.offer_heaher += socket.inet_aton(self.your_ip)
        self.offer_heaher += socket.inet_aton(self.next_server_ip)
        self.offer_heaher += self.giaddr
        self.offer_heaher += self.chaddr
        self.offer_heaher += b'\x00' * 192  # hardware_address padding
        self.offer_heaher += struct.pack('!I', self.magic_cookie)
        return self.offer_heaher

    def _make_opt(self):
        self.offer_opt = struct.pack('!BBB', *self.opt53)  # opt 53
        self.offer_opt += struct.pack('!BB', *self.opt01[:2]) + socket.inet_aton(self.opt01[2])   # opt01
        self.offer_opt += struct.pack('!BB', *self.opt03[:2]) + socket.inet_aton(self.opt03[2])   # opt03
        self.offer_opt += struct.pack('!BB', *self.opt28[:2]) + socket.inet_aton(self.opt28[2])   # opt28
        self.offer_opt += struct.pack('!BBI', *self.opt51)  # opt 51
        self.offer_opt += struct.pack('!BB', *self.opt54[:2]) + socket.inet_aton(self.opt54[2])   # opt54
        self.offer_opt += struct.pack('!BBI', *self.opt58)  # opt 58  renew time
        self.offer_opt += struct.pack('!BBI', *self.opt59)  # opt 59  rebuild time
        try:
            # 关于client  Option: (55) Parameter Request List  55：长度：opt编号
            unpack_fmt = '!'+'B'*(self.client_opt_dict[55][0])   # 每个编号都是2位
            client_opt_req_list = struct.unpack(unpack_fmt, self.client_opt_dict[55][1])  # 请求编号的列表
            # (client_opt53,) = struct.unpack('!B', self.client_opt_dict[53][1])  # DISCOVER :1   REQUEST:3
            # if client_opt53 == 3 and 66 in client_opt_req_list:
            # OFFER包不给66+67， ACK包才给66+67
            if 66 in client_opt_req_list or 67 in client_opt_req_list:
                # client 请求了66，给66+67； 如果没有请求66，也不给66和67
                self.offer_opt += struct.pack('!BB', *self.opt66[:2]) + socket.inet_aton(self.opt66[2])   # opt66
                (client_arch,) = struct.unpack('!H', self.client_opt_dict[93][1])   # Client ARCH
                if client_arch in (0, 7, ):   # 0:x86_64 7:x86_64 EFI
                    if self.client_opt_dict.get(175):    # is IPXE
                        bootfile = settings["Filename"]["x86_64"]
                    elif client_arch == 0:
                        bootfile = "boot/ipxe/undionly.kpxe"
                    else:
                        bootfile = "boot/ipxe/ipxe.efi"
                elif client_arch in (12, 14, ): # 12: PPC  14:PPC_OPAL
                    bootfile = settings["Filename"]["ppc64le"]
                else:
                    bootfile = "boot/pxelinux.cfg/defult"
                self.opt67 = (67, len(bootfile), bootfile)
                self.offer_opt += struct.pack('!BB', *self.opt67[:2]) + bytes(self.opt67[2].encode('ascii'))  # opt67
        except Exception as e:
            print("the client msg do NOT have option 55:", e)
        return self.offer_opt

    def make_offer_ack(self):
        (client_opt53,) = struct.unpack('!B', self.client_opt_dict[53][1])   # DISCOVER :1   REQUEST:3
        if client_opt53 == 1:
            self.opt53 = (53, 1, 2)  # opt:53, len:1, value: ack=5, offer=2
        elif client_opt53 == 3:
            self.opt53 = (53, 1, 5)  # opt:53, len:1, value: ack=5, offer=2
        else:
            print("[dhcp] error: the client opt53 is wrong. opt53 = ", client_opt53)
        ret = self._make_head() + self._make_opt() + b'\xff'
        return ret

class TFTPServer(object):
    def __init__(self):
        self.mainsock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.mainsock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)  # reuse the addr
        self.mainsock.bind(('', 69))

    def _send_file_block(self, rrq_msg_dict, client_addr):
        send_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        send_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)    # reuse the addr
        send_sock.bind(('', 0))
        filename = rrq_msg_dict.get("filename")
        fullpath_filename = os.path.join(settings.get("TFTProot", "tftpboot"), filename)
        blksize = rrq_msg_dict.get("blksize", '512')  # str   如何没有就512

        data = struct.pack('!H', 6)  # opcode
        data += b'blksize' + b'\x00' + blksize.encode('ascii') + b'\x00'
        if rrq_msg_dict.get("tsize"):
            tsize = os.path.getsize(fullpath_filename)
            data += b'tsize' + b'\x00' + str(tsize).encode('ascii') + b'\x00'
        send_sock.sendto(data, client_addr)

        fo = open(fullpath_filename, 'rb')
        block_id = 1
        # retry_time = 0
        print("[tftp]  begin to send file :", filename)
        while True:
            message, addr = send_sock.recvfrom(1024)
            if struct.unpack('!H', message[0:2])[0]  == 4 :  # 开始发送数据
                data = struct.pack('!HH', 3, block_id)   # op: 3  发送数据
                blksize = int(blksize)   # 比如 '1468' --> 1468
                file_data = fo.read(blksize)
                send_sock.sendto(data+file_data, client_addr)
                if len(file_data) < blksize:
                    break
                block_id += 1
            else:   # op == 5
                # 收到出错误码，丢弃数据
                print("[tftp] recv a error code , drop it.  clinet:", addr)
                break
        print("[tftp]  send file :{} ...Done".format(filename))
        fo.close()
        send_sock.close()

    def _handle_rrq_message(self, message):
        rrq_msg_dict = {}
        rrq_msg_dict["op"] = struct.unpack('!H', message[0:2])[0]
        message_list = message[2:].split(b'\x00')
        rrq_msg_dict["filename"] = message_list[0].decode('ascii')
        rrq_msg_dict["mode"] = message_list[1].decode('ascii')
        for i in range(2, len(message_list)-1, 2):
            if message_list[i] == b'\x00':
                break
            rrq_msg_dict[message_list[i].decode()] = message_list[i+1].decode()
        return rrq_msg_dict

    def start(self):
        while True:
            message, client_addr = self.mainsock.recvfrom(1024)
            print("[tftp] recv message : tftp rrq , from :", client_addr)
            rrq_msg_dict = self._handle_rrq_message(message)
            if rrq_msg_dict.get("op") == 1:    # RRQ
                # 创建新的socket来发送文件；
                print(rrq_msg_dict)
                self._send_file_block(rrq_msg_dict, client_addr)
            else:
                print("[tftp] error:  The Message  from Client:", client_addr, "is NOT a tftp RRQ.")
        # self.mainsock.close()

class HTTPServer(object):
    def __init__(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(('', 80))
        self.sock.listen(1)
        self.httproot = settings.get("TFTProot")

    def _handle(self, conn, addr):
        message = conn.recv(1024)
        print("[http] recv message , client: ", addr)
        # method = GET  filename=/ipxe/boot.http.ipxe
        req_method, req_uri, req_version = message.decode('ascii').split('\r\n')[0].split(' ')
        second_line = message.decode('ascii').split('\r\n')[1]
        if "Range" in second_line:
            start_bytes, end_bytes = second_line.split('=')[1].split('-')
            range_bytes = [int(start_bytes), int(end_bytes)]
        else:
            range_bytes = []
        filename = os.path.join(self.httproot, req_uri.lstrip('/'))    # 分隔符问题
        filename = urllib.parse.unquote(filename)
        # print("filename:", filename, "is file :", os.path.isfile(filename))
        if os.path.isfile(filename) and range_bytes:
            status = "206 Partial Content"
            data = "HTTP/1.1 " + status + "\r\n"  # 发送数据的第一行
            # data += "Date: {} \r\n".format(datetime.datetime.now())  # 时间
            # data += "Server: MyPXE http server/0.1 Python3 \r\n"
            # data += "Last-Modified: {}\r\n".format(os.path.getmtime(filename))
            data += "Accept-Ranges: bytes\r\n"
            data += "Content-Length: {}\r\n".format(range_bytes[1]-range_bytes[0]+1)
            data += "Content_Range: bytes {}-{}/{}\r\n".format(*range_bytes, os.path.getsize(filename))
            data += "\r\n"
            data = data.encode('ascii')   # to bytes
            f = open(filename, 'rb')
            f.seek(range_bytes[0])
            data += f.read(range_bytes[1] - range_bytes[0] + 1)
            conn.sendall(data)
            print("[http] send file {} range ok(206). client: {}".format(filename, addr))
            f.close()
        elif os.path.isfile(filename):
            status = "200 OK"
            header = "HTTP/1.1 " + status + "\r\n"  # 发送数据的第一行
            # header += "Date: {} \r\n".format(datetime.datetime.now())  # 时间
            # header += "Server: MyPXE http server/0.1 Python3 \r\n"
            header += "Content-Length: {}\r\n".format(os.path.getsize(filename))
            # header += "Content-Type: application/octet-stream \r\n"  #
            header += "\r\n"
            conn.send(header.encode('ascii'))
            # print("[http] send http header ok. client: ", addr)
            f = open(filename, 'rb')
            conn.sendall(f.read())
            print("[http] send file {} ok(200). client: {}".format(filename, addr))
            f.close()
        else:
            status = "404 Not Found"    # 没有做太多的判断
            # status = "403 forbidden"    # 没有做太多的判断
            header = "HTTP/1.1 "+ status + "\r\n"    #发送数据的第一行
            header += "Date: {}\r\n".format(datetime.datetime.now())  # 时间
            header += "Server: MyPXE http server/0.1 Python3\r\n"
            header += "Content-Length: 0\r\n"
            header += "Content-Type: text/html \r\n"  #
            header += "\r\n"
            header += "<h1>404 Not Found</h1>"
            conn.send(header.encode('ascii'))
        conn.close()

    def start(self):
        while True:
            connection, client_addr = self.sock.accept()
            self._handle(connection, client_addr)

if __name__ == '__main__':

    dhcp_server = DHCPServer()
    dhcpd = threading.Thread(target= dhcp_server.start)
    dhcpd.daemon = True
    dhcpd.start()

    tftp_server = TFTPServer()
    tftpd = threading.Thread(target = tftp_server.start)
    tftpd.daemon = True
    tftpd.start()

    http_server = HTTPServer()
    httpd = threading.Thread(target= http_server.start)
    # httpd.daemon = True
    httpd.start()
