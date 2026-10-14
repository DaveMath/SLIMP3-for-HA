# SPDX-License-Identifier: GPL-2.0-only
"""Read-only Google Cast monitor: finds Google Home, Nest and other Cast devices on the network and listens for what
they are playing. It speaks just enough of the Cast protocol (a TLS connection to port 8009 carrying length-prefixed
protobuf messages) to read the receiver and media status, and it never sends a playback command. No Google account or
login is involved. Connections are made only while some SLIMP3 is idle and wants to show a Cast device."""
import asyncio
import json
import ssl
import struct
import time
import urllib.request

NS_CONN = "urn:x-cast:com.google.cast.tp.connection"
NS_HEART = "urn:x-cast:com.google.cast.tp.heartbeat"
NS_RECV = "urn:x-cast:com.google.cast.receiver"
NS_MEDIA = "urn:x-cast:com.google.cast.media"
SENDER = "sender-slimp3"
SERVICE = "_googlecast._tcp.local."


# ---- the Cast message: a protobuf with six fields, encoded by hand so no extra library is needed ----
def _varint(n):
    out = bytearray()
    while True:
        b = n & 0x7F
        n >>= 7
        out.append(b | (0x80 if n else 0))
        if not n:
            return bytes(out)


def _field(num, data):
    return _varint(num << 3 | 2) + _varint(len(data)) + data


def encode(src, dst, namespace, payload):
    body = (b"\x08\x00" + _field(2, src.encode()) + _field(3, dst.encode()) + _field(4, namespace.encode())
            + b"\x28\x00" + _field(6, json.dumps(payload).encode()))
    return struct.pack(">I", len(body)) + body


def decode(buf):
    """Return {source, dest, namespace, payload (parsed JSON or None)} from one Cast message."""
    out, i = {}, 0
    while i < len(buf):
        key, shift = 0, 0
        while True:
            b = buf[i]
            i += 1
            key |= (b & 0x7F) << shift
            shift += 7
            if not b & 0x80:
                break
        num, wire = key >> 3, key & 7
        if wire == 0:
            while buf[i] & 0x80:
                i += 1
            i += 1
        elif wire == 2:
            n, shift = 0, 0
            while True:
                b = buf[i]
                i += 1
                n |= (b & 0x7F) << shift
                shift += 7
                if not b & 0x80:
                    break
            data, i = buf[i:i + n], i + n
            if num in (2, 3, 4, 6):
                out[{2: "source", 3: "dest", 4: "namespace", 6: "payload"}[num]] = data.decode("utf-8", "replace")
        else:
            raise ValueError("unexpected protobuf wire type %d" % wire)
    try:
        out["payload"] = json.loads(out.get("payload") or "null")
    except ValueError:
        out["payload"] = None
    return out


class CastLink:
    """One connection to one Cast device."""

    def __init__(self, name, host, port, model, log, on_update):
        self.name, self.host, self.port, self.model = name, host, port, model
        self.log, self.on_update = log, on_update
        self.transport, self.app, self.meta, self.player_state = None, "", {}, ""
        self._w, self._rid = None, 0

    def _send(self, namespace, payload, dest):
        if self._w is not None:
            self._w.write(encode(SENDER, dest, namespace, payload))

    def _request(self, namespace, dest, kind="GET_STATUS"):
        self._rid += 1
        self._send(namespace, {"type": kind, "requestId": self._rid}, dest)

    async def _beat(self):
        while True:
            await asyncio.sleep(5)
            self._send(NS_HEART, {"type": "PING"}, "receiver-0")

    async def run(self):
        ctx = ssl.create_default_context()
        ctx.check_hostname, ctx.verify_mode = False, ssl.CERT_NONE      # Cast devices use self-signed certificates
        r, self._w = await asyncio.wait_for(asyncio.open_connection(self.host, self.port, ssl=ctx), 10)
        beat = asyncio.ensure_future(self._beat())
        try:
            self._send(NS_CONN, {"type": "CONNECT"}, "receiver-0")
            self._request(NS_RECV, "receiver-0")
            self._publish()
            while True:
                n = struct.unpack(">I", await asyncio.wait_for(r.readexactly(4), 20))[0]
                if n > 1 << 20:
                    raise ValueError("oversized Cast message")
                self._handle(decode(await asyncio.wait_for(r.readexactly(n), 20)))
        finally:
            beat.cancel()
            try:
                self._w.close()
            except Exception:
                pass
            self._w = None

    def _handle(self, m):
        p, ns = m.get("payload") or {}, m.get("namespace")
        kind = p.get("type")
        if ns == NS_HEART and kind == "PING":
            self._send(NS_HEART, {"type": "PONG"}, m.get("source") or "receiver-0")
        elif ns == NS_RECV and kind == "RECEIVER_STATUS":
            self._apps((p.get("status") or {}).get("applications") or [])
        elif ns == NS_CONN and kind == "CLOSE" and m.get("source") == self.transport:
            self._apps([])
        elif ns == NS_MEDIA and kind == "MEDIA_STATUS" and m.get("source") == self.transport:
            self._media(p.get("status") or [])

    def _apps(self, apps):
        """Follow the app that can play media (Spotify, YouTube Music, ...); the idle screen and bare apps do not count."""
        app = next((a for a in apps if not a.get("isIdleScreen")
                    and any(n.get("name") == NS_MEDIA for n in a.get("namespaces") or [])), None)
        tid = app.get("transportId") if app else None
        if tid != self.transport:
            self.transport, self.meta, self.player_state = tid, {}, ""
            self.app = (app.get("displayName") or "") if app else ""
            if tid:
                self._send(NS_CONN, {"type": "CONNECT"}, tid)
                self._request(NS_MEDIA, tid)
        self._publish()

    def _media(self, statuses):
        if not statuses:
            return
        s = statuses[0]
        self.player_state = s.get("playerState") or self.player_state
        media = s.get("media")
        if media:                       # later updates leave "media" out, so keep what was last said
            md = media.get("metadata") or {}
            self.meta = {"title": md.get("title") or "",
                         "artist": md.get("artist") or md.get("albumArtist") or md.get("seriesTitle") or "",
                         "album": md.get("albumName") or ""}
        self._publish()

    def _publish(self):
        playing = bool(self.transport) and self.player_state in ("PLAYING", "BUFFERING")
        paused = bool(self.transport) and self.player_state == "PAUSED"
        self.on_update(self.name, {
            "station": "", "room": self.name, "app": self.app,
            "state": "PLAYING" if playing else ("PAUSED" if paused else "STOPPED"),
            "artist": self.meta.get("artist", ""), "title": self.meta.get("title", ""), "album": self.meta.get("album", ""),
            "source": self.app or self.model, "uri": "", "kind": "cast"})


def _scan(timeout=4.0):
    """Browse the network for Cast devices (blocking; run in a thread). Returns ([{name, host, port, model}], error)."""
    try:
        from zeroconf import ServiceBrowser, Zeroconf
    except Exception as e:
        return [], "%s: %s" % (type(e).__name__, e)
    found = {}

    class Listener:
        def add_service(self, zc, kind, name):
            try:
                info = zc.get_service_info(kind, name, 2000)
                if not info:
                    return
                props = {(k.decode() if isinstance(k, bytes) else k): (v.decode("utf-8", "replace") if isinstance(v, bytes) else v)
                         for k, v in (info.properties or {}).items()}
                addrs = info.parsed_addresses()
                if addrs:
                    found[name] = {"name": props.get("fn") or name.split(".")[0], "host": addrs[0], "port": info.port or 8009,
                                   "model": props.get("md") or "Google Cast"}
            except Exception:
                pass

        update_service = add_service

        def remove_service(self, zc, kind, name):
            pass

    zc = Zeroconf()
    try:
        browser = ServiceBrowser(zc, SERVICE, Listener())
        time.sleep(timeout)
        browser.cancel()
    finally:
        zc.close()
    return list(found.values()), ""


def _eureka(host):
    """The friendly name and model of a Cast device at a known address, or None."""
    try:
        with urllib.request.urlopen("http://%s:8008/setup/eureka_info?params=name,detail" % host, timeout=3) as r:
            d = json.load(r)
        return {"name": d.get("name") or host, "host": host, "port": 8009,
                "model": (d.get("detail") or {}).get("model_name") or "Google Cast"}
    except Exception:
        return {"name": host, "host": host, "port": 8009, "model": "Google Cast"}


class CastMonitor:
    REDISCOVER = 600

    def __init__(self, log=print, enabled=True, ips=()):
        self.log, self.enabled, self.ips = log, bool(enabled), [str(i) for i in (ips or []) if i]
        self.devices = {}           # name -> latest play state
        self._found = {}            # name -> {name, host, port, model}
        self._tasks = {}            # name -> running connection task
        self._retry = {}
        self._disc_t = 0.0
        self._dev_err = {}
        self._seen_t = {}
        self.error = ""             # why automatic discovery is unavailable, if it is

    def available(self):
        return self.enabled and not self.error

    def names(self):
        return sorted(self._found)

    def model(self, name):
        return (self._found.get(name) or {}).get("model", "Google Cast")

    def info(self, name):
        d = self.devices.get(name) or {}
        t = self._tasks.get(name)
        return {"connected": bool(t and not t.done() and name in self._seen_t), "state": d.get("state", ""),
                "title": d.get("title", ""), "artist": d.get("artist", ""), "app": d.get("app", ""),
                "error": self._dev_err.get(name, ""),
                "age": round(time.time() - self._seen_t[name]) if name in self._seen_t else None}

    async def discover(self):
        loop = asyncio.get_event_loop()
        found, self.error = await loop.run_in_executor(None, _scan)
        for ip in self.ips:
            if not any(f["host"] == ip for f in found):
                found.append(await loop.run_in_executor(None, _eureka, ip))
        new = {f["name"]: f for f in found}
        if set(new) != set(self._found):
            self.log("Google Cast devices found: %s%s" % (", ".join(sorted(new)) or "none",
                     " (automatic discovery unavailable: %s)" % self.error if self.error else ""))
        self._found, self._disc_t = new, time.time()

    def _apply(self, name, state):
        self._seen_t[name] = time.time()
        self._dev_err.pop(name, None)
        self.devices[name] = state

    async def _session(self, name):
        f = self._found[name]
        link = CastLink(name, f["host"], f["port"], f["model"], self.log, self._apply)
        try:
            await link.run()
        except asyncio.CancelledError:
            raise
        except Exception as e:
            self._dev_err[name] = "%s: %s" % (type(e).__name__, e) if str(e) else type(e).__name__
            self.log("Google Cast %s: connection ended (%s); retrying in a minute" % (name, self._dev_err[name]))
        finally:
            self.devices.pop(name, None)
            self._seen_t.pop(name, None)
            self._retry[name] = time.time() + 60

    async def _drop(self, name):
        t = self._tasks.pop(name, None)
        if t and not t.done():
            t.cancel()
            await asyncio.gather(t, return_exceptions=True)
        self.devices.pop(name, None)
        self._seen_t.pop(name, None)

    async def run(self, needed, interval=3.0):
        """needed(): the set of lowercase device names an idle SLIMP3 wants ('' = any). Empty: stay disconnected."""
        if not self.enabled:
            return
        while True:
            want = needed()
            try:
                if not want:
                    for n in list(self._tasks):
                        await self._drop(n)
                    await asyncio.sleep(5)
                    continue
                if not self._found or time.time() - self._disc_t > self.REDISCOVER:
                    await self.discover()
                for name in self._found:
                    wanted = "" in want or name.lower() in want
                    t = self._tasks.get(name)
                    if t and t.done():
                        self._tasks.pop(name, None)
                        t = None
                    if wanted and not t and time.time() >= self._retry.get(name, 0):
                        self._tasks[name] = asyncio.ensure_future(self._session(name))
                    elif not wanted and t:
                        await self._drop(name)
            except Exception as e:
                self.log("Google Cast monitor error: %s: %s" % (type(e).__name__, e))
                await asyncio.sleep(10)
            await asyncio.sleep(interval)

    def active(self, name=None):
        for n, d in self.devices.items():
            if d["state"] == "PLAYING" and (not name or n.lower() == name.lower()):
                return d
        return None

    async def close(self):
        for n in list(self._tasks):
            await self._drop(n)
