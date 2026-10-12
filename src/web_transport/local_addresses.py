"""本机可达地址枚举。

自签证书 SAN 与「扫码配对」要展示的局域网地址是同一组事实：服务端自己
知道监听在哪些网卡上，客户端（浏览器）只知道自己访问用的那个地址——GM 在
本机打开的往往是 localhost，对手机毫无意义。所以候选地址必须由服务端给出。
"""

from __future__ import annotations

import ipaddress
import socket


def local_ip_addresses() -> list[ipaddress.IPv4Address | ipaddress.IPv6Address]:
    """按「默认路由源地址优先」的顺序返回本机地址，去重后保持稳定顺序。"""
    addresses: list[ipaddress.IPv4Address | ipaddress.IPv6Address] = []
    # UDP connect 不会真正发包，只用于让系统选择默认路由的源地址。
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.settimeout(0)
        probe.connect(("8.8.8.8", 80))
        append_address(addresses, probe.getsockname()[0])
    except OSError:
        pass
    finally:
        probe.close()
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None):
            append_address(addresses, info[4][0])
    except (OSError, UnicodeError):
        pass
    return addresses


def append_address(
    addresses: list[ipaddress.IPv4Address | ipaddress.IPv6Address],
    raw: str,
) -> None:
    try:
        address = ipaddress.ip_address(raw)
    except ValueError:
        return
    if address.is_unspecified or address.is_multicast:
        return
    if address in addresses:
        return
    addresses.append(address)


def reachable_host_candidates() -> list[str]:
    """给其它设备用的主机名候选：局域网地址优先，回环地址垫底。

    回环地址保留是因为「服务器与浏览器同机、手机走隧道/反代」也是合法部署，
    前端仍应看到完整清单并自行选择，而不是被这里静默过滤掉。
    """
    lan: list[str] = []
    loopback: list[str] = []
    for address in local_ip_addresses():
        if address.is_link_local:
            # IPv6 link-local 带 zone id，跨设备粘贴基本不可用，直接排除。
            continue
        (loopback if address.is_loopback else lan).append(str(address))
    return lan + loopback
