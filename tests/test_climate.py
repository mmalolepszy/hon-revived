import importlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest
from homeassistant.components.climate.const import HVACMode
from homeassistant.core import HomeAssistant
from pyhon.appliance import HonAppliance
from pyhon.connection.api import TestAPI as FakeAPI
from pyhon.parameter.range import HonParameterRange

from custom_components.hon.climate import (
    CLIMATES,
    HonACClimateEntity,
    HonClimateEntity,
)
from custom_components.hon.const import DOMAIN

ENTITIES = [
    pytest.param(
        HonACClimateEntity, CLIMATES["AC"][0], "tempSel", "tempIndoor", id="AC"
    ),
    pytest.param(
        HonClimateEntity, CLIMATES["OV"][0], "settings.tempSel", "temp", id="OV"
    ),
]


def create_entity(
    hass: HomeAssistant, entity_class: Any, description: Any, data: dict[str, Any]
) -> Any:
    temperature = MagicMock(spec=HonParameterRange, min=16, max=30, step=1)
    device = SimpleNamespace(
        unique_id="test",
        get=data.get,
        settings={
            "settings.tempSel": temperature,
            "settings.machMode": SimpleNamespace(values=["0"]),
            "startProgram.program": SimpleNamespace(values=[]),
        },
        commands={"startProgram": SimpleNamespace(categories={})},
    )
    hass.data[DOMAIN] = {"test": {"coordinator": None, "hon": None}}
    entry = SimpleNamespace(unique_id="test")
    entity = entity_class(hass, entry, device, description)
    entity.hass = hass
    return entity


def test_import_without_deprecation_warnings(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    name = "custom_components.hon.climate"
    monkeypatch.delitem(sys.modules, name)
    importlib.import_module(name)
    assert not caplog.records


@pytest.mark.parametrize(("entity_class", "description", "target", "current"), ENTITIES)
async def test_temperatures(
    hass: HomeAssistant,
    caplog: pytest.LogCaptureFixture,
    entity_class: Any,
    description: Any,
    target: str,
    current: str,
) -> None:
    caplog.clear()
    data = {
        target: 24.0,
        current: 21.5,
        "windSpeed": 1,
        "windDirectionHorizontal": 0,
        "windDirectionVertical": 0,
    }
    entity = create_entity(hass, entity_class, description, data)
    assert entity.state_attributes["temperature"] == 24.0
    assert entity.state_attributes["current_temperature"] == 21.5

    data[target] = 25.0
    data[current] = None
    assert entity.state_attributes["temperature"] == 25.0
    assert entity.state_attributes["current_temperature"] is None
    assert not [r for r in caplog.records if r.levelname == "WARNING"]


def fixed(value: str) -> dict[str, Any]:
    return {"typology": "fixed", "mandatory": 1, "fixedValue": value}


def enum(values: list[int], default: str) -> dict[str, Any]:
    return {
        "typology": "enum",
        "mandatory": 1,
        "enumValues": values,
        "defaultValue": default,
    }


def temp_sel() -> dict[str, Any]:
    return {
        "typology": "range",
        "mandatory": 1,
        "minimumValue": "16",
        "maximumValue": "30",
        "incrementValue": "1",
        "defaultValue": "22",
    }


def command(on_off: str, mach_mode: Any, wind_speed: Any) -> dict[str, Any]:
    return {
        "description": "",
        "protocolType": "",
        "parameters": {
            "onOffStatus": fixed(on_off),
            "machMode": mach_mode,
            "windSpeed": wind_speed,
            "tempSel": temp_sel(),
        },
    }


@pytest.fixture(name="sent")
def fixture_sent(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, dict[str, Any]]]:
    sent: list[tuple[str, dict[str, Any]]] = []

    async def send_command(
        _api: Any, _appliance: Any, name: str, parameters: Any, *_args: Any
    ) -> bool:
        sent.append((name, dict(parameters)))
        return True

    monkeypatch.setattr(FakeAPI, "send_command", send_command)
    return sent


@pytest.fixture(name="climate")
async def fixture_climate(hass: HomeAssistant, tmp_path: Path) -> HonACClimateEntity:
    all_modes = enum([0, 1, 2, 4, 6], "0")
    all_speeds = enum([1, 2, 3, 5], "5")
    commands = {
        "settings": {"setParameters": command("1", all_modes, all_speeds)},
        "startProgram": {
            "PROGRAMS.AC.IOT_HEAT": command("1", fixed("4"), all_speeds),
            "PROGRAMS.AC.IOT_FAN": command("1", fixed("6"), enum([1, 2, 3], "3")),
        },
        "stopProgram": command("0", all_modes, all_speeds),
    }
    state = {"onOffStatus": "1", "machMode": "4", "windSpeed": "5", "tempSel": "25"}
    parameters = {name: {"parNewVal": value} for name, value in state.items()}
    data = tmp_path / "ac_1"
    data.mkdir()
    (data / "commands.json").write_text(json.dumps(commands))
    attributes = {"shadow": {"parameters": parameters}}
    (data / "attributes.json").write_text(json.dumps(attributes))
    info = {"applianceTypeName": "AC", "applianceModelId": 1, "nickName": "AC"}
    device = HonAppliance(FakeAPI(tmp_path), info)
    await device.load_commands()
    await device.load_attributes()
    device.sync_params_to_command("settings")
    hass.data[DOMAIN] = {"test": {"coordinator": MagicMock(), "hon": None}}
    entry: Any = SimpleNamespace(unique_id="test")
    entity = HonACClimateEntity(hass, entry, device, CLIMATES["AC"][0])
    entity.hass = hass
    entity.schedule_update_ha_state = MagicMock()  # type: ignore[method-assign]
    return entity


@pytest.mark.parametrize("hvac_mode", [True, False])
async def test_turn_off_keeps_settings(
    climate: HonACClimateEntity,
    sent: list[tuple[str, dict[str, Any]]],
    hvac_mode: bool,
) -> None:
    if hvac_mode:
        await climate.async_set_hvac_mode(HVACMode.OFF)
    else:
        await climate.async_turn_off()
    parameters = {
        "onOffStatus": "0",
        "machMode": "4",
        "windSpeed": "5",
        "tempSel": "25",
    }
    assert sent == [("stopProgram", parameters)]
    assert climate.hvac_mode == HVACMode.OFF


async def test_turn_on_keeps_settings(
    climate: HonACClimateEntity, sent: list[tuple[str, dict[str, Any]]]
) -> None:
    await climate.async_turn_off()
    await climate.async_turn_on()
    parameters = {
        "onOffStatus": "1",
        "machMode": "4",
        "windSpeed": "5",
        "tempSel": "25",
    }
    assert sent[1] == ("settings", parameters)
    assert climate.hvac_mode == HVACMode.HEAT


async def test_mode_keeps_only_allowed_settings(
    climate: HonACClimateEntity, sent: list[tuple[str, dict[str, Any]]]
) -> None:
    await climate.async_set_hvac_mode(HVACMode.FAN_ONLY)
    parameters = {
        "onOffStatus": "1",
        "machMode": "6",
        "windSpeed": "3",
        "tempSel": "25",
    }
    assert sent == [("settings", parameters)]


async def test_mode_after_preset(
    climate: HonACClimateEntity, sent: list[tuple[str, dict[str, Any]]]
) -> None:
    await climate.async_set_preset_mode("iot_fan")
    await climate.async_set_hvac_mode(HVACMode.HEAT)
    parameters = {
        "onOffStatus": "1",
        "machMode": "4",
        "windSpeed": "3",
        "tempSel": "22",
    }
    assert sent[1] == ("settings", parameters)
