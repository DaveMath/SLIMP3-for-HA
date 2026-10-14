# How it works

## Architecture

```
 Plex / DLNA server --HTTP--> ffmpeg --MP3 128k CBR--> stream engine --UDP 3483--> SLIMP3
        (ContentDirectory)       |                          ^   acks + read pointer    |
                                 |                          +--------------------------+
                                 +--> ffmpeg (PCM) --> FFT --> spectrum (by playback position)
 Sonos (UPnP :1400), HomePod (AirPlay 2), Google Cast (:8009) --> read-only monitors --> display text, when the SLIMP3 is idle
 Browser / HA sidebar --ingress--> HTTP API (:8099) --> player queue and controls
```

Everything runs in one Python process inside the app container (`slimp3_player/app/`):

| Module | Role |
| --- | --- |
| `slimp3/server.py` | UDP endpoint on port 3483: discovery, hello keep-alive, acknowledgements, IR codes |
| `slimp3/protocol.py` | Packet builders and parsers, display frame encoding |
| `slimp3/stream.py` | Streaming engine: the buffer, acknowledgement and retransmit state machine |
| `slimp3/mas3507d.py` | i2c commands for the SLIMP3's MP3 decoder chip (init and volume) |
| `slimp3/player.py` | One device: ffmpeg, queue, display tasks |
| `slimp3/nowplaying.py` | The display screens and text scrolling |
| `slimp3/spectrum.py` | FFT analysis of the track being played (the waveform display) |
| `slimp3/upnp.py` | DLNA/UPnP ContentDirectory client |
| `slimp3/sonos.py`, `apple.py`, `cast.py` | Read-only Sonos, HomePod and Google Cast monitors ([SPEAKERS.md](SPEAKERS.md)) |
| `main.py`, `web/index.html` | HTTP API and the sidebar page |

## The SLIMP3 protocol

The SLIMP3 (2001) has no operating system to speak of. It speaks a small UDP protocol and the server
drives its hardware directly: the display, the decoder chip and the audio buffer. The reference is
[the Lyrion protocol page](https://lyrion.org/reference/slimp3-protocol/); the behavior of real
firmware was checked against a SLIMP3 running firmware 2.2.

- **Port.** Firmware 1.3 and later use UDP 3483. (Firmware 1.2 and earlier used 1069, which this app
  does not support.)
- **Discovery.** The player broadcasts a `d` packet; the app answers with a `D` packet whose server
  address is `0.0.0.0` (meaning "use the address this packet came from") and a hello. The player replies
  with `h` carrying its MAC address and firmware version. The app sends a hello every 10 seconds to keep
  the player attached, and every 3 seconds while no player is known. If the app stops answering, the
  player shows its own "cannot connect to SLIMP3 server" message.
- **Identity.** Players are identified by the MAC address in the hello packet. (The discovery packet
  carries zeros there on firmware 2.2.)
- **Header.** Every packet starts with an 18-byte header whose first byte is the packet type.

## Streaming audio

**Why the app is needed at all.** The SLIMP3 contains an MP3 decoder chip, but no network file client and
no file system. It cannot fetch a URL or read a share; it only accepts audio bytes pushed into its buffer
over UDP. The app is therefore a *feeder*, not a player. Slimserver is built the same way: its
`convert.conf` says "SliMP3 supports only MP3", the rule `mp3 mp3 * *` is a plain pass-through (`-`), and only
other formats are converted.

- **MP3 sources (the normal case):** the bytes are read from the source (an HTTP URL or a file) and sent
  to the player **unchanged**. Only a leading ID3v2 tag is skipped so the decoder starts on a real audio
  frame. No ffmpeg process is started and no audio is decoded. The average bit rate is taken from the
  file size and the DLNA duration (the first frame's bit rate is unreliable for VBR files, whose Xing header
  frame reports a low rate); it only matters for position tracking.
- **Everything else (FLAC, AAC, ...) and live TV:** ffmpeg converts to 44.1 kHz stereo, 128 kbps CBR MP3 with
  no tags and no Xing header, and the bytes are fed the same way.
- `mp3_passthrough: false` forces the ffmpeg path for everything.

The player has a **128 KB circular buffer**, addressed in 16-bit words (64K words). The server pushes
data into it and the player reports how much it has consumed:

1. The server sends `m` packets of up to **1400 bytes** (an even number of bytes), each with a buffer
   address (the write pointer) and a 16-bit sequence number.
2. The player acknowledges every packet with an `a` packet containing the buffer read pointer.
3. Only **one data packet is in flight** at a time. If an acknowledgement does not arrive within
   **50 ms** the packet is resent. After **30 seconds** without any acknowledgement the app gives up.
4. Each packet carries a control byte: `3` stops the decoder and resets the read pointer (used while
   buffering), `1` stops without resetting (pause), `0` decodes.
5. Playback starts when the buffer holds **64 KB**. When the buffer is nearly full (within two packets of
   128 KB) the server sends empty packets to poll the read pointer instead of data.
6. If the buffer drains to 512 bytes mid-track, the app pauses the decoder and rebuffers. If the source
   has ended, that is the end of the track and the queue advances.

When a stream is stopped it sends one halt packet and then goes silent. Stopped streams must never keep
retransmitting, otherwise they would interrupt the next track.

Before each track the app writes the decoder's configuration over i2c (config, PLL offsets, PLL
set) and sets the volume. Volume uses a squared curve: the decoder gain is `0x80000 x (volume/100)^2`.

## The display

The SLIMP3's vacuum-fluorescent display is **2 lines of 40 characters**. A display update is one `l`
packet: a short init sequence (leave 4-bit mode, set brightness, increment mode, cursor home, display
on) followed by 40 characters for line 1, a cursor jump to line 2, and 40 more characters. The display's
character ROM is not Unicode, so text is folded to plain ASCII first.

The waveform display draws bars with the display's **custom characters**. A character cell is 5x7
dots, so a bar has 7 heights; the 7 bar shapes are written into the display's character memory and
resent every 20 seconds in case the memory is lost. A frame with the custom characters is 320 bytes, below the 500
byte limit slimserver enforces.

Text rules: a title that fits in 40 characters is centered and still; a longer one scrolls continuously
with a separator between repeats. In the waveform screen, the top line alternates artist and title,
holding each for about three seconds (scrolling if long).

## Every display screen

The SLIMP3 shows two lines of 40 characters. Text that fits is centered and still; longer text scrolls. The goal is that
no screen is blank or just says "Now playing": when something is not known, the line says where it comes from.

| When | Line 1 | Line 2 |
| --- | --- | --- |
| Player connects or restarts | `Connected to Home Assistant`, then `IP <address>` | `SLIMP3-for-HA`, then `MAC <address>` |
| Setup prompts (see Boot screens) | the prompt, for example `Optional: name this player` | what to do, for example `App Configuration > players` |
| Idle | `SLIMP3 server ready` | the player's name and address |
| Starting a track | `Buffering from <server>` (or `Buffering...`) | the title |
| Playing, artist known | the artist | the title |
| Playing, no artist | the album, else `<server> - Live TV` / `<server> - Live radio`, else the server name | the title (a channel name, a file name) |
| Playing, waveform on | alternates the line above and the title | a 40-band spectrum |
| Paused or rebuffering | `Paused - ` or `Buffering - ` in front of line 1 | unchanged |
| Stopped | `Stopped` | the last title, else `Pick music in Home Assistant` |
| Queue finished | `Queue finished` | `Pick more music in Home Assistant` |
| A Sonos room, HomePod or Cast speaker playing, SLIMP3 idle | see [SPEAKERS.md](SPEAKERS.md) | |
| Sleep sounds, sleep mode on | the normal screen for 10 s, then `Going to sleep` / `Screen off in 10`, then dark | see [SLEEP-MODE.md](SLEEP-MODE.md) |

`<server>` is a short name for the music server (`HDHomeRun` for `HDHomeRun DMS 1069CDD7`, `Plex` for
`Plex Media Server: HAPi5`). The sidebar page and the Home Assistant media player show the same information: the
page's player card shows the server next to "Now playing" and "Live TV from HDHomeRun" when there is no artist; the media player uses the
server name as the artist and the app name, and the type `channel` for live sources.

## Seeking

The web page's timeline restarts the current queue item at a time offset (`POST /api/control` with `action: seek`). The stream engine
is not rewound; the player closes the current stream and opens the same item again at that point, then the display and the buffer
carry on as for any new track.

- **MP3 pass-through.** The file's Xing/Info header, when present, holds a 100 entry table mapping each percent of the duration to a
  byte position. The app looks the time up in it, asks the server for a byte range from there (`Range: bytes=N-`), skips to the next
  valid MPEG frame header, and reports the position back through the same table so the timeline matches the sound. Without a table,
  the byte is the time times the average rate (file size over duration), exact for constant bit rate only. A server that ignores
  `Range` is read and discarded up to the position.
- **ffmpeg path.** `-ss` before the input.
- **Spectrum analyzer.** Its decoder starts at the same offset.
- **Measured** on a 188 second Plex file with a seek table: restarts landed between 0.1 and 0.8 seconds from the request (measured by
  adding up every frame's real duration). With the average-rate method on the same file the error was up to 1.4 seconds, and an
  earlier version that read the wrong first-frame bit rate was off by up to 8 seconds.
- **Not seekable:** live sources and items with no known length (`seekable` is false in the API and the scrubber is disabled).

## Boot screens

A new player is created when its first hello arrives. A player that is already known and sends a discovery broadcast again has restarted. Either event starts the boot sequence (see [CONFIGURATION.md](CONFIGURATION.md#boot-screens-seeing-each-players-ip-and-mac)): a small task writes a few screens to the display, with prompts chosen from the live configuration, then hands the display back. Starting playback, or another connect within 20 seconds, cancels or suppresses it. The speaker display waits until the sequence has finished.

## Footprint

The app needs very little CPU. Measured on a Mac with Apple silicon (Python 3.13; the idle and waveform rows on an M2 Max) against a simulated SLIMP3, a real Plex server and a real Sonos system. The figures are shares of one core:

| Situation | Network | CPU |
| --- | --- | --- |
| Idle, player attached (one hello every 10 s), with Cast and the other monitors idle | negligible | 0.0% (about 56 MB resident) |
| Mirroring Sonos in one room | 1.7 KB/s (3 HTTP calls every 3 s) | 0.11% |
| Mirroring Sonos, any room (all groups polled) | 3.1 KB/s | 0.26% |
| MP3 pass-through at 261 kbps | to the player about 33 KB/s plus 27 acks/s and about 4 empty polls/s | 0.53% (includes the simulated player) |
| Waveform display on, 8 frames/s | none extra | about 1.0%, plus under 1 s of ffmpeg CPU once per 4-5 minute track |
| Converting with ffmpeg (non-MP3, TV) | as above, at 128 kbps | about 2.7% |

- **On a Raspberry Pi 5.** One Pi 5 core is several times slower than an M2 Max core, so expect a few percent of one core while the waveform runs and well under 1% otherwise. The waveform times itself at start-up and drops to the artist/title layout if the host is too slow (see below), so a slow host cannot be overloaded by it.
- **Download side.** The source is read over HTTP. If the media server runs on the same host (Plex as a Home Assistant app), that traffic never reaches the LAN.
- **Memory.** The Python process measured 22 to 56 MB. The waveform holds the decoded track in memory (22.05 kHz mono, capped at 15 minutes, about 40 MB at the cap).
- **Disk.** The container image is about 218 MiB installed, mostly ffmpeg and its libraries.
- **Speakers.** Two HomePods connected cost about 0.10% of a core and 5 MB; with a Cast connection open the idle figure above still rounds to 0.0% ([SPEAKERS.md](SPEAKERS.md)). Connections exist only while an idle SLIMP3 wants them.
- Sonos is polled, not event-driven, and the engine polls a full player buffer about 4 times a second.

## The waveform display

Music from a media server shows a live 40-band spectrum analyzer on the bottom line (the `spectrum` option, on by default; the `sync_ms` option is the **waveform delay**, default 2 ms). It must show the audio **the player is playing now**, but the player buffers up to about eight seconds ahead of what you hear. So the app does not analyze what it just sent:

1. A second ffmpeg decodes the same source to 22.05 kHz mono PCM into memory (capped at 15 minutes).
2. The app tracks **playback position** from the acknowledgements: the read pointer counts the bytes the decoder has consumed, and at 128 kbps that is exactly 16,000 bytes per second.
3. At each display frame it takes 1024 samples around that position, applies a Hann window and an FFT, groups the result into **40 logarithmic bands from 60 Hz to 10 kHz**, adds a +3 dB/octave tilt so treble is visible, and scales to 7 levels with a slow automatic gain and a gentle fall-off.

Because position comes from the player itself, the bars follow what you hear rather than what was sent. The delay option trims any remaining offset. At start-up the app times the analyzer on its own host and logs the result (`spectrum analyzer: x ms per frame`); if a frame would take more than half of a display frame period, or numpy is missing, it switches to the artist/title layout by itself. Live sources (a TV tuner) always skip the analyzer, because it reads the source separately from the audio sent to the player.

## Sleep mode

See [SLEEP-MODE.md](SLEEP-MODE.md).

## Network discovery

Sonos players and DLNA servers are found with an SSDP (multicast) search; HomePods and Cast devices with mDNS (Bonjour). On a host with several network
interfaces (wired, Wi-Fi, container bridges) a single search may leave by the wrong one, so on Linux the search
is sent on the default route and again on each interface address. The DLNA server search also tries Plex's DLNA
port on the host the app runs on, because a Plex running as a Home Assistant app does not answer the network
search.

## Sources and the queue

`slimp3/upnp.py` speaks UPnP ContentDirectory (SOAP `Browse`) to a DLNA server. Plex's DLNA server is
reachable on port 32469. Two details:

- **Internal addresses.** Servers running in containers can advertise container-internal addresses
  in stream URLs (Plex on Home Assistant advertised `172.30.x.x`). The app rewrites any host that
  differs from the one it connected to, keeping the port.
- **Queues.** Playing a track queues the rest of its container; the queue advances on track end, and
  next, previous, pause, resume and volume are available. Each player has its own queue.

## Speakers

Sonos, HomePod and Google Cast speakers are read by three small monitors that connect only while an idle SLIMP3 wants them. They never send a playback command. See [SPEAKERS.md](SPEAKERS.md).

## Security

- The HTTP API and sidebar page accept connections only from Home Assistant's internal network.
- The app runs on the **host network**, which Home Assistant requires for the SLIMP3's broadcast
  discovery. Home Assistant lowers an app's security rating for that.
- The SLIMP3 UDP protocol has no authentication. Anything on the same network segment can send packets
  to the app's UDP port, as it could to the original server.
- The app stores no credentials and has no login dependencies. It reads from Sonos, HomePod, Google Cast and DLNA servers and never writes to them.

## Origin

The protocol handling, display encoding, decoder initialization and the streaming algorithm are
derived from Lyrion Music Server (slimserver, GPL-2.0), so this project is licensed GPL-2.0-only.
