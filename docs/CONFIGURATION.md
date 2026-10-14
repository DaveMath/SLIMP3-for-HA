# Configuration

All settings live on the app's **Configuration** tab in Home Assistant (stored in `/data/options.json`). The sidebar page has no settings. Changes apply after restarting the app. Every option is optional; the defaults work.

## Options

| Option | Default | Description |
| --- | --- | --- |
| `dlna_servers` | `[]` | DLNA/UPnP media server description URLs to write into the configuration. Servers on your network are found automatically and added with a click on the page's Info section, so this is only for people who want them written down. For Plex's DLNA server: `http://<host>:32469/DeviceDescription.xml`. |
| `player_ips` | `[]` | SLIMP3 addresses. Only needed if a player does not find the app by broadcast (another VLAN). The app sends these addresses a hello until the player registers. |
| `sonos_ips` | `[]` | Sonos player addresses. Only needed if discovery cannot see them. One address is enough. |
| `sonos_discovery` | `true` | Search the network for Sonos players. `false` uses only `sonos_ips`. |
| `apple_discovery` | `true` | Find HomePods and show what they play. |
| `cast_discovery` | `true` | Find Google Home, Nest and other Cast devices and show what they play. |
| `cast_ips` | `[]` | Cast device addresses. Only needed if discovery cannot see them. |
| `sonos_display` | `true` | Default for `show_sonos`: show Sonos, HomePod and Cast speakers on the display while the SLIMP3 is idle. |
| `sleep_mode` | `false` | Turn the display off for sleep sounds, for every player. See [SLEEP-MODE.md](SLEEP-MODE.md). |
| `sleep_keywords` | see [SLEEP-MODE.md](SLEEP-MODE.md) | Words that mark sleep sounds. |
| `spectrum` | `true` | Waveform display (spectrum analyzer) on the bottom line while music plays from a media server. `false`: artist on the top line, title on the bottom. |
| `sync_ms` | `2` | Waveform delay in milliseconds: shifts the display earlier (negative) or later (positive) to line up with the sound (-2000 to 2000). |
| `display_fps` | `8` | Display updates per second while the waveform runs (1-15). |
| `default_volume` | `40` | Volume (0-100) a player starts at. |
| `boot_screens` | `true` | When a SLIMP3 connects or restarts, show its IP and MAC address and setup prompts. |
| `mp3_passthrough` | `true` | Send MP3 files to the SLIMP3 untouched. `false` converts everything to 128 kbps MP3 with ffmpeg. |
| `players` | `[]` | Per-SLIMP3 settings, matched by MAC address. See below. |

### `players` entries

| Key | Description |
| --- | --- |
| `mac` | **Required.** The SLIMP3's MAC address, for example `00:04:20:xx:xx:xx` (case does not matter). |
| `name` | A label shown on the page, the display and the log. |
| `sonos_room` | The Sonos room this player shows when idle. |
| `apple_room` | The HomePod this player shows when idle (its name in the Home app). |
| `cast_room` | The Google Cast device this player shows when idle (its name in the Google Home app). |
| `show_sonos` | `false` turns the speaker display off for this player. |
| `sleep_mode` | Overrides the global `sleep_mode` for this player. |
| `volume` | Starting volume for this player. |
| `spectrum` | Overrides the global `spectrum` for this player. |
| `sync_ms` | Overrides the global `sync_ms` for this player. |

The names to use in `sonos_room`, `apple_room` and `cast_room` are listed on the Info page (matching ignores case). Leave all three empty to show whichever speaker is playing.

A SLIMP3 with no `players` entry still works with the global defaults. The app logs `player <mac> has no entry in 'players'` so you can copy the MAC into the list.

## Examples

### One SLIMP3, one Plex server

```yaml
dlna_servers:
  - http://192.168.1.10:32469/DeviceDescription.xml
```

### Several rooms

```yaml
sonos_ips:
  - 192.168.1.20
players:
  - mac: "00:04:20:12:34:56"
    name: Kitchen
    sonos_room: Kitchen
  - mac: "00:04:20:65:43:21"
    name: Bedroom
    apple_room: Bedroom
    sleep_mode: true
  - mac: "00:04:20:aa:bb:cc"
    name: Garage
    show_sonos: false
    volume: 55
    spectrum: false
```

Each SLIMP3 has its own playback queue and its own ffmpeg process. The sidebar page has a player selector; play and control commands go to the selected player.

## Boot screens: seeing each player's IP and MAC

When a SLIMP3 connects, or restarts (it broadcasts a new discovery), the app takes over its display for about 15 seconds:

1. `Connected to Home Assistant`
2. `IP  192.168.1.50` and `MAC 00:04:20:xx:xx:xx`, held for five seconds so it can be read or photographed.
3. A prompt that depends on the setup:
   - No `players` entry: `Optional: name this player` / `App Configuration > players`.
   - Configured: `Player: <name>` and what it shows when idle (`HomePod: <name>`, `Cast: <name>`, `Sonos room: <room>`, `Showing any speaker playing`, `Speaker display: off`).
   - Configured Sonos room not found: `Sonos room not found: <room>` and the real room names.
4. `No music source set up yet` / `Add a DLNA server in app config`, if no server is known.

It then settles on `SLIMP3 server ready` with the player's name and IP. Starting playback interrupts the sequence. Set `boot_screens: false` to turn it off. To tell several players apart, send `{"action": "identify"}` to `/api/control` (see [API.md](API.md)) with the player's `mac`.

## Music sources (DLNA/UPnP)

Music servers come from two places: `dlna_servers` in the configuration, and the ones **added on the sidebar page** (Info, Music servers). Opening Info searches the network (and this host's Plex DLNA port) and lists what it finds with an Add button; or type just an address such as `192.168.1.10` and the app works out the rest. Servers added on the page are saved in the app's data folder and can be removed there; servers from the configuration are removed in the configuration. You browse a server as it presents itself: every library, folder, playlist or view it exposes through its ContentDirectory is available.

**Sonos players are never offered as music servers.** Each Sonos publishes a DLNA server of its own, but its folders are mostly blank, so they are left out of the server list, and typing a Sonos address is refused with an explanation.

**Live TV tuners** such as an HDHomeRun publish their channels as a DLNA server (typically `http://<tuner>/dms/device.xml`). A channel's audio plays on the SLIMP3 through ffmpeg (for example AC-3 5.1 converted to 128 kbps stereo MP3). Playing a channel occupies a tuner for as long as it plays, and the waveform is skipped for live sources because it would open the stream a second time and occupy a second tuner.

## How a SLIMP3 chooses what to show

1. If the SLIMP3 is playing music from this app, it shows that (artist and title, with the waveform if enabled).
2. Otherwise, if `show_sonos` is true and a speaker it follows is playing (its `sonos_room`, `apple_room` or `cast_room`, or any speaker if none is set), it shows that. With none chosen it shows whichever is playing, Sonos first, then HomePod, then Cast.
3. Otherwise it shows `SLIMP3 server ready`.

With sleep mode on, steps 1 and 2 follow the rule in [SLEEP-MODE.md](SLEEP-MODE.md).

## Finding the values

- **SLIMP3 MAC address:** shown on the player's own display at connect, on the page's Info section, and in the app log (`player 00:04:20:... at 192.168.1.50 fw 2.2`).
- **Speaker names:** listed on the Info page.
- **Plex DLNA URL:** enable the DLNA server in Plex's settings, then use port 32469 on the Plex host. Open the URL in a browser; it should return an XML device description.
