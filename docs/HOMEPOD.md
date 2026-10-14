# HomePods

Like Sonos, a HomePod can be shown on a SLIMP3's display while the SLIMP3 is idle: the HomePod's name and variant on the top
line, and what it is playing (artist and title, or show and episode) on the bottom line. The app **only reads** what a HomePod is
playing. It does not control it, stream to it, or pair with it.

## Setup

None. HomePods are found automatically (Bonjour, the same discovery the Home app uses) and appear in the sidebar page. For each
SLIMP3, the **Show on the display when this player is idle** dropdown in Settings lists the Sonos rooms and the HomePods:

- **Anything that is playing:** any playing Sonos group, otherwise any playing HomePod.
- **A Sonos room** or **a HomePod:** only that one.
- **Do not show Sonos or HomePod.**

In the configuration the same choice is `apple_room` on a `players` entry (a HomePod's name, as the Home app shows it). The option
`apple_discovery` (default on) switches HomePod support off.

## What shows

| HomePod | Line 1 | Line 2 |
| --- | --- | --- |
| Playing music | `Kitchen: HomePod` (or `HomePod mini`) | `Artist - Title` |
| Playing a podcast | the same | `Show - Episode` |
| Paused or idle | nothing: the SLIMP3 shows its idle screen | |

It appears only while the SLIMP3 is not playing its own music, and only while the HomePod is **playing**, the same as Sonos.
Because it shows exactly what the HomePod reports, anyone looking at the SLIMP3 sees the titles of what is playing in that room.

## How it works

HomePods report what they are playing over AirPlay 2. The app uses the [pyatv](https://pyatv.dev) library (MIT license) to listen:
it opens a connection to the HomePod and receives push updates, so it does no polling. A HomePod and HomePod mini report "pairing
not needed" for this, so nothing is paired and no credentials are stored. An Apple TV requires a PIN to pair and is not supported.

The app connects **only while a SLIMP3 is idle and wants to show a HomePod**, and only to the HomePods it wants. Starting
playback on the SLIMP3 closes the connections. Choosing one HomePod in the dropdown closes the others.

pyatv imports a compiled audio package (`miniaudio`) that it uses only to stream audio *to* speakers. That package has no prebuilt
version for the app's container, and this app never streams audio, so a small stand-in module (`app/stubs/miniaudio.py`) satisfies
the import; anything that would actually stream audio fails loudly. The container installs pyatv and its other dependencies from
prebuilt packages only (no compiler). If that install fails, the app still builds and runs without HomePod support, and the log says
`HomePod support is not available`.

## Cost

Measured on a Mac with a HomePod and a HomePod mini, both connected and idle: about **0.10% of a core**, about **5 MB** more memory,
and **six TCP connections** (three per HomePod). With nothing connected: about 0.03% of a core. These are Mac figures; see
[HOW-IT-WORKS.md](HOW-IT-WORKS.md#footprint) for the method. The container adds roughly 13 MB of downloaded packages.

## Limits

- Tested with a HomePod and a HomePod mini. Stereo pairs, other HomePod generations and HomePods inside a room group were not tested.
- A HomePod's access setting in the Home app ("Speakers and TV access") can block unpaired listeners; the default worked in testing.
- No spectrum analyzer: the audio is not available, only the title and artist.
- It shows nothing for a HomePod that is paused, as with Sonos.

## Troubleshooting

- **No HomePods listed.** The search is multicast and does not cross network segments. HomePods must be on the same network segment as
  Home Assistant.
- **`HomePod Kitchen: cannot connect`** in the log: the app retries every minute. Check the HomePod's access setting.
- **`HomePod support is not available`** in the log: pyatv could not be loaded in the container. The message names the error; open an
  issue with it. Everything else keeps working.

## Tested and not tested

Tested on a Mac (Python 3.13) against a real HomePod and HomePod mini: discovery, connection, push updates, per-player selection,
disconnecting when a SLIMP3 starts playing, and the display lines. **Not yet validated:** the container (Alpine, Python 3.14), where
pyatv and its prebuilt dependencies are installed at build time.
