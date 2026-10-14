# SPDX-License-Identifier: GPL-2.0-only
# SLIMP3 UDP packet builders and parsers.
# Reference: https://lyrion.org/reference/slimp3-protocol/
import struct

PORT = 3483
LINE_LEN = 40


def discovery_reply(port=PORT):
    return b"D\x00" + bytes(4) + struct.pack(">H", port) + bytes(10)


def hello():
    return b"h" + bytes(17)


def mpeg_packet(control, wptr, seq, chunk):
    # 'm', control, 4 pad, wptr(2), 2 pad, seq(2), 6 pad = 18-byte header
    return struct.pack(">cBxxxxHxxHxxxxxx", b"m", control, wptr, seq) + chunk


def i2c_packet(data):
    return b"2" + b" " * 17 + data


def parse_ack(data):
    wptr, rptr, seq = struct.unpack_from(">HHH", data, 6)
    return wptr, rptr, seq


def mac_of(data):
    return ":".join("%02x" % b for b in data[12:18])


def display_packet(line1, line2, brightness=0x00, custom=None):
    """Mirrors Slim::Display::Lib::TextVFD::vfdUpdate (noritake path).
    custom: optional list of (code 0-7, [8 row bitmasks]) written to display CGRAM first."""
    cmd = lambda v: b"\x02" + bytes([v])
    chars = lambda t: b"".join(b"\x03" + bytes([ord(c) & 0xFF])
                               for c in t.ljust(LINE_LEN)[:LINE_LEN])
    data = cmd(0x33) + cmd(0x00) + cmd(0x30) + b"\x03" + bytes([brightness])
    for code, rows in (custom or []):
        data += cmd(0x40 + code * 8) + b"".join(b"\x03" + bytes([r & 0x1F]) for r in rows)
    data += cmd(0x06) + cmd(0x02) + cmd(0x0C)
    data += chars(line1) + cmd(0xC0) + chars(line2)
    return b"l" + b" " * 17 + data
