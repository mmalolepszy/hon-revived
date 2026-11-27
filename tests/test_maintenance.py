"""Washer maintenance counters and statistics refresh lifecycle."""

# pylint: disable=protected-access

import asyncio
import logging
from tempfile import TemporaryDirectory
from datetime import timedelta
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

from homeassistant import loader
from homeassistant.bootstrap import async_load_base_functionality
from homeassistant.config_entries import ConfigEntries
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_component import EntityComponent

from custom_components.hon import maintenance, sensor
from custom_components.hon.const import DOMAIN


class MaintenanceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.timers = []
        self.cancel_timer = Mock()
        self.unloads = []

        def track(_hass, action, interval):
            self.assertEqual(interval, timedelta(hours=1))
            self.timers.append(action)
            return self.cancel_timer

        self.track = patch.object(
            maintenance, "async_track_time_interval", side_effect=track
        )
        self.track.start()
        self.addCleanup(self.track.stop)
        self.payload = {
            "drawerCleaning": {
                "remaining": -2,
                "count": 102,
                "tot": 100,
                "percentage": 102,
            },
            "drumCleaning": {
                "remaining": "18.0",
                "count": "72.0",
                "tot": 90,
                "percentage": 80.5,
            },
            "filterCleaning": {
                "remaining": 0,
                "count": 100,
                "tot": 100,
                "percentage": 100,
            },
        }
        self.device = SimpleNamespace(
            appliance_type="WM",
            unique_id="test",
            available_settings=[],
            get=lambda key, default=None: (
                self.payload if key == "statistics" else default
            ),
            load_statistics=AsyncMock(),
        )
        self.coordinator = SimpleNamespace(
            last_update_success=True, data={}, async_update_listeners=Mock()
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
        self.entry = SimpleNamespace(
            unique_id="entry", async_on_unload=self.unloads.append
        )

    async def setup_entities(self):
        return await maintenance.async_setup_maintenance(
            self.hass, self.entry, self.device
        )

    async def test_discovery_and_provider_values(self):
        entities = await self.setup_entities()
        self.assertEqual(len(entities), 3)
        self.assertEqual(len({entity.unique_id for entity in entities}), 3)
        self.assertEqual([entity.native_value for entity in entities], [-2, 18, 0])
        self.assertEqual(
            entities[0].extra_state_attributes,
            {"count": 102, "total": 100, "percentage": 102},
        )
        self.assertEqual(entities[1].extra_state_attributes["percentage"], 80.5)
        self.assertTrue(all(entity.available for entity in entities))
        self.assertEqual(len(self.timers), 1)
        self.device.load_statistics.assert_not_awaited()

    async def test_missing_and_invalid_blocks_are_not_discovered(self):
        self.payload = {
            "drawerCleaning": {"remaining": 18.5},
            "filterCleaning": {"remaining": True},
        }
        self.assertEqual(await self.setup_entities(), [])
        self.assertEqual(len(self.timers), 0)

    async def test_only_washer_profiles_register_counters(self):
        with patch.object(sensor, "SENSORS", {}):
            for profile, expected in (("WM", 3), ("WD", 3), ("TD", 0)):
                self.device.appliance_type = profile
                added = []
                await sensor.async_setup_entry(self.hass, self.entry, added.extend)
                self.assertEqual(len(added), expected)
        self.assertEqual(len(self.timers), 1)

    async def test_refresh_success_failure_and_recovery(self):
        entities = await self.setup_entities()
        self.payload["drawerCleaning"]["remaining"] = 7
        self.device.load_statistics.side_effect = RuntimeError("sensitive detail")
        with self.assertLogs(maintenance.__name__, level="WARNING") as logs:
            await self.timers[0](None)
        self.assertNotIn("sensitive detail", str(logs.output))
        self.assertFalse(entities[0].available)
        entities[0]._handle_coordinator_update(False)
        self.assertEqual(entities[0].native_value, -2)
        self.device.load_statistics.side_effect = None
        await self.timers[0](None)
        entities[0]._handle_coordinator_update(False)
        self.assertTrue(entities[0].available)
        self.assertEqual(entities[0].native_value, 7)
        self.assertEqual(self.coordinator.async_update_listeners.call_count, 2)

    async def test_refresh_does_not_change_coordinator_availability(self):
        await self.setup_entities()
        self.coordinator.last_update_success = False
        await self.timers[0](None)
        self.assertFalse(self.coordinator.last_update_success)
        self.coordinator.async_update_listeners.assert_called_once()

    async def test_empty_initial_statistics_fetch_once(self):
        self.payload = None
        entities = await self.setup_entities()
        self.assertEqual(entities, [])
        self.device.load_statistics.assert_awaited_once()
        self.assertEqual(len(self.timers), 0)

    async def test_initial_fetch_failure_does_not_schedule_background_polling(self):
        self.payload = None
        self.device.load_statistics.side_effect = TimeoutError
        with self.assertLogs(maintenance.__name__, level="WARNING"):
            self.assertEqual(await self.setup_entities(), [])
        self.assertEqual(len(self.timers), 0)
        self.device.load_statistics.assert_awaited_once()

    async def test_initial_fetch_can_discover_a_supported_counter(self):
        self.payload = None

        async def load():
            self.payload = {"filterCleaning": {"remaining": 5}}

        self.device.load_statistics.side_effect = load
        entities = await self.setup_entities()
        self.assertEqual(len(entities), 1)
        self.assertEqual(entities[0].native_value, 5)
        self.device.load_statistics.assert_awaited_once()

    async def test_real_home_assistant_timer_registers_and_unloads(self):
        self.track.stop()
        with TemporaryDirectory() as directory:
            hass = HomeAssistant(directory)
            hass.data[DOMAIN] = {
                "entry": {"coordinator": self.coordinator, "hon": None}
            }
            entities = await maintenance.async_setup_maintenance(
                hass, self.entry, self.device
            )
            self.assertEqual(len(entities), 3)
            self.assertEqual(len(self.unloads), 1)
            self.unloads[0]()
            self.assertEqual(hass.data[DOMAIN]["entry"]["maintenance_refresh"], {})
            await hass.async_stop()

    async def test_native_entity_component_publishes_maintenance_states(self):
        self.track.stop()
        self.coordinator.async_add_listener = Mock(return_value=lambda: None)
        self.device.nick_name = "washer"
        self.device.model_name = "test"
        self.device.model_id = "test"
        with TemporaryDirectory() as directory:
            hass = HomeAssistant(directory)
            hass.data[DOMAIN] = {
                "entry": {"coordinator": self.coordinator, "hon": None}
            }
            hass.config.skip_pip = True
            hass.config_entries = ConfigEntries(hass, {})
            loader.async_setup(hass)
            self.assertTrue(await async_load_base_functionality(hass))
            entities = await maintenance.async_setup_maintenance(
                hass, self.entry, self.device
            )
            component = EntityComponent(logging.getLogger(__name__), "sensor", hass)
            await component.async_add_entities(entities)
            state = hass.states.get(entities[0].entity_id)
            self.assertIsNotNone(state)
            self.assertEqual(state.state, "-2")
            self.assertEqual(state.attributes["unit_of_measurement"], "cycles")
            self.assertEqual(state.attributes["count"], 102)
            self.unloads[0]()
            for entity in entities:
                await entity.async_remove()
            await hass.async_stop(force=True)

    async def test_serialization_and_unload_cancel_pending_refresh(self):
        await self.setup_entities()
        started = asyncio.Event()

        async def wait():
            started.set()
            await asyncio.Event().wait()

        self.device.load_statistics.side_effect = wait
        task = asyncio.create_task(self.timers[0](None))
        await started.wait()
        await self.timers[0](None)
        self.unloads[0]()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.cancel_timer.assert_called_once()
        self.coordinator.async_update_listeners.assert_not_called()
        await self.timers[0](None)
        self.assertEqual(self.device.load_statistics.await_count, 1)

    async def test_timeout_marks_only_maintenance_unavailable(self):
        entities = await self.setup_entities()

        async def wait():
            await asyncio.Event().wait()

        self.device.load_statistics.side_effect = wait
        original_timeout = asyncio.timeout
        with patch.object(
            maintenance.asyncio, "timeout", side_effect=lambda _: original_timeout(0)
        ) as timeout:
            with self.assertLogs(maintenance.__name__, level="WARNING"):
                await self.timers[0](None)
        timeout.assert_called_once_with(30)
        self.assertFalse(entities[0].available)
        self.assertTrue(self.coordinator.last_update_success)

    async def test_fractional_and_missing_updates_do_not_fabricate_counts(self):
        entities = await self.setup_entities()
        self.payload["drawerCleaning"] = {"remaining": 18.5, "count": 72.5, "tot": None}
        await self.timers[0](None)
        entities[0]._handle_coordinator_update(False)
        self.assertIsNone(entities[0].native_value)
        self.assertFalse(entities[0].available)
        self.assertEqual(entities[0].extra_state_attributes, {})
