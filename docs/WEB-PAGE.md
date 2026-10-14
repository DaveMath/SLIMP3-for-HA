# The web page (sidebar)

Open **SLIMP3** in the Home Assistant sidebar. The page has the player card, the library and **Info**. It has no settings: everything is set on the app's Configuration tab ([CONFIGURATION.md](CONFIGURATION.md)). The header shows the page's version (for example `v0.12.0`); if it is not the version you installed, reload the page.

## Player card

- **Timeline.** Elapsed time, a scrubber and the length of the track. **Drag the scrubber to jump to a point**; the track restarts there after a short pause (a second or two). The scrubber is greyed out, with the length shown as `Live` or `-:--`, when the thing playing cannot be searched: live TV and radio, and anything whose length is not known.
- **Controls.** Previous, play/pause, next, stop.
- **Volume.** A short control to the right: a **minus** button, the number (0-100) and a **plus** button. Each press changes the volume by 5; quick presses are sent as one change.
- **Player.** With more than one SLIMP3, a menu picks which one the page controls.

## Library and Back

Music servers are listed at the top. Open one to browse folders, albums and tracks. Inside a server or folder, a **Back** button appears at the left of the library header (hidden on the top list). You can also click any name in the **breadcrumb**, press **Escape**, or use the **browser's or phone's own back** button or gesture: each level you opened adds one history entry, so going back moves up one level instead of leaving the page.

**Play all** starts the folder from its first track. Tapping a track plays it and continues through the folder.

## Wording follows the source

The page only says things that are true for what you opened. Live TV and radio are not "tracks", and a channel list has no "play all".

| Source | Row | Click message | Previous/Next | Timeline | Play all |
| --- | --- | --- | --- | --- | --- |
| Music | title, artist, length | `Playing <title> and 29 more tracks` (the number is what comes after it), or `Playing <title>` for one | track | scrubber | shown |
| Live TV (for example HDHomeRun) | channel name, `Live TV`, TV icon | `Playing channel 2.4 BUZZR`, no count | channel | `Live` | hidden |
| Live radio | station name, `Live radio` | `Playing <station>`, no count | station | `Live` | hidden |
| Video files | title, `Video` | as music | track | scrubber | shown |

Clicking a channel starts it and queues the rest of the list after it, so Next and Previous move along the channel list. A folder shows `N items` when the server says how many. Filler such as `Unknown` in empty artist and album fields is dropped. If a folder has more entries than the page shows (the first 200), a line says `Showing the first 200 of N`.

## Info

**Info** sits below the library and opens with a **Back to the library** button.

- **This player:** name, address, MAC and firmware.
- **Music servers:** DLNA servers on your network are searched for automatically when you open Info and listed with an **Add** button (or `Added`); **Find servers** searches again. The servers you have added are listed above, and you can add one by address, for example `192.168.1.10`. This host's Plex DLNA port is included when the app runs on the same machine as Plex.
- **Sonos, HomePods and Google Cast:** what was found and what each device reports right now, why one cannot be reached, and which names to use in the `players` list. See [SPEAKERS.md](SPEAKERS.md).
- **Dashboard tile:** whether the Home Assistant integration was installed, and the steps to add the tile. See [DASHBOARD.md](DASHBOARD.md).

## Seeking

- **MP3 sent untouched (the default).** The app restarts the file at a byte position. If the file has a variable-bit-rate seek table (most MP3s from Plex do), the position is looked up in that table; on a 3 minute test file, restarts landed within about a second of the requested time. Without a table the position is estimated from the average bit rate, which is exact only for constant-bit-rate files and can be several seconds off for variable-bit-rate ones. The media server must accept byte-range requests (Plex does); one that does not is read from the start up to the position, which is slower.
- **Other formats (ffmpeg).** ffmpeg starts at the requested time.
- **The timeline** moves smoothly between updates (the page asks the app every 1.5 seconds) and matches what the SLIMP3 has played.
- **Not available:** live streams and tracks of unknown length. The Home Assistant media player entity does not offer seeking; the scrubber is on this page only.
