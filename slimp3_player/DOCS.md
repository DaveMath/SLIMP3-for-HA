# SLIMP3 Player

Play music from Plex/DLNA servers on a SLIMP3 network music player, or show what Sonos is playing on your network.

Visit [SLIMP3 Player](https://github.com/DaveMath/SLIMP3-for-HA) page for more details. Written by @GGDM on Krystalize.AI local harness. Get your own local private LLM.

## Setup

1. Set `dlna_servers` to your media server's description URL. For Plex's DLNA server:
   `http://<host>:32469/DeviceDescription.xml`.
2. Optional: set `sonos_ips` to the address of any one Sonos player.
3. Start the app and open **SLIMP3** in the sidebar.

The SLIMP3 finds this app by broadcast on UDP 3483, so the app uses the host network. If your player
is on another VLAN, add its address to `player_ips`.

## Several rooms

Add one `players` entry per SLIMP3, matched by MAC address (shown in the app log and the sidebar page):

```yaml
players:
  - mac: "00:04:20:12:34:56"
    name: Kitchen
    sonos_room: Kitchen
  - mac: "00:04:20:65:43:21"
    name: Garage
    show_sonos: false
    volume: 55
```

`sonos_room` is the Sonos room that player mirrors. Room names are listed at `/api/sonos`.

## Display

While playing music from this app: artist on the top line, title on the bottom. MP3 files are sent to the
SLIMP3 untouched (it decodes MP3 itself); other formats are converted by ffmpeg. Optional: `spectrum: true` turns
the bottom line into a 40-band spectrum analyzer (it needs a second decode and extra memory, so it is off by default). When the SLIMP3 is idle and its
Sonos room is playing: top line is the station (for example `CH 55 - SiriusXM Chill`), bottom line is
`Artist - Title`. Text that fits is shown still; long text scrolls. While showing Sonos the app does no audio work.

The app only reads from Sonos. It cannot get Sonos audio, so there is no spectrum for Sonos.

## Web page

Timeline scrubber (drag to jump within a track), a small volume control (minus and plus, 5 per press), and a Back button, breadcrumbs,
Escape and the phone's back gesture for the library. The header shows the version. **Info** lists this player's details, the DLNA servers found
(add with a click), Sonos and HomePods, and the dashboard tile steps; **Settings** has the player's name and what its display shows when idle. Details: `docs/WEB-PAGE.md` in the repository.

## Sleep mode

Optional, and set here in the Configuration tab only. With `sleep_mode: true`, when what is playing looks like sleep sounds (the `sleep_keywords`,
for example white noise or rain), the display shows it for 10 seconds, shows `Going to sleep` with a 10 second countdown, then stays
dark while that plays. Some songs match a keyword (for example "Purple Rain"); edit the list to taste. Details: `docs/SLEEP-MODE.md`.

## More

Full documentation: configuration, how it works, API and troubleshooting are in the
[docs folder](https://github.com/DaveMath/SLIMP3-for-HA/tree/main/docs).

Licensed GPL-2.0-only. Derived in part from Lyrion Music Server.
