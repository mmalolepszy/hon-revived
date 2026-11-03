import json
import unittest
from pathlib import Path
from unittest.mock import MagicMock
import tests.conftest_mock  # noqa: F401

from custom_components.hon.const import DOMAIN
from custom_components.hon.sensor import SENSORS, HonSensorEntity, HonAWEnergySensorEntity
from custom_components.hon.binary_sensor import BINARY_SENSORS, HonBinarySensorEntity, HonBinaryModeSensorEntity
from custom_components.hon.select import SELECTS, HonAWModeSelectEntity
from custom_components.hon.switch import SWITCHES, HonDeviceAttributeSwitchEntity, HonConfigSwitchEntity
from custom_components.hon.number import NUMBERS, HonNumberEntity, HonConfigNumberEntity
from pyhon.parameter.range import HonParameterRange


class RealApplianceMock:
    """Mock simulating a pyhon HonAppliance loaded with aw_16600 fixture data."""
    def __init__(self, fixture_dir: Path):
        with open(fixture_dir / "attributes.json", "r", encoding="utf-8") as f:
            self._raw_attrs = json.load(f)
        with open(fixture_dir / "commands.json", "r", encoding="utf-8") as f:
            self._raw_cmds = json.load(f)

        self.appliance_type = "AW"
        self.unique_id = "test_aw_16600"
        self.nick_name = "Heat Pump ATW-A03N"
        self.connection = True
        self.available_settings = []
        self.settings = {}
        self.commands = {}
        self.attributes = {}

        if (fixture_dir / "statistics.json").exists():
            with open(fixture_dir / "statistics.json", "r", encoding="utf-8") as f:
                stats_raw = json.load(f)
                self.statistics = stats_raw.get("payload", stats_raw)
        else:
            self.statistics = {}

        # 1. Flatten shadow parameters into attributes dictionary
        shadow_params = self._raw_attrs.get("shadow", {}).get("parameters", {})
        for k, v in shadow_params.items():
            val = v.get("parNewVal") if isinstance(v, dict) else v
            self.attributes[k] = val

        # Add top-level attributes
        if "lastConnEvent" in self._raw_attrs:
            self.attributes["attributes.lastConnEvent.category"] = self._raw_attrs["lastConnEvent"].get("category", "CONNECTED")

        # 2. Build pyhon settings from commands.json
        settings_params = self._raw_cmds.get("settings", {}).get("setParameters", {}).get("parameters", {})
        for param_name, param_info in settings_params.items():
            setting_key = f"settings.{param_name}"
            self.available_settings.append(setting_key)
            current_val = self.attributes.get(param_name, param_info.get("defaultValue", "0"))
            
            if param_info.get("typology") == "range":
                p_range = HonParameterRange(
                    value=float(current_val) if "." in str(current_val) else int(current_val),
                    min_val=float(param_info.get("minimumValue", 0)),
                    max_val=float(param_info.get("maximumValue", 100)),
                    step=float(param_info.get("incrementValue", 1)),
                )
                self.settings[setting_key] = p_range
            else:
                param_mock = MagicMock()
                param_mock.value = current_val
                self.settings[setting_key] = param_mock

        # 3. Build startProgram mock
        start_prog_mock = MagicMock()
        start_prog_mock.send = MagicMock()
        self.commands["startProgram"] = start_prog_mock

        prog_setting = MagicMock()
        # Extract program names from startProgram
        programs = []
        for p in self._raw_cmds.get("startProgram", {}).keys():
            prog_name = p.split(".")[-1].lower()
            programs.append(prog_name)
        prog_setting.values = programs
        prog_setting.value = "heat_dhw"
        self.settings["startProgram.program"] = prog_setting
        self.available_settings.append("startProgram.program")

        # 4. Build stopProgram mock
        stop_prog_mock = MagicMock()
        stop_prog_mock.send = MagicMock()
        self.commands["stopProgram"] = stop_prog_mock

    def get(self, key, default=None):
        return self.attributes.get(key, default)


class TestRealApplianceFixture(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture_path = Path("tests/fixtures/aw_16600")
        cls.device = RealApplianceMock(fixture_path)
        
        cls.entry = MagicMock()
        cls.entry.unique_id = "test_entry"
        cls.coordinator = MagicMock()
        cls.hon = MagicMock()
        cls.hass = MagicMock()
        cls.hass.data = {
            DOMAIN: {
                cls.entry.unique_id: {
                    "coordinator": cls.coordinator,
                    "hon": cls.hon,
                }
            }
        }

    def test_outdoor_and_dhw_temperatures(self):
        """Outdoor (8.9°C) and DHW (83.0°C) must be read accurately from shadow."""
        sensor_outdoor_desc = next(s for s in SENSORS["AW"] if s.key == "tempOutdoor")
        sensor_outdoor = HonSensorEntity(self.hass, self.entry, self.device, sensor_outdoor_desc)
        sensor_outdoor._handle_coordinator_update(update=False)
        self.assertEqual(sensor_outdoor._attr_native_value, 8.9)

        sensor_dhw_desc = next(s for s in SENSORS["AW"] if s.key == "tempDhw")
        sensor_dhw = HonSensorEntity(self.hass, self.entry, self.device, sensor_dhw_desc)
        sensor_dhw._handle_coordinator_update(update=False)
        self.assertEqual(sensor_dhw._attr_native_value, 83.0)

    def test_disconnected_zones_filtering(self):
        """Disconnected thermistors with -30.0°C in tempZ1 and tempZ2 must filter to None."""
        sensor_z1_desc = next(s for s in SENSORS["AW"] if s.key == "tempZ1")
        sensor_z1 = HonSensorEntity(self.hass, self.entry, self.device, sensor_z1_desc)
        sensor_z1._handle_coordinator_update(update=False)
        self.assertIsNone(sensor_z1._attr_native_value, "tempZ1=-30.0 should be filtered to None")

        sensor_z2_desc = next(s for s in SENSORS["AW"] if s.key == "tempZ2")
        sensor_z2 = HonSensorEntity(self.hass, self.entry, self.device, sensor_z2_desc)
        sensor_z2._handle_coordinator_update(update=False)
        self.assertIsNone(sensor_z2._attr_native_value, "tempZ2=-30.0 should be filtered to None")

    def test_binary_mode_sensors_with_real_mach_mode(self):
        """In real fixture, machMode='8' (Auto Heat+DHW) and onOffStatus='1'."""
        heating_desc = next(s for s in BINARY_SENSORS["AW"] if s.key == "heatingStatus")
        dhw_desc = next(s for s in BINARY_SENSORS["AW"] if s.key == "dhwStatus")

        heating_sensor = HonBinaryModeSensorEntity(self.hass, self.entry, self.device, heating_desc)
        dhw_sensor = HonBinaryModeSensorEntity(self.hass, self.entry, self.device, dhw_desc)

        self.assertTrue(heating_sensor.is_on, "machMode=8 must trigger heatingStatus ON")
        self.assertTrue(dhw_sensor.is_on, "machMode=8 must trigger dhwStatus ON")

    def test_select_mode_programs_from_real_device(self):
        """AWModeSelectEntity must expose all programs supported in commands.json."""
        select_desc = next(s for s in SELECTS["AW"] if s.key == "startProgram.program")
        select_entity = HonAWModeSelectEntity(self.hass, self.entry, self.device, select_desc)

        self.assertEqual(select_entity.current_option, "heat_dhw")
        self.assertIn("heat", select_entity.options)
        self.assertIn("cool", select_entity.options)
        self.assertIn("dhw", select_entity.options)
        self.assertIn("heat_dhw", select_entity.options)
        self.assertIn("cool_dhw", select_entity.options)

    def test_target_temperatures_and_curves(self):
        """Verify target DHW temp (63.5°C), zone 1 temp (39.0°C), and outdoor curves."""
        dhw_num_desc = next(n for n in NUMBERS["AW"] if n.key == "settings.tempSelDhw")
        dhw_num = HonNumberEntity(self.hass, self.entry, self.device, dhw_num_desc)
        dhw_num._handle_coordinator_update(update=False)
        self.assertEqual(dhw_num._attr_native_value, 63.5)

        z1_num_desc = next(n for n in NUMBERS["AW"] if n.key == "settings.tempSelZ1")
        z1_num = HonNumberEntity(self.hass, self.entry, self.device, z1_num_desc)
        z1_num._handle_coordinator_update(update=False)
        self.assertEqual(z1_num._attr_native_value, 39.0)

        # Config number: Heating curve 3
        curve3_desc = next(n for n in NUMBERS["AW"] if n.key == "settings.highOutdoorTempCurve3")
        curve3_num = HonConfigNumberEntity(self.hass, self.entry, self.device, curve3_desc)
        curve3_num._handle_coordinator_update(update=False)
        self.assertEqual(curve3_num._attr_native_value, 20.0)

    def test_switch_entities_from_fixture(self):
        """Test power switch is ON and quiet mode switch is OFF."""
        power_desc = next(s for s in SWITCHES["AW"] if s.key == "onOffStatus")
        power_switch = HonDeviceAttributeSwitchEntity(self.hass, self.entry, self.device, power_desc)
        self.assertTrue(power_switch.is_on)

        quiet_desc = next(s for s in SWITCHES["AW"] if s.key == "quietMode1")
        quiet_switch = HonDeviceAttributeSwitchEntity(self.hass, self.entry, self.device, quiet_desc)
        self.assertFalse(quiet_switch.is_on)

    def test_energy_statistics_and_cop(self):
        """Verify energy consumption, thermal heat production, and COP sensors from real statistics."""
        energy_sensors = {
            s.key: s for s in SENSORS["AW"] if s.key.startswith("stats.")
        }
        self.assertEqual(len(energy_sensors), 10)

        # 1. Heating energy consumption (3438 kWh)
        s_desc = energy_sensors["stats.heatHeatPumpEnergyConsumption"]
        entity = HonAWEnergySensorEntity(self.hass, self.entry, self.device, s_desc)
        self.assertEqual(entity.native_value, 3438)
        self.assertEqual(entity.native_unit_of_measurement, "kWh")
        self.assertEqual(entity.extra_state_attributes.get("current_year"), 3270)
        self.assertEqual(entity.extra_state_attributes.get("today"), 18)
        self.assertEqual(entity.extra_state_attributes.get("storage_date"), "2026-11-03 14:00")

        # 2. DHW energy consumption (1279 kWh)
        s_desc = energy_sensors["stats.dhwHeatPumpEnergyConsumption"]
        entity = HonAWEnergySensorEntity(self.hass, self.entry, self.device, s_desc)
        self.assertEqual(entity.native_value, 1279)
        self.assertEqual(entity.extra_state_attributes.get("today"), 4)

        # 3. Cooling energy consumption (0 kWh)
        s_desc = energy_sensors["stats.coolEnergyConsumption"]
        entity = HonAWEnergySensorEntity(self.hass, self.entry, self.device, s_desc)
        self.assertEqual(entity.native_value, 0)

        # 4. Total energy consumption (4717 kWh)
        s_desc = energy_sensors["stats.totalEnergyConsumption"]
        entity = HonAWEnergySensorEntity(self.hass, self.entry, self.device, s_desc)
        self.assertEqual(entity.native_value, 4717)
        self.assertEqual(entity.extra_state_attributes.get("heating_kwh"), 3438)
        self.assertEqual(entity.extra_state_attributes.get("dhw_kwh"), 1279)

        # 5. Heating heat production (16133 kWh)
        s_desc = energy_sensors["stats.heatHeatPumpHeatProduction"]
        entity = HonAWEnergySensorEntity(self.hass, self.entry, self.device, s_desc)
        self.assertEqual(entity.native_value, 16133)
        self.assertEqual(entity.extra_state_attributes.get("current_year"), 15493)
        self.assertEqual(entity.extra_state_attributes.get("today"), 113)

        # 6. DHW heat production (5716 kWh)
        s_desc = energy_sensors["stats.dhwHeatPumpHeatProduction"]
        entity = HonAWEnergySensorEntity(self.hass, self.entry, self.device, s_desc)
        self.assertEqual(entity.native_value, 5716)
        self.assertEqual(entity.extra_state_attributes.get("today"), 21)

        # 7. Total heat production (21849 kWh)
        s_desc = energy_sensors["stats.totalHeatProduction"]
        entity = HonAWEnergySensorEntity(self.hass, self.entry, self.device, s_desc)
        self.assertEqual(entity.native_value, 21849)

        # 8. COP (4.63)
        s_desc = energy_sensors["stats.cop"]
        entity = HonAWEnergySensorEntity(self.hass, self.entry, self.device, s_desc)
        self.assertEqual(entity.native_value, 4.63)
        self.assertEqual(entity.extra_state_attributes.get("cop_heating"), 4.69)
        self.assertEqual(entity.extra_state_attributes.get("cop_dhw"), 4.47)
        self.assertEqual(entity.extra_state_attributes.get("cop_today"), 6.09)


if __name__ == "__main__":
    unittest.main()
