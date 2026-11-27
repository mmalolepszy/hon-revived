"""The reported remote-control flag must not turn invalid data into off."""

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
from pyhon.attributes import HonAttribute

from custom_components.hon.binary_sensor import BINARY_SENSORS, HonBinarySensorEntity
from custom_components.hon.const import DOMAIN


def make_sensor(profile="WM", key="remoteCtrValid", raw=1):
    data = {key: raw}
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
    description = next(item for item in BINARY_SENSORS[profile] if item.key == key)
    entity = HonBinarySensorEntity(
        hass, SimpleNamespace(unique_id="entry"), device, description
    )
    return entity, data, coordinator


@pytest.mark.parametrize("profile", ["WM", "WD", "TD", "OV", "IH", "DW"])
@pytest.mark.parametrize(
    "raw,expected",
    [(0, False), (1, True), (0.0, False), (1.0, True), ("0", False), ("1", True)],
)
def test_supported_values(profile, raw, expected):
    entity, _data, _coordinator = make_sensor(profile, raw=raw)
    assert entity.is_on is expected
    assert entity.state == ("on" if expected else "off")


@pytest.mark.parametrize(
    "raw", [None, True, False, -1, 2, 0.5, "", "bad", "nan", "inf"]
)
def test_missing_and_invalid_values_are_unknown(raw):
    entity, _data, _coordinator = make_sensor(raw=raw)
    assert entity.is_on is None
    assert entity.state is None


@pytest.mark.parametrize("raw,expected", [("0", False), ("1", True), ("bad", None)])
def test_real_pyhon_attribute_values(raw, expected):
    entity, _data, _coordinator = make_sensor(raw=HonAttribute(raw))
    assert entity.is_on is expected


def test_other_binary_sensor_behavior_is_unchanged():
    entity, data, _coordinator = make_sensor(
        key="attributes.lastConnEvent.category", raw="CONNECTED"
    )
    assert entity.is_on is True
    data[entity.entity_description.key] = None
    assert entity.is_on is False


class NativePublicationTests(unittest.IsolatedAsyncioTestCase):
    async def test_remote_status_becomes_unknown_after_missing_update(self):
        entity, data, coordinator = make_sensor(raw=1)
        with TemporaryDirectory() as directory:
            hass = HomeAssistant(directory)
            hass.data[DOMAIN] = {"entry": {"coordinator": coordinator, "hon": None}}
            hass.config.skip_pip = True
            hass.config_entries = ConfigEntries(hass, {})
            loader.async_setup(hass)
            self.assertTrue(await async_load_base_functionality(hass))
            component = EntityComponent(
                logging.getLogger(__name__), "binary_sensor", hass
            )
            await component.async_add_entities([entity])
            self.assertEqual(hass.states.get(entity.entity_id).state, "on")
            data["remoteCtrValid"] = None
            entity._handle_coordinator_update()
            await hass.async_block_till_done()
            self.assertEqual(hass.states.get(entity.entity_id).state, "unknown")
            await entity.async_remove()
            await hass.async_stop(force=True)
