# SLIMP3 Player

Play music from Plex/DLNA servers on a SLIMP3 network music player, and show what Sonos, HomePod and Google Home / Nest speakers are playing on its display.

Free software by @GGDM, inspired by Kevin Kelly ([kk.org](https://kk.org)), who gave me an old SLIMP3. This project is all about my love of hacking newly compatible interfaces on popular back-ends to devices which typically lose their legacy servers.

## Setup

1. Start the app and open **SLIMP3** in the sidebar. The SLIMP3 finds the app by broadcast on UDP 3483 (the app uses the host network). If your player is on another VLAN, add its address to `player_ips`.
2. On the sidebar page, open **Info**: DLNA media servers on your network are found automatically and added with a click. Sonos, HomePod and Google Cast speakers are found automatically too.
3. Everything else is optional and is set on this **Configuration** tab. There are no settings on the sidebar page.

## Several rooms

Add one `players` entry per SLIMP3, matched by MAC address (shown on the Info page and in the app log):

```yaml
players:
  - mac: "00:04:20:12:34:56"
    name: Kitchen
    sonos_room: Kitchen
  - mac: "00:04:20:65:43:21"
    name: Garage
    cast_room: Garage speaker
    volume: 55
```

`sonos_room`, `apple_room` and `cast_room` choose the Sonos room, HomePod or Google Cast device a player shows when idle. Leave them empty to show whatever is playing.

## Display

- Music from the app: artist and title, with a live spectrum analyzer on the bottom line (the **Waveform display** option, on by default, with a **Waveform delay** of 2 ms).
- Idle: what a Sonos room, HomePod or Google Cast speaker is playing, as text only.
- **Sleep mode** (optional): sleep sounds show for 10 seconds, count down 10 seconds with `Going to sleep`, then the display stays dark while they play.

Alexa devices are not supported: Alexa has no local now-playing interface, and this app has no login dependencies.

## More

Full documentation: the [docs folder](https://github.com/DaveMath/SLIMP3-for-HA/tree/main/docs). Licensed GPL-2.0-only. Derived in part from Lyrion Music Server.
