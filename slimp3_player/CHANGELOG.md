# Changelog

## 0.12.0
- **Google Cast.** Google Home, Nest, Chromecast and Cast speaker groups are found automatically and shown on an idle SLIMP3's display like Sonos
  and HomePods (read-only, no Google account or login). New options `cast_discovery` and `cast_ips`, and `cast_room` in `players`. The Info
  page lists the Cast devices and what each reports; `GET /api/cast` returns the same. See docs/SPEAKERS.md.
- **All settings are in the Configuration tab.** The Settings section of the web page is gone, along with `POST /api/player`; a name or room saved
  from the page by an earlier version is no longer used, so set `name`, `sonos_room`, `apple_room` or `cast_room` in `players`. The Info page lists
  the exact names to use.
- **Waveform display on by default**, with a **waveform delay** (`sync_ms`) of 2 ms. Set `spectrum: false` for the artist and title layout. The
  app still times the analyzer at start-up and falls back by itself when the host is too slow.
- Boot screens describe what each player will show (`HomePod: ...`, `Cast: ...`) and no longer say `Sonos: not set up` when another speaker
  type is in use.
- Documentation rewritten without repetition: speakers are in docs/SPEAKERS.md (replacing docs/HOMEPOD.md), the footprint section has
  current CPU figures, and the README explains why Alexa devices are not supported and credits the project's origin.

## 0.11.2
- New **Info** section on the sidebar page: this player's details, the DLNA servers found on the network (searched automatically when you
  open it, add with a click), Sonos and HomePods with what each reports, and the **dashboard tile** steps. Those moved out of Settings.
- Sleep mode is set in the **Configuration** tab only. The duplicate switch on the page is removed, and any value saved from it is ignored.
  The Configuration descriptions now carry the full explanation.
- Configuration tab: media servers are labeled **optional** and the text says servers are found automatically.
- HomePods: the page now says what each HomePod reports and why one cannot be reached or why HomePod support is unavailable, instead of
  failing silently. `Loading` and `Seeking` count as playing.

## 0.11.1
- Wording now follows the source. Clicking a live channel says `Playing channel 2.4 BUZZR` instead of `Playing N tracks`; music says
  `Playing <title> and N more tracks`, where N is what follows the clicked track. Live lists have no `Play all`, show a TV icon and
  `Live TV`, and Next/Previous are labeled channel or station.
- Folders no longer show `Unknown` as an artist; filler artist and album values from servers are dropped. Folders show `N items` when known.
- A folder with more entries than the page shows says `Showing the first 200 of N`.
- The Home Assistant media browser lists live entries as channels.
- `POST /api/play` returns `remaining`, `title`, `kind` and `live`; `GET /api/browse` returns `live`. See docs/API.md.

## 0.11.0
- **Sleep mode (optional, off by default).** When what is playing matches sleep keywords (white noise, rain, ocean and similar), the
  display shows it for 10 seconds, then `Going to sleep` with a 10 second countdown, then stays dark while it plays. Switch per player on
  the page or `sleep_mode` in the configuration; editable `sleep_keywords`. Works for music from the app and for Sonos and HomePod
  mirroring.
- **Timeline scrubber** on the web page: elapsed time, drag to seek, length. Seeking works for MP3 pass-through (using the file's seek
  table when it has one, otherwise the average bit rate), the ffmpeg path and the spectrum analyzer. Not for live sources or tracks of
  unknown length. New API action `seek`, and `duration`, `seekable` and `sleep_mode` in the player state.
- **Volume** is now a short minus/plus control (5 per press) instead of a long slider.
- **Back button** is now prominent and appears inside every server and folder; also clickable breadcrumbs, the Escape key, and the
  browser's or phone's back gesture. Settings has a **Back to the library** button.
- The page shows its version in the header and is served with `Cache-Control: no-store`, so an old copy cannot hide new controls.
- New docs: `docs/WEB-PAGE.md`, `docs/SLEEP-MODE.md`; updates throughout.

## 0.10.0
- **HomePods.** HomePods and HomePod minis are found automatically and shown on a SLIMP3's display while it is idle, like Sonos:
  the HomePod's name over `Artist - Title`. Read-only and no pairing. Choose Sonos rooms and HomePods from one dropdown on the sidebar
  page (or `apple_room` in `players`). New option `apple_discovery`.
- The app connects to a HomePod only while a SLIMP3 is idle and wants it, and only to the ones it wants.
- The container installs pyatv from prebuilt packages (no compiler); if that fails the app still runs without HomePod support.
- Settings text says "Sonos support is switched off" when it is.

## 0.9.0
- **No more bare "Now playing".** When there is no artist (live TV, untagged files) the display, the page and the Home Assistant
  media player show where it comes from, for example `HDHomeRun - Live TV` over the channel name. The page's player card shows the
  server next to "Now playing". Paused and buffering states are shown on the display.
- **Sonos players are not music servers.** They are left out of Find servers and the library, and adding one is refused with an
  explanation, removing the blank DLNA folders to click through.
- **Sonos screen without track info** (TV audio, line-in) shows the room over the source instead of the room twice; a track shows the
  room and source (`Office: Spotify`).
- Stopped and Queue finished screens now say something useful; Buffering names the server.
- **Fix: Stop or Next could hang** after playing a live source such as a TV channel (ffmpeg's backed-up output stopped asyncio from
  reaping it). Stopping is now immediate; found and tested with a real tuner.
- The sidebar page's library list shows `Live TV` or `Track` instead of a blank subtitle.

## 0.8.0
- **Dashboard tile.** The app installs a Home Assistant integration (SLIMP3) that makes each SLIMP3 a media player:
  play, pause, stop, next, previous, volume, and a media browser (music servers, folders, tracks) with play buttons.
  Add it as a Tile card; tapping it opens Home Assistant's own media browser.
- **Fix: a music server could be listed twice** in Find servers when it answered both the network search and the check of
  this host's Plex port. Results are now merged by the server's unique identity, and adding the same server twice is ignored.
- The app accepts connections from the host's own addresses, so Home Assistant Core can reach it.

## 0.7.0
- **Fix: Sonos did not show unless `sonos_ips` was filled in.** The Sonos monitor only started when addresses were
  configured, so automatic discovery never ran. It now starts whenever discovery is on.
- Redesigned sidebar page: connection status with a "Looking for your SLIMP3" screen (and the addresses it has heard),
  a library browser with a Back button and breadcrumbs, a music-server picker (Find servers, or add by address), and
  settings that save automatically.
- Music servers can be added and removed on the page (saved in the app's data folder); `dlna_servers` is optional.
- Network searches go out on every interface of the host (Linux).
- The boot prompt for an unnamed player now points to the sidebar page.

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
