from types import SimpleNamespace
from typing import Any

import pytest
from pyhon.parameter.enum import HonParameterEnum
from pyhon.parameter.fixed import HonParameterFixed
from pyhon.parameter.range import HonParameterRange

from custom_components.hon.const import DOMAIN
from custom_components.hon.switch import (
    SWITCHES,
    HonControlSwitchEntity,
    HonControlSwitchEntityDescription,
    sync_dry_program_flag,
)

APPLIANCE_TYPES = ["WM", "TD", "WD"]


def cycle_switch(appliance_type: str, **data: Any) -> HonControlSwitchEntity:
    """Create the cycle switch of an appliance reporting the given data."""
    description = next(
        description
        for description in SWITCHES[appliance_type]
        if isinstance(description, HonControlSwitchEntityDescription)
        and description.key == "active"
    )
    device = SimpleNamespace(unique_id="test", get=data.get)
    hass = SimpleNamespace(data={DOMAIN: {"test": {"coordinator": None, "hon": None}}})
    entry = SimpleNamespace(unique_id="test")
    return HonControlSwitchEntity(hass, entry, device, description)


@pytest.mark.parametrize("appliance_type", APPLIANCE_TYPES)
@pytest.mark.parametrize("mach_mode", [2, 3, 4, 5, 9])
def test_on_during_cycle(appliance_type: str, mach_mode: int) -> None:
    assert cycle_switch(appliance_type, machMode=mach_mode, active=False).is_on is True


@pytest.mark.parametrize("appliance_type", APPLIANCE_TYPES)
@pytest.mark.parametrize("mach_mode", [1, 7])
def test_off_outside_cycle_despite_active_flag(
    appliance_type: str, mach_mode: int
) -> None:
    assert cycle_switch(appliance_type, machMode=mach_mode, active=True).is_on is False


@pytest.mark.parametrize("appliance_type", APPLIANCE_TYPES)
@pytest.mark.parametrize("active", [True, False])
def test_follows_active_flag_without_mach_mode(
    appliance_type: str, active: bool
) -> None:
    assert cycle_switch(appliance_type, active=active).is_on is active


def start_command(**parameters: Any) -> Any:
    """Create a startProgram command with the given parameters."""
    return SimpleNamespace(parameters=parameters)


def washing_program(dry_level: str) -> Any:
    """Create a washer dryer washing program (e.g. cottons) as hOn reports it."""
    level = HonParameterEnum(
        "dryLevel",
        {"typology": "enum", "enumValues": "0|2|3|4", "defaultValue": "4"},
        "parameters",
    )
    level.value = dry_level
    flag = HonParameterRange(
        "dryProgFlag",
        {
            "typology": "range",
            "minimumValue": "0",
            "maximumValue": "1",
            "incrementValue": "1",
            "defaultValue": "0",
        },
        "parameters",
    )
    return start_command(dryLevel=level, dryProgFlag=flag)


@pytest.mark.parametrize(("dry_level", "flag"), [("2", "1"), ("3", "1"), ("4", "1")])
def test_washing_program_with_dry_level_sets_dry_flag(
    dry_level: str, flag: str
) -> None:
    command = washing_program(dry_level)
    sync_dry_program_flag(command)
    assert str(command.parameters["dryProgFlag"].value) == flag


def test_washing_program_without_drying_clears_dry_flag() -> None:
    command = washing_program("0")
    command.parameters["dryProgFlag"].value = 1
    sync_dry_program_flag(command)
    assert str(command.parameters["dryProgFlag"].value) == "0"


def test_drying_program_keeps_fixed_dry_flag() -> None:
    level = HonParameterEnum(
        "dryLevel", {"typology": "enum", "enumValues": "2|3|4"}, "parameters"
    )
    flag = HonParameterFixed(
        "dryProgFlag", {"typology": "fixed", "fixedValue": "1"}, "parameters"
    )
    command = start_command(dryLevel=level, dryProgFlag=flag)
    sync_dry_program_flag(command)
    assert str(command.parameters["dryProgFlag"].value) == "1"


def test_program_without_dry_parameters_is_untouched() -> None:
    command = start_command()
    sync_dry_program_flag(command)
    assert command.parameters == {}
