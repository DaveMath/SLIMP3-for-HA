# SPDX-License-Identifier: GPL-2.0-only
"""MP3 pass-through. The SLIMP3 decodes MP3 itself, so an MP3 source is fed to it untouched
(slimserver does the same: convert.conf rule 'mp3 mp3 * *' is a plain pass-through). Only the
leading ID3v2 tag is skipped so the decoder starts on a real audio frame."""
import asyncio
import os

_BITRATES = {   # kbps for header index 1..14, by (MPEG version 1 or 2/2.5, layer)
    ("1", 1): [32, 64, 96, 128, 160, 192, 224, 256, 288, 320, 352, 384, 416, 448],
    ("1", 2): [32, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320, 384],
    ("1", 3): [32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320],
    ("2", 1): [32, 48, 56, 64, 80, 96, 112, 128, 144, 160, 176, 192, 224, 256],
    ("2", 2): [8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160],
    ("2", 3): [8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160],
}


def frame_bitrate(h):
    """Bitrate in bits/s from a 4-byte MPEG audio frame header, or None if it is not one."""
    if len(h) < 4 or h[0] != 0xFF or (h[1] & 0xE0) != 0xE0:
        return None
    ver, layer, idx = (h[1] >> 3) & 3, (h[1] >> 1) & 3, (h[2] >> 4) & 15
    if ver == 1 or layer == 0 or idx in (0, 15):
        return None
    return _BITRATES[("1" if ver == 3 else "2", 4 - layer)][idx - 1] * 1000


def parse_xing(frame):
    """The Xing/Info header in a file's first MPEG frame: {'frames', 'bytes', 'toc'} (keys present only if the file has
    them). The 'toc' is a 100-entry table: the byte position, in 256ths of the file, at each percent of the duration."""
    if len(frame) < 140 or frame[0] != 0xFF:
        return None
    mpeg1 = ((frame[1] >> 3) & 3) == 3
    mono = ((frame[3] >> 6) & 3) == 3
    off = 4 + (0 if frame[1] & 1 else 2) + ((17 if mono else 32) if mpeg1 else (9 if mono else 17))
    if frame[off:off + 4] not in (b"Xing", b"Info"):
        return None
    flags, p, out = int.from_bytes(frame[off + 4:off + 8], "big"), off + 8, {}
    for bit, key, size in ((1, "frames", 4), (2, "bytes", 4)):
        if flags & bit:
            out[key] = int.from_bytes(frame[p:p + size], "big")
            p += size
    if flags & 4:
        toc = list(frame[p:p + 100])
        if len(toc) == 100 and toc[0] == 0 and all(b >= a for a, b in zip(toc, toc[1:])):
            out["toc"] = toc + [256]
    return out


def id3v2_size(head):
    """Total size in bytes of a leading ID3v2 tag (header, body, optional footer), or 0."""
    if len(head) < 10 or head[:3] != b"ID3":
        return 0
    size = (head[6] << 21) | (head[7] << 14) | (head[8] << 7) | head[9]
    return 10 + size + (10 if head[5] & 0x10 else 0)


class Mp3Source:
    """Async reader over an http:// URL or a local file. read(n) returns b'' at the end."""

    def __init__(self, source):
        self.source = source
        self.bitrate = None
        self.total_bytes = None      # audio bytes (file size minus tags), when the size is known
        self._audio_start = 0        # file offset of the first audio frame
        self.xing = {}
        self._pending = b""
        self._left = None
        self._session = self._resp = self._fh = None

    async def _raw(self, n):
        if self._fh is not None:
            return await asyncio.get_event_loop().run_in_executor(None, self._fh.read, n)
        return await self._resp.content.read(n)

    async def open(self):
        if self.source.startswith(("http://", "https://")):
            import aiohttp  # only needed for URLs
            self._session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(
                total=None, sock_connect=10, sock_read=30))
            self._resp = await self._session.get(self.source)
            self._resp.raise_for_status()
        else:
            self._fh = open(self.source, "rb")
        size = self._resp.content_length if self._resp is not None else os.path.getsize(self.source)
        buf = await self._raw(16384)
        skip = id3v2_size(buf)
        dropped = skip
        while skip > len(buf):               # a tag larger than the first read: discard it
            skip -= len(buf)
            buf = await self._raw(65536)
            if not buf:
                break
        buf = buf[skip:]
        buf, skipped = self._find_sync(buf)
        dropped += skipped
        self._audio_start = dropped
        self.xing = parse_xing(buf[:400]) or {}
        self.bitrate = frame_bitrate(buf[:4])
        self.total_bytes = (size - dropped) if size else None
        self._pending = buf
        return self

    @staticmethod
    def _find_sync(buf):
        """Trim to the first MPEG audio frame header within the first 4 KB. Returns (buffer, bytes dropped)."""
        for i in range(min(len(buf) - 1, 4096)):
            if buf[i] == 0xFF and (buf[i + 1] & 0xE0) == 0xE0 and frame_bitrate(buf[i:i + 4]):
                return buf[i:], i
        return buf, 0

    @property
    def has_toc(self):
        return bool(self.xing.get("toc")) and bool(self.total_bytes)

    def byte_for_time(self, t, duration):
        """Audio byte offset at `t` seconds, from the file's seek table (needs has_toc)."""
        toc, total = self.xing["toc"], self.xing.get("bytes") or self.total_bytes
        pct = max(0.0, min(99.999, t / float(duration) * 100.0))
        i = int(pct)
        return int((toc[i] + (toc[i + 1] - toc[i]) * (pct - i)) / 256.0 * total)

    def time_for_byte(self, b, duration):
        """Seconds into the track at audio byte offset `b` (the inverse of byte_for_time)."""
        toc, total = self.xing["toc"], self.xing.get("bytes") or self.total_bytes
        x = max(0.0, min(255.999, b / float(total) * 256.0))
        i = 0
        while i < 99 and toc[i + 1] <= x:
            i += 1
        span = toc[i + 1] - toc[i]
        return (i + ((x - toc[i]) / span if span else 0.0)) / 100.0 * duration

    async def seek_to(self, offset):
        """Restart `offset` bytes into the audio (callers derive it from the average bit rate, so it is approximate
        for variable bit rate files). A web source is asked for a byte range; a server that ignores that is read
        past instead."""
        target = self._audio_start + max(0, int(offset))
        if self._fh is not None:
            self._fh.seek(target)
        else:
            self._resp.close()
            self._resp = await self._session.get(self.source, headers={"Range": "bytes=%d-" % target})
            self._resp.raise_for_status()
            if self._resp.status != 206:
                skip = target
                while skip > 0:
                    chunk = await self._resp.content.read(min(skip, 65536))
                    if not chunk:
                        break
                    skip -= len(chunk)
        self._pending, _ = self._find_sync(await self._raw(16384))

    def limit_bytes(self, n):
        self._left = int(n)

    async def read(self, n):
        if self._left is not None:
            n = min(n, self._left)
            if n <= 0:
                return b""
        out = bytearray()
        while len(out) < n:
            if self._pending:
                take = self._pending[:n - len(out)]
                self._pending = self._pending[len(take):]
                out += take
                continue
            chunk = await self._raw(n - len(out))
            if not chunk:
                break
            out += chunk
        if self._left is not None:
            self._left -= len(out)
        return bytes(out)

    async def close(self):
        if self._resp is not None:
            self._resp.close()
        if self._session is not None:
            await self._session.close()
        if self._fh is not None:
            self._fh.close()
        self._resp = self._session = self._fh = None
