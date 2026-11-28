from types import SimpleNamespace
from typing import Any

import pytest
from pyhon.parameter.fixed import HonParameterFixed
from pyhon.parameter.range import HonParameterRange

from custom_components.hon.const import DOMAIN
from custom_components.hon.switch import (
    SWITCHES,
    HonControlSwitchEntity,
    HonConfigSwitchEntity,
    HonControlSwitchEntityDescription,
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


def dry_flag_setting(fixed: bool = False) -> Any:
    """dryProgFlag of a washing program (adjustable 0/1) or a drying program (fixed 1)."""
    if fixed:
        return HonParameterFixed(
            "dryProgFlag", {"typology": "fixed", "fixedValue": "1"}, "parameters"
        )
    return HonParameterRange(
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


def dry_after_wash_switch(setting: Any) -> HonConfigSwitchEntity:
    """Create the Dry After Wash switch of a washer dryer with the given setting."""
    description = next(
        description
        for description in SWITCHES["WD"]
        if description.key == "startProgram.dryProgFlag"
    )
    device = SimpleNamespace(
        unique_id="test", settings={"startProgram.dryProgFlag": setting}
    )
    coordinator = SimpleNamespace(async_set_updated_data=lambda data: None)
    hass = SimpleNamespace(
        data={DOMAIN: {"test": {"coordinator": coordinator, "hon": None}}}
    )
    entity = HonConfigSwitchEntity(
        hass, SimpleNamespace(unique_id="test"), device, description
    )
    entity.schedule_update_ha_state = lambda *args, **kwargs: None  # type: ignore[method-assign]
    return entity


def test_only_washer_dryers_have_dry_after_wash() -> None:
    keys = {
        appliance: {description.key for description in SWITCHES[appliance]}
        for appliance in ("WM", "WD")
    }
    assert "startProgram.dryProgFlag" in keys["WD"]
    assert "startProgram.dryProgFlag" not in keys["WM"]


async def test_dry_after_wash_is_off_by_default_and_toggles() -> None:
    setting = dry_flag_setting()
    switch = dry_after_wash_switch(setting)
    assert switch.is_on is False
    await switch.async_turn_on()
    assert str(setting.value) == "1"
    assert switch.is_on is True
    await switch.async_turn_off()
    assert str(setting.value) == "0"
    assert switch.is_on is False


def test_drying_program_reports_dry_after_wash_on() -> None:
    assert dry_after_wash_switch(dry_flag_setting(fixed=True)).is_on is True
