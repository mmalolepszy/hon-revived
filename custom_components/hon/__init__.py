import logging
from pathlib import Path
from typing import Any

import voluptuous as vol  # type: ignore[import-untyped]
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.helpers import config_validation as cv, aiohttp_client
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from pyhon import Hon

from .const import DOMAIN, PLATFORMS, MOBILE_ID, CONF_REFRESH_TOKEN

_LOGGER = logging.getLogger(__name__)


def _patch_pyhon_statistics() -> None:
    """Patch pyhon HonAPI.load_statistics to use the official statistics retrieve endpoint for heat pumps (AW)."""
    try:
        from pyhon.connection.api import HonAPI
        from pyhon import const as pyhon_const

        if getattr(HonAPI, "_aw_stats_patched", False):
            return

        original_load_statistics = HonAPI.load_statistics

        async def patched_load_statistics(self: Any, appliance: Any) -> dict[str, Any]:
            if getattr(appliance, "appliance_type", "") == "AW":
                url = f"{pyhon_const.API_URL}/statistics/v1/retrieve"
                params = {
                    "macAddress": appliance.mac_address,
                    "applianceType": appliance.appliance_type,
                }
                try:
                    if hasattr(self, "_hon") and self._hon:
                        async with self._hon.get(url, params=params) as response:
                            if response.status == 200:
                                payload = (await response.json()).get("payload", {})
                                return payload
                except Exception as exc:
                    _LOGGER.warning("Failed to retrieve AW statistics: %s", exc)
            return await original_load_statistics(self, appliance)

        HonAPI.load_statistics = patched_load_statistics
        HonAPI._aw_stats_patched = True
    except Exception as exc:
        _LOGGER.debug("Could not patch pyhon HonAPI: %s", exc)


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
    _patch_pyhon_statistics()
    session = aiohttp_client.async_get_clientsession(hass)
    if (config_dir := hass.config.config_dir) is None:
        raise ValueError("Missing Config Dir")
    hon = await Hon(
        email=entry.data[CONF_EMAIL],
        password=entry.data[CONF_PASSWORD],
        mobile_id=MOBILE_ID,
        session=session,
        test_data_path=Path(config_dir),
        refresh_token=entry.data.get(CONF_REFRESH_TOKEN, ""),
    ).create()

    # Save the new refresh token
    hass.config_entries.async_update_entry(
        entry, data={**entry.data, CONF_REFRESH_TOKEN: hon.api.auth.refresh_token}
    )

    coordinator: DataUpdateCoordinator[dict[str, Any]] = DataUpdateCoordinator(
        hass, _LOGGER, name=DOMAIN
    )
    hon.subscribe_updates(coordinator.async_set_updated_data)

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.unique_id] = {"hon": hon, "coordinator": coordinator}

    # Periodic update for heat pump energy statistics (every 30 minutes)
    async def async_refresh_heatpump_statistics(*_: Any) -> None:
        for appliance in hon.appliances:
            if getattr(appliance, "appliance_type", "") == "AW":
                try:
                    await appliance.load_statistics()
                except Exception as exc:
                    _LOGGER.warning("Periodic AW statistics refresh failed: %s", exc)
        coordinator.async_set_updated_data({})

    try:
        from homeassistant.helpers.event import async_track_time_interval
        from datetime import timedelta
        entry.async_on_unload(
            async_track_time_interval(
                hass, async_refresh_heatpump_statistics, timedelta(minutes=30)
            )
        )
    except Exception as exc:
        _LOGGER.debug("Could not schedule periodic statistics refresh: %s", exc)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    refresh_token = hass.data[DOMAIN][entry.unique_id]["hon"].api.auth.refresh_token

    hass.config_entries.async_update_entry(
        entry, data={**entry.data, CONF_REFRESH_TOKEN: refresh_token}
    )
    unload = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload:
        if not hass.data[DOMAIN]:
            hass.data.pop(DOMAIN, None)
    return unload
