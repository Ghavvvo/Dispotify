import os
import socket
import fcntl
import struct
import ipaddress
from typing import Optional


def _interface_name(ifname: Optional[str] = None) -> str:
    return (ifname or os.getenv("OVERLAY_INTERFACE") or "eth0")[:15]


def get_local_ip(ifname: Optional[str] = None) -> str:
    interface = _interface_name(ifname)
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        data = fcntl.ioctl(
            s.fileno(),
            0x8915,
            struct.pack("256s", interface.encode())
        )
        return socket.inet_ntoa(data[20:24])
    finally:
        s.close()


def get_overlay_network(ifname: Optional[str] = None) -> ipaddress.IPv4Network:
    interface = _interface_name(ifname)
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        ip_data = fcntl.ioctl(
            s.fileno(),
            0x8915,
            struct.pack("256s", interface.encode())
        )
        mask_data = fcntl.ioctl(
            s.fileno(),
            0x891b,
            struct.pack("256s", interface.encode())
        )
        ip = socket.inet_ntoa(ip_data[20:24])
        netmask = socket.inet_ntoa(mask_data[20:24])
    finally:
        s.close()

    return ipaddress.ip_network(f"{ip}/{netmask}", strict=False)
