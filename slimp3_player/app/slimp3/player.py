# SPDX-License-Identifier: GPL-2.0-only
import asyncio

from . import mas3507d
from .nowplaying import NowPlaying
from .mp3 import Mp3Source
from .protocol import display_packet, i2c_packet
from .stream import Stream

FFMPEG = "ffmpeg"


def _seconds(hms):
    """'0:03:13.000' -> 193.0 (DLNA duration), or None."""
    try:
        h, m, s = (hms or "").split(":")
        return int(h) * 3600 + int(m) * 60 + float(s) or None
    except ValueError:
        return None


class Player:
    """One SLIMP3 device: display, volume, queue, and MP3 streaming via ffmpeg."""

    def __init__(self, server, mac, addr, log=print):
        self.server, self.mac, self.addr, self.log = server, mac, addr, log
        self.loop = asyncio.get_event_loop()
        self.volume = 40
        self.fps = 8
        self.sync_ms = 0
        self.use_spectrum = False
        self.passthrough = True
        self.stream = None
        self.proc = None
        self.reader = None
        self.spectrum = None
        self._np_task = None
        self._runner = None
        self.sonos_task = None
        self.name = ""
        self.fw = ""
        self.configured = False
        self.welcome_task = None
        self.welcome_t = 0.0
        self.sonos_room = ""
        self.show_sonos = True
        self.meta = {}
        self.queue = []
        self.index = -1
        self.ended = asyncio.Event()
        self.on_ir = None

    # ---- device I/O -------------------------------------------------
    def _send(self, data):
        self.server.send(self.addr, data)

    def show(self, line1, line2=""):
        self._send(display_packet(line1, line2))

    def set_volume(self, vol):
        self.volume = max(0, min(100, int(vol)))
        self._send(i2c_packet(mas3507d.volume(self.volume)))

    def position(self):
        return self.stream.position() if self.stream else 0.0

    def status(self):
        state = self.stream.state if self.stream else "stop"
        return {"mac": self.mac, "name": self.name, "fw": self.fw, "configured": self.configured, "ip": self.addr[0], "state": state,
                "position": round(self.position(), 1), "volume": self.volume,
                "meta": self.meta if self.stream else {}, "index": self.index,
                "queue_len": len(self.queue)}

    # ---- queue ------------------------------------------------------
    async def play_queue(self, items, start=0):
        """items: dicts with url/title/artist/album. Plays through, then goes idle."""
        await self._cancel_runner()
        self.queue, self.index = list(items), start - 1
        self._runner = self.loop.create_task(self._run_queue())

    async def _run_queue(self):
        try:
            while self.index + 1 < len(self.queue):
                self.index += 1
                it = self.queue[self.index]
                try:
                    proto = it.get("protocol") or ""
                    await self.play(it["url"], it.get("title") or "", it.get("artist") or "",
                                    it.get("album") or "", live="Broadcast" in (it.get("class") or ""),
                                    mp3=("audio/mpeg" in proto) if proto else None,
                                    length_s=_seconds(it.get("duration")))
                except Exception as e:  # keep the queue moving on a bad track
                    self.log("play failed: %s" % e)
                    continue
                await self.ended.wait()
            await self._halt()
            self.show("Queue finished", "")
        except asyncio.CancelledError:
            pass

    def next(self):
        if self.queue and self.index + 1 < len(self.queue):
            self.ended.set()

    def prev(self):
        if self.queue and self.index > 0:
            self.index -= 2
            self.ended.set()

    async def _cancel_runner(self):
        r, self._runner = self._runner, None
        if r and r is not asyncio.current_task():
            r.cancel()
            try:
                await r
            except asyncio.CancelledError:
                pass

    # ---- single-track playback --------------------------------------
    def cancel_welcome(self):
        if self.welcome_task:
            self.welcome_task.cancel()
            self.welcome_task = None

    def cancel_sonos(self):
        if self.sonos_task:
            self.sonos_task.cancel()
            self.sonos_task = None

    async def play(self, source, title="", artist="", album="", duration=None, live=False, mp3=None, length_s=None):
        """MP3 sources are fed to the SLIMP3 untouched (it decodes MP3 itself). Anything else, and
        live streams, are converted to 128 kbps MP3 by ffmpeg. mp3=None means: judge by the file name."""
        self.cancel_sonos()
        self.cancel_welcome()
        await self._halt()
        if mp3 is None:
            mp3 = source.lower().split("?")[0].endswith(".mp3")
        bytes_per_sec = 16000.0
        if mp3 and self.passthrough and not live and not source.startswith("rtsp"):
            try:
                self.reader = await Mp3Source(source).open()
                if self.reader.total_bytes and length_s:      # VBR-safe: true average rate
                    bytes_per_sec = self.reader.total_bytes / float(length_s)
                elif self.reader.bitrate:
                    bytes_per_sec = self.reader.bitrate / 8.0
                if duration:
                    self.reader.limit_bytes(duration * bytes_per_sec)
                self.log("pass-through MP3 (about %d kbps), no transcoding" % (bytes_per_sec * 8 / 1000))
            except Exception as e:
                self.log("pass-through failed (%s); transcoding instead" % e)
                await self._close_reader()
        if self.reader is None:
            cmd = [FFMPEG, "-nostdin", "-v", "error", "-i", source]
            if duration:
                cmd += ["-t", str(duration)]
            cmd += ["-vn", "-map_metadata", "-1", "-c:a", "libmp3lame", "-b:a", "128k",
                    "-ar", "44100", "-ac", "2", "-write_xing", "0", "-id3v2_version", "0",
                    "-f", "mp3", "pipe:1"]
            self.proc = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        self.meta = {"title": title or source.rsplit("/", 1)[-1], "artist": artist, "album": album}
        if self.use_spectrum and not live:   # optional extra: needs numpy and a second decode of the source
            from .spectrum import Spectrum
            self.spectrum = Spectrum(source, FFMPEG, duration)
            self.spectrum.start()
        self.ended.clear()
        s = Stream(self.loop, self._send, self._read, self.log)
        s.bytes_per_sec = bytes_per_sec
        s.on_end = self._finished
        s.on_dead = self._finished
        s.on_started = self._started
        self.stream = s
        self.set_volume(self.volume)
        self._send(i2c_packet(mas3507d.init_sequence()))
        await asyncio.sleep(0.05)         # let the player digest the i2c writes
        self.show("Buffering...", self.meta["title"])
        s.start()

    def _started(self):
        self._stop_display()
        spec = self.spectrum if (self.spectrum and self.spectrum.available) else None
        np_ = NowPlaying(self, self.meta, spec, self.fps, self.sync_ms)
        self._np_task = self.loop.create_task(np_.run())

    def _stop_display(self):
        if self._np_task:
            self._np_task.cancel()
            self._np_task = None

    def _finished(self):
        self._stop_display()
        self.ended.set()

    async def _read(self, n):
        if self.reader is not None:
            return await self.reader.read(n)
        try:
            return await self.proc.stdout.readexactly(n)
        except asyncio.IncompleteReadError as e:
            return e.partial

    async def _close_reader(self):
        r, self.reader = self.reader, None
        if r is not None:
            try:
                await r.close()
            except Exception:
                pass

    def pause(self):
        if self.stream:
            self.stream.pause()

    def resume(self):
        if self.stream:
            self.stream.resume()

    async def _halt(self):
        self._stop_display()
        if self.spectrum:
            self.spectrum.stop()
            self.spectrum = None
        if self.stream:
            self.stream.stop()
            self.stream = None
        await self._close_reader()
        if self.proc and self.proc.returncode is None:
            self.proc.kill()
            await self.proc.wait()
        self.proc = None

    async def stop(self):
        await self._cancel_runner()
        await self._halt()
        self.queue, self.index = [], -1
        self.show("Stopped", "")
