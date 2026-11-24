import importlib
import sys
from unittest.mock import patch

import pytest
from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.hon.const import DOMAIN

USER_INPUT = {CONF_EMAIL: "test@example.com", CONF_PASSWORD: "password"}


def test_import_without_deprecation_warnings(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    name = "custom_components.hon.config_flow"
    monkeypatch.delitem(sys.modules, name, raising=False)
    importlib.import_module(name)
    assert not caplog.records


async def test_user_step(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    with patch("custom_components.hon.async_setup_entry", return_value=True):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], USER_INPUT
        )
        await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == USER_INPUT[CONF_EMAIL]
    assert result["data"] == USER_INPUT
