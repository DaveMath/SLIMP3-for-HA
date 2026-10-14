# How it works

## Architecture

```
 Plex / DLNA server --HTTP--> ffmpeg --MP3 128k CBR--> stream engine --UDP 3483--> SLIMP3
        (ContentDirectory)       |                          ^   acks + read pointer    |
                                 |                          +--------------------------+
                                 +--> ffmpeg (PCM) --> FFT --> spectrum (by playback position)
 Sonos (UPnP :1400) --> Sonos monitor --> display text, when the SLIMP3 is idle
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
| `slimp3/spectrum.py` | FFT analysis of the track being played |
| `slimp3/upnp.py` | DLNA/UPnP ContentDirectory client |
| `slimp3/sonos.py` | Read-only Sonos monitor |
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

The spectrum analyzer draws bars with the display's **custom characters**. A character cell is 5x7
dots, so a bar has 7 heights; the 7 bar shapes are written into the display's character memory and
resent every 20 seconds in case the memory is lost. A frame with the custom characters is 320 bytes, below the 500
byte limit slimserver enforces.

Text rules: a title that fits in 40 characters is centered and still; a longer one scrolls continuously
with a separator between repeats. In the spectrum screen, the top line alternates artist and title,
holding each for about three seconds (scrolling if long).

## Boot screens

A new player is created when its first hello arrives. A player that is already known and sends a
discovery broadcast again has restarted. Either event starts the boot sequence (see
[CONFIGURATION.md](CONFIGURATION.md#boot-screens-seeing-each-players-ip-and-mac)): a small task that
writes a few screens to the display, with prompts chosen from the live configuration, then hands the
display back. Starting playback or another connect within 20 seconds cancels or suppresses it. The Sonos
display waits until the sequence has finished.

## Footprint

Measured on a Mac against a simulated SLIMP3 (not on Home Assistant hardware), streaming the same Plex MP3
for 40 seconds of audio: pass-through used about **0.5 s of CPU** (13 ms per audio second) even though it sent
twice as many bytes (the file is 261 kbps against the 128 kbps re-encode), and the ffmpeg path used about
**1.1 s** (0.43 s in the app plus 0.64 s in ffmpeg). The simulated device runs inside the same process for both,
so the app's own share is smaller than these numbers. Idle, the app does nothing but answer the player's
10-second hello. While mirroring Sonos it sends no audio and one display packet when the text changes.

## The spectrum analyzer (optional, off by default)

The analyzer must show the audio **the player is playing now**, but the player buffers up to about
eight seconds ahead of the audio you hear. So the app does not analyze what it just sent:

1. A second ffmpeg decodes the same source to 22.05 kHz mono PCM into memory (capped at 15 minutes).
2. The app tracks **playback position** from the acknowledgements: the read pointer counts the bytes
   the decoder has consumed, and at 128 kbps that is exactly 16,000 bytes per second.
3. At each display frame it takes 1024 samples around that position, applies a Hann window and an FFT,
   groups the result into **40 logarithmic bands from 60 Hz to 10 kHz**, adds a +3 dB/octave tilt so treble
   is visible, and scales to 7 levels with a slow automatic gain and a gentle fall-off.

Because position comes from the player itself, the bars follow what you hear rather than what was
sent. `sync_ms` trims any remaining offset (decoder and output delays are not measured). The analysis
assumes the 128 kbps CBR stream described above.

numpy is imported only when the analyzer is switched on. With it off, the display shows artist and title.
When it is on, at startup the app times the analyzer on its own host and logs the result
(`spectrum analyzer: x ms per frame`). If a
frame would take more than half of a display frame period, or numpy is missing, it switches to the
artist/title layout by itself. Live sources (a TV tuner) always skip the analyzer, because it reads the
source separately from the audio sent to the player.

## Sources and the queue

`slimp3/upnp.py` speaks UPnP ContentDirectory (SOAP `Browse`) to a DLNA server. Plex's DLNA server is
reachable on port 32469. Two details:

- **Internal addresses.** Servers running in containers can advertise container-internal addresses
  in stream URLs (Plex on Home Assistant advertised `172.30.x.x`). The app rewrites any host that
  differs from the one it connected to, keeping the port.
- **Queues.** Playing a track queues the rest of its container; the queue advances on track end, and
  next, previous, pause, resume and volume are available. Each player has its own queue.

## Sonos

The monitor is **read-only**: it never sends a play, pause or volume command.

- It asks any configured Sonos player for the household topology (UPnP `ZoneGroupTopology` on port 1400).
  That lists every group, its coordinator and its rooms. Invisible members (such as bonded subs and
  surrounds) are left out.
- For each group coordinator it reads the transport state every 3 seconds. Only if the group is
  playing does it also read the current media and track metadata (`AVTransport`). It polls only while
  some SLIMP3 is idle and wants to show Sonos; otherwise it sleeps.
- The **station** line comes from the current item's title when its class is a radio broadcast, for
  example `CH 55 - SiriusXM Chill`. **Artist and title** come from the track metadata, or from the
  stream-content string some radio sources use.
- A player is attached to a **room**; the room's group coordinator is what knows what is playing.

**There is no Sonos spectrum.** The Sonos network interface provides control and metadata, not the
audio, and streaming-service audio goes from the service to the Sonos player directly. A live
spectrum would need the audio signal itself, for example from a Sonos line-out into a USB audio-capture
input on the Home Assistant host. That is not implemented.

## Security

- The HTTP API and sidebar page accept connections only from Home Assistant's internal network.
- The app runs on the **host network**, which Home Assistant requires for the SLIMP3's broadcast
  discovery. Home Assistant lowers an app's security rating for that.
- The SLIMP3 UDP protocol has no authentication. Anything on the same network segment can send packets
  to the app's UDP port, as it could to the original server.
- The app stores no credentials. It reads from Sonos and DLNA servers and never writes to them.

## Origin

The protocol handling, display encoding, decoder initialization and the streaming algorithm are
derived from Lyrion Music Server (slimserver, GPL-2.0), so this project is licensed GPL-2.0-only.
