# mypxe-server

一个使用Python3编写的PXE服务器，只用了Python3的标准库，
可以在Windows/Linux上运行，简单易用。

## 文件目录

目录结构如下：
```bash
├── config.json    # 启动参数配置
├── LICENSE
├── mypxe.py       # 主程序文件
├── README.md      
└── tftpboot       # 服务根目录
    ├── boot
    │   ├── ipxe
    │   │   ├── boot.ipxe
    │   │   ├── ipxe.efi
    │   │   └── undionly.kpxe
    ├── clients
    │   ├── 192.168.100.120.ipxe.bootfile
    │   ├── 192.168.100.120.ks
    │   ├── centos7.ipxe.bootfile.template
    │   ├── centos7.ks.template
    │   └── default.ipxe.bootfile
    └── images
        ├── centos7
        │   └── CentOS-7-x86_64-Minimal-1908
        ├── centos8
        ├── Core.iso
        └── ubuntu20.04.3
```

## 使用说明

### 1. 安装好Python3

略

### 2. 配置config.json

```bash
# config.json配置文件包含如下内容：

## Server  DHCP、TFTP、HTTP服务器的地址都是这个
## 
## 后面几个是DHCP的几个参数
## Offer_addr_start   dhcp服务器提供的最小IP
## Offer_addr_counts  提供IP地址的个数，从最小IP依次累加
## Netmask: "255.255.255.0"        # 掩码
## Boardcast: "192.168.100.255"    # 广播地址
## Filename      启动文件位置
##   "boot/ipxe/boot.ipxe"  已经固定使用ipxe来引导x86设备，本文件可编辑
## TFTProot    TFTP服务器和HTTP服务器的根目录

配置示例：
$ cat config.json
{
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

如果不配置这个配置文件，主程序会使用默认参数（与上面的配置示例一样）。
```

### 3. 配置启动脚本

使用`boot/ipxe/boot.ipxe`默认启动脚本，会依次查找如下启动文件，优先顺序如下：

- `tftpboot/clients/MAC地址.ipxe.bootfile`
- `tftpboot/clients/IP地址.ipxe.bootfile`
- `tftpboot/clients/default.ipxe.bootfile`

只需要根据需求编辑这几个[ipxe](https://ipxe.org/) 脚本就可以。比如编写一个安装`Centos7`的启动脚本文件：

```bash
$ cat tftpboot/clients/192.168.100.120.ipxe.bootfile
#!ipxe
set base http://${next-server}/images
set ks_file http://${next-server}/clients/${ip}.ks
set iso CentOS-7-x86_64-Minimal-1908

initrd ${base}/centos7/${iso}/images/pxeboot/initrd.img
kernel ${base}/centos7/${iso}/images/pxeboot/vmlinuz inst.ks=${ks_file} ip=dhcp initrd=initrd.img
boot
```
然后编写一个`192.168.100.120.ks`即可。

### 4. 启动服务器

```bash
$ cd mypxe-server/
$ python3 mypxe.py
```

关闭服务器使用`Ctrl+C`即可。

