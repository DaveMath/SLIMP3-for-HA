# Sonos, HomePod and Google Cast speakers

When a SLIMP3 is idle it can show what a speaker in your home is playing. All three kinds work the same way and are **read-only**: the app never plays, pauses or changes the volume of a speaker, never streams to it, and needs no login or pairing. It only reads what the speaker reports.

## Setup

None. Speakers are found automatically and listed on the sidebar page's **Info** section, with what each one reports right now (for example `Bedroom (HomePod mini): playing, Rain Sounds: Ambient Sounds - Rain`).

To choose which speaker a SLIMP3 shows, set `sonos_room`, `apple_room` or `cast_room` in its `players` entry on the app's Configuration tab, using the names Info lists. Leave all three empty and it shows whichever speaker is playing (Sonos first, then HomePod, then Cast). `show_sonos: false` turns the display off for one player. See [CONFIGURATION.md](CONFIGURATION.md).

## What shows

A speaker appears only while it is **playing** and the SLIMP3 is not playing its own music. When it stops or pauses, the last screen stays for 4 seconds and then the display goes black (brightness 0%, the same dark display sleep mode uses) until something plays again. Starting music on the SLIMP3 takes over the display.

| Source | Line 1 | Line 2 |
| --- | --- | --- |
| Sonos radio station | the station, for example `CH 55 - SiriusXM Chill` | `Artist - Title`, or the source if there is no track |
| Sonos track | the room and source, for example `Office: Spotify` | `Artist - Title` |
| Sonos, no track info | the room | `TV audio`, `Line-in` or `Playing` |
| HomePod | the name and variant, for example `Kitchen: HomePod mini` | `Artist - Title` (a podcast: `Show - Episode`) |
| Google Cast | the device name and app, for example `Bedroom: Spotify` | `Artist - Title` |

Text that fits is centered and still; longer text scrolls. Because the display shows exactly what a speaker reports, anyone looking at the SLIMP3 sees the titles of what is playing in that room. With [sleep mode](SLEEP-MODE.md) on, sleep sounds on a speaker blank the display after the countdown.

## Sonos

- **Discovery.** An SSDP (multicast) search for Sonos `ZonePlayer` devices, repeated every 10 minutes and only while an idle SLIMP3 wants Sonos. Addresses in `sonos_ips` are used as well; one is enough, since the app reads the whole household from it. Set `sonos_discovery: false` to use only those addresses.
- **Rooms and groups.** The app asks one player for the household topology (UPnP `ZoneGroupTopology`, port 1400) and caches it for 60 seconds. A player mapped to a room mirrors the **group** the room is in, because the group coordinator is what knows what plays. An ungrouped, stopped room shows nothing even if another room plays.
- **Polling.** Every 3 seconds it reads the transport state of the groups a SLIMP3 is showing, and reads the track only if a group is playing, over one persistent connection per player. It sleeps when no idle SLIMP3 wants Sonos.
- **The station line** comes from the current item's title when it is a radio broadcast; artist and title come from the track metadata, or from the stream-content string some radio sources use.
- **No spectrum.** Sonos exposes control and metadata, not audio.

## HomePod

HomePods and HomePod minis are found with Bonjour (the discovery the Home app uses). They report what they play over AirPlay 2, and the app listens with the [pyatv](https://pyatv.dev) library (MIT): it receives push updates and does no polling. A HomePod needs no pairing for this, so no credentials are stored. An Apple TV requires a PIN and is not supported.

- The app connects **only while a SLIMP3 is idle and wants a HomePod**, and only to the HomePods it wants. Starting playback on the SLIMP3 closes the connections.
- Besides push updates, the app asks each connected HomePod directly every 10 seconds, so a stop is never missed.
- Info shows what each HomePod reports. If a HomePod reports `paused` (Ambient Sounds such as White Noise can do this), the SLIMP3 shows nothing for it, and Info shows exactly what the HomePod said.
- pyatv imports a compiled audio package (`miniaudio`) that it uses only to stream audio *to* speakers. It has no prebuilt version for the app's container and this app never streams audio, so a small stand-in module (`app/stubs/miniaudio.py`) satisfies the import. The container installs pyatv from prebuilt packages only (no compiler); if that install fails, the app still runs without HomePod support, and Info says why.
- Cost: with two HomePods connected and idle, about 0.10% of a core and 5 MB of memory (six TCP connections). With nothing connected, about 0.03%.
- A HomePod's access setting in the Home app ("Speakers and TV access") can block unpaired listeners; the default works.

## Google Cast (Google Home, Nest, Chromecast)

Google Home, Nest speakers and displays, Chromecast devices and Cast speaker groups are found automatically with mDNS (`_googlecast._tcp`). The app opens the Cast connection (TLS, port 8009), reads the receiver status and the media status, and sends only connection, status-request and keep-alive messages, never a playback command. No Google account, login or token is involved, and nothing is installed beyond the `zeroconf` package that HomePod support also uses.

- What appears is whatever the playing app reports over Cast: the app name (Spotify, YouTube Music, and so on), then artist, title and album. A playing app that reports no title shows the device name on line 1 and the app name on line 2.
- As with HomePod, the app connects only while an idle SLIMP3 wants a Cast device, and disconnects otherwise. A dropped connection is retried every minute.
- If a device is on another network segment, list its address under `cast_ips`; the app asks the device for its name. Set `cast_discovery: false` to switch Cast support off.

## Amazon Alexa: not supported

Echo devices have no local interface that reports what is playing. The only route is the unofficial, community-maintained [alexa_media_player](https://github.com/alandtse/alexa_media_player/wiki) approach, which signs in to your Amazon account and polls Amazon's cloud, and which its own wiki warns Amazon may cut off at any time. This app deliberately has no login dependencies, stores no credentials and makes no cloud calls, so Alexa is left out. If you also use that Home Assistant integration, you can show an Echo's state on a dashboard next to the SLIMP3 tile.

## Troubleshooting

- **No speakers listed.** The searches are multicast and do not cross network segments. Put the speakers on Home Assistant's segment, or give the app an address: `sonos_ips` for Sonos, `cast_ips` for Cast. HomePods must be on Home Assistant's segment.
- **A speaker is listed but the SLIMP3 shows nothing.** Check its line on the Info page. It must be `playing`, the SLIMP3 must be idle (not playing its own music), and the player's `sonos_room`, `apple_room` and `cast_room` must be empty or name that speaker.
- **`cannot connect: ...` on Info.** The app retries every minute. For a HomePod, check its access setting in the Home app.
- **`HomePod support is not available`** (Info or log): pyatv could not be loaded in the container. The message names the error; open an issue with it. Everything else keeps working.
- **Google Cast: `automatic discovery is unavailable`**: the `zeroconf` package could not be loaded. Devices listed under `cast_ips` still work.
