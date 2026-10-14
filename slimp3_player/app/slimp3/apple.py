# SPDX-License-Identifier: GPL-2.0-only
"""Read-only HomePod monitor: finds HomePods on the network and listens for what they are playing, using the pyatv
library. A HomePod needs no pairing for this. Everything here is optional: if pyatv cannot be loaded, the app runs
without HomePod support. Connections are made only while some SLIMP3 is idle and wants to show a HomePod."""
import asyncio
import os
import sys
import time

_PYATV = None
LOAD_ERROR = [""]


def load_pyatv(log=print):
    """Import pyatv (and, if the compiled 'miniaudio' package is missing, a stand-in: pyatv needs it only to stream
    audio TO speakers, which this app never does). Returns the module, or None with a logged reason."""
    global _PYATV
    if _PYATV is not None:
        return _PYATV or None
    try:
        try:
            import miniaudio  # noqa: F401
        except ImportError:
            sys.path.append(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "stubs"))
        import pyatv
        _PYATV = pyatv
        return pyatv
    except Exception as e:
        _PYATV = False
        LOAD_ERROR[0] = "%s: %s" % (type(e).__name__, e)
        log("HomePod support is not available (%s)" % LOAD_ERROR[0])
        return None


def pick(devices, state, name=None):
    """The device called `name` in `state`, or with no name the first one, with its room joined to every other device
    in that state that carries the same track (a simulcast: 'Kitchen + Bedroom')."""
    hits = [(n, d) for n, d in devices.items() if d["state"] == state and (d["title"] or d["artist"] or state == "PLAYING")]
    if name:
        hits = [(n, d) for n, d in hits if n.lower() == name.lower()]
        return hits[0][1] if hits else None
    if not hits:
        return None
    first = hits[0][1]
    same = [n for n, d in hits if (d["artist"], d["title"]) == (first["artist"], first["title"])]
    return dict(first, room=" + ".join(same)) if len(same) > 1 else first


class AppleMonitor:
    REDISCOVER = 600
    POLL_PLAYING = 10.0     # seconds between direct checks of a HomePod that last said it was playing (catches a missed stop)
    POLL_IDLE = 60.0        # ... and of one that is not playing; push updates announce a start

    def __init__(self, log=print, enabled=True):
        self.log = log
        self.enabled = bool(enabled)
        self.devices = {}          # name -> latest play state
        self._confs = {}           # name -> pyatv config of a discovered HomePod
        self._conns = {}           # name -> open pyatv connection
        self._retry = {}           # name -> do not retry before
        self._disc_t = 0.0
        self._listeners = {}
        self._ok = None
        self.error = ""            # why HomePod support is unavailable, if it is
        self._dev_err = {}         # name -> last connection error
        self._seen_t = {}          # name -> when the HomePod last reported
        self._poll_t = {}          # name -> when the app last asked the HomePod directly

    # ---- discovery ---------------------------------------------------------------
    def available(self):
        """True when the HomePod library loaded (or has not been needed yet and nothing failed)."""
        return self.enabled and _PYATV is not False

    def info(self, name):
        """What the app knows about one HomePod, for the Info page."""
        d = self.devices.get(name) or {}
        return {"connected": name in self._conns, "state": d.get("state", ""), "title": d.get("title", ""),
                "artist": d.get("artist", ""), "app": d.get("app", ""), "error": self._dev_err.get(name, ""),
                "age": round(time.time() - self._seen_t[name]) if name in self._seen_t else None}

    async def discover(self):
        pyatv = load_pyatv(self.log)
        if not pyatv:
            self.error = LOAD_ERROR[0]
            return
        found = await pyatv.scan(asyncio.get_event_loop(), timeout=5)
        confs = {}
        for c in found:
            model = getattr(c.device_info.model, "name", str(c.device_info.model))
            if "HomePod" in model:
                confs[c.name] = (c, model)
        self._confs = {n: v[0] for n, v in confs.items()}
        self._models = {n: v[1] for n, v in confs.items()}
        self._disc_t = time.time()
        if self._ok is None or set(self._confs) != set(getattr(self, "_seen", set())):
            self.log("HomePods found: %s" % (", ".join(sorted(self._confs)) or "none"))
        self._seen = set(self._confs)
        self._ok = True

    def names(self):
        return sorted(self._confs)

    def model(self, name):
        m = getattr(self, "_models", {}).get(name, "HomePod")
        return "HomePod mini" if "Mini" in m else "HomePod"

    # ---- connections and push updates ------------------------------------------------
    async def _connect(self, name):
        pyatv = load_pyatv(self.log)
        try:
            atv = await asyncio.wait_for(pyatv.connect(self._confs[name], asyncio.get_event_loop()), 20)
        except Exception as e:
            self._retry[name] = time.time() + 60
            self._dev_err[name] = "%s: %s" % (type(e).__name__, e)
            self.log("HomePod %s: cannot connect (%s: %s); retrying in a minute" % (name, type(e).__name__, e))
            return
        from pyatv.interface import DeviceListener, PushListener

        monitor = self

        class Listener(PushListener, DeviceListener):
            def playstatus_update(self, updater, playstatus):
                monitor._apply(name, playstatus)

            def playstatus_error(self, updater, exception):
                monitor.log("HomePod %s: update error %s" % (name, exception))

            def connection_lost(self, exception):
                monitor._dropped(name)

            def connection_closed(self):
                pass

        listener = Listener()
        self._listeners[name] = listener
        atv.listener = listener
        atv.push_updater.listener = listener
        atv.push_updater.start(initial_delay=0)
        self._conns[name] = atv
        self._dev_err.pop(name, None)
        try:
            self._apply(name, await atv.metadata.playing())
        except Exception:
            pass

    def _dropped(self, name):
        self._conns.pop(name, None)
        self.devices.pop(name, None)
        self._retry[name] = time.time() + 30

    async def _disconnect(self, name):
        atv = self._conns.pop(name, None)
        self.devices.pop(name, None)
        self._listeners.pop(name, None)
        if atv is not None:
            try:
                pending = atv.close()
                if pending:
                    await asyncio.wait_for(asyncio.gather(*pending, return_exceptions=True), 3)
            except Exception:
                pass

    def _apply(self, name, p):
        state = getattr(p.device_state, "name", str(p.device_state))
        self._seen_t[name] = time.time()
        try:
            app = self._conns[name].metadata.app.name or ""
        except Exception:
            app = ""
        self.devices[name] = {
            "station": "", "room": name, "app": app,
            # "Loading" is not playing: a HomePod can sit in it for hours with no track (seen with the Podcasts app), and
            # counting it as playing left its name on the display.
            "state": "PLAYING" if state in ("Playing", "Seeking") else ("PAUSED" if state == "Paused" else (
                "LOADING" if state == "Loading" else "STOPPED")),
            "artist": p.artist or "", "title": p.title or "", "album": p.album or "",
            "source": self.model(name), "uri": "", "kind": "apple"}

    async def run(self, needed, interval=3.0):
        """needed(): the set of lowercase HomePod names an idle SLIMP3 wants ('' = any). Empty: stay disconnected."""
        if not self.enabled:
            return
        while True:
            want = needed()
            try:
                if not want:
                    for n in list(self._conns):
                        await self._disconnect(n)
                    await asyncio.sleep(5)
                    continue
                if not load_pyatv(self.log):      # loaded only when a SLIMP3 first wants a HomePod
                    return
                if not self._confs or time.time() - self._disc_t > self.REDISCOVER:
                    await self.discover()
                for name in self._confs:
                    wanted = "" in want or name.lower() in want
                    if wanted and name not in self._conns and time.time() >= self._retry.get(name, 0):
                        await self._connect(name)
                    elif not wanted and name in self._conns:
                        await self._disconnect(name)
                # Push updates can be missed (a stop that is never announced would leave the display on the last
                # song), so ask each connected HomePod directly every 10 seconds as well.
                now = time.time()
                for name in list(self._conns):
                    every = self.POLL_PLAYING if (self.devices.get(name) or {}).get("state") == "PLAYING" else self.POLL_IDLE
                    if now - self._poll_t.get(name, 0) >= every:
                        await self._poll(name)
            except Exception as e:
                self.log("HomePod monitor error: %s: %s" % (type(e).__name__, e))
                await asyncio.sleep(10)
            await asyncio.sleep(interval)

    async def _poll(self, name, timeout=5):
        atv = self._conns.get(name)
        self._poll_t[name] = time.time()
        if atv is None:
            return
        try:
            self._apply(name, await asyncio.wait_for(atv.metadata.playing(), timeout))
        except Exception:
            pass

    async def poll_now(self):
        """Ask every connected HomePod for its state right now (used to confirm a stop before the display goes black)."""
        await asyncio.gather(*[self._poll(n, 2) for n in list(self._conns)])

    def paused(self, name=None):
        """A paused device with a track loaded, for the 'Paused <room>' screen."""
        return pick(self.devices, "PAUSED", name)

    def active(self, name=None):
        """The playing HomePod called `name` (case-insensitive), or any playing HomePod if name is empty."""
        return pick(self.devices, "PLAYING", name)

    async def close(self):
        for n in list(self._conns):
            await self._disconnect(n)
