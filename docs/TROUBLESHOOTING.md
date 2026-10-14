# Troubleshooting

## The page says "Looking for your SLIMP3"

The app is running but no player has announced itself yet. The page lists any address it has heard from. If it says "Nothing heard yet", the player is off, on another network segment, or its broadcast is not reaching Home Assistant. After a minute and a half the page suggests setting `player_ips` in the configuration, which makes the app contact the player directly.

## The SLIMP3 says "cannot connect to SLIMP3 server"

The player has stopped getting answers from the server.

- Is the app running? Check **Settings > Apps > SLIMP3 Player** and its log.
- Is another SLIMP3 server, such as Lyrion Music Server, running? Only one can own UDP port 3483.
- Are the player and Home Assistant on the same network segment? Discovery is a broadcast and does not cross routers or most VLANs. Put the player's address in `player_ips`.
- The log should show `player <mac> at <ip>` shortly after the app starts.

## Playback fails immediately, or the log says ffmpeg is missing the MP3 encoder

At start-up the app logs either `ffmpeg ok: libmp3lame encoder present` or `ERROR: ffmpeg has no libmp3lame MP3 encoder...` followed by what ffmpeg printed. The SLIMP3 decodes MP3 only, so the encoder is required. Open an issue with that log line.

## The library is empty or shows no server

- Open **Info**: DLNA servers on your network are listed there with an Add button. Or add one by address.
- To write one into the configuration, use `dlna_servers`, and open the URL in a browser first: it should return an XML device description.
- Opening the app's port directly from another machine returns `403`; use the sidebar entry.

## A Plex track will not play

Plex running as a container can advertise internal addresses in stream URLs; the app rewrites them to the address it connected to. If playback still fails, check that the Plex host and port 32469 are reachable from Home Assistant, and look for an ffmpeg error in the app log.

## One particular MP3 will not play, or sounds wrong

MP3 files are sent to the SLIMP3 untouched. If one misbehaves (for example a very high bit rate file), set `mp3_passthrough: false` to convert everything to 128 kbps with ffmpeg, and open an issue with the file's bit rate.

## Music plays but stutters or restarts

The log shows `buffer underrun, rebuffering` when the player's buffer runs dry. Usual causes are a slow source (a remote or overloaded server) or an unreliable network path between Home Assistant and the player. The SLIMP3 is a wired Ethernet device; keep that path clean.

## The waveform is early or late, or missing

- Adjust `sync_ms` (the waveform delay): negative moves the bars earlier, positive later. Set it per player in `players` if rooms differ.
- Missing: check that `spectrum` is not `false` (for that player or globally), and read the `spectrum analyzer: ...` line in the app log. It reports the time per frame on your hardware, and says `unavailable (numpy missing)` or `too slow, using artist/title layout` if it switched itself off. Live sources (TV tuners) never show the waveform.

## The display shows garbage characters

The display ROM is not Unicode. Titles are folded to ASCII and characters that cannot be folded show as `?`. If other characters appear, open an issue with the exact title and your player's firmware version.

## The page says a different number than I expect

For music, `Playing <title> and N more tracks` counts what is queued **after** the track you clicked, not the folder size. Live TV and radio never show a count. The list shows the first 200 entries and says so when there are more; playing can queue up to 500. If the number of channels differs from your tuner's own lineup, compare with the tuner (for an HDHomeRun, `http://<tuner address>/lineup.json`); a rescan on the tuner changes the list.

## I do not see the Back button, the timeline or the volume buttons

The header shows the page's version (for example `v0.12.0`). If it shows an older version or none, the browser or Home Assistant is showing a stale copy: reload the page, or close and reopen the sidebar entry (after updating the app, restart it).

- **Back** appears only inside a server or folder, at the left of the library header. Elsewhere you can click a breadcrumb name, press Escape, or use the browser's or phone's back.
- The **timeline** is hidden until something is playing, and greyed out for live sources and tracks of unknown length.
- **Volume** is the small minus and plus pair at the right of the controls; each press is 5.

## Seeking lands in the wrong place, or does nothing

See [WEB-PAGE.md](WEB-PAGE.md#seeking). Files without a seek table are positioned by average bit rate and can be a few seconds off if they are variable-bit-rate; `mp3_passthrough: false` makes ffmpeg do the seeking, which is exact. A greyed-out scrubber means live or unknown length.

## Sleep mode does not turn the display off

Sleep mode is set on the app's Configuration tab (`sleep_mode`, or `sleep_mode` in that player's `players` entry). The content must contain one of the `sleep_keywords` as a whole word (title, artist, album or station), and the 10 second show plus 10 second countdown must have passed. See [SLEEP-MODE.md](SLEEP-MODE.md). If a HomePod or other speaker is the source, it must be reporting `playing`: check its line on the Info page.

## A Sonos, HomePod or Google Cast speaker does not show

See the troubleshooting list in [SPEAKERS.md](SPEAKERS.md#troubleshooting).

## The dashboard tile or the SLIMP3 integration is missing

See [DASHBOARD.md](DASHBOARD.md#troubleshooting).

## Collecting a log

The app log (Settings > Apps > SLIMP3 Player > Log) records player connections, stream starts, underruns and speaker changes. Include it, with your SLIMP3 firmware version, when opening an issue.
