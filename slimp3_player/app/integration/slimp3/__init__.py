# SPDX-License-Identifier: GPL-2.0-only
"""SLIMP3: each SLIMP3 player served by the SLIMP3 Player app becomes a media player with a media browser."""
from __future__ import annotations

import logging
from datetime import timedelta

from aiohttp import ClientError, ClientTimeout

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN, PLATFORMS

_LOGGER = logging.getLogger(__name__)


class SlimApi:
    """Thin client for the SLIMP3 Player app's local HTTP API."""

    def __init__(self, hass: HomeAssistant, host: str, port: int) -> None:
        self._session = async_get_clientsession(hass)
        self._base = f"http://{host}:{port}"

    async def get(self, path: str, **params):
        async with self._session.get(self._base + path, params=params or None,
                                     timeout=ClientTimeout(total=20)) as resp:
            if resp.status >= 400:
                raise HomeAssistantError((await resp.text()) or f"HTTP {resp.status}")
            return await resp.json()

    async def post(self, path: str, body: dict):
        async with self._session.post(self._base + path, json=body,
                                      timeout=ClientTimeout(total=30)) as resp:
            if resp.status >= 400:
                raise HomeAssistantError((await resp.text()) or f"HTTP {resp.status}")
            return await resp.json()


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    api = SlimApi(hass, entry.data["host"], entry.data["port"])

    async def _update():
        try:
            return await api.get("/api/state")
        except (ClientError, TimeoutError, ValueError, HomeAssistantError) as err:
            raise UpdateFailed(f"SLIMP3 Player app not reachable: {err}") from err

    kwargs = dict(name=DOMAIN, update_method=_update, update_interval=timedelta(seconds=5))
    try:
        coordinator = DataUpdateCoordinator(hass, _LOGGER, config_entry=entry, **kwargs)
    except TypeError:        # older Home Assistant without the config_entry argument
        coordinator = DataUpdateCoordinator(hass, _LOGGER, **kwargs)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {"api": api, "coordinator": coordinator}
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    if await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id, None)
        return True
    return False
