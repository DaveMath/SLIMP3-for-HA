# SPDX-License-Identifier: GPL-2.0-only
"""Now-playing screen: top line alternates artist / title (scrolling if too long),
bottom line is a 40-band spectrum analyzer drawn with custom VFD characters."""
import asyncio
import time
import unicodedata

from .protocol import LINE_LEN, display_packet
BANDS = 40      # analyzer bands (one per display column)
LEVELS = 7      # bar heights a 5x7 character cell can show

# Character cell is 5x7 with an 8th (cursor) row. Heights 1..7 -> codes 0..6.
CUSTOM = [(h - 1, [0] * (7 - h) + [0x1F] * h + [0]) for h in range(1, LEVELS + 1)]


def vfd_safe(text):
    """Fold to plain ASCII; the unit's character ROM has no Unicode."""
    t = unicodedata.normalize("NFKD", text or "")
    return "".join(c if 32 <= ord(c) < 127 else ("" if unicodedata.combining(c) else "?")
                   for c in t)


def headline(meta):
    """The top line for what is playing. Never a bare 'Now playing' when something more useful is known:
    artist, else album, else where it comes from ('HDHomeRun - Live TV', 'Plex')."""
    if meta.get("artist"):
        return meta["artist"]
    if meta.get("album"):
        return meta["album"]
    src, kind = meta.get("source"), meta.get("kind")
    if src and kind:
        return "%s - %s" % (src, kind)
    return src or kind or "Now playing"


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
        self.animated = len(self.segs) > 1 or any(sc for _, _, sc in self.segs)
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


def state_prefix(player):
    """'Paused - ' / 'Buffering - ' while the player is not actually playing, so the screen never looks like it is."""
    stream = getattr(player, "stream", None)
    return {"paused": "Paused - ", "rebuffer": "Buffering - "}.get(getattr(stream, "state", ""), "")


class NowPlaying:
    """Spectrum layout: line 1 alternates artist/title, line 2 is the analyzer.
    Text layout (spectrum off): line 1 artist, line 2 title, each scrolls if too long."""

    def __init__(self, player, meta, spectrum, fps=8, sync_ms=0):
        self.player, self.spectrum = player, spectrum
        self.fps, self.sync = fps, sync_ms / 1000.0
        title, first = meta.get("title"), headline(meta)
        if spectrum:
            self.ticker = Ticker([t for t in (first, title) if t])
        else:
            self.t1 = Ticker([first])
            self.t2 = Ticker([title or ""])
            self.fps = min(self.fps, 4)

    async def run(self):
        t0 = time.time()
        last_custom = last_sent = 0.0
        last = None
        try:
            while True:
                now = time.time()
                custom = None
                if self.spectrum:
                    bands = self.spectrum.frame(self.player.position() - self.sync)
                    line1 = (state_prefix(self.player) + self.ticker.line(now - t0).strip())[:LINE_LEN]
                    line2 = "".join(" " if h <= 0 else chr(min(h, LEVELS) - 1) for h in bands)
                    if now - last_custom > 20:
                        custom, last_custom = CUSTOM, now
                    self.player._send(display_packet(line1, line2, custom=custom))
                    await asyncio.sleep(1.0 / self.fps)
                    continue
                # text layout: only send when something changed (or every 10 s, in case the display lost it)
                line1, line2 = self.t1.line(now - t0), self.t2.line(now - t0)
                pre = state_prefix(self.player)
                if pre:
                    line1 = (pre + line1.strip())[:LINE_LEN]
                if (line1, line2) != last or now - last_sent > 10:
                    self.player._send(display_packet(line1, line2))
                    last, last_sent = (line1, line2), now
                await asyncio.sleep(1.0 / self.fps if (self.t1.animated or self.t2.animated) else 1.0)
        except asyncio.CancelledError:
            pass


class Marquee:
    """Bottom-line text: centered and still if it fits, continuous scroll only if it is too long."""

    def __init__(self, text, width=LINE_LEN, speed=6.0, gap="   *   "):
        t = vfd_safe(text)
        self.width, self.speed = width, speed
        self.static = t.center(width) if len(t) <= width else None
        self.animated = self.static is None
        self.loop = (t + gap) if t else ""

    def line(self, t):
        if self.static is not None:
            return self.static
        n = len(self.loop)
        off = int(t * self.speed) % n
        return (self.loop * (self.width // n + 3))[off:off + self.width]


def sonos_lines(st):
    """(top, bottom) text for a Sonos group. A station, else a track, else just where it comes from, but never the
    same words on both lines:
      station + track   'CH 55 - SiriusXM Chill'  /  'Artist - Title'
      track + source    'Office: Spotify'          /  'Artist - Title'
      no track info     'Living Room'              /  'TV audio' (or 'Line-in', 'Playing')"""
    room, src, station = st.get("room") or "", st.get("source") or "", st.get("station") or ""
    track = " - ".join(x for x in (st.get("artist"), st.get("title")) if x) or st.get("album") or ""
    if station:
        return station, track or src or "Playing"
    if track:
        return ("%s: %s" % (room, src) if room and src else room or src or "Sonos"), track
    return room or "Sonos", src or "Playing"


class SonosNowPlaying:
    """Mirrors what a Sonos group is playing: station (e.g. 'CH 55 - SiriusXM Chill')
    on the top line, 'Artist - Title' on the bottom line. Text only: no audio is touched, and a frame is
    sent only when the text changes (or scrolls), so a still title costs one packet every 10 seconds."""

    def __init__(self, player, get_state, fps=4):
        self.player, self.get_state, self.fps = player, get_state, fps

    async def run(self):
        t0, key, top, bottom = time.time(), None, None, None
        last, last_sent = None, 0.0
        try:
            while True:
                st = self.get_state()
                animated = False
                if st:
                    new = (st["station"], st["room"], st["artist"], st["title"], st["album"], st.get("source"))
                    if new != key:
                        key, t0, last = new, time.time(), None
                        head, body = sonos_lines(st)
                        top, bottom = Ticker([head]), Marquee(body)
                    if top:
                        now = time.time()
                        lines = (top.line(now - t0), bottom.line(now - t0))
                        animated = top.animated or bottom.animated
                        if lines != last or now - last_sent > 10:
                            self.player._send(display_packet(*lines))
                            last, last_sent = lines, now
                await asyncio.sleep(1.0 / self.fps if animated else 1.0)
        except asyncio.CancelledError:
            pass
