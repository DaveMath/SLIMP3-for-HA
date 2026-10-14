# SLIMP3-for-HA

[![Add this repository to your Home Assistant](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2FDaveMath%2FSLIMP3-for-HA)

A Home Assistant app (formerly "add-on") that brings a Slim Devices **SLIMP3** network music player back to life. It plays music from Plex or any DLNA/UPnP media server on the SLIMP3, and it shows what your **Sonos**, **HomePod** and **Google Home / Nest** speakers are playing on the SLIMP3's vacuum fluorescent display.

## Why this exists

This is free software by @GGDM, inspired by [Kevin Kelly](https://kk.org) (founding executive editor of Wired), who gave me an old SLIMP3 with its awesome vacuum fluorescent display.

This project is all about my love of hacking newly compatible interfaces on popular back-ends to devices which typically lose their legacy servers.

Built on the [Krystalize.AI](https://krystalize.ai/) local harness.

## What it does

- **Plays your library on a SLIMP3.** Browse a Plex (DLNA) library from the Home Assistant sidebar, play a track or an album, skip, pause, seek and set the volume. The SLIMP3 decodes MP3 itself, so MP3 files are sent to it **untouched** over its own UDP protocol. Other formats and live TV (for example an HDHomeRun) are converted to MP3 by ffmpeg only when needed.
- **Waveform display.** While music plays from a media server, the bottom line of the display is a live 40-band spectrum analyzer synced to what you hear, with the artist and title alternating on the top line. On by default; see [docs/HOW-IT-WORKS.md](docs/HOW-IT-WORKS.md#the-waveform-display).
- **Speaker mirroring.** When the SLIMP3 is idle it shows what a Sonos room, a HomePod or a Google Home / Nest speaker is playing. Read-only, found automatically, no logins. See [docs/SPEAKERS.md](docs/SPEAKERS.md).
- **Sleep mode.** For white noise, rain and similar sleep sounds the display shows the screen for 10 seconds, counts down 10 seconds with `Going to sleep`, then goes dark for as long as that plays. See [docs/SLEEP-MODE.md](docs/SLEEP-MODE.md).
- **A web page in the sidebar** with a timeline scrubber, a short volume control, a Back button, and an Info page that lists your players, media servers and speakers. See [docs/WEB-PAGE.md](docs/WEB-PAGE.md).
- **A dashboard tile.** The app installs a small Home Assistant integration that makes each SLIMP3 a media player, with Home Assistant's own media browser. See [docs/DASHBOARD.md](docs/DASHBOARD.md).
- **Setup help on the player itself.** At connect the display shows its IP and MAC address and short prompts.
- **Multi-room.** Each SLIMP3 is matched by MAC address to its own settings.
- **Very little CPU.** MP3 is passed through without decoding, and the app idles at about 0% of a core. On a Raspberry Pi 5 it uses less than 1% of one core. Details in [docs/HOW-IT-WORKS.md](docs/HOW-IT-WORKS.md#footprint).

## Requirements

- Home Assistant OS or Supervised (apps are not available on Container/Core installs).
- A SLIMP3 with firmware that uses UDP port 3483 (1.3 and later; developed with 2.2), on the same network as Home Assistant.
- A DLNA/UPnP media server for music (developed against Plex Media Server's DLNA server), and/or Sonos, HomePod or Google Cast speakers.

## Install

1. Click the button above, or in Home Assistant open **Settings > Apps > App store**, open the menu (top right), choose **Repositories**, and add `https://github.com/DaveMath/SLIMP3-for-HA`.
2. Install **SLIMP3 Player** and start it.
3. Open **SLIMP3** in the sidebar. Media servers and speakers are found automatically; everything else is optional and lives on the app's **Configuration** tab ([docs/CONFIGURATION.md](docs/CONFIGURATION.md)).

## Documentation

| Page | Contents |
| --- | --- |
| [docs/CONFIGURATION.md](docs/CONFIGURATION.md) | Every option, examples, boot screens, finding MAC addresses and DLNA URLs |
| [docs/SPEAKERS.md](docs/SPEAKERS.md) | Sonos, HomePod and Google Cast display, and why Alexa is not supported |
| [docs/SLEEP-MODE.md](docs/SLEEP-MODE.md) | The sleep countdown and dark display |
| [docs/WEB-PAGE.md](docs/WEB-PAGE.md) | The sidebar page: timeline, volume, Back, Info, seeking |
| [docs/DASHBOARD.md](docs/DASHBOARD.md) | The dashboard tile and media browser |
| [docs/POLLING.md](docs/POLLING.md) | How little the app polls, and the method used to keep it that way |
| [docs/HOW-IT-WORKS.md](docs/HOW-IT-WORKS.md) | Architecture, the SLIMP3 protocol, streaming, display, footprint |
| [docs/API.md](docs/API.md) | The HTTP API behind the page |
| [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) | Common problems and fixes |
| [slimp3_player/CHANGELOG.md](slimp3_player/CHANGELOG.md) | Release notes |

## Not included

SMB sources, SLIMP3 remote-control button mapping (button codes are logged), seeking from the Home Assistant media player entity (the web page has it), firmware 1.2 and earlier (UDP port 1069), a spectrum for Sonos, HomePod or Cast audio (those expose titles, not audio), and **Amazon Alexa devices**: Alexa has no local way to report what is playing, and the only route is an unofficial, login-based cloud connection. This app deliberately has no login dependencies and stores no credentials.

## License and credits

Licensed **GPL-2.0-only** (see [LICENSE](LICENSE) and [NOTICE.txt](NOTICE.txt)). The SLIMP3 protocol handling, display encoding, decoder initialization and streaming algorithm are derived from [Lyrion Music Server (slimserver)](https://github.com/LMS-Community/slimserver) and its [protocol documentation](https://lyrion.org/reference/slimp3-protocol/). HomePod support uses [pyatv](https://pyatv.dev) (MIT).

Slim Devices, SLIMP3, Sonos, HomePod, Google Home, Nest, Plex and HDHomeRun are trademarks of their respective owners. This project is not affiliated with or endorsed by them.
