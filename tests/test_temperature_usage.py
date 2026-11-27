"""Washer temperature counters and percentages use the reported buckets."""

# pylint: disable=protected-access

import asyncio
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
from custom_components.hon.sensor import async_setup_entry
from custom_components.hon.temperature_usage import temperature_usage_entities


def make_context(values, profile="WM"):
    coordinator = SimpleNamespace(
        last_update_success=True, async_add_listener=Mock(return_value=lambda: None)
    )
    device = SimpleNamespace(
        unique_id="device",
        appliance_type=profile,
        available_settings=[],
        get=values.get,
        nick_name="washer",
        model_name="test",
        model_id="test",
    )
    hass = SimpleNamespace(
        data={
            DOMAIN: {
                "entry": {
                    "coordinator": coordinator,
                    "hon": SimpleNamespace(appliances=[device]),
                }
            }
        }
    )
    return hass, SimpleNamespace(unique_id="entry"), device


def test_counts_percentages_and_independent_reference_fields():
    values = {
        "temp0to30": "158.0",
        "temp40": 13.0,
        "temp60to90": 3,
        "totalWashCycle": 173,
        "statistics": {"temperatureUsage": {"temp40": 99}},
    }
    hass, entry, device = make_context(values)
    entities = temperature_usage_entities(hass, entry, device)
    assert [entity.native_value for entity in entities] == [158, 13, 3]
    assert [entity.extra_state_attributes["percentage"] for entity in entities] == [
        90.8,
        7.5,
        1.7,
    ]
    assert all(type(entity.native_value) is int for entity in entities)
    assert all(entity.entity_description.state_class is None for entity in entities)
    assert all(
        entity.entity_description.native_unit_of_measurement == "cycles"
        for entity in entities
    )


def test_partial_invalid_and_zero_total_keep_valid_counts():
    values = {"temp0to30": 158, "temp40": 13, "temp60to90": 3}
    hass, entry, device = make_context(values)
    entities = temperature_usage_entities(hass, entry, device)
    values["temp40"] = 13.5
    for entity in entities:
        entity._handle_coordinator_update(False)
    assert entities[0].native_value == 158
    assert entities[0].extra_state_attributes == {}
    assert entities[1].native_value is None
    assert not entities[1].available
    values.update(temp0to30=0, temp40=0, temp60to90=0)
    for entity in entities:
        entity._handle_coordinator_update(False)
        assert entity.native_value == 0
        assert entity.extra_state_attributes == {}


@pytest.mark.parametrize(
    "raw", [None, True, False, -1, 1.5, "bad", "nan", float("inf")]
)
def test_invalid_count_is_not_discovered(raw):
    values = {"temp0to30": raw, "temp40": 5}
    hass, entry, device = make_context(values)
    entities = temperature_usage_entities(hass, entry, device)
    assert len(entities) == 1
    assert entities[0].entity_description.key == "temp40"
    assert entities[0].extra_state_attributes == {}


@pytest.mark.parametrize("profile, expected", [("WM", 3), ("WD", 3), ("TD", 0)])
def test_discovery_is_limited_to_washer_profiles(profile, expected):
    values = {"temp0to30": 1, "temp40": 2, "temp60to90": 3}
    hass, entry, _device = make_context(values, profile)
    entities = []
    asyncio.run(async_setup_entry(hass, entry, entities.extend))
    assert len(entities) == expected
    assert len({entity.unique_id for entity in entities}) == expected


class NativePublicationTests(unittest.IsolatedAsyncioTestCase):
    async def test_native_sensor_publication(self):
        values = {"temp0to30": 158, "temp40": 13, "temp60to90": 3}
        synthetic_hass, entry, device = make_context(values)
        with TemporaryDirectory() as directory:
            hass = HomeAssistant(directory)
            hass.data[DOMAIN] = synthetic_hass.data[DOMAIN]
            hass.config.skip_pip = True
            hass.config_entries = ConfigEntries(hass, {})
            loader.async_setup(hass)
            self.assertTrue(await async_load_base_functionality(hass))
            entities = temperature_usage_entities(hass, entry, device)
            component = EntityComponent(logging.getLogger(__name__), "sensor", hass)
            await component.async_add_entities(entities)
            state = hass.states.get(entities[0].entity_id)
            self.assertIsNotNone(state)
            self.assertEqual(state.state, "158")
            self.assertEqual(state.attributes["unit_of_measurement"], "cycles")
            self.assertEqual(state.attributes["percentage"], 90.8)
            for entity in entities:
                await entity.async_remove()
            await hass.async_stop(force=True)
