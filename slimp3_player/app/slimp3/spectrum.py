# SPDX-License-Identifier: GPL-2.0-only
"""Spectrum analysis of the track being played, looked up by playback position."""
import asyncio

try:
    import numpy as np
except ImportError:  # analyzer is optional
    np = None

RATE = 22050
N = 1024
BANDS = 40
MAX_SECONDS = 900          # cap analysis memory (~40 MB)
LEVELS = 7                 # a 5x7 character cell gives 7 bar heights


class Spectrum:
    def __init__(self, source, ffmpeg="ffmpeg", duration=None):
        self.source, self.ffmpeg, self.duration = source, ffmpeg, duration
        self.pcm = bytearray()
        self.done = False
        self.task = None
        self.peak = -20.0
        self.prev = [0.0] * BANDS
        if np is not None:
            freqs = np.fft.rfftfreq(N, 1.0 / RATE)
            edges = np.geomspace(60, 10000, BANDS + 1)
            bw = RATE / float(N)
            self.slices = []
            for i in range(BANDS):
                lo = int(edges[i] / bw)
                hi = max(lo + 1, int(np.ceil(edges[i + 1] / bw)))
                self.slices.append((lo, hi))
            centers = np.sqrt(edges[:-1] * edges[1:])
            self.tilt = 3.0 * np.log2(centers / 1000.0)      # +3 dB/octave
            self.win = np.hanning(N)

    @property
    def available(self):
        return np is not None

    def start(self):
        if np is None:
            return
        self.task = asyncio.ensure_future(self._decode())

    async def _decode(self):
        cmd = [self.ffmpeg, "-nostdin", "-v", "error", "-i", self.source]
        if self.duration:
            cmd += ["-t", str(self.duration)]
        cmd += ["-vn", "-ac", "1", "-ar", str(RATE), "-f", "s16le", "pipe:1"]
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
        try:
            while len(self.pcm) < MAX_SECONDS * RATE * 2:
                data = await proc.stdout.read(65536)
                if not data:
                    break
                self.pcm += data
        finally:
            self.done = True
            if proc.returncode is None:
                proc.kill()

    def stop(self):
        if self.task:
            self.task.cancel()

    def frame(self, t):
        """40 integers 0..7 for playback position t (seconds)."""
        if np is None or t < 0:
            return [0] * BANDS
        start = int(t * RATE) - N // 2
        a, b = max(start, 0) * 2, (max(start, 0) + N) * 2
        if b > len(self.pcm):
            return [0] * BANDS
        x = np.frombuffer(self.pcm, dtype=np.int16, count=N, offset=a).astype(np.float32) / 32768.0
        mag = np.abs(np.fft.rfft(x * self.win)) / (N / 4.0)
        db = np.array([20 * np.log10(mag[lo:hi].max() + 1e-9) for lo, hi in self.slices])
        db = db + self.tilt
        top = float(db.max())
        self.peak = max(top, self.peak - 0.15)               # slow AGC release
        span = 42.0
        lvl = np.clip((db - (self.peak - span)) / span * LEVELS, 0, LEVELS)
        out = []
        for i in range(BANDS):
            v = max(float(lvl[i]), self.prev[i] - 0.7)        # gentle fall-off
            self.prev[i] = v
            out.append(int(round(v)))
        return out
