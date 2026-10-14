# Troubleshooting

## The SLIMP3 says "cannot connect to SLIMP3 server"

The player has stopped getting answers from the server.

- Is the app running? Check **Settings > Apps > SLIMP3 Player** and its log.
- Is another SLIMP3 server running, such as Lyrion Music Server? Only one can own UDP port 3483.
- Are the player and Home Assistant on the same network segment? Discovery is a broadcast and does not
  cross routers or most VLANs. Put the player's IP address in `player_ips`; the app will send it a hello
  and it should register without needing the broadcast.
- The log should show `player <mac> at <ip>` shortly after the app starts.

## The app does not build

The Dockerfile checks that ffmpeg can encode MP3 and stops with `this ffmpeg build lacks the
libmp3lame encoder` if not. The SLIMP3 decodes MP3 only, so that is a hard requirement. Open an issue
with the full build log.

## The sidebar page is empty or shows no source

- Add the DLNA URL to `dlna_servers` and restart the app.
- Open the URL in a browser: it should return an XML device description.
- Opening the app's port directly from another machine returns `403`; use the sidebar entry.

## A Plex track will not play

Plex running as a container can advertise internal addresses in stream URLs; the app rewrites them to the
address you configured. If playback still fails, check that the Plex host and port 32469 are reachable
from Home Assistant, and look for an ffmpeg error in the app log.

## Music plays but stutters or restarts

The log shows `buffer underrun, rebuffering` when the player's buffer runs dry. Usual causes are a
slow source (a remote or overloaded server) or an unreliable network path between Home Assistant and
the player. The SLIMP3 is a wired Ethernet device; keep that path clean.

## The spectrum bars are early or late

Adjust `sync_ms`: negative moves the bars earlier, positive later. Set it per player in `players`
if different rooms differ.

## The spectrum analyzer is missing

Look at the app log at startup for `spectrum analyzer: ...`. It reports the time per frame on your
hardware, and says `unavailable (numpy missing)` or `too slow, using artist/title layout` if it switched
itself off. Live sources (TV tuners) never show the analyzer.

## The display shows garbage characters

The display ROM is not Unicode. Titles are folded to ASCII and characters that cannot be folded show as
`?`. If other characters appear, open an issue with the exact title and your player's firmware version.

## Sonos does not show

- Set `sonos_ips` to the address of any Sonos player.
- Open `/api/sonos` through the app and check `rooms` for the exact room name; `sonos_room` must match
  it (case does not matter).
- A player mapped to a room mirrors the **group** that room is in, and only while the group is
  `PLAYING`. An ungrouped, stopped room shows nothing even if another room plays.
- Sonos is shown only when the SLIMP3 itself is idle.
- The top line shows the station only for radio-type sources; other sources show the room name.

## Collecting a log

The app log (Settings > Apps > SLIMP3 Player > Log) records player connections, stream starts,
underruns and Sonos changes. Include it, with your SLIMP3 firmware version, when opening an issue.
