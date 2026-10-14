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


def poll_system(seed_ips):
    """Blocking. Ask the first reachable seed for the household topology, then read the
    state of every group's coordinator. Returns a list of group dicts."""
    last = None
    for seed in seed_ips:
        try:
            z = _field(_soap(seed, ZGT, "GetZoneGroupState"), "ZoneGroupState")
            break
        except Exception as e:  # try the next seed
            last = e
    else:
        raise last or RuntimeError("no Sonos address configured")
    root = ET.fromstring(z)
    groups = []
    for g in root.iter("ZoneGroup"):
        members = [m for m in g.iter("ZoneGroupMember") if m.get("Invisible") != "1"]
        coord = next((m for m in g.iter("ZoneGroupMember") if m.get("UUID") == g.get("Coordinator")), None)
        ip = re.search(r"//([\d.]+):", coord.get("Location", "")) if coord is not None else None
        if not ip:
            continue
        group = {"coordinator": ip.group(1), "room": coord.get("ZoneName", ""),
                 "rooms": [m.get("ZoneName", "") for m in members], "state": "",
                 "station": "", "artist": "", "title": "", "album": "", "uri": ""}
        try:
            group.update(_read_group(group["coordinator"]))
        except Exception:
            pass
        groups.append(group)
    return groups


def _read_group(cip):
    inst = "<InstanceID>0</InstanceID>"
    state = _field(_soap(cip, AVT, "GetTransportInfo", inst), "CurrentTransportState")
    if state != "PLAYING":
        return {"state": state}
    media = _soap(cip, AVT, "GetMediaInfo", inst)
    station = parse_didl(_field(media, "CurrentURIMetaData"))
    track = parse_didl(_field(_soap(cip, AVT, "GetPositionInfo", inst), "TrackMetaData"))
    artist, title = track.get("creator", ""), track.get("title", "")
    if track.get("stream"):
        a, t = parse_stream_content(track["stream"])
        artist, title = a or artist, t or title
    is_radio = "audioBroadcast" in station.get("cls", "")
    return {"state": state, "station": station.get("title", "") if is_radio else "",
            "artist": artist, "title": title if title != station.get("title") else "",
            "album": track.get("album", ""), "uri": _field(media, "CurrentURI")}


class SonosMonitor:
    def __init__(self, ips, log=print):
        self.ips, self.log = list(ips), log
        self.groups = []
        self._ok = True

    async def run(self, interval=2.0):
        loop = asyncio.get_event_loop()
        while True:
            try:
                self.groups = await loop.run_in_executor(None, poll_system, self.ips)
                if not self._ok:
                    self.log("sonos reachable again")
                self._ok = True
            except Exception as e:
                if self._ok:
                    self.log("sonos unreachable: %s" % e)
                self._ok, self.groups = False, []
            await asyncio.sleep(interval)

    def rooms(self):
        return sorted(r for g in self.groups for r in g["rooms"])

    def active(self, room=None):
        """The playing group that contains `room` (case-insensitive), or any playing group if room is empty."""
        for g in self.groups:
            if g["state"] != "PLAYING":
                continue
            if not room or room.lower() in [r.lower() for r in g["rooms"]]:
                return g
        return None
