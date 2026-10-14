# Sleep mode

For white noise, rain and other sleep sounds, a SLIMP3 can turn its display off so it does not glow in a dark bedroom.
It is **off by default** and is a switch you choose, per player or for all players.

## What happens

When what is playing looks like sleep sounds:

1. The normal screen shows for **10 seconds** (so you can see what started).
2. The display says `Going to sleep` over `Screen off in 10`, counting down once a second to 1.
3. The display goes dark (brightness 0%, both lines blank) and **stays dark for as long as that content plays**.

When the content changes to something that does not match (the next track, a different station, a HomePod or Sonos room
changing songs), the normal screen comes straight back at full brightness. Starting music on the SLIMP3, a boot screen or any
other screen also restores the display.

Sleep mode applies to everything the SLIMP3 can show: music it plays itself, and a Sonos room or HomePod it mirrors while idle.

## Turning it on

It is set in one place, the app's **Configuration** tab in Home Assistant (there is no switch on the sidebar page):

- **`sleep_mode`:** `true` turns it on for every player.
- **A `players` entry** can set `sleep_mode` to override that for one player (matched by MAC address).
- **`sleep_keywords`:** the words that count.

Earlier versions (0.11.0 and 0.11.1) had a second switch on the page, saved separately. It is gone, and a value saved from it is ignored,
so the Configuration tab is the only setting.

## What counts as sleep sounds

A keyword list, `sleep_keywords`. Each keyword is matched as a whole word, ignoring case, in the **title, artist or album**
(and, for Sonos, the station). The default list:

`white noise`, `brown noise`, `pink noise`, `balanced noise`, `bright noise`, `dark noise`, `rain`, `rainfall`, `ocean`,
`thunder`, `thunderstorm`, `ambient sounds`, `sleep sounds`, `nature sounds`, `lullaby`, `sleep`

Edit the list in the app configuration to add or remove words. Matching is by whole word, so `rain` matches `Rain Sounds` but
not `Raining Blood` or `Training`.

**Limits of keyword matching:**

- Some songs match. `Purple Rain` contains the word `rain`, and `Sleep Walk` contains `sleep`. Remove those words from
  `sleep_keywords` if that bothers you.
- Anything that does not contain a keyword is not treated as sleep sounds, even if you play it to sleep.
- The list is shared by all players; only the on/off switch is per player.

## Tested and not tested

Tested with the real code driving a simulated display: the keyword matching above, the 10 second show, the countdown, the dark
screen, and the return to the normal screen when a HomePod or Sonos room changes content, for both mirrored content and music
played from this app, with sleep mode on and off. The test shortened the 10 second timers to 1 and 3 seconds. **Not yet
confirmed on the real SLIMP3:** that brightness 0% looks fully dark on your display (the VFD has four brightness levels; if
`0%` is only very dim on yours, tell us and the screen can be blanked another way).
