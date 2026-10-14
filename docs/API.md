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
    "meta": {"title": "...", "artist": "...", "album": "..."},
    "fw": "2.2", "configured": true,
    "index": 3, "queue_len": 31
  }],
  "sources": [{"id": "0", "name": "Plex Media Server: <host>"}]
}
```

`state` is one of `stop`, `buffering`, `play`, `paused`, `rebuffer`, `eof`. `index` is the zero-based
queue position. `position` is seconds of audio the decoder has consumed.

## `GET /api/browse?source=0&id=0&start=0`

Lists the children of a DLNA container (`id=0` is the root). Returns `{"items": [...], "total": N}`.
Each item has `id`, `title`, `container` (true for folders), `artist`, `album`, `duration`, `url`.

## `POST /api/play`

Queue and play. Either play a container from a given track:

```json
{"source": "0", "container": "<container id>", "start_id": "<track id>", "mac": "..."}
```

or a single item: `{"source": "0", "item": "<item id>"}`. Omit `start_id` to start at the first track.
Playback continues through the container automatically. Returns `{"queued": N, "start": index}`.

## `POST /api/control`

```json
{"action": "pause|resume|toggle|stop|next|prev|volume|identify", "value": 40, "mac": "..."}
```

`value` is only used by `volume` (0-100). `identify` runs the boot screens (IP, MAC, prompts) on that player. Returns the player's status.

## `GET /api/sonos`

```json
{"rooms": ["Kitchen", "Living Room"],
 "groups": [{"coordinator": "192.168.1.20", "room": "Living Room", "rooms": ["Living Room"],
             "state": "PLAYING", "station": "CH 55 - SiriusXM Chill",
             "artist": "...", "title": "...", "album": "", "uri": "..."}]}
```

`station` is filled only for radio-type sources. Artist and title are read only while a group is playing.
