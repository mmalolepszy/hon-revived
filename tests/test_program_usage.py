"""Most-used washer programs share the maintenance statistics refresh."""

# pylint: disable=protected-access

import logging
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

from homeassistant import loader
from homeassistant.bootstrap import async_load_base_functionality
from homeassistant.config_entries import ConfigEntries
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_component import EntityComponent

from custom_components.hon import sensor, washer_statistics
from custom_components.hon.const import DOMAIN


class ProgramUsageTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.timers = []
        self.cancel = Mock()
        self.unloads = []
        self.track = patch.object(
            washer_statistics,
            "async_track_time_interval",
            side_effect=lambda _hass, action, _interval: (
                self.timers.append(action) or self.cancel
            ),
        )
        self.track.start()
        self.addCleanup(self.track.stop)
        self.payload = {
            "mostUsedPrograms": [
                {
                    "programName": "PROGRAMS.WM_WD.ALL_IN_ONE_59",
                    "count": 48,
                    "prCode": 1,
                    "prPosition": 2,
                    "ignored": "private",
                },
                {"programName": "PROGRAMS.WM_WD.ALL_IN_ONE_49", "count": "17"},
                {"programName": "HANDWASH_WOOL", "count": 13},
                {"programName": "NEW_NAME", "count": 13},
                {"programName": "invalid", "count": -1},
            ],
            "programsCounter": 167,
            "drawerCleaning": {"remaining": 18},
        }
        self.device = SimpleNamespace(
            appliance_type="WM",
            unique_id="test",
            available_settings=[],
            get=lambda key, default=None: (
                self.payload if key == "statistics" else default
            ),
            load_statistics=AsyncMock(),
            nick_name="washer",
            model_name="test",
            model_id="test",
        )
        self.coordinator = SimpleNamespace(
            last_update_success=True,
            data={},
            async_update_listeners=Mock(),
            async_add_listener=Mock(return_value=lambda: None),
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

    def usage(self):
        return washer_statistics.program_usage_entities(
            self.hass, self.entry, self.device
        )

    async def test_ranking_is_normalized_sorted_and_sanitized(self):
        entity = self.usage()[0]
        self.assertEqual(entity.native_value, "all_in_one_59")
        ranking = entity.extra_state_attributes["ranking"]
        self.assertEqual(
            [item["program"] for item in ranking],
            ["all_in_one_59", "all_in_one_49", "handwash_wool", "new_name"],
        )
        self.assertEqual(
            ranking[0],
            {"program": "all_in_one_59", "count": 48, "pr_code": 1, "pr_position": 2},
        )
        self.assertEqual(entity.extra_state_attributes["programs_counter"], 167)
        self.assertTrue(entity.available)

    async def test_empty_and_invalid_rankings_are_unknown(self):
        self.payload["mostUsedPrograms"] = [
            {"programName": "bad", "count": True},
            {"programName": "bad", "count": 1.5},
            {"programName": None, "count": 1},
            {"programName": "A.", "count": 1},
        ]
        self.payload["programsCounter"] = "167.5"
        entity = self.usage()[0]
        self.assertIsNone(entity.native_value)
        self.assertEqual(entity.extra_state_attributes, {"ranking": []})
        self.assertTrue(entity.available)

    async def test_shared_refresh_is_registered_once(self):
        counters = await washer_statistics.async_setup_maintenance(
            self.hass, self.entry, self.device
        )
        entity = self.usage()[0]
        self.assertEqual(len(counters), 1)
        self.assertEqual(len(self.timers), 1)
        self.device.load_statistics.assert_not_awaited()
        self.payload["mostUsedPrograms"][0]["count"] = 3
        await self.timers[0](None)
        entity._handle_coordinator_update(False)
        self.assertEqual(entity.native_value, "all_in_one_49")
        self.device.load_statistics.assert_awaited_once()
        self.coordinator.async_update_listeners.assert_called_once()
        self.unloads[0]()
        self.cancel.assert_called_once()

    async def test_ranking_without_maintenance_has_one_refresh(self):
        self.payload.pop("drawerCleaning")
        self.assertEqual(
            await washer_statistics.async_setup_maintenance(
                self.hass, self.entry, self.device
            ),
            [],
        )
        self.assertEqual(len(self.timers), 0)
        self.assertEqual(self.usage()[0].native_value, "all_in_one_59")
        self.assertEqual(len(self.timers), 1)

    async def test_empty_startup_discovers_both_with_one_fetch(self):
        self.payload = None

        async def load():
            self.payload = {
                "mostUsedPrograms": [{"programName": "COTTON", "count": "2.0"}],
                "drawerCleaning": {"remaining": 0},
            }

        self.device.load_statistics.side_effect = load
        entities = []
        await sensor.async_setup_entry(self.hass, self.entry, entities.extend)
        self.assertEqual(len(entities), 2)
        self.assertEqual(len(self.timers), 1)
        self.device.load_statistics.assert_awaited_once()
        self.assertIn("cotton", [entity.native_value for entity in entities])

    async def test_missing_ranking_does_not_register_timer(self):
        self.payload = {"mostUsedPrograms": None}
        self.assertEqual(self.usage(), [])
        self.assertEqual(len(self.timers), 0)

    async def test_failed_refresh_marks_statistics_unavailable_and_recovers(self):
        entity = self.usage()[0]
        self.device.load_statistics.side_effect = RuntimeError("sensitive detail")
        with self.assertLogs(washer_statistics.__name__, level="WARNING") as logs:
            await self.timers[0](None)
        self.assertNotIn("sensitive detail", str(logs.output))
        self.assertFalse(entity.available)
        self.assertEqual(entity.native_value, "all_in_one_59")
        self.device.load_statistics.side_effect = None
        await self.timers[0](None)
        entity._handle_coordinator_update(False)
        self.assertTrue(entity.available)

    async def test_native_sensor_publication(self):
        self.track.stop()
        with TemporaryDirectory() as directory:
            hass = HomeAssistant(directory)
            hass.data[DOMAIN] = self.hass.data[DOMAIN]
            hass.config.skip_pip = True
            hass.config_entries = ConfigEntries(hass, {})
            loader.async_setup(hass)
            self.assertTrue(await async_load_base_functionality(hass))
            entity = washer_statistics.program_usage_entities(
                hass, self.entry, self.device
            )[0]
            component = EntityComponent(logging.getLogger(__name__), "sensor", hass)
            await component.async_add_entities([entity])
            state = hass.states.get(entity.entity_id)
            self.assertIsNotNone(state)
            self.assertEqual(state.state, "all_in_one_59")
            self.assertEqual(state.attributes["ranking"][0]["count"], 48)
            self.unloads[0]()
            await entity.async_remove()
            await hass.async_stop(force=True)
