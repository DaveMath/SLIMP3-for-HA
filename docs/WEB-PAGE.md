# The web page (sidebar)

Open **SLIMP3** in the Home Assistant sidebar. The page shows the version in the header (for example `v0.11.0`). If the version is
not the one you installed, the page is stale: reload it (see Troubleshooting below).

## Player card

- **Timeline.** Elapsed time, a scrubber and the length of the track. **Drag the scrubber to jump to a point**; the track restarts
  there after a short pause (about a second or two). The scrubber is greyed out, with the length shown as `Live` or `-:--`,
  when the thing playing cannot be searched: live TV and radio, and anything whose length is not known.
- **Controls.** Previous, play/pause, next, stop.
- **Volume.** A small control to the right: a **minus** button, the number (0-100) and a **plus** button. Each press changes the
  volume by 5. Presses made in quick succession are sent as one change.
- **Player.** With more than one SLIMP3, a menu picks which one the page controls.

## Library and Back

Music servers are listed at the top. Open one to browse folders, albums and tracks. Inside a server or folder, a **Back** button
appears at the left of the library header (it is hidden on the top list, where there is nothing to go back to). You can also:

- click any name in the **breadcrumb** (`Music servers / Plex / Albums / ...`) to jump straight to that level;
- press **Escape**;
- use the **browser's or phone's own back** button or gesture. Each level you open adds one history entry, so going back moves up
  one level inside the page instead of leaving it.

**Play all** starts the folder from its first track. Tapping a track plays it and continues through the folder.

## Wording follows the source

The page only says things that are true for what you opened. Live TV and radio are not "tracks", and a channel list has no "play all".

| Source | Row | Click message | Previous/Next | Timeline | Play all |
| --- | --- | --- | --- | --- | --- |
| Music | title, artist, length | `Playing <title> and 29 more tracks` (the number is what comes after it), or `Playing <title>` for one | Previous/Next track | scrubber | shown |
| Live TV (for example HDHomeRun) | channel name, `Live TV`, TV icon | `Playing channel 2.4 BUZZR`, no count | Previous/Next channel | `Live`, no scrubber | hidden |
| Live radio | station name, `Live radio` | `Playing <station>`, no count | Previous/Next station | `Live` | hidden |
| Video files | title, `Video` | as music | track | scrubber | shown |

Clicking a channel starts it and queues the rest of the list after it, so Next and Previous move along the channel list (channel up and
down). A folder shows `N items` when the server says how many, and nothing otherwise. Filler such as `Unknown` that servers put in empty
artist and album fields is dropped instead of shown. If a folder has more entries than the page shows (the first 200), a line says
`Showing the first 200 of N` instead of silently cutting the list.

## Settings

The Settings section opens with a **Back to the library** button that closes it and scrolls to the library. Per player:

- **Name.**
- **Show on the display when this player is idle:** a Sonos room, a HomePod, anything that is playing, or off. See
  [CONFIGURATION.md](CONFIGURATION.md) and [HOMEPOD.md](HOMEPOD.md).
- **Sleep mode for this player.** See [SLEEP-MODE.md](SLEEP-MODE.md).

Changes are saved as you make them and survive restarts and updates. The same section also finds and adds music servers and shows
the Sonos and HomePod devices the app found.

## Seeking: how it works and its limits

- **MP3 sent untouched (the default).** The app restarts the file at a byte position. If the file has a variable-bit-rate seek
  table (most MP3s from Plex do), the position is looked up in that table; measured on a real 3 minute file, restarts landed within
  about a second of the requested time. Without a table the position is estimated from the average bit rate, which is exact only
  for constant-bit-rate files and can be several seconds off for variable-bit-rate ones. The web server must accept byte-range
  requests (Plex does); one that does not is read from the start up to the position, which is slower.
- **Other formats (ffmpeg).** ffmpeg starts at the requested time.
- **The timeline** moves smoothly between updates (the page asks the app every 1.5 seconds) and matches what the SLIMP3 has played.
- **Not available:** seeking in live streams, and in tracks of unknown length. The Home Assistant media player entity does not
  offer seeking yet; the scrubber is on this page only.
