"""Prepared night/silent settings require a writable binary capability."""

# pylint: disable=protected-access

import logging
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock

from homeassistant import loader
from homeassistant.bootstrap import async_load_base_functionality
from homeassistant.config_entries import ConfigEntries
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_component import EntityComponent
from pyhon.parameter.base import HonParameter
from pyhon.parameter.enum import HonParameterEnum
from pyhon.parameter.range import HonParameterRange

from custom_components.hon.const import DOMAIN
from custom_components.hon.switch import async_setup_entry

NIGHT = "startProgram.nightWashStatus"
SILENT = "startProgram.silentMode"


def make_range(key, minimum=0, maximum=1, step=1, value=0):
    return HonParameterRange(
        key,
        {
            "minimumValue": minimum,
            "maximumValue": maximum,
            "incrementValue": step,
            "defaultValue": value,
        },
        "parameters",
    )


def make_enum(key, values=("0", "1")):
    return HonParameterEnum(
        key, {"enumValues": list(values), "defaultValue": "0"}, "parameters"
    )


class WasherModeSettingsTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.command = SimpleNamespace(send=AsyncMock(), send_specific=AsyncMock())
        self.coordinator = SimpleNamespace(
            last_update_success=True,
            data={},
            async_set_updated_data=Mock(),
            async_add_listener=Mock(return_value=lambda: None),
        )
        self.settings = {
            NIGHT: make_range("nightWashStatus"),
            SILENT: make_enum("silentMode"),
        }
        self.device = SimpleNamespace(
            unique_id="device",
            appliance_type="WM",
            settings=self.settings,
            available_settings=self.settings,
            commands={"startProgram": self.command},
            connection=True,
            get=lambda _key, default=None: default,
            nick_name="washer",
            model_name="test",
            model_id="test",
        )
        self.hass = SimpleNamespace(
            data={
                DOMAIN: {
                    "entry": {
                        "coordinator": self.coordinator,
                        "hon": SimpleNamespace(appliances=[self.device]),
                    }
                }
            }
        )
        self.entry = SimpleNamespace(unique_id="entry")

    async def discover(self):
        entities = []
        await async_setup_entry(self.hass, self.entry, entities.extend)
        return {entity.entity_description.key: entity for entity in entities}

    async def test_discovery_wm_wd_and_no_unrelated_profile(self):
        for profile in ("WM", "WD"):
            self.device.appliance_type = profile
            entities = await self.discover()
            self.assertIn(NIGHT, entities)
            self.assertIn(SILENT, entities)
        self.device.appliance_type = "TD"
        entities = await self.discover()
        self.assertNotIn(NIGHT, entities)
        self.assertNotIn(SILENT, entities)

    async def test_invalid_fixed_and_nonbinary_capabilities_are_not_exposed(self):
        invalid = [
            None,
            HonParameter("nightWashStatus", {}, "parameters"),
            make_range("nightWashStatus", maximum=0),
            make_range("nightWashStatus", maximum=2),
            make_range("nightWashStatus", step=2),
            make_range("nightWashStatus", step=0.5),
            make_enum("nightWashStatus", ("0", "2")),
            make_enum("nightWashStatus", ("0.0", "1.0")),
        ]
        for setting in invalid:
            with self.subTest(setting=setting):
                self.settings[NIGHT] = setting
                self.assertNotIn(NIGHT, await self.discover())

    async def test_turning_controls_only_prepares_settings_without_sending(self):
        goodnight = make_range("goodNight", value=1)
        self.settings["startProgram.goodNight"] = goodnight
        entities = await self.discover()
        for key in (NIGHT, SILENT):
            entity = entities[key]
            entity.schedule_update_ha_state = Mock()
            self.assertFalse(entity.is_on)
            await entity.async_turn_on()
            self.assertTrue(entity.is_on)
            self.assertEqual(goodnight.value, 1)
            self.assertEqual(self.settings[key].intern_value, "1")
            await entity.async_turn_off()
            self.assertFalse(entity.is_on)
        self.command.send.assert_not_awaited()
        self.command.send_specific.assert_not_awaited()
        self.assertEqual(self.coordinator.async_set_updated_data.call_count, 4)

    async def test_provider_rules_can_run_when_a_setting_changes(self):
        trigger = Mock()
        self.settings[SILENT].add_trigger("1", trigger, object())
        entity = (await self.discover())[SILENT]
        entity.schedule_update_ha_state = Mock()
        await entity.async_turn_on()
        trigger.assert_called_once()
        self.command.send.assert_not_awaited()
        self.command.send_specific.assert_not_awaited()

    async def test_program_capability_is_rechecked_before_use(self):
        entity = (await self.discover())[NIGHT]
        entity.schedule_update_ha_state = Mock()
        self.assertTrue(entity.available)
        for replacement in (None, make_range("nightWashStatus", maximum=0)):
            self.settings[NIGHT] = replacement
            self.assertFalse(entity.available)
            self.assertIsNone(entity.is_on)
            await entity.async_turn_on()
        self.settings.pop(NIGHT)
        self.assertFalse(entity.available)
        self.settings[NIGHT] = make_range("nightWashStatus", value=1)
        self.assertTrue(entity.available)
        self.assertTrue(entity.is_on)
        self.command.send.assert_not_awaited()
        self.command.send_specific.assert_not_awaited()

    async def test_prepared_settings_publish_in_native_home_assistant(self):
        entity = (await self.discover())[NIGHT]
        with TemporaryDirectory() as directory:
            hass = HomeAssistant(directory)
            hass.data[DOMAIN] = self.hass.data[DOMAIN]
            hass.config.skip_pip = True
            hass.config_entries = ConfigEntries(hass, {})
            loader.async_setup(hass)
            self.assertTrue(await async_load_base_functionality(hass))
            component = EntityComponent(logging.getLogger(__name__), "switch", hass)
            await component.async_add_entities([entity])
            self.assertEqual(hass.states.get(entity.entity_id).state, "off")
            await entity.async_turn_on()
            await hass.async_block_till_done()
            self.assertEqual(hass.states.get(entity.entity_id).state, "on")
            self.command.send.assert_not_awaited()
            self.command.send_specific.assert_not_awaited()
            await entity.async_remove()
            await hass.async_stop(force=True)
