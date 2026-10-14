# SPDX-License-Identifier: GPL-2.0-only
# i2c command builder for the MAS3507D decoder in the SLIMP3.
# Derived from Slim::Hardware::mas3507d (Lyrion Music Server, GPL-2.0).

REGS = {
    "dccf": ("r", "8e"), "mute": ("r", "aa"), "treble": ("r", "6f"),
    "bass": ("r", "6b"), "prefactor": ("r", "e7"), "piodata": ("r", "ed"),
    "config": ("r", "e6"),
    "plloffset48": ("d0", "032d"), "plloffset44": ("d0", "032e"),
    "outputconfig": ("d0", "032f"),
    "ll": ("d1", "07f8"), "lr": ("d1", "07f9"),
    "rl": ("d1", "07fa"), "rr": ("d1", "07fb"),
    "loadconfig": ("run", "0fcd"), "setpll": ("run", "0475"),
}
_HEX = "0123456789abcdefABCDEF"


def mas_write(key, data=None):
    bank, addr = REGS[key]
    a = list(reversed(addr))                       # a[0] = least significant nibble
    d = list(reversed([c for c in (data or "") if c in _HEX]))
    if bank == "r":
        toks = ["s", "3a", "68", "9" + a[1], a[0] + d[0], d[4] + d[3], d[2] + d[1], "p"]
    elif bank in ("d0", "d1"):
        first = "a0" if bank == "d0" else "b0"
        toks = ["s", "3a", "68", first, "00", "00", "01", a[3] + a[2], a[1] + a[0],
                d[3] + d[2], d[1] + d[0], "00", "0" + d[4], "p"]
    else:
        toks = ["s", "3a", "68", a[3] + a[2], a[1] + a[0], "p"]
    out = b""
    for t in toks:
        out += t.encode() if t in ("s", "p") else b"w" + bytes([int(t, 16)])
    return out


def init_sequence():
    """Sent before each new stream (see Slim::Player::SLIMP3::play)."""
    return (mas_write("config", "00002") + mas_write("loadconfig")
            + mas_write("plloffset48", "5d9e9") + mas_write("plloffset44", "cecf5")
            + mas_write("setpll"))


def volume(vol, max_vol=100):
    level = "%05X" % int(0x80000 * ((vol / float(max_vol)) ** 2))
    return mas_write("ll", level) + mas_write("rr", level)
