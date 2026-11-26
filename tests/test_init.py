from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import HomeAssistant
from pytest_homeassistant.common import MockConfigEntry

from custom_components.hon.const import (
    CONF_INTEGRATION,
    CONF_REFRESH_TOKEN,
    DOMAIN,
    INTEGRATION,
)


async def test_setup_marks_existing_entry(hass: HomeAssistant) -> None:
    # An entry created before the marker existed (also the format of Andre0512/hon)
    data = {CONF_EMAIL: "test@example.com", CONF_PASSWORD: "password"}
    entry = MockConfigEntry(domain=DOMAIN, unique_id=data[CONF_EMAIL], data=data)
    entry.add_to_hass(hass)
    hon = MagicMock()
    hon.api.auth.refresh_token = "token"
    with (
        patch("custom_components.hon.Hon") as hon_class,
        patch.object(hass.config_entries, "async_forward_entry_setups", AsyncMock()),
        patch.object(
            hass.config_entries,
            "async_unload_platforms",
            AsyncMock(return_value=True),
        ),
    ):
        hon_class.return_value.create = AsyncMock(return_value=hon)
        assert await hass.config_entries.async_setup(entry.entry_id)
        assert entry.data == {
            **data,
            CONF_REFRESH_TOKEN: "token",
            CONF_INTEGRATION: INTEGRATION,
        }
        assert await hass.config_entries.async_unload(entry.entry_id)
