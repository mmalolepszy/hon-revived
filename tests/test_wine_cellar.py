"""Wine cellar (WC) regression tests: issues #56, #85 (both zones reset to 5 °C)
and stale state. Everything runs against a fake hOn API; nothing reaches the cloud."""

from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace
import json

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.util import dt as dt_util
from pyhon.connection.mqtt import MQTTClient
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.hon import wine_cellar
from tests.conftest import FakeHon, entity_id, make_appliance
from tests.wine_cellar_data import FakeApi

ZONE_1 = "settings.tempSel"
ZONE_2 = "settings.tempSelZ2"


def base(hon: FakeHon):
    return next(a for a in hon.appliances if a.zone == 0)


async def test_settings_defaults_are_the_bug(api: FakeApi) -> None:
    """Root cause: pyhon syncs settings before attributes load (5 °C defaults
    stay until a push/update reaches this appliance object), and when it syncs it
    truncates the °F round trip (7.8 -> 7 instead of 8)."""
    device = await make_appliance(api)
    assert device.get("settings.tempSel") == 5
    assert device.get("settings.tempSelZ2") == 5
    assert device.get("tempSel") == 16.1
    device.sync_params_to_command("settings")
    assert device.get("settings.tempSelZ2") == 7
    assert wine_cellar.seed_settings(device) == []
    assert device.get("settings.tempSel") == 16
    assert device.get("settings.tempSelZ2") == 8


async def test_light_sends_only_light_status(
    hass: HomeAssistant, setup, api: FakeApi
) -> None:
    light = entity_id(hass, "light", "settings.lightStatus")
    await hass.services.async_call(
        "light", "turn_on", {"entity_id": light}, blocking=True
    )
    await hass.services.async_call(
        "light", "turn_off", {"entity_id": light}, blocking=True
    )
    assert api.sent == [
        {
            "command": "startProgram",
            "parameters": {"lightStatus": "1"},
            "ancillary": {},
            "program": "",
        },
        {
            "command": "startProgram",
            "parameters": {"lightStatus": "0"},
            "ancillary": {},
            "program": "",
        },
    ]
    for sent in api.sent:
        assert not {"tempSel", "tempSelZ2", "prCode", "prCodeZ2"} & set(
            sent["parameters"]
        )


async def test_light_state_is_optimistic_then_confirmed(
    hass: HomeAssistant, setup, api: FakeApi
) -> None:
    light = entity_id(hass, "light", "settings.lightStatus")
    assert hass.states.get(light).state == "off"
    await hass.services.async_call(
        "light", "turn_on", {"entity_id": light}, blocking=True
    )
    await hass.async_block_till_done()
    assert hass.states.get(light).state == "on"
    # The cloud confirms on the re-read after the command
    api.state["lightStatus"] = "1"
    async_fire_time_changed(
        hass, dt_util.utcnow() + timedelta(seconds=wine_cellar.CONFIRM_DELAY + 15)
    )
    await hass.async_block_till_done()
    assert hass.states.get(light).state == "on"


async def test_zone_1_does_not_touch_zone_2(
    hass: HomeAssistant, setup, api: FakeApi
) -> None:
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
            "ancillary": {
                "programFamily": "[dashboard]",
                "remoteActionable": "1",
                "remoteVisible": "1",
            },
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


async def test_zone_2_only_sends_zone_2(
    hass: HomeAssistant, setup, api: FakeApi
) -> None:
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
    assert (
        hass.states.get(entity_id(hass, "climate", ZONE_1)).attributes["temperature"]
        == 16
    )


async def test_zone_preset(hass: HomeAssistant, setup, api: FakeApi) -> None:
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


async def test_zone_climate_has_no_on_off(
    hass: HomeAssistant, setup, api: FakeApi
) -> None:
    """turn_on/off would send startProgram with both zones' default targets."""
    climate = entity_id(hass, "climate", ZONE_1)
    with pytest.raises(Exception):
        await hass.services.async_call(
            "climate", "turn_on", {"entity_id": climate}, blocking=True
        )
    assert api.sent == []


async def test_sabbath_switch_carries_real_targets(
    hass: HomeAssistant, setup, api: FakeApi, hon: FakeHon
) -> None:
    switch = entity_id(hass, "switch", "sabbathStatus")
    sent = []
    command = base(hon).commands["settings"]

    async def send(only_mandatory: bool = False) -> bool:
        sent.append(dict(command.parameter_value))
        return True

    command.send = send  # type: ignore[method-assign]
    # Simulate the bad state the integration starts from
    command.parameters["tempSel"].value = 5
    command.parameters["tempSelZ2"].value = 5
    await hass.services.async_call(
        "switch", "turn_on", {"entity_id": switch}, blocking=True
    )
    assert sent == [
        {
            "lightStatus": 0,
            "sabbathStatus": 1,
            "tempSel": 16,
            "tempSelZ2": 8,
            "tempUnit": 0,
        }
    ]


async def test_settings_refused_without_real_targets(api: FakeApi) -> None:
    api.state.pop("tempSelZ2")
    device = await make_appliance(api)
    with pytest.raises(HomeAssistantError):
        await wine_cellar.async_send_settings(device, {"sabbathStatus": 1})
    assert api.sent == []


async def test_polling_updates_state(hass: HomeAssistant, setup, api: FakeApi) -> None:
    """Targets changed in the hOn app show up without reloading the entry."""
    sensor = entity_id(hass, "sensor", "tempSelZ2")
    climate = entity_id(hass, "climate", ZONE_2)
    assert hass.states.get(sensor).state == "7.8"
    api.state["tempSelZ2"] = "10.0"
    api.state["prCodeZ2"] = "2"
    async_fire_time_changed(
        hass, dt_util.utcnow() + wine_cellar.REFRESH_INTERVAL + timedelta(seconds=1)
    )
    await hass.async_block_till_done()
    assert hass.states.get(sensor).state == "10.0"
    assert hass.states.get(climate).attributes["temperature"] == 10
    assert hass.states.get(climate).attributes["preset_mode"] == "white"
    assert api.sent == []


async def test_mqtt_push_reaches_base_device(
    hass: HomeAssistant, setup, hon: FakeHon
) -> None:
    """pyhon routes a push to the first appliance on the topic: must be the base."""
    assert hon.appliances[0].zone == 0
    client = MQTTClient.__new__(MQTTClient)
    client._appliances = hon.appliances
    client._hon = hon
    topic = hon.appliances[0].info["topics"]["subscribe"][0]
    payload = {"parameters": [{"parName": "tempSel", "parNewVal": "12.2"}]}
    client._on_publish_received(
        SimpleNamespace(
            publish_packet=SimpleNamespace(
                topic=topic, payload=json.dumps(payload).encode()
            )
        )
    )
    await hass.async_block_till_done()
    assert hass.states.get(entity_id(hass, "sensor", "tempSel")).state == "12.2"
    assert (
        hass.states.get(entity_id(hass, "climate", ZONE_1)).attributes["temperature"]
        == 12
    )


async def test_refused_command_raises(hass: HomeAssistant, setup, api: FakeApi) -> None:
    api.accept = False
    light = entity_id(hass, "light", "settings.lightStatus")
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            "light", "turn_on", {"entity_id": light}, blocking=True
        )
    await hass.async_block_till_done()
    assert hass.states.get(light).state == "off"


async def test_other_appliance_types_unchanged(api: FakeApi) -> None:
    device = await make_appliance(api)
    device._info["applianceTypeName"] = "DW"  # pylint: disable=protected-access
    assert not wine_cellar.is_wine_cellar(device)
    appliances = [device]
    wine_cellar.prefer_base_appliances(appliances)
    assert await wine_cellar.async_refresh(appliances) == {}
