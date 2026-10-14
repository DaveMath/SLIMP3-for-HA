# SLIMP3 Player

Runs the server side for a Slim Devices SLIMP3 network music player. The player
finds this app by broadcast on UDP 3483, so the app uses the host network.

## Setup

1. Install and start the app.
2. In the app configuration, add your DLNA/UPnP media server description URL(s).
   For Plex's DLNA server this is `http://<host>:32469/DeviceDescription.xml`.
3. Open **SLIMP3** in the sidebar, pick a source, browse, and play.

Plex (and other servers running in Docker) may advertise internal addresses in
stream URLs. The app rewrites them to the address it used to reach the server.

## Display

With the spectrum analyzer on, the top line alternates between artist and title
(scrolling when longer than 40 characters) and the bottom line shows a 40-band
analyzer. With it off, the top line shows the artist and the bottom line the title.

## Sonos now-playing

Add the IP address of any Sonos player to `sonos_ips`. When the SLIMP3 is not playing
its own music and a Sonos group is playing, the display shows the station name on the top
line (for example `CH 55 - SiriusXM Chill`) and `Artist - Title` scrolling continuously on
the bottom line. The app only reads from Sonos. It cannot get the audio itself, so the
spectrum analyzer is available only for music this app plays.
