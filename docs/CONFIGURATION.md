# Configuration

All options are set on the app's **Configuration** tab in Home Assistant (stored in `/data/options.json`).
Changes apply after restarting the app.

## Options

| Option | Default | Description |
| --- | --- | --- |
| `dlna_servers` | `[]` | List of DLNA/UPnP media server description URLs. For Plex's DLNA server: `http://<host>:32469/DeviceDescription.xml`. |
| `player_ips` | `[]` | Optional SLIMP3 addresses. Only needed if a player does not find the server by broadcast. The app sends these addresses a hello until the player registers. |
| `sonos_ips` | `[]` | IP address of **any one** Sonos player (add a second as a backup). The app reads the whole household from it. |
| `players` | `[]` | Per-SLIMP3 settings, matched by MAC address. See below. |
| `sonos_display` | `true` | Default for `show_sonos`: show Sonos on the display while the SLIMP3 is idle. |
| `default_volume` | `40` | Volume (0-100) a player starts at. |
| `spectrum` | `true` | Spectrum analyzer on the bottom line while playing. Off: artist on the top line, title on the bottom. |
| `display_fps` | `8` | Display updates per second while the analyzer runs (1-15). |
| `sync_ms` | `0` | Shift the analyzer earlier (negative) or later (positive) to line up with the sound (-2000 to 2000). |

### `players` entries

| Key | Required | Description |
| --- | --- | --- |
| `mac` | yes | The SLIMP3's MAC address, for example `00:04:20:xx:xx:xx` (case does not matter). |
| `name` | no | A label shown in the sidebar page and the log. |
| `sonos_room` | no | The Sonos room this player mirrors. Empty: mirror any playing Sonos group. |
| `show_sonos` | no | `false` turns the Sonos display off for this player. |
| `volume` | no | Starting volume for this player. |
| `spectrum` | no | Overrides the global `spectrum` for this player. |
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

## How a SLIMP3 chooses what to show

1. If the SLIMP3 is playing music from this app, it shows that (spectrum or artist/title).
2. Otherwise, if `show_sonos` is true and its `sonos_room` (or any room, if empty) is in a Sonos group
   that is playing, it shows that group's station and track.
3. Otherwise it shows `SLIMP3 server ready`.

Sonos groups matter: if the Kitchen is grouped with the Living Room, a SLIMP3 mapped to `Kitchen`
mirrors the group's coordinator, because the coordinator knows what the group plays. If the Kitchen
is ungrouped and stopped, that SLIMP3 shows nothing from Sonos even if another room is playing.

## Finding the values

- **SLIMP3 MAC address:** printed in the app log when the player connects
  (`player 00:04:20:... at 192.168.1.50 fw 2.2`), and shown in the sidebar page's player selector.
- **Sonos IP address:** in the Sonos app (About My System) or your router's device list.
- **Sonos room names:** open `/api/sonos` through the app (see [API.md](API.md)); the `rooms` list holds
  the exact names. Room matching ignores case.
- **Plex DLNA URL:** enable the DLNA server in Plex's settings, then use port 32469 on the Plex host.
  Open the URL in a browser; it should return an XML device description.
