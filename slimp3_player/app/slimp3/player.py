# SPDX-License-Identifier: GPL-2.0-only
import asyncio

from . import mas3507d
from .nowplaying import DEFAULT_SLEEP_KEYWORDS, NowPlaying
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
        self.mirror_idle_since = 0.0
        self.blank_t = 0.0
        self.name = ""
        self.fw = ""
        self.configured = False
        self.welcome_task = None
        self.welcome_t = 0.0
        self.sonos_room = ""
        self.apple_room = ""
        self.cast_room = ""
        self.show_sonos = True
        self.sleep_mode = False
        self.sleep_keywords = list(DEFAULT_SLEEP_KEYWORDS)
        self.pos_base = 0.0          # seconds into the track where this stream started (after a seek)
        self._start_at = 0.0
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
        return {"mac": self.mac, "name": self.name, "fw": self.fw, "configured": self.configured, "sonos_room": self.sonos_room, "apple_room": self.apple_room, "cast_room": self.cast_room,
                "show_sonos": self.show_sonos, "ip": self.addr[0], "state": state,
                "position": round(self.pos_base + self.position(), 1), "volume": self.volume,
                "sleep_mode": self.sleep_mode,
                "duration": (self.meta.get("duration") if self.stream else None),
                "seekable": bool(self.stream and self.meta.get("seekable")),
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
                                    source_name=it.get("source") or "", kind=it.get("kind") or "",
                                    mp3=("audio/mpeg" in proto) if proto else None,
                                    length_s=_seconds(it.get("duration")), start_s=self._take_start())
                except Exception as e:  # keep the queue moving on a bad track
                    self.log("play failed: %s" % e)
                    continue
                await self.ended.wait()
            await self._halt()
            self.show("Queue finished", "Pick more music in Home Assistant")
        except asyncio.CancelledError:
            pass

    def _take_start(self):
        s, self._start_at = self._start_at, 0.0
        return s

    def seek(self, seconds):
        """Restart the current track at `seconds` (the page's timeline). Only for tracks of known length that are
        not live. Returns False if this one cannot be searched."""
        m = self.meta
        if not (self.stream and m.get("seekable") and self.queue and self.index >= 0):
            return False
        top = max(0.0, float(m.get("duration") or 0) - 2.0)
        self._start_at = max(0.0, min(float(seconds), top))
        self.index -= 1                  # the queue runner replays the same item from there
        self.ended.set()
        return True

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

    async def play(self, source, title="", artist="", album="", duration=None, live=False, mp3=None, length_s=None,
                   source_name="", kind="", start_s=0.0):
        """MP3 sources are fed to the SLIMP3 untouched (it decodes MP3 itself). Anything else, and
        live streams, are converted to 128 kbps MP3 by ffmpeg. mp3=None means: judge by the file name."""
        self.cancel_sonos()
        self.cancel_welcome()
        await self._halt()
        if mp3 is None:
            mp3 = source.lower().split("?")[0].endswith(".mp3")
        bytes_per_sec = 16000.0
        pos_fn = None
        if mp3 and self.passthrough and not live and not source.startswith("rtsp"):
            try:
                self.reader = await Mp3Source(source).open()
                if self.reader.total_bytes and length_s:      # VBR-safe: true average rate
                    bytes_per_sec = self.reader.total_bytes / float(length_s)
                elif self.reader.bitrate:
                    bytes_per_sec = self.reader.bitrate / 8.0
                if self.reader.has_toc and length_s:      # variable bit rate: exact seeking and position
                    start_byte = self.reader.byte_for_time(start_s, length_s) if start_s else 0
                    if start_s:
                        await self.reader.seek_to(start_byte)
                    r, t0 = self.reader, self.reader.time_for_byte(start_byte, length_s)
                    pos_fn = lambda consumed: r.time_for_byte(start_byte + consumed, length_s) - t0
                    start_s = t0
                    self.log("variable bit rate file with a seek table: exact seeking")
                elif start_s:
                    await self.reader.seek_to(start_s * bytes_per_sec)
                if duration:
                    self.reader.limit_bytes(duration * bytes_per_sec)
                self.log("pass-through MP3 (about %d kbps), no transcoding" % (bytes_per_sec * 8 / 1000))
            except Exception as e:
                self.log("pass-through failed (%s); transcoding instead" % e)
                await self._close_reader()
        if self.reader is None:
            cmd = [FFMPEG, "-nostdin", "-v", "error"] + (["-ss", str(start_s)] if start_s else []) + ["-i", source]
            if duration:
                cmd += ["-t", str(duration)]
            cmd += ["-vn", "-map_metadata", "-1", "-c:a", "libmp3lame", "-b:a", "128k",
                    "-ar", "44100", "-ac", "2", "-write_xing", "0", "-id3v2_version", "0",
                    "-f", "mp3", "pipe:1"]
            self.proc = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
        self.meta = {"title": title or source.rsplit("/", 1)[-1], "artist": artist, "album": album,
                     "source": source_name, "kind": kind, "duration": length_s or None,
                     "seekable": bool(length_s) and not live}
        self.pos_base = float(start_s or 0.0)
        if self.use_spectrum and not live:   # optional extra: needs numpy and a second decode of the source
            from .spectrum import Spectrum
            self.spectrum = Spectrum(source, FFMPEG, duration, start_s)
            self.spectrum.start()
        self.ended.clear()
        s = Stream(self.loop, self._send, self._read, self.log)
        s.bytes_per_sec = bytes_per_sec
        s.pos_fn = pos_fn
        s.on_end = self._finished
        s.on_dead = self._finished
        s.on_started = self._started
        self.stream = s
        self.set_volume(self.volume)
        self._send(i2c_packet(mas3507d.init_sequence()))
        await asyncio.sleep(0.05)         # let the player digest the i2c writes
        self.show(("Buffering from %s" % source_name) if source_name else "Buffering...", self.meta["title"])
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

    async def _reap(self, proc):
        """Kill ffmpeg and collect it without ever hanging. If something is still reading its output, a plain wait
        finishes at once. If nothing is (a fast source such as live TV leaves unread output buffered), asyncio's
        wait() can wait forever for the pipe to reach end-of-file, so drain the pipe and wait again."""
        if proc.returncode is None:
            try:
                proc.kill()
            except ProcessLookupError:
                pass
        try:
            await asyncio.wait_for(proc.wait(), 1.0)
            return
        except asyncio.TimeoutError:
            pass

        async def drain():
            while await proc.stdout.read(65536):
                pass
        try:
            await asyncio.wait_for(drain(), 3)
            await asyncio.wait_for(proc.wait(), 3)
        except Exception as e:
            self.log("ffmpeg did not exit cleanly (%s); continuing" % type(e).__name__)

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
        proc, self.proc = self.proc, None
        if proc is not None:
            await self._reap(proc)

    async def stop(self):
        await self._cancel_runner()
        await self._halt()
        self.queue, self.index = [], -1
        self.show("Stopped", self.meta.get("title") or "Pick music in Home Assistant")
