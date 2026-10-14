# SPDX-License-Identifier: GPL-2.0-only
"""SLIMP3 Player app: UDP endpoint for SLIMP3 devices + HTTP API/UI (HA ingress)."""
import asyncio
import hashlib
import ipaddress
import json
import shutil
import uuid
import os
import subprocess
import time

from aiohttp import web

from slimp3.net import local_ipv4s
from slimp3.nowplaying import SonosNowPlaying
from slimp3.server import Server
from slimp3.sonos import SonosMonitor
from slimp3.upnp import MediaServer, discover_servers, resolve_server

OPTS_PATH = os.environ.get("SLIMP3_OPTIONS", "/data/options.json")
PORT = int(os.environ.get("SLIMP3_PORT", "8099"))
UDP_PORT = int(os.environ.get("SLIMP3_UDP_PORT", "3483"))    # only a test setup changes this
WEB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")
T0 = time.time()
# Home Assistant's internal network (ingress gateway is 172.30.32.2); set SLIMP3_ALLOW_ALL=1 for local dev.
ALLOWED = [ipaddress.ip_network(n) for n in ("127.0.0.0/8", "172.30.32.0/23")]
ALLOW_ALL = os.environ.get("SLIMP3_ALLOW_ALL") == "1"


@web.middleware
async def guard(request, handler):
    if not ALLOW_ALL:
        try:
            ok = any(ipaddress.ip_address(request.remote) in n for n in ALLOWED) or request.remote in local_ipv4s()
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


def check_ffmpeg():
    """The SLIMP3 decodes MP3 only, so ffmpeg must have the libmp3lame encoder."""
    try:
        r = subprocess.run(["ffmpeg", "-hide_banner", "-encoders"], capture_output=True, text=True, timeout=30)
        text = (r.stdout or "") + (r.stderr or "")
        if "libmp3lame" in text:
            log("ffmpeg ok: libmp3lame encoder present")
            return True
        log("ERROR: ffmpeg has no libmp3lame MP3 encoder, so playback will fail. ffmpeg exit %s, said: %s"
            % (r.returncode, " | ".join(text.strip().splitlines()[:6])[:400]))
    except Exception as e:
        log("ERROR: cannot run ffmpeg: %s" % e)
    return False


def install_integration(bases=("/homeassistant_config", "/config")):
    """Copy the SLIMP3 Home Assistant integration (a media player with a media browser) into the Home Assistant
    configuration folder, so it can be added under Settings, Devices & services. Needs the config map in config.yaml."""
    src = os.path.join(os.path.dirname(os.path.abspath(__file__)), "integration", "slimp3")
    status = {"installed": False, "version": None, "restart_needed": False, "path": None}
    try:
        with open(os.path.join(src, "manifest.json")) as f:
            status["version"] = json.load(f)["version"]
    except (OSError, ValueError, KeyError):
        return status
    for base in bases:
        if not (os.path.isdir(base) and os.access(base, os.W_OK)):
            continue
        dest = os.path.join(base, "custom_components", "slimp3")
        have = None
        try:
            with open(os.path.join(dest, "manifest.json")) as f:
                have = json.load(f).get("version")
        except (OSError, ValueError):
            pass
        try:
            if have != status["version"]:
                shutil.copytree(src, dest, dirs_exist_ok=True, ignore=shutil.ignore_patterns("__pycache__"))
                status["restart_needed"] = True
                log("installed the SLIMP3 Home Assistant integration %s (was %s) in %s; restart Home Assistant, "
                    "then add SLIMP3 under Settings, Devices & services" % (status["version"], have or "not installed", dest))
            else:
                log("SLIMP3 Home Assistant integration %s is already installed" % have)
            status.update(installed=True, path=dest)
        except OSError as e:
            log("could not install the Home Assistant integration into %s: %s" % (dest, e))
        return status
    log("Home Assistant config folder is not mapped into the app; the dashboard integration was not installed")
    return status


class App:
    def __init__(self, opts):
        self.opts = opts
        self.sources = []
        self.started = time.time()
        self.server = Server(opts.get("player_ips") or [], log)
        self.server.player_defaults = {
            "volume": int(opts.get("default_volume", 40)),
            "fps": int(opts.get("display_fps", 8)),
            "sync_ms": int(opts.get("sync_ms", 0)),
            "use_spectrum": bool(opts.get("spectrum", False)),
            "passthrough": bool(opts.get("mp3_passthrough", True)),
        }
        check_ffmpeg()
        wants_spectrum = bool(opts.get("spectrum", False)) or any(
            c.get("spectrum") for c in (opts.get("players") or []))
        self.spectrum_ok = False
        if wants_spectrum:      # numpy is imported only if the analyzer is actually switched on
            from slimp3.spectrum import selftest
            ms = selftest()
            fps = int(opts.get("display_fps", 8))
            self.spectrum_ok = ms is not None and ms < 500.0 / fps   # at most half a frame period
            if ms is None:
                log("spectrum analyzer unavailable (numpy missing); using the artist/title layout")
            else:
                log("spectrum analyzer: %.1f ms per frame, budget %.0f ms at %d fps -> %s"
                    % (ms, 500.0 / fps, fps, "ok" if self.spectrum_ok else "too slow, using artist/title layout"))
        else:
            log("spectrum analyzer is off (default): MP3 is passed straight through, no audio processing")
        self.server.on_new_player = self._new_player
        self.server.on_reboot = self.start_welcome
        self.sonos = SonosMonitor(opts.get("sonos_ips") or [], log, bool(opts.get("sonos_discovery", True)))
        self.cfg = {str(c.get("mac", "")).lower(): c for c in (opts.get("players") or [])}
        self.data_dir = os.environ.get("SLIMP3_DATA", "/data")
        self.saved = self._load_saved()      # settings made on the sidebar page; they override the options
        self.instance_id = self._instance_id()
        self.integration = install_integration()
        for u in opts.get("dlna_servers") or []:
            self._add_source(u, "config")
        for e in self._load_json("sources.json", []):
            self._add_source(e.get("url", ""), "added", e.get("name"))

    # ---- music servers: from the options, plus the ones added on the sidebar page ----
    def _load_json(self, name, default):
        try:
            with open(os.path.join(self.data_dir, name)) as f:
                return json.load(f)
        except (OSError, ValueError):
            return default

    def _instance_id(self):
        """A stable id for this app instance (the Home Assistant integration uses it as its unique id)."""
        data = self._load_json("instance.json", {})
        if not data.get("id"):
            data = {"id": uuid.uuid4().hex}
            try:
                with open(os.path.join(self.data_dir, "instance.json"), "w") as f:
                    json.dump(data, f)
            except OSError:
                pass
        return data["id"]

    def _add_source(self, url, origin, name=None):
        if not url:
            return None
        sid = hashlib.md5(url.encode()).hexdigest()[:8]
        found = next((s for s in self.sources if s["id"] == sid), None)
        if found:
            return found
        src = {"id": sid, "url": url, "server": None, "name": name or url, "origin": origin, "udn": ""}
        self.sources.append(src)
        return src

    def _save_sources(self):
        try:
            path = os.path.join(self.data_dir, "sources.json")
            with open(path + ".tmp", "w") as f:
                json.dump([{"url": s["url"], "name": s["name"]} for s in self.sources if s["origin"] == "added"], f)
            os.replace(path + ".tmp", path)
        except OSError as e:
            log("could not save music servers: %s" % e)

    async def _warm_sources(self):
        """Connect to each music server once so the page can show its real name."""
        loop = asyncio.get_event_loop()
        for s in self.sources:
            if s["server"] is None:
                try:
                    s["server"] = await loop.run_in_executor(None, MediaServer(s["url"], 4).connect)
                    s["name"], s["udn"] = s["server"].name or s["name"], s["server"].udn or ""
                except Exception as e:
                    log("music server %s not reachable yet: %s" % (s["url"], e))

    def _new_player(self, p):
        c = self.cfg_for(p.mac)
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

    # ---- per-player settings: options file, overridden by what was saved from the sidebar page ----
    def _load_saved(self):
        try:
            with open(os.path.join(self.data_dir, "player_settings.json")) as f:
                return {k.lower(): v for k, v in json.load(f).items()}
        except (OSError, ValueError):
            return {}

    def _save(self):
        try:
            path = os.path.join(self.data_dir, "player_settings.json")
            with open(path + ".tmp", "w") as f:
                json.dump(self.saved, f)
            os.replace(path + ".tmp", path)
        except OSError as e:
            log("could not save player settings: %s" % e)

    def cfg_for(self, mac):
        c = dict(self.cfg.get(mac.lower(), {}))
        c.update(self.saved.get(mac.lower(), {}))
        return c

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
            c = self.cfg_for(p.mac) or None
            later = []
            if c is None:
                later.append(("Optional: name this player", "HA sidebar > SLIMP3 > Settings", 4.0))
            else:
                room = c.get("sonos_room") or ""
                show = c.get("show_sonos", self.opts.get("sonos_display", True))
                if not self.sonos.enabled:
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
            if not self.sonos.enabled and c is None:
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
        now = time.time()
        return web.json_response({
            "players": [p.status() for p in self.server.players.values()],
            "sources": [{"id": s["id"], "name": s["name"]} for s in self.sources],
            "heard": [{"ip": ip, "ago": int(now - t)} for ip, t in self.server.heard.items()],
            "uptime": int(now - self.started), "udp_port": UDP_PORT,
            "sonos_enabled": self.sonos.enabled, "instance_id": self.instance_id,
            "integration": self.integration})

    async def sources_list(self, req):
        return web.json_response([{"id": s["id"], "name": s["name"], "url": s["url"], "origin": s["origin"]}
                                  for s in self.sources])

    async def sources_add(self, req):
        body = await req.json()
        try:
            srv = await asyncio.get_event_loop().run_in_executor(None, resolve_server, body.get("url"))
        except ValueError as e:
            raise web.HTTPBadRequest(text=str(e))
        same = next((s for s in self.sources if srv.udn and s["udn"] == srv.udn), None)
        if same:                                   # already listed (maybe under another address)
            return web.json_response({"id": same["id"], "name": same["name"], "url": same["url"], "origin": same["origin"]})
        src = self._add_source(srv.description_url, "added", srv.name)
        src["server"], src["name"], src["udn"] = srv, srv.name or src["name"], srv.udn or ""
        self._save_sources()
        return web.json_response({"id": src["id"], "name": src["name"], "url": src["url"], "origin": src["origin"]})

    async def sources_remove(self, req):
        src = next((s for s in self.sources if s["id"] == req.query.get("id")), None)
        if not src:
            raise web.HTTPNotFound(text="unknown music server")
        if src["origin"] == "config":
            raise web.HTTPBadRequest(text="This server comes from the app configuration. Remove it there.")
        self.sources.remove(src)
        self._save_sources()
        return web.json_response({"removed": src["id"]})

    async def sources_discover(self, req):
        found = await asyncio.get_event_loop().run_in_executor(None, discover_servers)
        have_urls = {s["url"] for s in self.sources}
        have_udns = {s["udn"] for s in self.sources if s["udn"]}
        for f in found:
            f["added"] = f["url"] in have_urls or (f["udn"] in have_udns if f["udn"] else False)
        return web.json_response(found)

    async def browse(self, req):
        srv = await self.source(req.query.get("source") or (self.sources[0]["id"] if self.sources else ""))
        oid, start = req.query.get("id", "0"), int(req.query.get("start", 0))
        loop = asyncio.get_event_loop()
        items, total = await loop.run_in_executor(None, srv.browse, oid, start, 200)
        out = {"items": items, "total": total}
        if req.query.get("title"):
            try:
                meta = await loop.run_in_executor(None, srv.metadata, oid)
                out["title"] = (meta or {}).get("title") or ""
            except Exception:
                out["title"] = ""
        return web.json_response(out)

    async def play(self, req):
        body = await req.json()
        p = self.player(body.get("mac"))
        if not p:
            raise web.HTTPServiceUnavailable(text="no SLIMP3 connected")
        srv = await self.source(body.get("source") or (self.sources[0]["id"] if self.sources else ""))
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

    def _sonos_needed(self):
        """Rooms (lowercase; '' = any) that an idle SLIMP3 wants to show. Empty: do not poll Sonos at all."""
        return {(p.sonos_room or "").lower() for p in self.server.players.values()
                if p.show_sonos and p.stream is None and p._runner is None}

    async def sonos_state(self, req):
        if not self.sonos.rooms():
            try:
                await asyncio.get_event_loop().run_in_executor(None, self.sonos.ensure_topology)
            except Exception as e:
                log("sonos rooms not available: %s" % e)
        return web.json_response({"rooms": self.sonos.rooms(), "groups": self.sonos.groups,
                                  "discovered": self.sonos.discovered})

    async def set_player(self, req):
        """Save a player's name and Sonos room from the sidebar page and apply it immediately."""
        body = await req.json()
        p = self.player(body.get("mac"))
        if not p:
            raise web.HTTPServiceUnavailable(text="no SLIMP3 connected")
        s = self.saved.setdefault(p.mac.lower(), {})
        if "name" in body:
            p.name = s["name"] = str(body["name"])[:30]
        if "sonos_room" in body:
            p.sonos_room = s["sonos_room"] = str(body["sonos_room"])
        if "show_sonos" in body:
            p.show_sonos = s["show_sonos"] = bool(body["show_sonos"])
        p.configured = True
        p.cancel_sonos()           # the display loop restarts it with the new room within a second
        self._save()
        return web.json_response(p.status())

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
        await self.server.start(port=UDP_PORT)
        app = web.Application(middlewares=[guard])
        app.add_routes([
            web.get("/", self.index), web.get("/api/state", self.state),
            web.get("/api/browse", self.browse), web.post("/api/play", self.play),
            web.post("/api/control", self.control), web.get("/api/sonos", self.sonos_state),
            web.post("/api/player", self.set_player), web.get("/api/sources", self.sources_list),
            web.post("/api/sources", self.sources_add), web.delete("/api/sources", self.sources_remove),
            web.get("/api/discover/servers", self.sources_discover)])
        runner = web.AppRunner(app)
        await runner.setup()
        await web.TCPSite(runner, "0.0.0.0", PORT).start()
        if self.sonos.enabled:      # configured addresses and/or automatic discovery
            asyncio.ensure_future(self.sonos.run(needed=self._sonos_needed))
            asyncio.ensure_future(self.sonos_display_loop())
        asyncio.ensure_future(self._warm_sources())
        log("web UI/API on port %d; %d music server(s); Sonos %s"
            % (PORT, len(self.sources),
               ("discovery on" if self.sonos.discovery else "addresses only") if self.sonos.enabled else "off"))
        await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(App(load_options()).run())
