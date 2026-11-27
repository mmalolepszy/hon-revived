"""Expose cached program and phase codes on the existing sensors."""

# pylint: disable=protected-access

import logging
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

import pytest
from homeassistant import loader
from homeassistant.bootstrap import async_load_base_functionality
from homeassistant.config_entries import ConfigEntries
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_component import EntityComponent

from custom_components.hon.const import DOMAIN
from custom_components.hon.sensor import HonSensorEntity, SENSORS


def make_sensor(key, raw, profile="WM"):
    data = {"programName": "cotton", "prPhase": 17, "prCode": 225}
    data["prCode" if key == "programName" else key] = raw
    reads = []

    def get(name, default=None):
        reads.append(name)
        return data.get(name, default)

    device = SimpleNamespace(
        unique_id="device",
        appliance_type=profile,
        get=get,
        settings={"startProgram.program": SimpleNamespace(values=["cotton"])},
        nick_name="washer",
        model_name="test",
        model_id="test",
    )
    coordinator = SimpleNamespace(
        last_update_success=True, async_add_listener=Mock(return_value=lambda: None)
    )
    hass = SimpleNamespace(
        data={DOMAIN: {"entry": {"coordinator": coordinator, "hon": None}}}
    )
    description = next(item for item in SENSORS[profile] if item.key == key)
    entity = HonSensorEntity(
        hass, SimpleNamespace(unique_id="entry"), device, description
    )
    return entity, data, reads, coordinator


@pytest.mark.parametrize("profile", ["WM", "WD", "TD"])
@pytest.mark.parametrize(
    ("key", "attribute", "raw"),
    [
        ("prPhase", "raw_program_phase", "17"),
        ("programName", "raw_program_code", "225"),
    ],
)
def test_codes_on_existing_sensor_profiles(profile, key, attribute, raw):
    entity, _data, reads, _coordinator = make_sensor(key, raw, profile)
    assert entity.extra_state_attributes == {attribute: int(raw)}
    assert entity.native_value == (
        "cotton"
        if key == "programName"
        else str(entity.entity_description.option_list.get(17, 17))
    )
    assert reads == ([key, "prCode"] if key == "programName" else [key])


@pytest.mark.parametrize(
    "key,attribute",
    [("prPhase", "raw_program_phase"), ("programName", "raw_program_code")],
)
@pytest.mark.parametrize("raw", [True, False, "", "bad", "nan", "inf", -1, 1.5, "1.5"])
def test_invalid_codes_remove_stale_attribute(key, attribute, raw):
    entity, data, _reads, _coordinator = make_sensor(key, 1)
    entity._attr_extra_state_attributes = {attribute: 1, "preserved": "yes"}
    data["prCode" if key == "programName" else key] = raw
    entity._handle_coordinator_update(False)
    assert entity.extra_state_attributes == {"preserved": "yes"}


@pytest.mark.parametrize("raw,expected", [(0, 0), ("0", 0), ("17.0", 17)])
def test_zero_and_integral_numeric_strings_are_retained(raw, expected):
    entity, _data, _reads, _coordinator = make_sensor("programName", raw)
    assert entity.extra_state_attributes["raw_program_code"] == expected


def test_missing_program_code_removes_stale_attribute():
    entity, data, _reads, _coordinator = make_sensor("programName", 225)
    data.pop("prCode")
    entity._handle_coordinator_update(False)
    assert "raw_program_code" not in entity.extra_state_attributes


def test_other_sensor_is_unchanged():
    entity, data, reads, _coordinator = make_sensor("currentWaterUsed", 12)
    entity._attr_extra_state_attributes = {"preserved": "yes"}
    data["currentWaterUsed"] = 15
    reads.clear()
    entity._handle_coordinator_update(False)
    assert entity.native_value == 15
    assert entity.extra_state_attributes == {"preserved": "yes"}
    assert reads == ["currentWaterUsed"]


class NativePublicationTests(unittest.IsolatedAsyncioTestCase):
    async def test_phase_attribute_is_published_and_updated(self):
        entity, data, _reads, coordinator = make_sensor("prPhase", 17, "TD")
        with TemporaryDirectory() as directory:
            hass = HomeAssistant(directory)
            hass.data[DOMAIN] = {"entry": {"coordinator": coordinator, "hon": None}}
            hass.config.skip_pip = True
            hass.config_entries = ConfigEntries(hass, {})
            loader.async_setup(hass)
            self.assertTrue(await async_load_base_functionality(hass))
            component = EntityComponent(logging.getLogger(__name__), "sensor", hass)
            await component.async_add_entities([entity])
            state = hass.states.get(entity.entity_id)
            self.assertEqual(state.attributes["raw_program_phase"], 17)
            data["prPhase"] = 16
            entity._handle_coordinator_update()
            await hass.async_block_till_done()
            self.assertEqual(
                hass.states.get(entity.entity_id).attributes["raw_program_phase"], 16
            )
            await entity.async_remove()
            await hass.async_stop(force=True)
