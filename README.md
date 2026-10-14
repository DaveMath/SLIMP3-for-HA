# SLIMP3-for-HA

A Home Assistant app (formerly "add-on") that acts as the server for a Slim Devices **SLIMP3**
network music player. It plays music from Plex or any DLNA/UPnP media server on the SLIMP3, and it
can show what your **Sonos** system is playing on the SLIMP3's display.

This application is written through the harness [Krystalize.AI](https://krystalize.ai/) - get your Mac M series private local LLM with memory for managing all of your development processes or as a local Chief of Staff.

Written by @GGDM on Krystalize.AI local harness.

## What it does

- **Plays your library on a SLIMP3.** Browse a Plex (DLNA) library from the Home Assistant sidebar,
  play a track or a whole album, skip, pause, set volume. Audio is transcoded to the MP3 the SLIMP3's
  decoder needs and streamed over the SLIMP3's own UDP protocol.
- **Spectrum analyzer.** While the SLIMP3 plays music from this app, the display alternates
  artist and title on the top line and shows a live 40-band spectrum analyzer on the bottom line.
  It can be switched off, which shows the artist on the top line and the title on the bottom.
- **Sonos now-playing.** When the SLIMP3 is idle, it mirrors a Sonos room: the station (for example
  `CH 55 - SiriusXM Chill`) on the top line and `Artist - Title` on the bottom line. Titles that fit
  are shown still and centered; long ones scroll. Read-only: the app never controls Sonos.
- **Setup help on the player itself.** At connect or restart the SLIMP3's display shows its IP and MAC
  address and step-by-step prompts (name this player, add a music source, Sonos room not found).
- **Multi-room.** Each SLIMP3 is matched by MAC address to its own settings, including which Sonos
  room it mirrors.

## Requirements

- Home Assistant OS or Supervised (apps are not available on Container/Core installs).
- A SLIMP3 with firmware that uses UDP port 3483 (firmware 1.3 and later; developed with 2.2),
  on the same network/VLAN as Home Assistant. Discovery is by broadcast.
- A DLNA/UPnP media server for music (developed against Plex Media Server's DLNA server), and/or a
  Sonos system.

## Install

1. In Home Assistant open **Settings > Apps > App store**, open the menu (top right), choose
   **Repositories**, and add `https://github.com/DaveMath/SLIMP3-for-HA`.
2. Install **SLIMP3 Player**.
3. On its **Configuration** tab set at least `dlna_servers` (and `sonos_ips` if you use Sonos).
   See [docs/CONFIGURATION.md](docs/CONFIGURATION.md).
4. Start the app, then open **SLIMP3** in the sidebar.

The first build compiles the container on your Home Assistant machine. The build fails with a clear
message if the base image's ffmpeg lacks the MP3 encoder.

## Documentation

| Page | Contents |
| --- | --- |
| [docs/CONFIGURATION.md](docs/CONFIGURATION.md) | Every option, single-room and multi-room examples, finding MAC addresses, Sonos rooms and DLNA URLs |
| [docs/HOW-IT-WORKS.md](docs/HOW-IT-WORKS.md) | Architecture, the SLIMP3 protocol, streaming engine, display, spectrum sync, Sonos, security |
| [docs/API.md](docs/API.md) | The HTTP API behind the sidebar page |
| [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) | Common problems and fixes |

## Status

**Tested with:** one SLIMP3 (firmware 2.2); Plex Media Server 1.43.4 DLNA server running as a Home
Assistant app; a Sonos S2 system (Playbar and Connect, software 86.10) with SiriusXM. Development and
all hardware tests ran the same application code on a Mac, driving that real hardware.

**Not yet validated:** building and running the container inside Home Assistant (including whether the
spectrum analyzer's speed is acceptable on your Home Assistant hardware: the app measures this itself at
startup and falls back automatically); the boot screens' appearance on the real display (the code ran
without errors on hardware, but nobody has confirmed the screens visually); playing a TV-tuner channel end to
end on a SLIMP3; two or more SLIMP3
players at the same time; any SLIMP3 firmware other than 2.2.

**Not implemented:** SMB sources, seeking within a track, SLIMP3 remote-control button mapping (button
codes are logged), a Home Assistant `media_player` entity and dashboard card, and the legacy UDP
port 1069 used by firmware 1.2 and earlier.

**Not possible from the network:** a spectrum for Sonos audio. Sonos exposes control and metadata,
not the audio. See [docs/HOW-IT-WORKS.md](docs/HOW-IT-WORKS.md#sonos).

## License and credits

Licensed **GPL-2.0-only** (see [LICENSE](LICENSE) and [NOTICE.txt](NOTICE.txt)). The SLIMP3 protocol
handling, display encoding, decoder initialization and streaming algorithm are derived from
[Lyrion Music Server (slimserver)](https://github.com/LMS-Community/slimserver) and its
[protocol documentation](https://lyrion.org/reference/slimp3-protocol/).

Slim Devices, SLIMP3, Sonos, SiriusXM and Plex are trademarks of their respective owners. This project
is not affiliated with or endorsed by them.
