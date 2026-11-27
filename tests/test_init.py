import logging
from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import HomeAssistant
from pyhon import log
import pytest
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


class ListHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


def test_ha_log_gets_only_anonymized_pyhon_records(
    capsys: pytest.CaptureFixture[str],
) -> None:
    # caplog also captures non-propagating loggers, so collect at the root logger
    handler = ListHandler()
    root = logging.getLogger()
    root.addHandler(handler)
    try:
        log.get_logger("pyhon.test").warning("mac 34-94-54-c6-bc-a8")
    finally:
        root.removeHandler(handler)
    assert [(r.name, r.getMessage()) for r in handler.records] == [
        ("pyhon_ha.test", f"mac {log.mac_hash('34-94-54-c6-bc-a8')}")
    ]
    assert not capsys.readouterr().err
