"""The fallback publishes a scheduled program through Home Assistant."""

# pylint: disable=protected-access

import logging
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from homeassistant import loader
from homeassistant.bootstrap import async_load_base_functionality
from homeassistant.config_entries import ConfigEntries
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_component import EntityComponent

from custom_components.hon.const import DOMAIN
from custom_components.hon.sensor import HonSensorEntity, SENSORS


class NativeScheduledProgramTests(unittest.IsolatedAsyncioTestCase):
    async def test_scheduled_fallback_and_idle_state(self):
        data = {"programName": "No Program", "machMode": 5, "prCode": 225}
        options = SimpleNamespace(
            values=["all_in_one_59", "cottons"], ids={225: "all_in_one_59"}
        )
        device = SimpleNamespace(
            unique_id="device",
            appliance_type="WD",
            get=data.get,
            settings={"startProgram.program": options},
            nick_name="washer",
            model_name="test",
            model_id="test",
        )
        coordinator = SimpleNamespace(
            last_update_success=True, async_add_listener=Mock(return_value=lambda: None)
        )
        with TemporaryDirectory() as directory:
            hass = HomeAssistant(directory)
            hass.data[DOMAIN] = {"entry": {"coordinator": coordinator, "hon": None}}
            hass.config.skip_pip = True
            hass.config_entries = ConfigEntries(hass, {})
            loader.async_setup(hass)
            self.assertTrue(await async_load_base_functionality(hass))
            description = next(
                item for item in SENSORS["WD"] if item.key == "programName"
            )
            entity = HonSensorEntity(
                hass, SimpleNamespace(unique_id="entry"), device, description
            )
            component = EntityComponent(logging.getLogger(__name__), "sensor", hass)
            await component.async_add_entities([entity])
            self.assertEqual(hass.states.get(entity.entity_id).state, "all_in_one_59")
            data["machMode"] = 1
            entity._handle_coordinator_update()
            await hass.async_block_till_done()
            self.assertEqual(hass.states.get(entity.entity_id).state, "No Program")
            await entity.async_remove()
            await hass.async_stop(force=True)
