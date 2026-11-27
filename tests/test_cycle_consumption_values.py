"""Cycle consumption sensors publish only valid nonnegative readings."""

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

KEYS = ("currentElectricityUsed", "currentWaterUsed")


def make_sensor(profile, key, value):
    data = {key: value}
    device = SimpleNamespace(
        unique_id="device",
        appliance_type=profile,
        get=data.get,
        nick_name="appliance",
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
    return entity, data, coordinator


@pytest.mark.parametrize("profile", ["WM", "WD", "DW"])
@pytest.mark.parametrize("key", KEYS)
@pytest.mark.parametrize("raw,expected", [(0, 0), ("0", 0), (1.25, 1.25), ("2.5", 2.5)])
def test_valid_readings_keep_zero_and_fractional_values(profile, key, raw, expected):
    entity, _data, _coordinator = make_sensor(profile, key, raw)
    assert entity.native_value == expected


@pytest.mark.parametrize("key", KEYS)
@pytest.mark.parametrize(
    "raw", [None, "", True, False, -1, "-0.1", "bad", "nan", "inf", float("-inf")]
)
def test_invalid_readings_are_unknown(key, raw):
    entity, _data, _coordinator = make_sensor("WM", key, raw)
    assert entity.native_value is None


def test_unrelated_sensor_value_is_unchanged():
    entity, data, _coordinator = make_sensor("WM", "temp", 40)
    assert entity.native_value == 40
    data["temp"] = 30
    entity._handle_coordinator_update(False)
    assert entity.native_value == 30


class NativePublicationTests(unittest.IsolatedAsyncioTestCase):
    async def test_sensor_updates_from_valid_to_unknown_and_zero(self):
        entity, data, coordinator = make_sensor("WM", "currentElectricityUsed", 2.5)
        with TemporaryDirectory() as directory:
            hass = HomeAssistant(directory)
            hass.data[DOMAIN] = {"entry": {"coordinator": coordinator, "hon": None}}
            hass.config.skip_pip = True
            hass.config_entries = ConfigEntries(hass, {})
            loader.async_setup(hass)
            self.assertTrue(await async_load_base_functionality(hass))
            component = EntityComponent(logging.getLogger(__name__), "sensor", hass)
            await component.async_add_entities([entity])
            self.assertEqual(hass.states.get(entity.entity_id).state, "2.5")
            data["currentElectricityUsed"] = "bad"
            entity._handle_coordinator_update()
            await hass.async_block_till_done()
            self.assertEqual(hass.states.get(entity.entity_id).state, "unknown")
            data["currentElectricityUsed"] = 0
            entity._handle_coordinator_update()
            await hass.async_block_till_done()
            self.assertEqual(float(hass.states.get(entity.entity_id).state), 0)
            await entity.async_remove()
            await hass.async_stop(force=True)
