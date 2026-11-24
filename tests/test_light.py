from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, call

import pytest
from homeassistant.components.light import ColorMode
from homeassistant.core import HomeAssistant
from pyhon.parameter.range import HonParameterRange

from custom_components.hon.const import DOMAIN
from custom_components.hon.light import LIGHTS, HonLightEntity


def create_light(hass: HomeAssistant, maximum: int, value: int) -> Any:
    """Create a light with the levels 0..maximum set to the given value."""
    parameter = HonParameterRange(
        "lightStatus",
        {"minimumValue": "0", "maximumValue": str(maximum), "incrementValue": "1"},
        "settings",
    )
    parameter.value = value
    device = SimpleNamespace(
        unique_id="test",
        get={"lightStatus": value}.get,
        settings={"settings.lightStatus": parameter},
        commands={"settings": AsyncMock()},
    )
    hass.data[DOMAIN] = {"test": {"coordinator": None, "hon": None}}
    entry = SimpleNamespace(unique_id="test")
    light = HonLightEntity(hass, entry, device, LIGHTS["DW"][0])
    light.hass = hass
    return light


@pytest.mark.parametrize(
    ("maximum", "color_mode"),
    [
        pytest.param(1, ColorMode.ONOFF, id="onoff"),
        pytest.param(2, ColorMode.BRIGHTNESS, id="brightness"),
    ],
)
async def test_color_mode(
    hass: HomeAssistant, maximum: int, color_mode: ColorMode
) -> None:
    light = create_light(hass, maximum, value=maximum)
    assert light.state_attributes["color_mode"] == color_mode
    assert light.supported_color_modes == {color_mode}

    light = create_light(hass, maximum, value=0)
    assert light.state_attributes["color_mode"] is None


async def test_sends_only_light(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch
) -> None:
    light = create_light(hass, maximum=1, value=0)
    monkeypatch.setattr(light, "schedule_update_ha_state", lambda: None)
    command = light._device.commands["settings"]  # pylint: disable=protected-access
    await light.async_turn_on()
    await light.async_turn_off()
    assert command.send_specific.await_args_list == [call(["lightStatus"])] * 2
    command.send.assert_not_awaited()
