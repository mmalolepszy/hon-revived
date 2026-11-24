from types import SimpleNamespace
from typing import Any

import pytest

from custom_components.hon.const import DOMAIN
from custom_components.hon.switch import (
    SWITCHES,
    HonControlSwitchEntity,
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
