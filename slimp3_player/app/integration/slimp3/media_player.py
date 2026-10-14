# SPDX-License-Identifier: GPL-2.0-only
"""Each SLIMP3 as a media player, with a browsable library of the music servers added to the app."""
from __future__ import annotations

from typing import Any

from homeassistant.components.media_player import (
    BrowseMedia,
    MediaClass,
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
    MediaType,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN

FEATURES = (
    MediaPlayerEntityFeature.PLAY
    | MediaPlayerEntityFeature.PAUSE
    | MediaPlayerEntityFeature.STOP
    | MediaPlayerEntityFeature.NEXT_TRACK
    | MediaPlayerEntityFeature.PREVIOUS_TRACK
    | MediaPlayerEntityFeature.VOLUME_SET
    | MediaPlayerEntityFeature.BROWSE_MEDIA
    | MediaPlayerEntityFeature.PLAY_MEDIA
)
STATES = {
    "play": MediaPlayerState.PLAYING,
    "paused": MediaPlayerState.PAUSED,
    "buffering": MediaPlayerState.BUFFERING,
    "rebuffer": MediaPlayerState.BUFFERING,
}


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    store = hass.data[DOMAIN][entry.entry_id]
    coordinator, api = store["coordinator"], store["api"]
    known: set[str] = set()

    @callback
    def _add_new() -> None:
        new = []
        for player in (coordinator.data or {}).get("players", []):
            if player["mac"] not in known:
                known.add(player["mac"])
                new.append(SlimPlayer(coordinator, api, player["mac"]))
        if new:
            async_add_entities(new)

    _add_new()
    entry.async_on_unload(coordinator.async_add_listener(_add_new))   # players that connect later


def _folder_class(item: dict) -> MediaClass:
    cls = (item.get("class") or "").lower()
    for key, media_class in (("album", MediaClass.ALBUM), ("artist", MediaClass.ARTIST),
                             ("playlist", MediaClass.PLAYLIST), ("genre", MediaClass.GENRE)):
        if key in cls:
            return media_class
    return MediaClass.DIRECTORY


def _playable_folder(item: dict) -> bool:
    cls = (item.get("class") or "").lower()
    return "album" in cls or "playlist" in cls


class SlimPlayer(CoordinatorEntity, MediaPlayerEntity):
    """One SLIMP3 network music player."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_supported_features = FEATURES

    def __init__(self, coordinator, api, mac: str) -> None:
        super().__init__(coordinator)
        self._api = api
        self._mac = mac
        self._attr_unique_id = mac

    # ---- state (from memory only) ------------------------------------------------
    @property
    def _p(self) -> dict | None:
        for player in (self.coordinator.data or {}).get("players", []):
            if player["mac"] == self._mac:
                return player
        return None

    @property
    def available(self) -> bool:
        return super().available and self._p is not None

    @property
    def device_info(self) -> DeviceInfo:
        p = self._p or {}
        return DeviceInfo(
            identifiers={(DOMAIN, self._mac)},
            name=p.get("name") or f"SLIMP3 {self._mac[-5:].replace(':', '')}",
            manufacturer="Slim Devices",
            model="SLIMP3",
            sw_version=p.get("fw") or None,
        )

    @property
    def state(self) -> MediaPlayerState | None:
        p = self._p
        return STATES.get(p["state"], MediaPlayerState.IDLE) if p else None

    def _meta(self, key: str) -> str | None:
        p = self._p
        return ((p or {}).get("meta") or {}).get(key) or None if p and p["state"] != "stop" else None

    @property
    def media_title(self) -> str | None:
        return self._meta("title")

    @property
    def media_artist(self) -> str | None:
        # a channel has no artist: show where it comes from instead of a blank line
        return self._meta("artist") or self._meta("source")

    @property
    def app_name(self) -> str | None:
        return self._meta("source")

    @property
    def media_content_type(self) -> MediaType | str | None:
        p = self._p
        return MediaType.CHANNEL if p and (p.get("meta") or {}).get("kind") else MediaType.MUSIC

    @property
    def media_album_name(self) -> str | None:
        return self._meta("album")

    @property
    def volume_level(self) -> float | None:
        p = self._p
        return p["volume"] / 100 if p else None

    # ---- commands ----------------------------------------------------------------
    async def _refresh_soon(self) -> None:
        """Refresh now, and again shortly after: the app starts a stream a moment after it accepts a command."""
        await self.coordinator.async_request_refresh()
        if self.hass is not None:
            async def _later(_now) -> None:
                await self.coordinator.async_request_refresh()
            async_call_later(self.hass, 1.5, _later)

    async def _control(self, action: str, **extra: Any) -> None:
        await self._api.post("/api/control", {"mac": self._mac, "action": action, **extra})
        await self._refresh_soon()

    async def async_media_play(self) -> None:
        await self._control("resume")

    async def async_media_pause(self) -> None:
        await self._control("pause")

    async def async_media_stop(self) -> None:
        await self._control("stop")

    async def async_media_next_track(self) -> None:
        await self._control("next")

    async def async_media_previous_track(self) -> None:
        await self._control("prev")

    async def async_set_volume_level(self, volume: float) -> None:
        await self._control("volume", value=round(volume * 100))

    # ---- media browser: music servers > folders > tracks -----------------------------
    async def async_browse_media(self, media_content_type: str | None = None,
                                 media_content_id: str | None = None) -> BrowseMedia:
        if not media_content_id or media_content_id == "library":
            servers = await self._api.get("/api/sources")
            return BrowseMedia(
                media_class=MediaClass.DIRECTORY, media_content_id="library", media_content_type="library",
                title="Music servers", can_play=False, can_expand=True,
                children=[BrowseMedia(
                    media_class=MediaClass.DIRECTORY, media_content_id=f"s:{s['id']}:0",
                    media_content_type="directory", title=s["name"], can_play=False, can_expand=True)
                    for s in servers],
            )
        try:
            _, sid, oid = media_content_id.split(":", 2)
        except ValueError as err:
            raise HomeAssistantError(f"Unknown folder: {media_content_id}") from err
        data = await self._api.get("/api/browse", source=sid, id=oid, title="1")
        children = []
        for item in data["items"]:
            if item["container"]:
                children.append(BrowseMedia(
                    media_class=_folder_class(item), media_content_id=f"s:{sid}:{item['id']}",
                    media_content_type="directory", title=item["title"] or "Folder",
                    can_play=_playable_folder(item), can_expand=True))
            else:
                label = " - ".join(x for x in (item.get("artist"), item.get("title")) if x)
                children.append(BrowseMedia(
                    media_class=MediaClass.TRACK, media_content_id=f"t:{sid}:{oid}:{item['id']}",
                    media_content_type=MediaType.MUSIC, title=label or "Track",
                    can_play=True, can_expand=False))
        return BrowseMedia(
            media_class=MediaClass.DIRECTORY, media_content_id=media_content_id, media_content_type="directory",
            title=data.get("title") or "Music", can_play=any(not i["container"] for i in data["items"]),
            can_expand=True, children=children,
        )

    async def async_play_media(self, media_type: str, media_id: str, **kwargs: Any) -> None:
        try:
            kind, sid, rest = media_id.split(":", 2)
            if kind == "s":                                   # a whole album or playlist
                body = {"source": sid, "container": rest}
            elif kind == "t":                                 # one track: play its folder from here on
                container, item = rest.rsplit(":", 1)
                body = {"source": sid, "container": container, "start_id": item}
            else:
                raise ValueError(kind)
        except ValueError as err:
            raise HomeAssistantError(f"Cannot play {media_id}: pick a track or album from the SLIMP3 library") from err
        await self._api.post("/api/play", {**body, "mac": self._mac})
        await self._refresh_soon()
