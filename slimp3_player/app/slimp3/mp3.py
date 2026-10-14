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
        for i in range(min(len(buf) - 1, 4096)):          # find the first frame sync
            if buf[i] == 0xFF and (buf[i + 1] & 0xE0) == 0xE0 and frame_bitrate(buf[i:i + 4]):
                buf = buf[i:]
                dropped += i
                break
        self.bitrate = frame_bitrate(buf[:4])
        self.total_bytes = (size - dropped) if size else None
        self._pending = buf
        return self

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
