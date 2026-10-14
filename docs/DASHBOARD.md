# Dashboard tile and media browser

The app installs a small Home Assistant integration called **SLIMP3**. It makes each connected SLIMP3 a normal Home
Assistant **media player**, so it works with the standard dashboard cards and Home Assistant's own media browser. There is no
separate card to install.

## Setup

1. **Install the app and start it.** On startup it copies the integration into Home Assistant's configuration folder
   (`custom_components/slimp3`). The app log says `installed the SLIMP3 Home Assistant integration`. This needs the
   configuration map that the app already declares; nothing to configure.
2. **Restart Home Assistant once** (Settings, System, Restart). Home Assistant only loads new integrations at startup.
   The same applies after an update that changes the integration (the app log says so).
3. **Settings, Devices and services, Add integration, SLIMP3.** The dialog suggests `127.0.0.1` and port `8099`. If that
   does not answer, it also tries `172.30.32.1`, `homeassistant` and `homeassistant.local`, so the default usually works.
   Each SLIMP3 that is connected to the app appears as a device with one media player.
4. **Add the tile.** On a dashboard: Edit, Add card, **Tile**, choose your SLIMP3 player.

## Using it

- **Tap the tile** to open the player. Use **Browse media** to open the library: your music servers, then folders and
  albums, then tracks, with Home Assistant's own Back navigation and breadcrumb. Folders that are albums or playlists have a
  play button; tracks play that track and continue through the folder.
- When what is playing has no artist (a live TV channel, an untagged file), the media player shows the music server's name as the
  artist and as the app name, and uses the type `channel` for live sources, so the tile is never blank.
- The media player supports play, pause, stop, next track, previous track and volume. It shows the artist, title and album
  of what is playing, and the state (playing, paused, buffering, idle).
- Music servers are the ones added to the app (on its page or in its configuration). See [CONFIGURATION.md](CONFIGURATION.md).

## What it does not do

- No seeking within a track, shuffle or repeat.
- While the SLIMP3 mirrors Sonos on its display, the media player shows idle: it reflects only what the SLIMP3 plays itself.
- The library browser shows the folders a server offers. Large folders are shown up to the first 200 entries.

## How it works

The integration polls the app's local HTTP API (`/api/state`, every 5 seconds, a small local request) and sends commands to it
(`/api/control`, `/api/play`). The browser calls `/api/sources` and `/api/browse`. See [API.md](API.md). It uses no cloud service and
no extra Python packages. The app accepts these requests from Home Assistant's own network and from the host itself, and from nothing else.

After a command the player refreshes its state after about a second and a half, because the app starts a stream a moment after
it accepts one.

## Manual installation

If the app cannot write to the configuration folder (the log says so), copy the folder
`slimp3_player/app/integration/slimp3` from this repository to `<Home Assistant config>/custom_components/slimp3`, restart Home
Assistant, and continue at step 3.

## Troubleshooting

- **SLIMP3 does not appear under Add integration.** Restart Home Assistant after the app has started once, and check the app
  log for the install line.
- **"Could not reach the SLIMP3 Player app".** Check that the app is started. Enter the address of the Home Assistant host if
  the suggested ones do not work; the app only accepts connections from Home Assistant's networks and from the host itself.
- **No media player appears.** A player shows up once the SLIMP3 has connected to the app (the sidebar page shows it as connected).
- **Browse media is empty.** Add a music server in the app first.
