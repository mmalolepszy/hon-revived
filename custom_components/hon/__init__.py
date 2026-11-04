import logging
from datetime import timedelta
from pathlib import Path
from typing import Any

import voluptuous as vol  # type: ignore[import-untyped]
from aiohttp import ClientConnectionError
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv, aiohttp_client
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.helpers.event import async_track_time_interval
from pyhon import Hon

from .const import DOMAIN, PLATFORMS, MOBILE_ID, CONF_REFRESH_TOKEN
from .recovery import HonStateRecovery

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
        raise ValueError("Missing Config Dir")
    client = Hon(
        email=entry.data[CONF_EMAIL],
        password=entry.data[CONF_PASSWORD],
        mobile_id=MOBILE_ID,
        session=session,
        test_data_path=Path(config_dir),
        refresh_token=entry.data.get(CONF_REFRESH_TOKEN, ""),
    )
    try:
        hon = await client.create()
    except (ClientConnectionError, TimeoutError) as err:
        # DNS and other temporary transport failures can happen before the
        # recovery coordinator exists. Let HA retry setup with its own backoff.
        try:
            await client.close()
        except Exception:
            _LOGGER.debug("Could not close hOn client after failed setup", exc_info=True)
        raise ConfigEntryNotReady(
            "Cannot connect to Haier; check DNS/network connectivity. "
            "Home Assistant will retry automatically."
        ) from err

    # Save the new refresh token
    hass.config_entries.async_update_entry(
        entry, data={**entry.data, CONF_REFRESH_TOKEN: hon.api.auth.refresh_token}
    )

    recovery = HonStateRecovery(hon)
    coordinator: DataUpdateCoordinator[dict[str, bool]] = DataUpdateCoordinator(
        hass, _LOGGER, name=DOMAIN, update_method=recovery.refresh
    )
    coordinator.async_set_updated_data(recovery.available.copy())

    def publish_update(_data: Any) -> None:
        # Pushes notify entity listeners, but do not turn a failed REST refresh
        # into a successful one or postpone the fallback timer.
        hass.loop.call_soon_threadsafe(coordinator.async_update_listeners)

    hon.subscribe_updates(publish_update)

    async def refresh_state(_now: Any) -> None:
        await coordinator.async_refresh()

    # Keep this timer independent of async_set_updated_data calls made by other
    # appliances and UI pickers. A busy washer must not starve a quiet dryer.
    cancel_refresh = async_track_time_interval(
        hass, refresh_state, timedelta(minutes=5)
    )
    entry.async_on_unload(cancel_refresh)

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.unique_id] = {
        "hon": hon,
        "coordinator": coordinator,
        "recovery": recovery,
        "cancel_refresh": cancel_refresh,
    }

    try:
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    except Exception:
        cancel_refresh()
        await recovery.close()
        await hon.close()
        hass.data[DOMAIN].pop(entry.unique_id, None)
        raise

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    refresh_token = hass.data[DOMAIN][entry.unique_id]["hon"].api.auth.refresh_token

    hass.config_entries.async_update_entry(
        entry, data={**entry.data, CONF_REFRESH_TOKEN: refresh_token}
    )
    unload = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload:
        runtime = hass.data[DOMAIN].pop(entry.unique_id)
        runtime["cancel_refresh"]()
        await runtime["recovery"].close()
        hon = runtime["hon"]
        hon.subscribe_updates(None)
        await hon.close()
        if not hass.data[DOMAIN]:
            hass.data.pop(DOMAIN, None)
    return unload
