# SPDX-License-Identifier: GPL-2.0-only
"""Small network helpers: multicast (SSDP) search that works on hosts with several interfaces."""
import re
import socket
import struct
import time


def local_ipv4s():
    """Non-loopback IPv4 addresses of this host's interfaces (Linux). Empty list when unknown."""
    try:
        import fcntl
        out = []
        for _, name in socket.if_nameindex():
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                packed = fcntl.ioctl(s.fileno(), 0x8915, struct.pack("256s", name.encode()[:15]))  # SIOCGIFADDR
                ip = socket.inet_ntoa(packed[20:24])
                if not ip.startswith("127.") and ip not in out:
                    out.append(ip)
            except OSError:
                pass
            finally:
                s.close()
        return out
    except Exception:
        return []


def ssdp_search(st, timeout=3.0):
    """Multicast an SSDP search and return {ip: (location, server_header)} for every responder.
    The search goes out on the default route and, on Linux, on every interface address, because a host with
    several networks (wired, Wi-Fi, container bridges) may otherwise send it out the wrong one."""
    msg = ("M-SEARCH * HTTP/1.1\r\nHOST: 239.255.255.250:1900\r\nMAN: \"ssdp:discover\"\r\nMX: 2\r\n"
           "ST: %s\r\n\r\n" % st).encode()
    socks = []
    try:
        for src in [None] + local_ipv4s():
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
            s.settimeout(0.3)
            if src:
                try:
                    s.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF, socket.inet_aton(src))
                except OSError:
                    s.close()
                    continue
            try:
                for _ in range(2):
                    s.sendto(msg, ("239.255.255.250", 1900))
            except OSError:
                s.close()
                continue
            socks.append(s)
        found = {}
        end = time.time() + timeout
        while time.time() < end and socks:
            for s in socks:
                try:
                    data, addr = s.recvfrom(4096)
                except (socket.timeout, OSError):
                    continue
                text = data.decode(errors="replace")
                loc = re.search(r"(?im)^location:\s*(.+)$", text)
                srv = re.search(r"(?im)^server:\s*(.+)$", text)
                found[addr[0]] = (loc.group(1).strip() if loc else "", srv.group(1).strip() if srv else "")
        return found
    finally:
        for s in socks:
            s.close()
