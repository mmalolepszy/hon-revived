"""Wine cellar (WC) zone-command tests: app-like startProgram per zone.

Everything runs against a fake hOn API; nothing reaches the cloud.
Tests cover: zone isolation, out-of-range program switching, preset change,
refused command, no-cloud-reads, and other appliance types.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.util import dt as dt_util
from pytest_homeassistant.common import async_fire_time_changed

from custom_components.hon import wine_cellar
from tests.conftest import entity_id, make_appliance
from tests.wine_cellar_data import FakeApi

ZONE_1 = "settings.tempSel"
ZONE_2 = "settings.tempSelZ2"


async def test_zone_1_does_not_touch_zone_2(
    hass: HomeAssistant, setup, api: FakeApi
) -> None:
    """set_temperature on zone 1 sends only zone-1 parameters."""
    climate = entity_id(hass, "climate", ZONE_1)
    assert hass.states.get(climate).attributes["temperature"] == 16
    await hass.services.async_call(
        "climate",
        "set_temperature",
        {"entity_id": climate, "temperature": 14},
        blocking=True,
    )
    assert api.sent == [
        {
            "command": "startProgram",
            "parameters": {"prCode": "1", "tempSel": "14"},
            "ancillary": {"programFamily": "[dashboard]"},
            "program": "PROGRAMS.WC.RED",
        }
    ]
    await hass.async_block_till_done()
    assert hass.states.get(climate).attributes["temperature"] == 14
    # Zone 2 keeps its target
    assert (
        hass.states.get(entity_id(hass, "climate", ZONE_2)).attributes["temperature"]
        == 8
    )


async def test_out_of_range_target_switches_program(
    hass: HomeAssistant, setup, api: FakeApi
) -> None:
    """When target is outside the current program range, pick one that fits."""
    climate = entity_id(hass, "climate", ZONE_2)
    assert hass.states.get(climate).attributes["temperature"] == 8
    await hass.services.async_call(
        "climate",
        "set_temperature",
        {"entity_id": climate, "temperature": 6},
        blocking=True,
    )
    # 12 °C is outside sparkling (5-8): the app's way is to switch to white
    await hass.services.async_call(
        "climate",
        "set_temperature",
        {"entity_id": climate, "temperature": 12},
        blocking=True,
    )
    assert [(s["program"], s["parameters"]) for s in api.sent] == [
        ("PROGRAMS.WC.SPARKLING", {"prCodeZ2": "3", "tempSelZ2": "6"}),
        ("PROGRAMS.WC.WHITE", {"prCodeZ2": "2", "tempSelZ2": "12"}),
    ]
    # Zone 1 target unchanged
    assert (
        hass.states.get(entity_id(hass, "climate", ZONE_1)).attributes["temperature"]
        == 16
    )


async def test_zone_preset(hass: HomeAssistant, setup, api: FakeApi) -> None:
    """set_preset_mode sends only the matching zone's program code + temperature."""
    climate = entity_id(hass, "climate", ZONE_2)
    state = hass.states.get(climate)
    assert state.attributes["preset_mode"] == "sparkling"
    assert "iot_rose" in state.attributes["preset_modes"]
    await hass.services.async_call(
        "climate",
        "set_preset_mode",
        {"entity_id": climate, "preset_mode": "white"},
        blocking=True,
    )
    await hass.services.async_call(
        "climate",
        "set_preset_mode",
        {"entity_id": climate, "preset_mode": "iot_rose"},
        blocking=True,
    )
    assert [
        (s["program"], s["parameters"], s["ancillary"]["programFamily"])
        for s in api.sent
    ] == [
        ("PROGRAMS.WC.WHITE", {"prCodeZ2": "2", "tempSelZ2": "12"}, "[dashboard]"),
        ("PROGRAMS.WC.IOT_ROSE", {"tempSelZ2": "6"}, "[download]"),
    ]


async def test_refused_command_raises(hass: HomeAssistant, setup, api: FakeApi) -> None:
    """HomeAssistantError when hOn refuses the zone command."""
    api.accept = False
    climate = entity_id(hass, "climate", ZONE_1)
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            "climate",
            "set_temperature",
            {"entity_id": climate, "temperature": 15},
            blocking=True,
        )
    assert api.sent == [
        {
            "command": "startProgram",
            "parameters": {"prCode": "1", "tempSel": "15"},
            "ancillary": {"programFamily": "[dashboard]"},
            "program": "PROGRAMS.WC.RED",
        }
    ]


async def test_out_of_range_raises_service_validation(api: FakeApi) -> None:
    """ServiceValidationError when no program covers the requested temperature."""
    device = await make_appliance(api)
    with pytest.raises(ServiceValidationError, match="outside every wine cellar"):
        wine_cellar.zone_command(device, ZONE_1, temperature=25)


async def test_preset_uses_program_default(api: FakeApi) -> None:
    """A target outside the new program falls back to its default, not its min."""
    device = await make_appliance(api)
    assert wine_cellar.zone_command(device, ZONE_1, program="sparkling")[1] == {
        "prCode": "3",
        "tempSel": "8",
    }


async def test_preset_uses_last_sent_temperature(api: FakeApi) -> None:
    """pyhon restores the last startProgram from history; that value is used."""
    api.history = [
        {
            "command": {
                "commandName": "startProgram",
                "parameters": {"program": "PROGRAMS.WC.SPARKLING", "tempSel": "6"},
            }
        }
    ]
    device = await make_appliance(api)
    assert wine_cellar.zone_command(device, ZONE_1, program="sparkling")[1] == {
        "prCode": "3",
        "tempSel": "6",
    }


async def test_zone_climate_has_no_on_off(
    hass: HomeAssistant, setup, api: FakeApi
) -> None:
    """turn_on on a wine cellar zone is not supported (would reset both zones)."""
    climate = entity_id(hass, "climate", ZONE_1)
    with pytest.raises(Exception):
        await hass.services.async_call(
            "climate", "turn_on", {"entity_id": climate}, blocking=True
        )
    assert api.sent == []


async def test_zone_shows_off_but_cannot_be_switched_off(
    hass: HomeAssistant, api: FakeApi, hon, setup, caplog: pytest.LogCaptureFixture
) -> None:
    """onOffStatus 0 shows off; setting off is rejected and sends nothing."""
    climate = entity_id(hass, "climate", ZONE_1)
    assert hass.states.get(climate).state == "cool"
    api.state["onOffStatus"] = "0"
    for appliance in hon.appliances:
        appliance.attributes["parameters"]["onOffStatus"].update("0")
    hon.notify()
    await hass.async_block_till_done()
    state = hass.states.get(climate)
    assert state.state == "off"
    assert "off" not in state.attributes["hvac_modes"]
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            "climate",
            "set_hvac_mode",
            {"entity_id": climate, "hvac_mode": "off"},
            blocking=True,
        )
    with pytest.raises(Exception):
        await hass.services.async_call(
            "climate", "turn_off", {"entity_id": climate}, blocking=True
        )
    assert api.sent == []
    assert "WARNING" not in caplog.text


async def test_no_cloud_reads_after_command(
    hass: HomeAssistant, setup, api: FakeApi
) -> None:
    """No REST re-read is triggered after a zone command (Haier 2024 takedown)."""
    climate = entity_id(hass, "climate", ZONE_1)
    reads_before = api.reads
    await hass.services.async_call(
        "climate",
        "set_temperature",
        {"entity_id": climate, "temperature": 15},
        blocking=True,
    )
    await hass.async_block_till_done()
    assert api.reads == reads_before
    # Fire time events well past any polling interval
    now = dt_util.utcnow()
    for minutes in (1, 15, 60):
        async_fire_time_changed(hass, now + timedelta(minutes=minutes, seconds=1))
        await hass.async_block_till_done()
    assert api.reads == reads_before


async def test_other_appliance_types_unchanged(api: FakeApi) -> None:
    """is_wine_cellar returns False for non-WC appliances."""
    device = await make_appliance(api)
    device._info["applianceTypeName"] = "DW"  # pylint: disable=protected-access
    assert not wine_cellar.is_wine_cellar(device)
