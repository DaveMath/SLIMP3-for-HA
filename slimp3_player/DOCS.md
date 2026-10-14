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

While playing music from this app: top line alternates artist and title, bottom line is a 40-band
spectrum analyzer (`spectrum: false` shows artist and title instead). When the SLIMP3 is idle and its
Sonos room is playing: top line is the station (for example `CH 55 - SiriusXM Chill`), bottom line is
`Artist - Title`. Text that fits is shown still; long text scrolls.

The app only reads from Sonos. It cannot get Sonos audio, so there is no spectrum for Sonos.

## More

Full documentation: configuration, how it works, API and troubleshooting are in the
[docs folder](https://github.com/DaveMath/SLIMP3-for-HA/tree/main/docs).

Licensed GPL-2.0-only. Derived in part from Lyrion Music Server.
