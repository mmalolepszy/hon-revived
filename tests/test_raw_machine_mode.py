"""The machine-mode sensor exposes its existing cached raw code."""

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


def make_sensor(value, key="machMode", profile="WM"):
    data = {key: value}
    reads = []

    def get(name, default=None):
        reads.append(name)
        return data.get(name, default)

    device = SimpleNamespace(
        unique_id="device",
        appliance_type=profile,
        get=get,
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
    return entity, data, reads, device, coordinator


@pytest.mark.parametrize("raw", [0, 1, 2, 6, 7, 9, "7", "7.0", 7.0])
def test_raw_code_uses_the_existing_single_read(raw):
    entity, _data, reads, _device, _coordinator = make_sensor(raw)
    assert entity.extra_state_attributes["raw_machine_mode"] == int(float(raw))
    assert type(entity.extra_state_attributes["raw_machine_mode"]) is int
    assert reads == ["machMode"]


@pytest.mark.parametrize("profile", ["WM", "WD", "TD", "DW", "AC", "HO"])
def test_raw_code_is_available_for_existing_machine_mode_profiles(profile):
    entity, _data, reads, _device, _coordinator = make_sensor(7, profile=profile)
    description = entity.entity_description
    expected = str(description.option_list.get(7, 7)) if description.option_list else 7
    assert entity.native_value == expected
    assert entity.extra_state_attributes == {"raw_machine_mode": 7}
    assert reads == ["machMode"]


def test_first_construction_and_existing_enum_state():
    entity, _data, reads, _device, _coordinator = make_sensor(7)
    assert entity.native_value == "ready"
    assert entity.extra_state_attributes == {"raw_machine_mode": 7}
    assert reads == ["machMode"]


@pytest.mark.parametrize(
    "raw", [True, False, "", "bad", "nan", "inf", "-inf", 7.5, "7.5"]
)
def test_invalid_mode_removes_stale_code_and_preserves_other_attributes(raw):
    entity, data, reads, _device, _coordinator = make_sensor(7)
    entity._attr_extra_state_attributes = {"preserved": "yes", "raw_machine_mode": 7}
    data["machMode"] = raw
    reads.clear()
    entity._handle_coordinator_update(False)
    assert entity.extra_state_attributes == {"preserved": "yes"}
    assert reads == ["machMode"]


def test_other_sensor_is_not_changed():
    entity, data, reads, _device, _coordinator = make_sensor(12, "currentWaterUsed")
    entity._attr_extra_state_attributes = {"preserved": "yes"}
    data["currentWaterUsed"] = 15
    reads.clear()
    entity._handle_coordinator_update(False)
    assert entity.native_value == 15
    assert entity.extra_state_attributes == {"preserved": "yes"}
    assert reads == ["currentWaterUsed"]


class NativePublicationTests(unittest.IsolatedAsyncioTestCase):
    async def test_native_sensor_publishes_state_and_attribute(self):
        entity, data, _reads, _device, coordinator = make_sensor(7)
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
            self.assertIsNotNone(state)
            self.assertEqual(state.state, "ready")
            self.assertEqual(state.attributes["raw_machine_mode"], 7)
            data["machMode"] = 1
            entity._handle_coordinator_update()
            await hass.async_block_till_done()
            self.assertEqual(
                hass.states.get(entity.entity_id).attributes["raw_machine_mode"], 1
            )
            await entity.async_remove()
            await hass.async_stop(force=True)
