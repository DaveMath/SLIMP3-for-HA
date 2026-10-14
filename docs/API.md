# HTTP API

The sidebar page is a thin client over this API. It is served through Home Assistant ingress on
port 8099 and **only accepts connections from Home Assistant's internal network** (`127.0.0.0/8` and
`172.30.32.0/23`). Other addresses get `403`. All paths below are relative to the app's root, which
matters behind ingress (the page uses relative URLs).

For local development, set `SLIMP3_ALLOW_ALL=1` to lift the address check.

`mac` is optional everywhere; when omitted, the first connected player is used.

## `GET /api/state`

```json
{
  "players": [{
    "mac": "00:04:20:12:34:56", "name": "Den", "ip": "192.168.1.50",
    "state": "play", "position": 41.2, "volume": 40,
    "duration": 188.0, "seekable": true, "sleep_mode": false,
    "meta": {"title": "...", "artist": "...", "album": "..."},
    "fw": "2.2", "configured": true,
    "index": 3, "queue_len": 31
  }],
  "sources": [{"id": "1a2b3c4d", "name": "Plex Media Server: <host>"}],
  "heard": [{"ip": "192.168.1.50", "ago": 12}], "uptime": 340, "udp_port": 3483, "sonos_enabled": true, "version": "0.11.0",
  "instance_id": "e70a23d7...", "integration": {"installed": true, "version": "0.8.0", "restart_needed": false}
}
```

`instance_id` is a stable identity for this app (the integration uses it as its unique id). `integration` reports whether the
Home Assistant integration was copied into the Home Assistant configuration folder. `heard` lists addresses that sent a discovery or hello packet recently (what the page shows while it is
looking for a player). `state` is one of `stop`, `buffering`, `play`, `paused`, `rebuffer`, `eof`. `index` is the zero-based
queue position. `position` is seconds into the track (it includes where a seek started). `duration` is the track length in seconds, or null if unknown. `seekable` is true when
`seek` will work (not live, length known). `sleep_mode` is this player's effective sleep mode (read-only; it comes from the configuration). `version` is the app's version. Every response carries `Cache-Control: no-store`.

## Music servers

- `GET /api/sources`: the music servers, `[{"id", "name", "url", "origin": "config" | "added"}]`.
- `POST /api/sources` with `{"url": "192.168.1.10"}`: adds a server. A bare address is enough; the app tries the
  usual DLNA ports and descriptor paths. Returns the server, or `400` with a readable reason.
- `DELETE /api/sources?id=<id>`: removes a server that was added on the page (`400` for configuration servers).
- `GET /api/discover/servers`: searches the network (takes a few seconds) and returns
  `[{"url", "name", "kind", "added"}]`; `kind` is, for example, `Media server`, `TV tuner`, `Sonos` or
  `Plex on this host`.

## `GET /api/browse?source=<id>&id=0&start=0[&title=1]`

Lists the children of a DLNA container (`id=0` is the root). With `title=1` the reply also carries the folder's own `title`. Returns `{"items": [...], "total": N}`.
Each item has `id`, `title`, `container` (true for folders), `artist`, `album`, `duration`, `url`.

## `POST /api/play`

Queue and play. Either play a container from a given track:

```json
{"source": "0", "container": "<container id>", "start_id": "<track id>", "mac": "..."}
```

or a single item: `{"source": "0", "item": "<item id>"}`. Omit `start_id` to start at the first track.
Playback continues through the container automatically. Returns `{"queued": N, "start": index}`.

`POST /api/play` returns what started, for the caller to word correctly:

```json
{"queued": 98, "start": 3, "remaining": 94, "title": "2.4 BUZZR", "kind": "Live TV", "live": true}
```

`remaining` is how many items follow the one that starts now. `kind` is `Live TV`, `Live radio` or empty. `live` is true for live sources, and a caller
should not show a track count for them. `GET /api/browse` also returns `live` (true when every playable item in the folder is live) and `total`
(the server's count, which can exceed the 200 items returned).

## `POST /api/control`

```json
{"action": "pause|resume|toggle|stop|next|prev|volume|seek|identify", "value": 40, "mac": "..."}
```

`value` is used by `volume` (0-100) and `seek` (seconds from the start of the track; clamped to just before the end). `seek` returns 400 if the
item is live or its length is not known. `identify` runs the boot screens (IP, MAC, prompts) on that player. Returns the player's status.

## `POST /api/player`

```json
{"mac": "...", "name": "Den", "sonos_room": "Living Room", "apple_room": "", "show_sonos": true}
```

Saves a player's name and Sonos room (any subset of the fields) and applies it immediately. Saved values
override the options file. An empty `sonos_room` means any playing room; `show_sonos: false` turns the Sonos
display off for that player.

## `GET /api/apple`

```json
{"enabled": true, "available": true,
 "devices": [{"name": "Kitchen", "model": "HomePod", "connected": false, "state": ""}]}
```

The HomePods found on the network. `connected`, `state` (`PLAYING`, `PAUSED`, `STOPPED`), `title`, `artist`, `app` and `age` (seconds since the
HomePod last reported) are filled only while the app is connected to that HomePod, which happens only while a SLIMP3 is idle and wants to show
it. `error` is the last reason a connection failed. At the top level, `available` is false when the HomePod library could not be loaded and `error`
says why.

## `GET /api/sonos`

```json
{"rooms": ["Kitchen", "Living Room"], "discovered": ["192.168.1.20"],
 "groups": [{"coordinator": "192.168.1.20", "room": "Living Room", "rooms": ["Living Room"],
             "state": "PLAYING", "station": "CH 55 - SiriusXM Chill",
             "artist": "...", "title": "...", "album": "", "uri": "..."}]}
```

`discovered` lists the Sonos addresses found by the network search. `station` is filled only for radio-type sources. Artist and title are read only while a group is playing.
