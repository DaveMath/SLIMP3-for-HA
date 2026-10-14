# SPDX-License-Identifier: GPL-2.0-only
"""Read-only Sonos monitor: finds each zone's group coordinator and reports what it is
playing (station, artist, title) using the local UPnP interface on port 1400."""
import asyncio
import html
import http.client
import re
import threading
import time
import xml.etree.ElementTree as ET

from .net import ssdp_search

AVT = ("/MediaRenderer/AVTransport/Control", "AVTransport")
ZGT = ("/ZoneGroupTopology/Control", "ZoneGroupTopology")
NS = {
    "d": "urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/",
    "dc": "http://purl.org/dc/elements/1.1/",
    "upnp": "urn:schemas-upnp-org:metadata-1-0/upnp/",
    "r": "urn:schemas-rinconnetworks-com:metadata-1-0/",
}


_pool = {}
_pool_lock = threading.Lock()


def _soap(ip, svc, action, args="", timeout=5):
    """One persistent HTTP connection per Sonos player (no new TCP handshake per call)."""
    path, name = svc
    env = ('<?xml version="1.0"?><s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" '
           's:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/"><s:Body>'
           '<u:%s xmlns:u="urn:schemas-upnp-org:service:%s:1">%s</u:%s></s:Body></s:Envelope>'
           % (action, name, args, action)).encode()
    headers = {"Content-Type": 'text/xml; charset="utf-8"',
               "SOAPACTION": '"urn:schemas-upnp-org:service:%s:1#%s"' % (name, action)}
    for attempt in (0, 1):
        with _pool_lock:
            conn = _pool.get(ip)
            if conn is None:
                conn = _pool[ip] = http.client.HTTPConnection(ip, 1400, timeout=timeout)
        try:
            conn.request("POST", path, env, headers)
            r = conn.getresponse()
            data = r.read()
            if r.status != 200:
                raise OSError("HTTP %d" % r.status)
            return data.decode("utf-8", "replace")
        except (OSError, http.client.HTTPException):
            with _pool_lock:
                _pool.pop(ip, None)
            try:
                conn.close()
            except Exception:
                pass
            if attempt:
                raise


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


_SOURCES = (("x-sonos-htastream:", "TV audio"), ("x-rincon-stream:", "Line-in"), ("x-sonos-vli:", "Line-in"),
            ("x-sonos-spotify:", "Spotify"), ("x-sonosapi-radio:", "Radio"), ("x-sonosapi-hls", "Radio"),
            ("x-sonosapi-stream:", "Radio"), ("x-rincon-mp3radio:", "Internet radio"), ("aac:", "Radio"),
            ("x-sonos-http:", "Streaming"), ("x-sonosprog-http:", "Streaming"), ("x-file-cifs:", "Music library"))


def describe_source(uri):
    """A short label for what a Sonos group is playing from, judged by its address scheme ('' if unknown)."""
    for prefix, label in _SOURCES:
        if (uri or "").startswith(prefix):
            return label
    return ""


def read_topology(seed_ips):
    """Blocking. Ask the first reachable seed for the household topology: a list of group dicts
    (coordinator address, rooms) with no playback state yet."""
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
                 "station": "", "artist": "", "title": "", "album": "", "uri": "", "source": ""}
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
            "album": track.get("album", ""), "uri": _field(media, "CurrentURI"),
            "source": describe_source(_field(media, "CurrentURI"))}


def discover(timeout=3.0):
    """SSDP search for Sonos players (device type ZonePlayer). Returns their IP addresses."""
    return sorted(ssdp_search("urn:schemas-upnp-org:device:ZonePlayer:1", timeout))


class SonosMonitor:
    TOPO_TTL = 60      # seconds; the household layout rarely changes

    REDISCOVER = 600   # seconds between discovery searches (addresses can change)
    FAST = 3.0         # seconds between polls while a wanted group is playing, or did within the last GRACE seconds
    SLOW = 10.0        # ... and while nothing has played for a while
    GRACE = 60.0

    def __init__(self, ips, log=print, discovery=True):
        self.ips, self.log, self.discovery = list(ips), log, discovery
        self.discovered, self._disc_t = [], 0.0
        self.groups = []
        self._topo, self._topo_t = [], 0.0
        self._ok = True
        self._want, self._last_playing = {""}, 0.0

    @property
    def enabled(self):
        """Sonos support is on if there are addresses to ask or discovery is allowed."""
        return bool(self.ips or self.discovery)

    def _seeds(self, force=False):
        """Addresses to ask for the household layout: configured ones plus whatever discovery finds."""
        now = time.time()
        if self.discovery and (force or not (self.ips or self.discovered) or now - self._disc_t > self.REDISCOVER):
            found = discover()
            self._disc_t = now
            if found != self.discovered:
                self.log("sonos discovery found: %s" % (", ".join(found) or "nothing"))
            self.discovered = found
        return list(dict.fromkeys(self.ips + self.discovered))

    def _read_layout(self):
        try:
            seeds = self._seeds()
            if not seeds:
                raise RuntimeError("no Sonos players found")
            return read_topology(seeds)
        except Exception:
            if not self.discovery:
                raise
            return read_topology(self._seeds(force=True) or [])   # one retry after a fresh search

    def ensure_topology(self):
        """Blocking. Make sure the household layout (rooms) is known, e.g. for the settings page."""
        if not self._topo:
            self._topo, self._topo_t = self._read_layout(), time.time()

    def _cycle(self, want):
        """Blocking. Refresh the topology now and then, and read playback state only for the groups
        that contain a room in `want` (a set of lowercase names; '' means every room)."""
        now = time.time()
        if not self._topo or now - self._topo_t > self.TOPO_TTL:
            self._topo, self._topo_t = self._read_layout(), now
        out = []
        for g in self._topo:
            g = dict(g)
            if "" in want or any(r.lower() in want for r in g["rooms"]):
                try:
                    g.update(_read_group(g["coordinator"]))
                except Exception:
                    self._topo_t = 0.0          # coordinator may have changed: re-read the layout next time
            out.append(g)
        return out

    async def poll_now(self):
        """Read the groups right now (used to confirm a stop before the display goes black)."""
        self.groups = await asyncio.get_event_loop().run_in_executor(None, self._cycle, self._want)

    async def run(self, needed=None):
        """needed(): returns the set of lowercase room names some idle SLIMP3 is showing ('' = any room).
        While it is empty nothing is polled at all (no network, no CPU)."""
        loop = asyncio.get_event_loop()
        while True:
            want = needed() if needed is not None else {""}
            if not want:
                self.groups = []
                await asyncio.sleep(5)
                continue
            self._want = want
            try:
                self.groups = await loop.run_in_executor(None, self._cycle, want)
                if any(g["state"] == "PLAYING" for g in self.groups if "" in want or any(r.lower() in want for r in g["rooms"])):
                    self._last_playing = time.time()
                if not self._ok:
                    self.log("sonos reachable again")
                self._ok = True
            except Exception as e:
                if self._ok:
                    self.log("sonos unreachable: %s" % e)
                self._ok, self.groups, self._topo = False, [], []
            await asyncio.sleep(self.FAST if time.time() - self._last_playing < self.GRACE else self.SLOW)

    def rooms(self):
        return sorted(r for g in (self._topo or self.groups) for r in g["rooms"])

    def active(self, room=None):
        """The playing group that contains `room` (case-insensitive), or any playing group if room is empty."""
        for g in self.groups:
            if g["state"] != "PLAYING":
                continue
            if not room or room.lower() in [r.lower() for r in g["rooms"]]:
                return g
        return None
