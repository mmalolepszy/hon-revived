"""Native Core climate/config-flow compatibility without provider requests."""

import importlib
import logging
import socket
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from homeassistant import loader
from homeassistant.config_entries import ConfigEntries
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator


class CoreCompatibilityTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.hass = HomeAssistant(directory.name)
        self.hass.config.skip_pip = True
        self.hass.config_entries = ConfigEntries(self.hass, {})
        loader.async_setup(self.hass)
        for name in ("connect", "connect_ex", "sendto", "sendmsg"):
            self.enterContext(
                patch.object(socket.socket, name, side_effect=AssertionError("Network"))
            )
        self.enterContext(
            patch.object(socket, "getaddrinfo", side_effect=AssertionError("DNS"))
        )

    async def asyncTearDown(self):
        await self.hass.async_stop(force=True)
        await self.hass.async_block_till_done()

    async def test_climate_temperatures_without_deprecation_warnings(self):
        with self.assertNoLogs(level="WARNING"):
            climate = importlib.import_module("custom_components.hon.climate")
            climate = importlib.reload(climate)
        coordinator = DataUpdateCoordinator(
            self.hass, logging.getLogger(__name__), name="synthetic", config_entry=None
        )
        self.hass.data[climate.DOMAIN] = {
            "synthetic": {"coordinator": coordinator, "hon": None}
        }
        for entity_type, description, target, current in (
            (
                climate.HonACClimateEntity,
                climate.CLIMATES["AC"][0],
                "tempSel",
                "tempIndoor",
            ),
            (
                climate.HonClimateEntity,
                climate.CLIMATES["OV"][0],
                "settings.tempSel",
                "temp",
            ),
        ):
            with self.subTest(entity=entity_type.__name__):
                values = {
                    target: 24.0,
                    current: 21.5,
                    "windSpeed": 1,
                    "windDirectionHorizontal": 0,
                    "windDirectionVertical": 0,
                }
                temperature = MagicMock(spec=climate.HonParameterRange)
                temperature.min, temperature.max, temperature.step = 16, 30, 1
                device = SimpleNamespace(
                    unique_id="synthetic",
                    get=values.get,
                    settings={
                        "settings.tempSel": temperature,
                        "settings.machMode": SimpleNamespace(values=["0"]),
                        "startProgram.program": SimpleNamespace(values=[]),
                    },
                    commands={"startProgram": SimpleNamespace(categories={})},
                )
                with self.assertNoLogs(level="WARNING"):
                    entity = entity_type(
                        self.hass,
                        SimpleNamespace(unique_id="synthetic"),
                        device,
                        description,
                    )
                    entity.hass = self.hass
                    self.assertEqual(
                        entity.state_attributes["current_temperature"], 21.5
                    )
                    self.assertEqual(entity.state_attributes["temperature"], 24.0)
                    values[current] = None
                    self.assertIsNone(entity.state_attributes["current_temperature"])
                    values[target] = 25.0
                    self.assertEqual(entity.state_attributes["temperature"], 25.0)

    async def test_config_flow_without_deprecated_connection_class(self):
        with self.assertNoLogs(level="WARNING"):
            module = importlib.import_module("custom_components.hon.config_flow")
            module = importlib.reload(module)
            flow = module.HonFlowHandler()
            flow.hass = self.hass
            result = await flow.async_step_user()
        self.assertEqual(result["type"], "form")
        self.assertEqual(result["step_id"], "user")
        self.assertEqual(
            result["data_schema"](
                {"email": "synthetic@example.invalid", "password": "synthetic"}
            ),
            {"email": "synthetic@example.invalid", "password": "synthetic"},
        )


if __name__ == "__main__":
    unittest.main()
