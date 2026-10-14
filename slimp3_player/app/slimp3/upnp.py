# SPDX-License-Identifier: GPL-2.0-only
"""Minimal UPnP/DLNA ContentDirectory client (browse + search), stdlib only."""
import asyncio
import urllib.request
import xml.etree.ElementTree as ET
import socket
import time
from urllib.parse import urljoin, urlsplit, urlunsplit
from xml.sax.saxutils import escape

from .net import ssdp_search

NS = {
    "d": "urn:schemas-upnp-org:device-1-0",
    "didl": "urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/",
    "dc": "http://purl.org/dc/elements/1.1/",
    "upnp": "urn:schemas-upnp-org:metadata-1-0/upnp/",
}
CD = "urn:schemas-upnp-org:service:ContentDirectory:1"


def _http(url, data=None, headers=None, timeout=10):
    req = urllib.request.Request(url, data=data, headers=headers or {})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


class MediaServer:
    def __init__(self, description_url, timeout=10):
        self.description_url = description_url
        self.timeout = timeout
        self.name = None
        self.control_url = None

    def connect(self):
        root = ET.fromstring(_http(self.description_url, timeout=self.timeout))
        self.name = root.findtext(".//d:device/d:friendlyName", namespaces=NS)
        base = root.findtext("d:URLBase", namespaces=NS) or self.description_url
        for svc in root.iterfind(".//d:service", NS):
            if (svc.findtext("d:serviceType", namespaces=NS) or "").startswith(
                    "urn:schemas-upnp-org:service:ContentDirectory"):
                self.control_url = urljoin(base, svc.findtext("d:controlURL", namespaces=NS))
        if not self.control_url:
            raise RuntimeError("no ContentDirectory service on %s" % self.description_url)
        return self

    def fix_url(self, url):
        """Servers behind Docker/NAT advertise internal addresses (e.g. 172.30.x.x).
        Point those at the host we actually reached the server on."""
        if not url:
            return url
        u, b = urlsplit(url), urlsplit(self.description_url)
        if u.hostname and u.hostname != b.hostname:
            port = u.port or b.port
            return urlunsplit((u.scheme, "%s:%s" % (b.hostname, port) if port else b.hostname,
                               u.path, u.query, u.fragment))
        return url

    def _fix_items(self, items):
        for it in items:
            it["url"] = self.fix_url(it["url"])
            it["art"] = self.fix_url(it["art"])
        return items

    def _action(self, name, args):
        body = "".join("<%s>%s</%s>" % (k, escape(str(v)), k) for k, v in args)
        env = ('<?xml version="1.0"?><s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" '
               's:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/"><s:Body>'
               '<u:%s xmlns:u="%s">%s</u:%s></s:Body></s:Envelope>' % (name, CD, body, name))
        raw = _http(self.control_url, env.encode(), {
            "Content-Type": 'text/xml; charset="utf-8"',
            "SOAPACTION": '"%s#%s"' % (CD, name)})
        root = ET.fromstring(raw)
        out = {}
        for el in root.iter():
            tag = el.tag.split("}")[-1]
            if tag in ("Result", "NumberReturned", "TotalMatches"):
                out[tag] = el.text or ""
        return out

    def browse(self, object_id="0", start=0, count=500):
        r = self._action("Browse", [
            ("ObjectID", object_id), ("BrowseFlag", "BrowseDirectChildren"),
            ("Filter", "*"), ("StartingIndex", start), ("RequestedCount", count),
            ("SortCriteria", "")])
        return self._fix_items(parse_didl(r.get("Result", ""))), int(r.get("TotalMatches") or 0)

    def metadata(self, object_id):
        r = self._action("Browse", [
            ("ObjectID", object_id), ("BrowseFlag", "BrowseMetadata"), ("Filter", "*"),
            ("StartingIndex", 0), ("RequestedCount", 1), ("SortCriteria", "")])
        items = self._fix_items(parse_didl(r.get("Result", "")))
        return items[0] if items else None


def parse_didl(xml_text):
    if not xml_text:
        return []
    root = ET.fromstring(xml_text)
    out = []
    for el in root:
        kind = el.tag.split("}")[-1]
        if kind not in ("container", "item"):
            continue
        res = el.find("didl:res", NS)
        out.append({
            "id": el.get("id"), "parent": el.get("parentID"),
            "container": kind == "container",
            "child_count": el.get("childCount"),
            "title": el.findtext("dc:title", namespaces=NS),
            "class": el.findtext("upnp:class", namespaces=NS),
            "artist": el.findtext("upnp:artist", namespaces=NS) or el.findtext("dc:creator", namespaces=NS),
            "album": el.findtext("upnp:album", namespaces=NS),
            "art": el.findtext("upnp:albumArtURI", namespaces=NS),
            "url": res.text if res is not None else None,
            "duration": res.get("duration") if res is not None else None,
            "protocol": res.get("protocolInfo") if res is not None else None,
        })
    return out


_PATHS = ["/DeviceDescription.xml", "/dms/device.xml", "/description.xml", "/rootDesc.xml"]
_PORTS = [32469, 80, 8200, 9000]          # Plex DLNA, generic, MiniDLNA, other


def _port_open(host, port, timeout=1.0):
    try:
        with socket.create_connection((host, port), timeout):
            return True
    except OSError:
        return False


def resolve_server(text):
    """Turn what a person types ('192.168.1.10', 'nas:8200', a full URL) into a connected MediaServer.
    Raises ValueError with a readable message."""
    t = (text or "").strip()
    if not t:
        raise ValueError("Enter a server address, for example 192.168.1.10")
    if "://" not in t:
        t = "http://" + t
    u = urlsplit(t)
    if not u.hostname:
        raise ValueError("That does not look like an address")
    if u.path not in ("", "/"):
        urls = [t]
    else:
        ports = [u.port] if u.port else _PORTS
        urls = ["http://%s:%d%s" % (u.hostname, p, path) for p in ports if _port_open(u.hostname, p)
                for path in _PATHS]
    deadline = time.time() + 12
    for url in urls:
        if time.time() > deadline:
            break
        try:
            return MediaServer(url, timeout=3).connect()
        except Exception:
            continue
    raise ValueError("No DLNA/UPnP media server answered at %s. Check the address, and that the server's "
                     "DLNA option is switched on." % u.hostname)


def discover_servers(timeout=3.0):
    """Find DLNA/UPnP media servers: an SSDP search, plus Plex's DLNA port on this host (a Plex running as a
    Home Assistant app does not answer the network search). Returns dicts with url, name, kind."""
    found, seen = [], set()
    for ip, (loc, srv) in ssdp_search("urn:schemas-upnp-org:device:MediaServer:1", timeout).items():
        if not loc or loc in seen:
            continue
        kind = "Sonos" if "sonos" in srv.lower() else ("TV tuner" if "hdhomerun" in srv.lower() else "Media server")
        try:
            name = MediaServer(loc, timeout=3).connect().name or loc
        except Exception:
            continue
        seen.add(loc)
        found.append({"url": loc, "name": name, "kind": kind})
    for url in ("http://127.0.0.1:32469/DeviceDescription.xml",):
        if url not in seen and _port_open("127.0.0.1", 32469, 0.5):
            try:
                found.append({"url": url, "name": MediaServer(url, timeout=3).connect().name or "Plex", "kind": "Plex on this host"})
            except Exception:
                pass
    return sorted(found, key=lambda f: (f["kind"] == "Sonos", f["name"].lower()))


async def aconnect(url):
    return await asyncio.get_event_loop().run_in_executor(None, MediaServer(url).connect)


async def abrowse(server, object_id="0", start=0, count=500):
    return await asyncio.get_event_loop().run_in_executor(None, server.browse, object_id, start, count)


if __name__ == "__main__":
    import sys
    srv = MediaServer(sys.argv[1]).connect()
    print("server:", srv.name, "|", srv.control_url)
    oid = sys.argv[2] if len(sys.argv) > 2 else "0"
    items, total = srv.browse(oid)
    print("object %s: %d of %d" % (oid, len(items), total))
    for it in items[:60]:
        print(("[D] " if it["container"] else "    "), it["id"], "|", it["title"], "|",
              it["artist"] or "", "|", it["child_count"] or "", "|", it["url"] or "")
