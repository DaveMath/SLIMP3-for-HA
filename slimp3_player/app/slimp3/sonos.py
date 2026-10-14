# SPDX-License-Identifier: GPL-2.0-only
"""Read-only Sonos monitor: finds each zone's group coordinator and reports what it is
playing (station, artist, title) using the local UPnP interface on port 1400."""
import asyncio
import html
import re
import urllib.request
import xml.etree.ElementTree as ET

AVT = ("/MediaRenderer/AVTransport/Control", "AVTransport")
ZGT = ("/ZoneGroupTopology/Control", "ZoneGroupTopology")
NS = {
    "d": "urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/",
    "dc": "http://purl.org/dc/elements/1.1/",
    "upnp": "urn:schemas-upnp-org:metadata-1-0/upnp/",
    "r": "urn:schemas-rinconnetworks-com:metadata-1-0/",
}


def _soap(ip, svc, action, args="", timeout=5):
    path, name = svc
    env = ('<?xml version="1.0"?><s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" '
           's:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/"><s:Body>'
           '<u:%s xmlns:u="urn:schemas-upnp-org:service:%s:1">%s</u:%s></s:Body></s:Envelope>'
           % (action, name, args, action)).encode()
    req = urllib.request.Request("http://%s:1400%s" % (ip, path), env, {
        "Content-Type": 'text/xml; charset="utf-8"',
        "SOAPACTION": '"urn:schemas-upnp-org:service:%s:1#%s"' % (name, action)})
    return urllib.request.urlopen(req, timeout=timeout).read().decode("utf-8", "replace")


def _field(xml, tag):
    m = re.search(r"<%s>(.*?)</%s>" % (tag, tag), xml, re.S)
    return html.unescape(m.group(1)) if m else ""


def parse_didl(md):
    """First <item> of a DIDL-Lite string -> dict (empty values omitted)."""
    out = {}
    if not md or "<item" not in md:
        return out
    try:
        item = ET.fromstring(md).find("d:item", NS)
    except ET.ParseError:
        return out
    if item is None:
        return out
    for key, path in (("title", "dc:title"), ("creator", "dc:creator"), ("album", "upnp:album"),
                      ("cls", "upnp:class"), ("stream", "r:streamContent")):
        v = (item.findtext(path, namespaces=NS) or "").strip()
        if v:
            out[key] = v
    return out


def parse_stream_content(s):
    """Radio-style 'now playing' strings -> (artist, title)."""
    if not s:
        return "", ""
    if "|" in s and "TITLE " in s:
        f = dict(p.split(" ", 1) for p in s.split("|") if " " in p)
        return f.get("ARTIST", ""), f.get("TITLE", "")
    if " - " in s:
        a, t = s.split(" - ", 1)
        return a.strip(), t.strip()
    return "", s.strip()


def poll_zone(ip):
    """Blocking. Returns a state dict for the group that `ip` belongs to."""
    z = _field(_soap(ip, ZGT, "GetZoneGroupState"), "ZoneGroupState")
    root = ET.fromstring(z)
    loc, names = {}, {}
    for m in root.iter("ZoneGroupMember"):
        mip = re.search(r"//([\d.]+):", m.get("Location", ""))
        if mip:
            loc[m.get("UUID")] = mip.group(1)
            names[m.get("UUID")] = m.get("ZoneName", "")
    coord = ip
    for g in root.iter("ZoneGroup"):
        if ip in [loc.get(m.get("UUID")) for m in g.iter("ZoneGroupMember")]:
            coord = loc.get(g.get("Coordinator"), ip)
            room = names.get(g.get("Coordinator"), "")
            break
    else:
        room = ""
    inst = "<InstanceID>0</InstanceID>"
    state = _field(_soap(coord, AVT, "GetTransportInfo", inst), "CurrentTransportState")
    media = _soap(coord, AVT, "GetMediaInfo", inst)
    station = parse_didl(_field(media, "CurrentURIMetaData"))
    pos = _soap(coord, AVT, "GetPositionInfo", inst)
    track = parse_didl(_field(pos, "TrackMetaData"))
    artist, title = track.get("creator", ""), track.get("title", "")
    if track.get("stream"):
        a, t = parse_stream_content(track["stream"])
        artist, title = a or artist, t or title
    is_radio = "audioBroadcast" in station.get("cls", "")
    return {"ip": ip, "coordinator": coord, "room": room, "state": state,
            "station": station.get("title", "") if is_radio else "",
            "artist": artist, "title": title if title != station.get("title") else "",
            "album": track.get("album", ""), "uri": _field(media, "CurrentURI")}


class SonosMonitor:
    def __init__(self, ips, log=print):
        self.ips, self.log = list(ips), log
        self.states = {}

    async def run(self, interval=2.0):
        loop = asyncio.get_event_loop()
        while True:
            for ip in self.ips:
                try:
                    self.states[ip] = await loop.run_in_executor(None, poll_zone, ip)
                except Exception as e:
                    if ip in self.states:
                        self.log("sonos %s unreachable: %s" % (ip, e))
                    self.states.pop(ip, None)
            await asyncio.sleep(interval)

    def active(self):
        """First zone group that is playing, else None."""
        for st in self.states.values():
            if st["state"] == "PLAYING":
                return st
        return None
