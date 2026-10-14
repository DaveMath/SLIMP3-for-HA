# SPDX-License-Identifier: GPL-2.0-only
"""SLIMP3 Player app: UDP endpoint for SLIMP3 devices + HTTP API/UI (HA ingress)."""
import asyncio
import json
import os
import time

from aiohttp import web

from slimp3.server import Server
from slimp3.upnp import MediaServer

OPTS_PATH = os.environ.get("SLIMP3_OPTIONS", "/data/options.json")
PORT = int(os.environ.get("SLIMP3_PORT", "8099"))
WEB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")
T0 = time.time()


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
        self.server.on_new_player = self._new_player

    def _new_player(self, p):
        p.on_ir = lambda code: log("IR 0x%s" % code)
        p.show("SLIMP3 server ready", "Home Assistant")

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
        elif act == "volume":
            p.set_volume(int(body["value"]))
        else:
            raise web.HTTPBadRequest(text="unknown action")
        return web.json_response(p.status())

    async def index(self, req):
        return web.FileResponse(os.path.join(WEB, "index.html"))

    async def run(self):
        await self.server.start()
        app = web.Application()
        app.add_routes([
            web.get("/", self.index), web.get("/api/state", self.state),
            web.get("/api/browse", self.browse), web.post("/api/play", self.play),
            web.post("/api/control", self.control)])
        runner = web.AppRunner(app)
        await runner.setup()
        await web.TCPSite(runner, "0.0.0.0", PORT).start()
        log("web UI/API on port %d; %d source(s) configured" % (PORT, len(self.sources)))
        await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(App(load_options()).run())
