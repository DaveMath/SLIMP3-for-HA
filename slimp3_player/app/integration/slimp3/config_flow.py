# SPDX-License-Identifier: GPL-2.0-only
"""Config flow: find the SLIMP3 Player app and set up the integration."""
from __future__ import annotations

import voluptuous as vol
from aiohttp import ClientError, ClientTimeout

from homeassistant import config_entries
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import DEFAULT_HOST, DEFAULT_PORT, DOMAIN

# The app listens on the host network; which address Home Assistant Core reaches it by depends on the install.
FALLBACK_HOSTS = ["127.0.0.1", "172.30.32.1", "homeassistant", "homeassistant.local"]


async def _probe(hass, host: str, port: int):
    session = async_get_clientsession(hass)
    try:
        async with session.get(f"http://{host}:{port}/api/state", timeout=ClientTimeout(total=4)) as resp:
            if resp.status != 200:
                return None
            data = await resp.json()
            return data if isinstance(data, dict) and data.get("instance_id") else None
    except (ClientError, TimeoutError, ValueError):
        return None


class SlimConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the setup dialog."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            host, port = user_input["host"].strip(), int(user_input["port"])
            for candidate in [host] + [h for h in FALLBACK_HOSTS if h != host]:
                data = await _probe(self.hass, candidate, port)
                if data:
                    await self.async_set_unique_id(data["instance_id"])
                    self._abort_if_unique_id_configured(updates={"host": candidate, "port": port})
                    return self.async_create_entry(title="SLIMP3", data={"host": candidate, "port": port})
            errors["base"] = "cannot_connect"
        schema = vol.Schema({
            vol.Required("host", default=DEFAULT_HOST): str,
            vol.Required("port", default=DEFAULT_PORT): int,
        })
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)
