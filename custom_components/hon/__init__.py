import logging
from datetime import timedelta
from pathlib import Path
from typing import Any

import voluptuous as vol  # type: ignore[import-untyped]
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv, aiohttp_client
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from pyhon import Hon

from .const import DOMAIN, PLATFORMS, MOBILE_ID, CONF_REFRESH_TOKEN

_LOGGER = logging.getLogger(__name__)

HON_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_EMAIL): cv.string,
        vol.Required(CONF_PASSWORD): cv.string,
    }
)

CONFIG_SCHEMA = vol.Schema(
    {DOMAIN: vol.Schema(vol.All(cv.ensure_list, [HON_SCHEMA]))},
    extra=vol.ALLOW_EXTRA,
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    session = aiohttp_client.async_get_clientsession(hass)
    if (config_dir := hass.config.config_dir) is None:
        raise ConfigEntryNotReady("Missing Config Dir")
    try:
        hon = await Hon(
            email=entry.data[CONF_EMAIL],
            password=entry.data[CONF_PASSWORD],
            mobile_id=MOBILE_ID,
            session=session,
            test_data_path=Path(config_dir),
            refresh_token=entry.data.get(CONF_REFRESH_TOKEN, ""),
        ).create()
    except Exception as exc:
        raise ConfigEntryNotReady(f"Failed to connect to hOn API: {exc}") from exc

    # Save the new refresh token
    hass.config_entries.async_update_entry(
        entry, data={**entry.data, CONF_REFRESH_TOKEN: hon.api.auth.refresh_token}
    )

    async def _async_update_data() -> dict[str, Any]:
        for appliance in hon.appliances:
            await appliance.update()
        return {}

    coordinator: DataUpdateCoordinator[dict[str, Any]] = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name=DOMAIN,
        update_interval=timedelta(minutes=5),
        update_method=_async_update_data,
    )
    hon.subscribe_updates(coordinator.async_set_updated_data)

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.unique_id] = {"hon": hon, "coordinator": coordinator}

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    refresh_token = hass.data[DOMAIN][entry.unique_id]["hon"].api.auth.refresh_token

    hass.config_entries.async_update_entry(
        entry, data={**entry.data, CONF_REFRESH_TOKEN: refresh_token}
    )
    unload = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload:
        hon = hass.data[DOMAIN].pop(entry.unique_id, {}).get("hon")
        if hon is not None:
            hon.subscribe_updates(None)  # type: ignore[arg-type]
            await hon.close()
        if not hass.data[DOMAIN]:
            hass.data.pop(DOMAIN, None)
    return unload
