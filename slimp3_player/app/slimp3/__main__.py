# SPDX-License-Identifier: GPL-2.0-only
"""Playback test.
  python3 -m slimp3 FILE_OR_URL [--artist A --title T]
  python3 -m slimp3 --upnp http://192.168.1.10:32469/DeviceDescription.xml --object TRACK_ID
"""
import argparse
import asyncio
import time

from .server import Server
from .upnp import MediaServer


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("source", nargs="?")
    ap.add_argument("--upnp")
    ap.add_argument("--object")
    ap.add_argument("--artist", default="")
    ap.add_argument("--title", default="")
    ap.add_argument("--album", default="")
    ap.add_argument("--seed-ip", action="append", default=[])
    ap.add_argument("--volume", type=int, default=40)
    ap.add_argument("--duration", type=int, default=None)
    ap.add_argument("--fps", type=float, default=8)
    ap.add_argument("--sync-ms", type=int, default=0)
    args = ap.parse_args()
    t0 = time.time()
    log = lambda m: print("[%5.1f] %s" % (time.time() - t0, m), flush=True)

    source, title, artist, album = args.source, args.title, args.artist, args.album
    if args.upnp:
        srv = MediaServer(args.upnp).connect()
        it = srv.metadata(args.object)
        if not it or not it["url"]:
            log("object %s not found or has no stream" % args.object)
            return
        source, title, artist, album = it["url"], it["title"], it["artist"] or "", it["album"] or ""
        log("UPnP: %s - %s (%s)" % (artist, title, source))

    srv = Server(args.seed_ip, log)
    await srv.start()
    for _ in range(100):
        if srv.players:
            break
        await asyncio.sleep(0.2)
    if not srv.players:
        log("no SLIMP3 found")
        return
    p = next(iter(srv.players.values()))
    p.on_ir = lambda code: log("IR 0x%s" % code)
    p.volume, p.fps, p.sync_ms = args.volume, args.fps, args.sync_ms
    await p.play(source, title=title, artist=artist, album=album, duration=args.duration)
    try:
        await asyncio.wait_for(p.ended.wait(), (args.duration or 900) + 30)
    except asyncio.TimeoutError:
        log("timed out")
    await p.stop()
    p.show("Done", "")
    log("finished")


asyncio.run(main())
