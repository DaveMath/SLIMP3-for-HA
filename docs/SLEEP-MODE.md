# Sleep mode

For white noise, rain and other sleep sounds, a SLIMP3 can turn its display off so it does not glow in a dark bedroom. It is **off by default**.

## What happens

When what is playing looks like sleep sounds:

1. The normal screen shows for **10 seconds**, so you can see what started.
2. The display says `Going to sleep` over `Screen off in 10`, counting down once a second to 1.
3. The display goes dark (brightness 0%, both lines blank) and **stays dark for as long as that content plays**.

When the content changes to something that does not match (the next track, a different station, a speaker changing songs), the normal screen comes straight back at full brightness. Starting music on the SLIMP3, a boot screen or any other screen also restores the display.

It applies to everything the SLIMP3 can show: music it plays itself, and a Sonos room, HomePod or Google Cast speaker it mirrors while idle (see [SPEAKERS.md](SPEAKERS.md)).

## Turning it on

Set it on the app's **Configuration** tab in Home Assistant, the only place it is set:

- **`sleep_mode`**: `true` turns it on for every player.
- **A `players` entry** can set `sleep_mode` to override that for one player (matched by MAC address).
- **`sleep_keywords`**: the words that count.

## What counts as sleep sounds

A keyword list, `sleep_keywords`. Each keyword is matched as a whole word, ignoring case, in the **title, artist or album** (and, for Sonos, the station). The default list:

`white noise`, `brown noise`, `pink noise`, `balanced noise`, `bright noise`, `dark noise`, `rain`, `rainfall`, `ocean`, `thunder`, `thunderstorm`, `ambient sounds`, `sleep sounds`, `nature sounds`, `lullaby`, `sleep`

Edit the list in the app configuration to add or remove words. Matching is by whole word, so `rain` matches `Rain Sounds` but not `Raining Blood` or `Training`.

Limits of keyword matching:

- Some songs match. `Purple Rain` contains the word `rain`, and `Sleep Walk` contains `sleep`. Remove those words from the list if that bothers you.
- Anything without a keyword is not treated as sleep sounds, even if you play it to sleep.
- The list is shared by all players; only the on/off switch is per player.

## How it works

One small watcher per display screen (the music screen and the speaker mirror screen share it). Each time the screen refreshes it checks whether the title, artist, album or station contains a keyword. While one does, it counts from the first match: 10 seconds of the normal screen, 10 seconds of countdown, then a blank frame at brightness 0%. While dark it sends one packet every 30 seconds in case the display lost the setting; when the match goes away the next normal frame restores brightness and redraws both lines.
