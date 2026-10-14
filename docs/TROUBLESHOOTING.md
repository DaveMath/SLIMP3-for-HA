# Troubleshooting

## The dashboard tile or the SLIMP3 integration is missing

See [DASHBOARD.md](DASHBOARD.md). In short: the app copies the integration into Home Assistant's configuration folder when
it starts (the log says `installed the SLIMP3 Home Assistant integration`); Home Assistant must be restarted once before
SLIMP3 appears under Add integration.

## The page says "Looking for your SLIMP3"

The app is running but no player has announced itself yet. The page lists any address it has heard from. If it
says "Nothing heard yet", the player is off, on another network segment, or its broadcast is not reaching Home
Assistant. After a minute and a half the page suggests setting `player_ips` in the configuration, which makes the
app contact the player directly instead of waiting for it.

## The SLIMP3 says "cannot connect to SLIMP3 server"

The player has stopped getting answers from the server.

- Is the app running? Check **Settings > Apps > SLIMP3 Player** and its log.
- Is another SLIMP3 server running, such as Lyrion Music Server? Only one can own UDP port 3483.
- Are the player and Home Assistant on the same network segment? Discovery is a broadcast and does not
  cross routers or most VLANs. Put the player's IP address in `player_ips`; the app will send it a hello
  and it should register without needing the broadcast.
- The log should show `player <mac> at <ip>` shortly after the app starts.

## Playback fails immediately, or the log says ffmpeg is missing the MP3 encoder

At startup the app logs either `ffmpeg ok: libmp3lame encoder present` or `ERROR: ffmpeg has no libmp3lame MP3
encoder...` followed by what ffmpeg itself printed. The SLIMP3 decodes MP3 only, so the encoder is required.
Open an issue with that log line. (The container build also prints the first ffmpeg version line and any MP3
encoders it finds, for the same purpose.)

## The sidebar page is empty or shows no source

- Add the DLNA URL to `dlna_servers` and restart the app.
- Open the URL in a browser: it should return an XML device description.
- Opening the app's port directly from another machine returns `403`; use the sidebar entry.

## A Plex track will not play

Plex running as a container can advertise internal addresses in stream URLs; the app rewrites them to the
address you configured. If playback still fails, check that the Plex host and port 32469 are reachable
from Home Assistant, and look for an ffmpeg error in the app log.

## One particular MP3 will not play, or sounds wrong

MP3 files are sent to the SLIMP3 untouched. If one misbehaves (for example a very high bit rate file), set
`mp3_passthrough: false` to convert everything to 128 kbps with ffmpeg, and open an issue with the file's bit rate.

## Music plays but stutters or restarts

The log shows `buffer underrun, rebuffering` when the player's buffer runs dry. Usual causes are a
slow source (a remote or overloaded server) or an unreliable network path between Home Assistant and
the player. The SLIMP3 is a wired Ethernet device; keep that path clean.

## The spectrum bars are early or late

Adjust `sync_ms`: negative moves the bars earlier, positive later. Set it per player in `players`
if different rooms differ.

## The spectrum analyzer is missing

It is off by default; set `spectrum: true` (or per player). Then look at the app log at startup for `spectrum analyzer: ...`. It reports the time per frame on your
hardware, and says `unavailable (numpy missing)` or `too slow, using artist/title layout` if it switched
itself off. Live sources (TV tuners) never show the analyzer.

## The display shows garbage characters

The display ROM is not Unicode. Titles are folded to ASCII and characters that cannot be folded show as
`?`. If other characters appear, open an issue with the exact title and your player's firmware version.

## The page says a different number than I expect

For music, `Playing <title> and N more tracks` counts what is queued **after** the track you clicked, not the folder size. Live TV and radio never
show a count. The list on the page shows the first 200 entries and says so when there are more; playing can queue up to 500. If the
number of channels differs from your tuner's own lineup, compare with the tuner (for an HDHomeRun, `http://<tuner address>/lineup.json`);
the app shows what the tuner's media server offers, and a rescan on the tuner changes that list.

## I do not see the Back button, the timeline or the volume buttons

The header shows the page's version (for example `v0.11.0`). If it shows an older version, or none, the browser or Home Assistant is showing a
stale copy: reload the page (a hard reload, or close and reopen the sidebar entry; in the Home Assistant app, restart the
app after updating it). The page now tells browsers not to cache it. Also:

- **Back** appears only inside a server or folder, at the left of the library header. On the top list it is hidden because there is
  nothing to go back to. Without it you can still click a name in the breadcrumb, press Escape, or use the browser's or phone's back.
- The **timeline** is hidden until something is playing, and greyed out for live sources and tracks of unknown length.
- **Volume** is the small minus and plus pair at the right of the controls; each press is 5.

## Seeking lands in the wrong place, or does nothing

See [WEB-PAGE.md](WEB-PAGE.md#seeking-how-it-works-and-its-limits). Files without a seek table are positioned by average bit rate and can be a few seconds
off if they are variable-bit-rate; setting `mp3_passthrough: false` makes ffmpeg do the seeking, which is exact. A greyed-out scrubber means live or unknown length.

## Sleep mode does not turn the display off

Sleep mode is set in the app's **Configuration** tab (`sleep_mode`), not on the page.

The content must contain one of the `sleep_keywords` as a whole word (title, artist, album or station), the switch must be on for that player,
and the 10 second show plus 10 second countdown must have passed. See [SLEEP-MODE.md](SLEEP-MODE.md). If the display only dims, tell us: the
display has four brightness levels and this has not yet been confirmed on every unit.

## A HomePod does not show

First open the sidebar page's **Info** section and read the line for that HomePod. It says what the HomePod reports (`playing`, `paused`, ...), or
`cannot connect: <reason>`, or that HomePod support is not available in this build and why.


See [HOMEPOD.md](HOMEPOD.md). The page lists the HomePods it found. Check the log for `HomePods found:` and for
`HomePod support is not available`. The HomePod must be playing (not paused), the SLIMP3 must be idle, and the dropdown must allow
HomePods.

## Sonos does not show

- Sonos players are found automatically with a multicast search. If the log says `sonos discovery found: nothing`,
  multicast is probably blocked or the players are on another network segment: set `sonos_ips` to the address of
  any Sonos player.
- Pick the room from the Sonos dropdown on the sidebar page, or check `/api/sonos` for the exact room name
  (matching ignores case).
- A player mapped to a room mirrors the **group** that room is in, and only while the group is
  `PLAYING`. An ungrouped, stopped room shows nothing even if another room plays.
- Sonos is shown only when the SLIMP3 itself is idle.
- The top line shows the station only for radio-type sources; other sources show the room name.

## Collecting a log

The app log (Settings > Apps > SLIMP3 Player > Log) records player connections, stream starts,
underruns and Sonos changes. Include it, with your SLIMP3 firmware version, when opening an issue.
