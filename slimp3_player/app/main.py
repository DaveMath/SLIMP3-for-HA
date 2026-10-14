# SPDX-License-Identifier: GPL-2.0-only
"""SLIMP3 Player app: UDP endpoint for SLIMP3 devices + HTTP API/UI (HA ingress)."""
import asyncio
import ipaddress
import json
import os
import time

from aiohttp import web

from slimp3.nowplaying import SonosNowPlaying
from slimp3.server import Server
from slimp3.sonos import SonosMonitor
from slimp3.spectrum import selftest
from slimp3.upnp import MediaServer

OPTS_PATH = os.environ.get("SLIMP3_OPTIONS", "/data/options.json")
PORT = int(os.environ.get("SLIMP3_PORT", "8099"))
WEB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")
T0 = time.time()
# Home Assistant's internal network (ingress gateway is 172.30.32.2); set SLIMP3_ALLOW_ALL=1 for local dev.
ALLOWED = [ipaddress.ip_network(n) for n in ("127.0.0.0/8", "172.30.32.0/23")]
ALLOW_ALL = os.environ.get("SLIMP3_ALLOW_ALL") == "1"


@web.middleware
async def guard(request, handler):
    if not ALLOW_ALL:
        try:
            ok = any(ipaddress.ip_address(request.remote) in n for n in ALLOWED)
        except ValueError:
            ok = False
        if not ok:
            raise web.HTTPForbidden(text="open this app from the Home Assistant sidebar")
    return await handler(request)


def log(msg):
    print("[%7.1f] %s" % (time.time() - T0, msg), flush=True)


def load_options():
    try:
        with open(OPTS_PATH) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


class App:
    def __init__(self, opts):
        self.opts = opts
        self.sources = [{"id": str(i), "url": u, "server": None, "name": u}
                        for i, u in enumerate(opts.get("dlna_servers") or [])]
        self.server = Server(opts.get("player_ips") or [], log)
        self.server.player_defaults = {
            "volume": int(opts.get("default_volume", 40)),
            "fps": int(opts.get("display_fps", 8)),
            "sync_ms": int(opts.get("sync_ms", 0)),
            "use_spectrum": bool(opts.get("spectrum", True)),
        }
        ms = selftest()
        fps = int(opts.get("display_fps", 8))
        self.spectrum_ok = ms is not None and ms < 500.0 / fps   # may use at most half a frame period
        if ms is None:
            log("spectrum analyzer unavailable (numpy missing); using the artist/title layout")
        else:
            log("spectrum analyzer: %.1f ms per frame, budget %.0f ms at %d fps -> %s"
                % (ms, 500.0 / fps, fps, "ok" if self.spectrum_ok else "too slow, using artist/title layout"))
        self.server.on_new_player = self._new_player
        self.server.on_reboot = self.start_welcome
        self.sonos = SonosMonitor(opts.get("sonos_ips") or [], log)
        self.cfg = {str(c.get("mac", "")).lower(): c for c in (opts.get("players") or [])}

    def _new_player(self, p):
        c = self.cfg.get(p.mac.lower(), {})
        p.name = c.get("name") or ""
        p.sonos_room = c.get("sonos_room") or ""
        p.show_sonos = c.get("show_sonos", self.opts.get("sonos_display", True))
        if "volume" in c:
            p.volume = int(c["volume"])
        if "spectrum" in c:
            p.use_spectrum = bool(c["spectrum"])
        if "sync_ms" in c:
            p.sync_ms = int(c["sync_ms"])
        if not self.spectrum_ok:
            p.use_spectrum = False
        p.configured = bool(c)
        if not c:
            log("player %s has no entry in 'players'; using defaults" % p.mac)
        p.on_ir = lambda code: log("IR 0x%s" % code)
        self.start_welcome(p)

    # ---- boot / identify screens ------------------------------------
    def idle_screen(self, p):
        p.show("SLIMP3 server ready", ("%s  %s" % (p.name, p.addr[0])).strip())

    def start_welcome(self, p, force=False):
        """Show connection details and setup prompts on the player (at connect, restart, or on request)."""
        if not force:
            if not self.opts.get("boot_screens", True) or time.time() - p.welcome_t < 20:
                return
        p.welcome_t = time.time()
        p.cancel_sonos()
        p.cancel_welcome()
        p.welcome_task = asyncio.ensure_future(self._welcome(p))

    async def _welcome(self, p):
        def ctr(t):
            return t[:40].center(40)
        try:
            steps = [("Connected to Home Assistant", "SLIMP3-for-HA", 3.0),
                     ("IP  " + p.addr[0], "MAC " + p.mac, 5.0)]
            for a, b, secs in steps:
                p.show(ctr(a), ctr(b))
                await asyncio.sleep(secs)
            c = self.cfg.get(p.mac.lower())
            later = []
            if c is None:
                later.append(("Optional: name this player", "Add the MAC to 'players' in app config", 4.0))
            else:
                room = c.get("sonos_room") or ""
                show = c.get("show_sonos", self.opts.get("sonos_display", True))
                if not self.sonos.ips:
                    sonos = "Sonos: not set up"
                elif not show:
                    sonos = "Sonos display: off"
                else:
                    sonos = "Sonos room: " + room if room else "Sonos: any playing room"
                later.append(("Player: " + (c.get("name") or "(unnamed)"), sonos, 4.0))
                if room and show and self.sonos.groups and room.lower() not in [r.lower() for r in self.sonos.rooms()]:
                    later.append(("Sonos room not found: " + room, "Rooms: " + ", ".join(self.sonos.rooms()), 6.0))
            if not self.sources:
                later.append(("No music source set up yet", "Add a DLNA server in app config", 4.0))
            if not self.sonos.ips and c is None:
                later.append(("Tip: add a Sonos address in", "app config to see what it plays", 4.0))
            for a, b, secs in later:
                p.show(ctr(a), ctr(b))
                await asyncio.sleep(secs)
            self.idle_screen(p)
        except asyncio.CancelledError:
            pass
        finally:
            if p.welcome_task is asyncio.current_task():
                p.welcome_task = None

    def player(self, mac=None):
        ps = self.server.players
        return ps.get(mac) if mac else (next(iter(ps.values())) if ps else None)

    async def source(self, sid):
        src = next((s for s in self.sources if s["id"] == str(sid)), None)
        if not src:
            raise web.HTTPNotFound(text="unknown source")
        if not src["server"]:
            loop = asyncio.get_event_loop()
            try:
                src["server"] = await loop.run_in_executor(None, MediaServer(src["url"]).connect)
            except Exception as e:
                raise web.HTTPBadGateway(text="cannot reach %s: %s" % (src["url"], e))
            src["name"] = src["server"].name or src["url"]
        return src["server"]

    # ---- handlers ---------------------------------------------------
    async def state(self, req):
        return web.json_response({
            "players": [p.status() for p in self.server.players.values()],
            "sources": [{"id": s["id"], "name": s["name"]} for s in self.sources]})

    async def browse(self, req):
        srv = await self.source(req.query.get("source", "0"))
        oid, start = req.query.get("id", "0"), int(req.query.get("start", 0))
        loop = asyncio.get_event_loop()
        items, total = await loop.run_in_executor(None, srv.browse, oid, start, 200)
        return web.json_response({"items": items, "total": total})

    async def play(self, req):
        body = await req.json()
        p = self.player(body.get("mac"))
        if not p:
            raise web.HTTPServiceUnavailable(text="no SLIMP3 connected")
        srv = await self.source(body.get("source", "0"))
        loop = asyncio.get_event_loop()
        start = 0
        if body.get("container"):
            items, _ = await loop.run_in_executor(None, srv.browse, body["container"], 0, 500)
            items = [i for i in items if not i["container"] and i["url"]]
            if body.get("start_id"):
                start = next((n for n, i in enumerate(items) if i["id"] == body["start_id"]), 0)
        else:
            it = await loop.run_in_executor(None, srv.metadata, body["item"])
            items = [it] if it and it["url"] else []
        if not items:
            raise web.HTTPNotFound(text="nothing playable")
        await p.play_queue(items, start)
        return web.json_response({"queued": len(items), "start": start})

    async def control(self, req):
        body = await req.json()
        p = self.player(body.get("mac"))
        if not p:
            raise web.HTTPServiceUnavailable(text="no SLIMP3 connected")
        act = body.get("action")
        if act == "pause":
            p.pause()
        elif act == "resume":
            p.resume()
        elif act == "toggle":
            p.resume() if p.stream and p.stream.state == "paused" else p.pause()
        elif act == "stop":
            await p.stop()
        elif act == "next":
            p.next()
        elif act == "prev":
            p.prev()
        elif act == "identify":
            self.start_welcome(p, force=True)
        elif act == "volume":
            p.set_volume(int(body["value"]))
        else:
            raise web.HTTPBadRequest(text="unknown action")
        return web.json_response(p.status())

    async def sonos_state(self, req):
        return web.json_response({"rooms": self.sonos.rooms(), "groups": self.sonos.groups})

    async def sonos_display_loop(self):
        """Per SLIMP3: mirror its Sonos room's group while the SLIMP3 itself is idle."""
        while True:
            await asyncio.sleep(1)
            for p in self.server.players.values():
                idle = p.stream is None and p._runner is None and p.welcome_task is None
                room = p.sonos_room
                want = idle and p.show_sonos and self.sonos.active(room) is not None
                if want and not p.sonos_task:
                    p.sonos_task = asyncio.ensure_future(
                        SonosNowPlaying(p, lambda r=room: self.sonos.active(r)).run())
                    log("showing Sonos (%s) on %s" % (room or "any room", p.name or p.mac))
                elif p.sonos_task and not want:
                    p.cancel_sonos()
                    if idle:
                        self.idle_screen(p)

    async def index(self, req):
        return web.FileResponse(os.path.join(WEB, "index.html"))

    async def run(self):
        await self.server.start()
        app = web.Application(middlewares=[guard])
        app.add_routes([
            web.get("/", self.index), web.get("/api/state", self.state),
            web.get("/api/browse", self.browse), web.post("/api/play", self.play),
            web.post("/api/control", self.control), web.get("/api/sonos", self.sonos_state)])
        runner = web.AppRunner(app)
        await runner.setup()
        await web.TCPSite(runner, "0.0.0.0", PORT).start()
        if self.sonos.ips:
            asyncio.ensure_future(self.sonos.run())
            asyncio.ensure_future(self.sonos_display_loop())
        log("web UI/API on port %d; %d source(s), %d Sonos zone(s) configured"
            % (PORT, len(self.sources), len(self.sonos.ips)))
        await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(App(load_options()).run())
