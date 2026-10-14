# Configuration

All options are set on the app's **Configuration** tab in Home Assistant (stored in `/data/options.json`).
Changes apply after restarting the app.

## Options

| Option | Default | Description |
| --- | --- | --- |
| `dlna_servers` | `[]` | Optional. DLNA/UPnP media server description URLs written in the configuration. You can also add servers on the sidebar page (see below). For Plex's DLNA server: `http://<host>:32469/DeviceDescription.xml`. |
| `player_ips` | `[]` | Optional SLIMP3 addresses. Only needed if a player does not find the server by broadcast. The app sends these addresses a hello until the player registers. |
| `sonos_ips` | `[]` | Optional. Sonos players are found automatically; add an address only if discovery cannot see them (for example another network segment). One address is enough, the app reads the whole household from it. |
| `sonos_discovery` | `true` | Search the network for Sonos players. `false` uses only `sonos_ips`. |
| `apple_discovery` | `true` | Find HomePods and show what they play, like Sonos (read-only, no pairing). See [HOMEPOD.md](HOMEPOD.md). |
| `players` | `[]` | Per-SLIMP3 settings, matched by MAC address. See below. |
| `sonos_display` | `true` | Default for `show_sonos`: show Sonos on the display while the SLIMP3 is idle. |
| `default_volume` | `40` | Volume (0-100) a player starts at. |
| `boot_screens` | `true` | When a SLIMP3 connects or restarts, show its IP and MAC address and setup prompts on its display. |
| `mp3_passthrough` | `true` | Send MP3 files to the SLIMP3 untouched (it decodes MP3 itself). `false` converts everything to 128 kbps MP3 with ffmpeg. |
| `spectrum` | `false` | Optional spectrum analyzer on the bottom line while playing (needs a second decode and extra memory). Off: artist on the top line, title on the bottom. |
| `display_fps` | `8` | Display updates per second while the analyzer runs (1-15). |
| `sync_ms` | `0` | Shift the analyzer earlier (negative) or later (positive) to line up with the sound (-2000 to 2000). |

### `players` entries

| Key | Required | Description |
| --- | --- | --- |
| `mac` | yes | The SLIMP3's MAC address, for example `00:04:20:xx:xx:xx` (case does not matter). |
| `name` | no | A label shown in the sidebar page and the log. |
| `sonos_room` | no | The Sonos room this player mirrors. Empty: mirror any playing Sonos group. |
| `apple_room` | no | The HomePod this player mirrors (its name in the Home app). Set one of `sonos_room` and `apple_room`, or neither to mirror anything that is playing. |
| `show_sonos` | no | `false` turns the Sonos display off for this player. |
| `volume` | no | Starting volume for this player. |
| `spectrum` | no | Overrides the global `spectrum` for this player (set `true` to turn the analyzer on for just this player). |
| `sync_ms` | no | Overrides the global `sync_ms` for this player. |

A SLIMP3 with no `players` entry still works and uses the global defaults. The app logs
`player <mac> has no entry in 'players'` so you can copy the MAC into the list.

## Examples

### One SLIMP3, one Plex server

```yaml
dlna_servers:
  - http://192.168.1.10:32469/DeviceDescription.xml
```

### Sonos now-playing on one SLIMP3

```yaml
sonos_ips:
  - 192.168.1.20
players:
  - mac: "00:04:20:12:34:56"
    name: Den
    sonos_room: Living Room
```

### Several rooms

```yaml
dlna_servers:
  - http://192.168.1.10:32469/DeviceDescription.xml
sonos_ips:
  - 192.168.1.20
  - 192.168.1.21
players:
  - mac: "00:04:20:12:34:56"
    name: Kitchen
    sonos_room: Kitchen
  - mac: "00:04:20:65:43:21"
    name: Garage
    show_sonos: false
    volume: 55
    spectrum: false
```

Each SLIMP3 has its own playback queue and its own ffmpeg process. The sidebar page has a player
selector; play and control commands go to the selected player.

## Setting a player's name and Sonos room from the sidebar page

Open **SLIMP3** in the sidebar. For the selected player, a name field and a Sonos dropdown sit at the top. The
dropdown lists the Sonos rooms the app discovered (plus "any playing room" and "Sonos display off"). Changes
apply immediately and are saved in the app's data folder, so they survive restarts and updates.

Saved settings **override** the same fields in `players` from the options; fields you never set on the page still
come from the options (for example `volume`). Use the page for the everyday choices and `players` when you want
the setup written down in configuration.

## Boot screens: seeing each player's IP and MAC

When a SLIMP3 connects, or restarts (it broadcasts a new discovery), the app takes over its display for
about 15 seconds with a short guided sequence:

1. `Connected to Home Assistant`
2. `IP  192.168.1.50` and `MAC 00:04:20:xx:xx:xx` (held for five seconds so it can be read or photographed)
3. A prompt that depends on the setup:
   - Player not named yet: `Optional: name this player` / `HA sidebar > SLIMP3 > Settings`.
   - Player configured: `Player: <name>` and its Sonos room (or `Sonos: not set up`, `Sonos display: off`).
   - Configured Sonos room not found: `Sonos room not found: <room>` and the list of real room names.
4. `No music source set up yet` / `Add a DLNA server in app config`, if `dlna_servers` is empty.
5. `Tip: add a Sonos address...`, only when Sonos is switched off (`sonos_discovery: false` and no `sonos_ips`).

It then settles on `SLIMP3 server ready` with the player's name and IP. Starting playback interrupts the
sequence at any point. Set `boot_screens: false` to turn it off.

**Telling several players apart:** send `{"action": "identify"}` to `/api/control` (see [API.md](API.md))
with the player's `mac` to run the sequence again on that unit.

## Music sources (DLNA/UPnP)

Music servers come from two places: `dlna_servers` in the configuration, and the ones **you add on the sidebar page**
(Settings, Music servers). On the page, **Find servers** searches the network (and this host's Plex DLNA port) and
lists what it finds with an Add button; or type just an address such as `192.168.1.10` and the app works out the
rest. Servers added on the page are saved in the app's data folder and can be removed there; servers from the
configuration can only be removed in the configuration. You browse a server exactly as it presents itself:
every library, folder, playlist or view the server exposes through its ContentDirectory is available,
so several music folders or libraries all show up under that one server.

**Sonos players are never offered as music servers.** Each Sonos publishes a DLNA server of its own, but its folders are
mostly blank, so they are left out of Find servers and the library, and typing a Sonos address is refused with an explanation. Sonos
is shown on the SLIMP3 display automatically instead (see below).

Find servers is a convenience, not a guarantee: a network search of the test network found a TV tuner and two
Sonos players but **not** the Plex server, even though Plex's DLNA service was running and reachable by address.
The search therefore also tries Plex's DLNA port on the host the app runs on, and you can always add a server by
address.

**Live TV tuners** such as an HDHomeRun publish their channels as a DLNA server (typically
`http://<tuner>/dms/device.xml`). The audio of a channel can be played on the SLIMP3: in testing, ffmpeg
read an HDHomeRun channel's AC-3 5.1 audio and converted it to 128 kbps stereo MP3. Notes:

- Playing a channel occupies a tuner for as long as it plays.
- The spectrum analyzer is skipped for live sources (it would open the stream a second time and occupy a
  second tuner), so the display shows artist and title.
- Only the ffmpeg conversion was tested against a tuner; playing a tuner channel end to end on a SLIMP3 has
  not been tested.

## How a SLIMP3 chooses what to show

1. If the SLIMP3 is playing music from this app, it shows that (artist and title, or the spectrum if enabled).
2. Otherwise, if `show_sonos` is true and a Sonos group it follows (its `sonos_room`, or any) or a HomePod it follows (its
   `apple_room`, or any) is playing, it shows that: the Sonos station and track, or the HomePod's name and what it plays.
   With neither chosen it shows whichever is playing, Sonos first.
3. Otherwise it shows `SLIMP3 server ready`.

Sonos groups matter: if the Kitchen is grouped with the Living Room, a SLIMP3 mapped to `Kitchen`
mirrors the group's coordinator, because the coordinator knows what the group plays. If the Kitchen
is ungrouped and stopped, that SLIMP3 shows nothing from Sonos even if another room is playing.

## Finding the values

- **SLIMP3 MAC address:** shown on the player's own display at connect (see Boot screens), printed in the app log when the player connects
  (`player 00:04:20:... at 192.168.1.50 fw 2.2`), and shown in the sidebar page's player selector.
- **Sonos players and rooms:** found automatically and listed in the sidebar page's Sonos dropdown. The same
  list is at `/api/sonos` (see [API.md](API.md)). Room matching ignores case.
- **Plex DLNA URL:** enable the DLNA server in Plex's settings, then use port 32469 on the Plex host.
  Open the URL in a browser; it should return an XML device description.
