# Changelog

## 0.6.0
- Sonos players are discovered automatically (no addresses needed). The sidebar page has a name field and a Sonos
  room dropdown per player; choices apply immediately and are saved (they override the options file).
- Lighter Sonos polling: one persistent connection per speaker, cached layout, only the wanted rooms are read.
- Lighter streaming: a full player buffer is polled 4 times a second instead of 20.
- New options: `sonos_discovery`; `sonos_ips` is now optional.

## 0.5.0
- MP3 files are now sent to the SLIMP3 untouched (it decodes MP3 itself), as slimserver does. ffmpeg is used only
  for other formats and live TV. `mp3_passthrough: false` restores converting everything.
- The spectrum analyzer is now opt-in (off by default); numpy is not loaded unless it is enabled.
- Display updates are sent only when the text changes (a still title: one packet per 10 seconds).
- Sonos is polled only while a SLIMP3 is idle and wants to show it, every 3 seconds.

## 0.4.1
- Fix: the container build no longer fails on its ffmpeg encoder check. That check could fail even though the
  encoder was installed. The build now only records what ffmpeg offers; the app checks at startup and logs
  ffmpeg's own output if the MP3 encoder is missing.

## 0.4.0
- Boot screens: IP and MAC address plus guided setup prompts on the SLIMP3's display at connect or restart
  (`boot_screens` option); `identify` control action.
- Startup self-test of the spectrum analyzer with automatic fallback to the artist/title layout.
- Live sources (TV tuners) skip the analyzer so they use a single tuner.

## 0.3.0
- Multi-room: per-player settings (`players`) matched by MAC address, including which Sonos room each
  SLIMP3 mirrors. The Sonos monitor now reads the whole household from any one Sonos address.
- The sidebar page has a player selector.
- Documentation in the repository's `docs/` folder.

## 0.2.0
- Sonos now-playing: station on the top line, artist and title on the bottom (scrolls only when too long).
- The web UI and API accept connections only from Home Assistant's internal network.

## 0.1.0
- First release: SLIMP3 player engine, Plex/DLNA browsing, web UI, spectrum display.
