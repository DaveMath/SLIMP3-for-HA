# SPDX-License-Identifier: GPL-2.0-only
"""Stand-in for the 'miniaudio' package (a compiled library with no prebuilt package for the app's container).
pyatv imports it to STREAM AUDIO TO AirPlay speakers; this app never does that, it only READS what a HomePod is
playing. The names below satisfy pyatv's import; anything that would actually decode or stream audio fails loudly."""
import enum


class DecodeError(Exception):
    pass


class SeekOrigin(enum.IntEnum):
    START = 0
    CURRENT = 1


class SampleFormat(enum.IntEnum):
    UNKNOWN = 0
    UNSIGNED8 = 1
    SIGNED16 = 2
    SIGNED24 = 3
    SIGNED32 = 4
    FLOAT32 = 5


class StreamableSource:
    def read(self, num_bytes):
        raise NotImplementedError("audio streaming is not available in this app")

    def seek(self, offset, origin):
        raise NotImplementedError("audio streaming is not available in this app")


class WavFileReadStream:
    def __init__(self, *args, **kwargs):
        raise RuntimeError("audio streaming is not available in this app")


def stream_any(*args, **kwargs):
    raise RuntimeError("audio streaming is not available in this app")


def get_file_info(*args, **kwargs):
    raise RuntimeError("audio file reading is not available in this app")


def __getattr__(name):
    """Any other name pyatv mentions while importing (mostly type annotations such as DecodedSoundFile) gets a
    placeholder class, so the import succeeds. Calling into it fails, which is what we want."""
    if name.startswith("__"):
        raise AttributeError(name)
    return type(name, (), {"__init__": lambda self, *a, **k: (_ for _ in ()).throw(
        RuntimeError("audio streaming is not available in this app"))})
