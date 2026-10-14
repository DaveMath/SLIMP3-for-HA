# Keeping polling low

The app reads what your speakers are playing without asking constantly. This page says what is asked, when, and how that was designed and checked.

## The rules

1. **Connect only when someone is looking.** Nothing connects to a speaker unless a SLIMP3 is idle and set to show that kind of speaker. Start music on the SLIMP3, or have no player waiting, and every speaker connection closes.
2. **Prefer being told over asking.** HomePod and Google Cast push their state when it changes, so the app listens. Only Sonos has to be asked.
3. **Poll only to cover a known gap.** A poll exists to catch something a push can miss, and it runs fast only when that gap matters.
4. **Slow down when nothing happens.** Rates drop when nothing has played for a while and return to full speed when something does.
5. **Confirm before acting on a stop.** A wrong "stopped" report must not blank the display, so one fresh read is made before it does.

## What runs, and how often

| Source | While it is playing | While nothing is playing | Notes |
| --- | --- | --- | --- |
| Sonos | every 3 s | every 10 s, after 60 s with nothing playing | Sonos can only be asked. One persistent connection per player, 1 request per group when idle and 3 when playing, and only for the rooms a SLIMP3 shows. |
| HomePod | push updates, plus a direct check every 10 s | push updates, plus a direct check every 60 s | The 10 s check catches a stop that was never announced. A start is announced by push. |
| Google Cast | push updates, 5 s keep-alive | push updates, 5 s keep-alive | Nothing is polled. |
| Display | the stored state is checked every 1 s | same | Local only, no network. |
| Stop confirmation | one extra read of every connected speaker, 2 s after a stop is reported | | Only if the stop is still reported at 4 s does the display go black. |

When a mirrored speaker stops, the last screen stays for 4 seconds. At 2 seconds the app reads every connected speaker once more. If any of them is playing again, the display carries on. Otherwise at about 4 seconds it goes black until something plays.

## The method

The same four steps were used each time polling was changed:

1. **Measure before changing.** Count requests, bytes and CPU per cycle in a test system, with the real Plex server and Sonos system and a simulated SLIMP3. Early measurements found two wastes: Sonos polling opened a new connection per call and polled every group (7 calls, 12.5 KB and 11.7 ms of CPU per cycle), and the streaming engine polled a full player buffer 20 times a second (19 empty polls and 43 acknowledgements per second, 1.33% CPU). Persistent connections, polling only the wanted rooms (now 3 calls, about 5 KB per cycle) and polling the buffer about 4 times a second removed them.
2. **Find who really needs to be asked.** For each source, ask whether it can tell us instead. HomePod and Cast can, Sonos cannot (Sonos event subscriptions need a callback port reachable from every player, which is more fragile than a light poll, so they are not used).
3. **Tie every poll to a reason.** A poll is kept only if it covers a named gap: a missed HomePod stop, a Sonos change, a wrong stop report. Its rate follows the gap: fast when the gap is open (something is playing or just played), slow when it is not.
4. **Test the behavior, not just the code.**
   - Cadence: the intervals were scaled down and the monitors run against stand-in devices that count requests. Sonos: 4 polls in 4 scaled seconds while idle, 15 in 3 while playing, and fast polling continues through the grace period after a stop. HomePod: 10 checks in 4 scaled seconds while playing and 2 while idle.
   - Confirmation, end to end: the real app, a simulated Cast speaker and a simulated SLIMP3 display. A speaker that reported a stop but was still playing kept the display lit, with one extra request. A speaker that had really stopped turned the display black about 4 to 5 seconds after the stop, also with one extra request.
   - Re-measure: after a change, the same counts are taken again and compared.

## What it costs

With nothing playing and no idle SLIMP3 waiting, nothing is polled and no speaker is connected. With one SLIMP3 idle: Cast costs a keep-alive every 5 seconds per device; HomePods one request a minute each; Sonos one cycle every 10 seconds. CPU figures are in [HOW-IT-WORKS.md](HOW-IT-WORKS.md#footprint).
