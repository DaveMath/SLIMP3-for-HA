# SPDX-License-Identifier: GPL-2.0-only
"""Now-playing screen: top line alternates artist / title (scrolling if too long),
bottom line is a 40-band spectrum analyzer drawn with custom VFD characters."""
import asyncio
import time
import unicodedata

from .protocol import LINE_LEN, display_packet
from .spectrum import BANDS, LEVELS

# Character cell is 5x7 with an 8th (cursor) row. Heights 1..7 -> codes 0..6.
CUSTOM = [(h - 1, [0] * (7 - h) + [0x1F] * h + [0]) for h in range(1, LEVELS + 1)]


def vfd_safe(text):
    """Fold to plain ASCII; the unit's character ROM has no Unicode."""
    t = unicodedata.normalize("NFKD", text or "")
    return "".join(c if 32 <= ord(c) < 127 else ("" if unicodedata.combining(c) else "?")
                   for c in t)


class Ticker:
    """Cycles through texts: short ones are centered and held, long ones scroll."""

    def __init__(self, texts, width=LINE_LEN, hold=3.0, edge=1.2, speed=6.0):
        self.width = width
        self.segs = []   # (duration, text, scrolls)
        for t in texts:
            t = vfd_safe(t)
            if not t:
                continue
            if len(t) <= width:
                self.segs.append((hold, t.center(width), False))
            else:
                self.segs.append((edge * 2 + (len(t) - width) / speed, t, True))
        self.speed, self.edge = speed, edge
        self.cycle = sum(s[0] for s in self.segs) or 1.0

    def line(self, t):
        if not self.segs:
            return ""
        t %= self.cycle
        for dur, text, scrolls in self.segs:
            if t < dur:
                if not scrolls:
                    return text
                off = int(max(0.0, t - self.edge) * self.speed)
                return text[min(off, len(text) - self.width):][:self.width]
            t -= dur
        return self.segs[-1][1]


class NowPlaying:
    """Spectrum layout: line 1 alternates artist/title, line 2 is the analyzer.
    Text layout (spectrum off): line 1 artist, line 2 title, each scrolls if too long."""

    def __init__(self, player, meta, spectrum, fps=8, sync_ms=0):
        self.player, self.spectrum = player, spectrum
        self.fps, self.sync = fps, sync_ms / 1000.0
        artist, title = meta.get("artist"), meta.get("title")
        if spectrum:
            self.ticker = Ticker([t for t in (artist, title) if t] or ["Now playing"])
        else:
            self.t1 = Ticker([artist or meta.get("album") or "Now playing"])
            self.t2 = Ticker([title or ""])
            self.fps = min(self.fps, 4)

    async def run(self):
        t0 = time.time()
        last_custom = 0.0
        try:
            while True:
                now = time.time()
                custom = None
                if self.spectrum:
                    bands = self.spectrum.frame(self.player.position() - self.sync)
                    line1 = self.ticker.line(now - t0)
                    line2 = "".join(" " if h <= 0 else chr(min(h, LEVELS) - 1) for h in bands)
                    if now - last_custom > 20:
                        custom, last_custom = CUSTOM, now
                else:
                    line1, line2 = self.t1.line(now - t0), self.t2.line(now - t0)
                self.player._send(display_packet(line1, line2, custom=custom))
                await asyncio.sleep(1.0 / self.fps)
        except asyncio.CancelledError:
            pass


class Marquee:
    """Always-scrolling line: the text repeats with a separator, never stops."""

    def __init__(self, text, width=LINE_LEN, speed=6.0, gap="   *   "):
        t = vfd_safe(text)
        self.width, self.speed = width, speed
        self.loop = (t + gap) if t else ""

    def line(self, t):
        if not self.loop:
            return ""
        n = len(self.loop)
        off = int(t * self.speed) % n
        return (self.loop * (self.width // n + 3))[off:off + self.width]


class SonosNowPlaying:
    """Mirrors what a Sonos group is playing: station (e.g. 'CH 55 - SiriusXM Chill')
    on the top line, 'Artist - Title' scrolling continuously on the bottom line."""

    def __init__(self, player, get_state, fps=5):
        self.player, self.get_state, self.fps = player, get_state, fps

    async def run(self):
        t0, key, top, bottom = time.time(), None, None, None
        try:
            while True:
                st = self.get_state()
                if st:
                    new = (st["station"], st["room"], st["artist"], st["title"], st["album"])
                    if new != key:
                        key, t0 = new, time.time()
                        head = st["station"] or st["room"] or "Sonos"
                        body = " - ".join(x for x in (st["artist"], st["title"]) if x) or st["album"]
                        top, bottom = Ticker([head]), Marquee(body or head)
                if top:
                    now = time.time() - t0
                    self.player._send(display_packet(top.line(now), bottom.line(now)))
                await asyncio.sleep(1.0 / self.fps)
        except asyncio.CancelledError:
            pass
