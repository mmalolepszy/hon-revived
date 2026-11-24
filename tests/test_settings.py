from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.components.climate import ATTR_TEMPERATURE
from pyhon.parameter.enum import HonParameterEnum
from pyhon.parameter.range import HonParameterRange

from custom_components.hon.climate import HonClimateEntity
from custom_components.hon.lock import HonLockEntity
from custom_components.hon.number import HonNumberEntity
from custom_components.hon.select import HonSelectEntity
from custom_components.hon.switch import HonSwitchEntity

RANGE = {"minimumValue": "0", "maximumValue": "20", "incrementValue": "1"}
ENUM = {"enumValues": [1, 2], "defaultValue": "1"}


def create_entity(entity_class: Any, key: str, command: str, parameter: Any) -> Any:
    """Create an entity without its constructor, which needs a whole appliance."""
    entity = entity_class.__new__(entity_class)
    entity.entity_description = SimpleNamespace(key=key, option_list=None)
    entity.coordinator = MagicMock()
    entity.schedule_update_ha_state = MagicMock()
    entity._device = MagicMock(  # pylint: disable=protected-access
        settings={f"{command}.test": parameter}, commands={command: AsyncMock()}
    )
    return entity


@pytest.mark.parametrize(
    ("entity_class", "key", "method", "args"),
    [
        (
            HonClimateEntity,
            "settings.test",
            "async_set_temperature",
            {ATTR_TEMPERATURE: 5},
        ),
        (HonNumberEntity, "settings.test", "async_set_native_value", {"value": 5}),
        (HonSelectEntity, "settings.test", "async_select_option", {"option": "2"}),
        (HonLockEntity, "test", "async_lock", {}),
        (HonLockEntity, "test", "async_unlock", {}),
        (HonSwitchEntity, "test", "async_turn_on", {}),
        (HonSwitchEntity, "test", "async_turn_off", {}),
    ],
)
async def test_setting_sends_only_changed(
    entity_class: Any, key: str, method: str, args: dict[str, Any]
) -> None:
    if entity_class is HonSelectEntity:
        parameter: Any = HonParameterEnum("test", ENUM, "parameters")
    else:
        parameter = HonParameterRange("test", RANGE, "parameters")
    entity = create_entity(entity_class, key, "settings", parameter)
    await getattr(entity, method)(**args)
    command = entity._device.commands["settings"]  # pylint: disable=protected-access
    command.send_specific.assert_awaited_once_with(["test"])
    command.send.assert_not_awaited()


@pytest.mark.parametrize(
    ("entity_class", "method", "args"),
    [
        (HonNumberEntity, "async_set_native_value", {"value": 5}),
        (HonSelectEntity, "async_select_option", {"option": "5"}),
    ],
)
async def test_program_option_sends_whole_program(
    entity_class: Any, method: str, args: dict[str, Any]
) -> None:
    parameter = HonParameterRange("test", RANGE, "parameters")
    entity = create_entity(entity_class, "startProgram.test", "startProgram", parameter)
    await getattr(entity, method)(**args)
    command = entity._device.commands["startProgram"]  # pylint: disable=protected-access
    command.send.assert_awaited_once_with()
    command.send_specific.assert_not_awaited()
