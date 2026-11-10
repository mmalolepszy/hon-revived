import unittest
import json
from pathlib import Path
from unittest.mock import MagicMock
import tests.conftest_mock  # noqa: F401

from custom_components.hon.const import DOMAIN, APPLIANCES, SENSOR_ATTRIBUTES
from custom_components.hon.sensor import SENSORS, HonSensorEntity, HonSensorEntityDescription
from custom_components.hon.binary_sensor import (
    BINARY_SENSORS,
    HonBinaryModeSensorEntity,
    HonBinarySensorEntityDescription,
)
from custom_components.hon.select import (
    SELECTS,
    AW_MODE_MAP,
    HonAWModeSelectEntity,
    HonAWModeSelectEntityDescription,
)
from custom_components.hon.number import (
    NUMBERS,
    HonConfigNumberEntity,
    HonConfigNumberEntityDescription,
)
from custom_components.hon.switch import (
    SWITCHES,
    HonDeviceAttributeSwitchEntity,
    HonDeviceAttributeSwitchEntityDescription,
)
from pyhon.parameter.range import HonParameterRange


class MockDevice:
    def __init__(self, data=None, settings=None, commands=None):
        self.data = data or {}
        self.settings = settings or {}
        self.commands = commands or {}
        self.unique_id = "test_device_123"
        self.nick_name = "Heat Pump"
        self.connection = True
        self.attributes = {}

    def get(self, key, default=None):
        return self.data.get(key, default)


def create_mock_hass_and_entry():
    entry = MagicMock()
    entry.unique_id = "test_entry"
    coordinator = MagicMock()
    hon = MagicMock()

    hass = MagicMock()
    hass.data = {
        DOMAIN: {
            entry.unique_id: {
                "coordinator": coordinator,
                "hon": hon,
            }
        }
    }
    return hass, entry


class TestHeatPumpEntities(unittest.TestCase):
    def setUp(self):
        self.hass, self.entry = create_mock_hass_and_entry()

    def test_const_aw(self):
        """Verify AW and HW appliance and sensor attributes are declared."""
        self.assertIn("AW", APPLIANCES)
        self.assertEqual(APPLIANCES["AW"], "Heat Pump")
        self.assertIn("HW", APPLIANCES)
        self.assertEqual(APPLIANCES["HW"], "Heat Pump Water Heater")
        self.assertIn("machMode", SENSOR_ATTRIBUTES)
        self.assertIn("tempOutdoor", SENSOR_ATTRIBUTES)
        self.assertIn("flowRate", SENSOR_ATTRIBUTES)
        self.assertIn("temp", SENSOR_ATTRIBUTES)
        self.assertIn("remainingWaterLevel", SENSOR_ATTRIBUTES)
        self.assertIn("compressorHeatingCurrentStatus", SENSOR_ATTRIBUTES)

    def test_sensors_aw_definitions(self):
        """Verify AW and HW sensors definitions exist."""
        self.assertIn("AW", SENSORS)
        keys = [s.key for s in SENSORS["AW"]]
        expected = [
            "tempOutdoor",
            "tempDhw",
            "tempZ1",
            "tempZ2",
            "tempWaterOut",
            "tempWaterIn",
            "compressorFrequency",
            "currentPower",
            "totalPower",
            "flowRate",
            "errors",
            # Energy & Production statistics
            "stats.heatHeatPumpEnergyConsumption",
            "stats.dhwHeatPumpEnergyConsumption",
            "stats.coolEnergyConsumption",
            "stats.heatElectricHeaterEnergyConsumption",
            "stats.dhwElectricHeaterEnergyConsumption",
            "stats.totalEnergyConsumption",
            "stats.heatHeatPumpHeatProduction",
            "stats.dhwHeatPumpHeatProduction",
            "stats.totalHeatProduction",
            "stats.cop",
        ]
        for exp in expected:
            self.assertIn(exp, keys)

        # Check HW sensors
        self.assertIn("HW", SENSORS)
        hw_keys = [s.key for s in SENSORS["HW"]]
        for exp in ("temp", "tempSel", "remainingWaterLevel", "productVolume", "energyConsumptionYearCp", "accumulatedHeatYear"):
            self.assertIn(exp, hw_keys)

    def test_sensor_invalid_temperature_handling(self):
        """Test -30°C disconnected sensor filtering in HonSensorEntity."""
        from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
        desc = HonSensorEntityDescription(
            key="tempZ2",
            device_class=SensorDeviceClass.TEMPERATURE,
            state_class=SensorStateClass.MEASUREMENT,
        )
        # Test normal temp
        device = MockDevice(data={"tempZ2": 21.5})
        sensor = HonSensorEntity(self.hass, self.entry, device, desc)
        sensor._handle_coordinator_update(update=False)
        self.assertEqual(sensor._attr_native_value, 21.5)

        # Test -30°C disconnected thermistor returns None
        device.data["tempZ2"] = -30.0
        sensor._handle_coordinator_update(update=False)
        self.assertIsNone(sensor._attr_native_value)

        device.data["tempZ2"] = "-30"
        sensor._handle_coordinator_update(update=False)
        self.assertIsNone(sensor._attr_native_value)

    def test_binary_sensors_aw_definitions(self):
        """Verify AW and HW binary sensors definitions exist."""
        self.assertIn("AW", BINARY_SENSORS)
        keys = [s.key for s in BINARY_SENSORS["AW"]]
        self.assertIn("heatingStatus", keys)
        self.assertIn("dhwStatus", keys)
        self.assertIn("boilerActState", keys)

        self.assertIn("HW", BINARY_SENSORS)
        hw_keys = [s.key for s in BINARY_SENSORS["HW"]]
        self.assertIn("compressorHeatingCurrentStatus", hw_keys)
        self.assertIn("electricHeatingCurrentStatus", hw_keys)
        self.assertIn("auxElecHeatingStatus", hw_keys)

    def test_binary_mode_sensor_entity(self):
        """Test HonBinaryModeSensorEntity logic based on machMode and onOffStatus."""
        desc = HonBinarySensorEntityDescription(
            key="heatingStatus",
            name="Heating Mode",
            on_values=("2", "8"),
        )
        device = MockDevice(data={"onOffStatus": "1", "machMode": "2"})
        entity = HonBinaryModeSensorEntity(self.hass, self.entry, device, desc)
        self.assertTrue(entity.is_on)

        # machMode 8 (Auto heat + dhw)
        device.data["machMode"] = "8"
        self.assertTrue(entity.is_on)

        # machMode 3 (DHW only) -> heatingStatus is False
        device.data["machMode"] = "3"
        self.assertFalse(entity.is_on)

        # Turned off completely (onOffStatus = 0) -> False
        device.data["machMode"] = "2"
        device.data["onOffStatus"] = "0"
        self.assertFalse(entity.is_on)

    def test_select_aw_mode(self):
        """Test HonAWModeSelectEntity current_option and options."""
        desc = HonAWModeSelectEntityDescription(key="startProgram.program")
        setting_mock = MockDevice()
        setting_mock.values = ["heat", "cool", "auto", "heat_dhw", "unsupported_xyz"]

        device = MockDevice(
            data={"machMode": "8"},
            settings={"startProgram.program": setting_mock},
        )
        select = HonAWModeSelectEntity(self.hass, self.entry, device, desc)

        # machMode "8" maps to "heat_dhw"
        self.assertEqual(select.current_option, "heat_dhw")
        # Allowed options are filtered by AW_MODE_MAP
        self.assertIn("heat_dhw", select.options)
        self.assertIn("heat", select.options)
        self.assertNotIn("unsupported_xyz", select.options)

    def test_number_aw_step_formatting(self):
        """Test integer vs float step formatting to prevent API crashes."""
        desc = HonConfigNumberEntityDescription(key="settings.turboModeTime")
        # Range with step 1.0 -> should convert value to int
        int_param = HonParameterRange(value=20, min_val=10, max_val=60, step=1.0)
        device = MockDevice(settings={"settings.turboModeTime": int_param})
        entity = HonConfigNumberEntity(self.hass, self.entry, device, desc)

        import asyncio
        asyncio.run(entity.async_set_native_value(30.0))
        self.assertIsInstance(int_param.value, int)
        self.assertEqual(int_param.value, 30)

        # Range with step 0.5 -> should keep float
        float_param = HonParameterRange(value=20.5, min_val=10, max_val=60, step=0.5)
        device.settings["settings.turboModeTime"] = float_param
        asyncio.run(entity.async_set_native_value(30.5))
        self.assertIsInstance(float_param.value, float)
        self.assertEqual(float_param.value, 30.5)

    def test_switch_aw_device_attribute(self):
        """Test HonDeviceAttributeSwitchEntity state checking."""
        desc = HonDeviceAttributeSwitchEntityDescription(
            key="onOffStatus",
            read_key="onOffStatus",
            turn_on_value="1",
            turn_off_value="0",
        )
        device = MockDevice(data={"onOffStatus": "1"})
        entity = HonDeviceAttributeSwitchEntity(self.hass, self.entry, device, desc)
        self.assertTrue(entity.is_on)

        device.data["onOffStatus"] = "0"
        self.assertFalse(entity.is_on)

    def test_translations_de(self):
        """Verify German translations contain key AW terms."""
        de_path = Path("custom_components/hon/translations/de.json")
        with open(de_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        entities = data.get("entity", {})

        # Sensor
        self.assertIn("outdoor_temperature", entities.get("sensor", {}))
        self.assertEqual(entities["sensor"]["outdoor_temperature"]["name"], "Außentemperatur")
        self.assertIn("heating_energy_consumption", entities.get("sensor", {}))
        self.assertEqual(entities["sensor"]["heating_energy_consumption"]["name"], "Energieverbrauch Heizen")
        self.assertIn("dhw_energy_consumption", entities.get("sensor", {}))
        self.assertEqual(entities["sensor"]["dhw_energy_consumption"]["name"], "Energieverbrauch Warmwasser")
        self.assertIn("total_energy_consumption", entities.get("sensor", {}))
        self.assertEqual(entities["sensor"]["total_energy_consumption"]["name"], "Gesamtenergieverbrauch Wärmepumpe")
        self.assertIn("heating_heat_production", entities.get("sensor", {}))
        self.assertEqual(entities["sensor"]["heating_heat_production"]["name"], "Wärmeproduktion Heizen")
        self.assertIn("dhw_heat_production", entities.get("sensor", {}))
        self.assertEqual(entities["sensor"]["dhw_heat_production"]["name"], "Wärmeproduktion Warmwasser")
        self.assertIn("total_heat_production", entities.get("sensor", {}))
        self.assertEqual(entities["sensor"]["total_heat_production"]["name"], "Gesamtwärmeproduktion")
        self.assertIn("cop", entities.get("sensor", {}))
        self.assertEqual(entities["sensor"]["cop"]["name"], "Arbeitszahl (COP)")

        # Select
        self.assertIn("programs_aw", entities.get("select", {}))
        self.assertIn("programs_hw", entities.get("select", {}))

        # Switch
        self.assertIn("power_switch", entities.get("switch", {}))
        self.assertEqual(entities["switch"]["power_switch"]["name"], "Hauptschalter")

        # Binary sensor
        self.assertIn("heating_mode", entities.get("binary_sensor", {}))
        self.assertEqual(entities["binary_sensor"]["heating_mode"]["name"], "Heizbetrieb")
        self.assertIn("compressor_heating", entities.get("binary_sensor", {}))


if __name__ == "__main__":
    unittest.main()
