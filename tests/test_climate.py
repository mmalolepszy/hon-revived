import importlib
import sys
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest
from homeassistant.core import HomeAssistant
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
