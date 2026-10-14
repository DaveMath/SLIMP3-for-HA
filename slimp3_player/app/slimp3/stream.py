# SPDX-License-Identifier: GPL-2.0-only
# MP3 streaming to a SLIMP3's 64K x 16 circular buffer.
# Derived from Slim::Networking::SliMP3::Stream (Lyrion Music Server, GPL-2.0).
import asyncio
import time

from .protocol import mpeg_packet

BUFFER_SIZE = 131072                      # bytes
MAX_PACKET = 1400
UNPAUSE_THRESHOLD = BUFFER_SIZE // 2      # fullness needed to start decoding
BUFFER_FULL_THRESHOLD = BUFFER_SIZE - MAX_PACKET * 2
WPTR_LIMIT = BUFFER_SIZE // 2             # buffer addresses are 16-bit words
SEQ_LIMIT = WPTR_LIMIT
TIMEOUT = 0.05                            # retransmit timeout (s)
ACK_TIMEOUT = 30.0
FULL_DELAY = 0.05
BYTES_PER_SEC = 16000.0                   # 128 kbps CBR output

# control byte per stream state: 0 = decode, 1 = stop (keep rptr), 3 = stop + reset rptr
CONTROL = {"stop": 3, "buffering": 3, "paused": 1, "rebuffer": 1, "play": 0, "eof": 0}


class Stream:
    def __init__(self, loop, send, read, log=None):
        self.loop, self._tx, self._read = loop, send, read
        self.log = log or (lambda m: None)
        self.on_started = self.on_end = self.on_dead = None
        self.state = "stop"
        self.seq = 1
        self.bytes_per_sec = BYTES_PER_SEC     # set from the MP3 bit rate for pass-through streams
        self.gen = 0
        self._t_retx = self._t_next = None
        self._reset()

    # ---- public API -------------------------------------------------
    def start(self, paused=False):
        self._reset()
        self.state = "paused" if paused else "buffering"
        self.log("stream start (%s)" % self.state)
        self._kick()

    def pause(self):
        if self.state in ("play", "buffering", "rebuffer"):
            self.state = "paused"
            self._send_empty()

    def resume(self):
        if self.state == "paused":
            self.state = "play"
            self.sent_underrun = False
            self._send_empty()

    def stop(self):
        """Close the stream for good: one best-effort halt packet, then silence.
        (A stopped stream must never keep retransmitting into the next track.)"""
        self.state = "stop"
        self.closed = True
        self.gen += 1
        self._cancel()
        self.data_inflight = self.empty_inflight = None
        self.fullness = 0
        self.on_started = self.on_end = self.on_dead = None
        self._tx(mpeg_packet(CONTROL["stop"], self.cur_wptr, self.seq, b""))   # halt + reset rptr
        self.seq = (self.seq + 1) % SEQ_LIMIT

    def position(self):
        """Seconds of audio the decoder has consumed (interpolated between acks)."""
        pos = self.played_bytes / self.bytes_per_sec
        if self.state in ("play", "eof"):
            pos += min(time.time() - self.played_t, 0.25)
        return pos

    # ---- internals --------------------------------------------------
    def _reset(self):
        self.gen += 1
        self._cancel()
        self.cur_wptr = self.bytes_sent = self.fullness = 0
        self.data_inflight = self.empty_inflight = None
        self.last_byte = b""
        self.sent_underrun = False
        self.last_ack = time.time()
        self._sending = False
        self.closed = False
        self._rptr_last = 0
        self._rptr_wraps = 0
        self.played_bytes = 0
        self.played_t = time.time()

    def _cancel(self):
        for h in (self._t_retx, self._t_next):
            if h:
                h.cancel()
        self._t_retx = self._t_next = None

    def _later(self, delay, fn):
        if self._t_next:
            self._t_next.cancel()
        self._t_next = self.loop.call_later(delay, fn)

    def _kick(self):
        if not self.closed:
            asyncio.ensure_future(self._send_next())

    async def _send_next(self):
        if self._sending:
            return
        self._sending = True
        gen = self.gen
        try:
            if self._t_next:
                self._t_next.cancel()
                self._t_next = None
            if self.data_inflight or self.empty_inflight:
                self._later(FULL_DELAY, self._kick)
                return
            if self.state == "stop":
                self._send_empty()
                return
            if self.fullness > BUFFER_FULL_THRESHOLD:
                self._later(FULL_DELAY, self._send_empty)
                return
            if self.state == "eof":
                self._later(FULL_DELAY, self._send_empty)    # poll for underrun
                return
            size = MAX_PACKET
            remaining = BUFFER_SIZE - self.cur_wptr * 2      # do not run past buffer end
            if remaining and size > remaining:
                size = remaining
            if self.last_byte:
                size -= 1
            chunk = await self._read(size)
            if gen != self.gen:
                return
            if not chunk:
                self.log("source exhausted, playing out")
                self.state = "eof"
            chunk = self.last_byte + chunk
            self.last_byte = b""
            if len(chunk) % 2:
                self.last_byte, chunk = chunk[-1:], chunk[:-1]
            self._send_pkt(chunk)
        finally:
            self._sending = False

    def _send_empty(self):
        if self.data_inflight or self.empty_inflight:
            return
        self._send_pkt(b"")

    def _send_pkt(self, chunk):
        pkt = {"wptr": self.cur_wptr, "len": len(chunk), "chunk": chunk, "seq": self.seq}
        self.cur_wptr = (self.cur_wptr + len(chunk) // 2) % WPTR_LIMIT
        self.seq = (self.seq + 1) % SEQ_LIMIT
        self._transmit(pkt, resend=False)

    def _transmit(self, pkt, resend):
        control = CONTROL[self.state]
        if self.bytes_sent == 0 and not resend:
            control = 3
        self._tx(mpeg_packet(control, pkt["wptr"], pkt["seq"], pkt["chunk"]))
        if pkt["len"]:
            self.data_inflight = pkt
            if not resend:
                self.bytes_sent += pkt["len"]
        else:
            self.empty_inflight = pkt
        if self._t_retx:
            self._t_retx.cancel()
        self._t_retx = self.loop.call_later(TIMEOUT, self._timeout)

    def _timeout(self):
        self._t_retx = None
        if self.closed:
            return
        pkt = self.data_inflight or self.empty_inflight
        if not pkt:
            return
        if self.last_ack + ACK_TIMEOUT < time.time():
            self.log("no ack for %ds, giving up" % ACK_TIMEOUT)
            self.data_inflight = self.empty_inflight = None
            self.state = "stop"
            if self.on_dead:
                self.on_dead()
            return
        self.data_inflight = self.empty_inflight = None
        self._transmit(pkt, resend=True)

    def on_ack(self, wptr, rptr, seq):
        if self.closed:
            return
        if self.state == "stop" and not (self.data_inflight or self.empty_inflight):
            return
        pkt = None
        if self.data_inflight and self.data_inflight["seq"] == seq:
            pkt, self.data_inflight = self.data_inflight, None
        elif self.empty_inflight and self.empty_inflight["seq"] == seq:
            pkt, self.empty_inflight = self.empty_inflight, None
        self.fullness = ((self.cur_wptr - rptr + WPTR_LIMIT) % WPTR_LIMIT) * 2
        if rptr - self._rptr_last < -WPTR_LIMIT // 2:
            self._rptr_wraps += 1
        self._rptr_last = rptr
        self.played_bytes = (self._rptr_wraps * WPTR_LIMIT + rptr) * 2
        self.played_t = time.time()
        if pkt:
            if self._t_retx:
                self._t_retx.cancel()
                self._t_retx = None
            self.last_ack = time.time()
        st = self.state
        if self.fullness <= 512 and not self.sent_underrun and st in ("play", "eof"):
            self.sent_underrun = True
            if st == "eof":
                self.log("track finished")
                self.state = "stop"
                self._send_empty()
                if self.on_end:
                    self.on_end()
                return
            self.log("buffer underrun, rebuffering")
            self.state = "rebuffer"
        elif self.fullness > UNPAUSE_THRESHOLD:
            if st == "buffering":
                self.state = "play"
                self.log("buffer %d bytes, decoder started" % self.fullness)
                if self.on_started:
                    self.on_started()
            elif st == "rebuffer":
                self.state = "play"
                self.sent_underrun = False
        if self.state != "stop":
            self._kick()
