# SPDX-License-Identifier: GPL-2.0-only
"""Read-only HomePod monitor: finds HomePods on the network and listens for what they are playing, using the pyatv
library. A HomePod needs no pairing for this. Everything here is optional: if pyatv cannot be loaded, the app runs
without HomePod support. Connections are made only while some SLIMP3 is idle and wants to show a HomePod."""
import asyncio
import os
import sys
import time

_PYATV = None


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
        log("HomePod support is not available (%s: %s)" % (type(e).__name__, e))
        return None


class AppleMonitor:
    REDISCOVER = 600

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

    # ---- discovery ---------------------------------------------------------------
    async def discover(self):
        pyatv = load_pyatv(self.log)
        if not pyatv:
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
        self.devices[name] = {
            "station": "", "room": name, "state": "PLAYING" if state == "Playing" else
            ("PAUSED" if state == "Paused" else "STOPPED"),
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
            except Exception as e:
                self.log("HomePod monitor error: %s: %s" % (type(e).__name__, e))
                await asyncio.sleep(10)
            await asyncio.sleep(interval)

    def active(self, name=None):
        """The playing HomePod called `name` (case-insensitive), or any playing HomePod if name is empty."""
        for n, d in self.devices.items():
            if d["state"] == "PLAYING" and (not name or n.lower() == name.lower()):
                return d
        return None

    async def close(self):
        for n in list(self._conns):
            await self._disconnect(n)
