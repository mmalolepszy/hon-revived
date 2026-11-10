import json
import unittest
from pathlib import Path
from unittest.mock import MagicMock
import tests.conftest_mock  # noqa: F401

from custom_components.hon.const import DOMAIN
from custom_components.hon.sensor import SENSORS, HonSensorEntity
from custom_components.hon.binary_sensor import BINARY_SENSORS, HonBinarySensorEntity
from custom_components.hon.select import SELECTS, HonHWModeSelectEntity
from custom_components.hon.switch import SWITCHES, HonDeviceAttributeSwitchEntity
from custom_components.hon.number import NUMBERS, HonNumberEntity, HonConfigNumberEntity
from pyhon.parameter.range import HonParameterRange


class RealApplianceHWMock:
    """Mock simulating a pyhon HonAppliance loaded with hw_13664 fixture data."""
    def __init__(self, fixture_dir: Path):
        with open(fixture_dir / "attributes.json", "r", encoding="utf-8") as f:
            self._raw_attrs = json.load(f)
        with open(fixture_dir / "commands.json", "r", encoding="utf-8") as f:
            self._raw_cmds = json.load(f)

        self.appliance_type = "HW"
        self.unique_id = "test_hw_13664"
        self.nick_name = "Heat Pump Water Heater HP250M7-F9"
        self.connection = True
        self.available_settings = []
        self.settings = {}
        self.commands = {}
        self.attributes = {}

        # 1. Flatten shadow parameters into attributes dictionary
        shadow_params = self._raw_attrs.get("shadow", {}).get("parameters", {})
        for k, v in shadow_params.items():
            val = v.get("parNewVal") if isinstance(v, dict) else v
            self.attributes[k] = val

        if "lastConnEvent" in self._raw_attrs:
            self.attributes["attributes.lastConnEvent.category"] = self._raw_attrs["lastConnEvent"].get("category", "CONNECTED")

        # 2. Build pyhon settings from commands.json
        settings_params = self._raw_cmds.get("settings", {}).get("setParameters", {}).get("parameters", {})
        for param_name, param_info in settings_params.items():
            setting_key = f"settings.{param_name}"
            self.available_settings.append(setting_key)
            current_val = self.attributes.get(param_name, param_info.get("defaultValue", "0"))

            if param_info.get("typology") == "range":
                try:
                    val_num = float(current_val) if "." in str(current_val) else int(current_val)
                except (ValueError, TypeError):
                    val_num = float(param_info.get("minimumValue", 0))
                p_range = HonParameterRange(
                    value=val_num,
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
        programs = []
        for p in self._raw_cmds.get("startProgram", {}).keys():
            prog_name = p.split(".")[-1].lower()
            programs.append(prog_name)
        prog_setting.values = programs
        prog_setting.value = "auto"
        self.settings["startProgram.program"] = prog_setting
        self.available_settings.append("startProgram.program")

        # 4. Settings command mock
        settings_cmd_mock = MagicMock()
        settings_cmd_mock.send = MagicMock()
        self.commands["settings"] = settings_cmd_mock

    def get(self, key, default=None):
        return self.attributes.get(key, default)


class TestRealApplianceHWFixture(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture_path = Path("tests/fixtures/hw_13664")
        cls.device = RealApplianceHWMock(fixture_path)

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

    def test_water_temperatures_and_level(self):
        """Water temperature (47°C), target (55°C), remaining level (11%), volume (250 L)."""
        sensors = {s.key: s for s in SENSORS["HW"]}

        # Current water temperature
        temp_sensor = HonSensorEntity(self.hass, self.entry, self.device, sensors["temp"])
        temp_sensor._handle_coordinator_update(update=False)
        self.assertEqual(temp_sensor.native_value, 47.0)

        # Target temperature
        target_sensor = HonSensorEntity(self.hass, self.entry, self.device, sensors["tempSel"])
        target_sensor._handle_coordinator_update(update=False)
        self.assertEqual(target_sensor.native_value, 55.0)

        # Remaining water level
        level_sensor = HonSensorEntity(self.hass, self.entry, self.device, sensors["remainingWaterLevel"])
        level_sensor._handle_coordinator_update(update=False)
        self.assertEqual(level_sensor.native_value, 11.0)

        # Volume
        vol_sensor = HonSensorEntity(self.hass, self.entry, self.device, sensors["productVolume"])
        vol_sensor._handle_coordinator_update(update=False)
        self.assertEqual(int(vol_sensor.native_value), 250)

    def test_energy_and_heat_production(self):
        """Semicolon-delimited values must parse correctly to current year values."""
        sensors = {s.key: s for s in SENSORS["HW"]}

        # Compressor energy (0;0;0;0;158 -> 158.0 kWh)
        cp_sensor = HonSensorEntity(self.hass, self.entry, self.device, sensors["energyConsumptionYearCp"])
        cp_sensor._handle_coordinator_update(update=False)
        self.assertEqual(cp_sensor.native_value, 158.0)

        # Electric heater energy (0;0;0;0;19 -> 19.0 kWh)
        ec_sensor = HonSensorEntity(self.hass, self.entry, self.device, sensors["energyConsumptionYearEc"])
        ec_sensor._handle_coordinator_update(update=False)
        self.assertEqual(ec_sensor.native_value, 19.0)

        # Total heat production (0;0;0;0;949 -> 949.0 kWh)
        heat_sensor = HonSensorEntity(self.hass, self.entry, self.device, sensors["accumulatedHeatYear"])
        heat_sensor._handle_coordinator_update(update=False)
        self.assertEqual(heat_sensor.native_value, 949.0)

    def test_binary_sensors(self):
        """Test compressor running, power on, and electric heater off."""
        binary_sensors = {s.key: s for s in BINARY_SENSORS["HW"]}

        # Power status (1 -> True)
        power = HonBinarySensorEntity(self.hass, self.entry, self.device, binary_sensors["onOffStatus"])
        self.assertTrue(power.is_on)

        # Compressor heating active (1 -> True)
        comp = HonBinarySensorEntity(self.hass, self.entry, self.device, binary_sensors["compressorHeatingCurrentStatus"])
        self.assertTrue(comp.is_on)

        # Electric heating inactive (0 -> False)
        elec = HonBinarySensorEntity(self.hass, self.entry, self.device, binary_sensors["electricHeatingCurrentStatus"])
        self.assertFalse(elec.is_on)

        # Solar heating inactive (0 -> False)
        solar = HonBinarySensorEntity(self.hass, self.entry, self.device, binary_sensors["solarHeatingCurrentStatus"])
        self.assertFalse(solar.is_on)

    def test_switches(self):
        """Test power switch ON, boost/silent/sterilization OFF."""
        switches = {s.key: s for s in SWITCHES["HW"]}

        power = HonDeviceAttributeSwitchEntity(self.hass, self.entry, self.device, switches["onOffStatus"])
        self.assertTrue(power.is_on)

        boost = HonDeviceAttributeSwitchEntity(self.hass, self.entry, self.device, switches["boostStatus"])
        self.assertFalse(boost.is_on)

        silent = HonDeviceAttributeSwitchEntity(self.hass, self.entry, self.device, switches["silentStatus"])
        self.assertFalse(silent.is_on)

        steri = HonDeviceAttributeSwitchEntity(self.hass, self.entry, self.device, switches["sterilizationStatus"])
        self.assertFalse(steri.is_on)

    def test_mode_select(self):
        """HonHWModeSelectEntity must map machMode 2 to auto and expose programs."""
        select_desc = next(s for s in SELECTS["HW"] if s.key == "startProgram.program")
        select = HonHWModeSelectEntity(self.hass, self.entry, self.device, select_desc)

        # machMode "2" -> "auto"
        self.assertEqual(select.current_option, "auto")
        self.assertIn("auto", select.options)
        self.assertIn("eco", select.options)
        self.assertIn("elec", select.options)
        self.assertIn("vac", select.options)

    def test_target_temperatures(self):
        """Test number entities: target water temp (55.0°C) and sterilization temp (66.1°C)."""
        numbers = {n.key: n for n in NUMBERS["HW"]}

        target_temp = HonNumberEntity(self.hass, self.entry, self.device, numbers["settings.tempSel"])
        target_temp._handle_coordinator_update(update=False)
        self.assertEqual(target_temp.native_value, 55.0)

        steri_temp = HonConfigNumberEntity(self.hass, self.entry, self.device, numbers["settings.sterilizationTempSel"])
        steri_temp._handle_coordinator_update(update=False)
        self.assertEqual(steri_temp.native_value, 66.1)


if __name__ == "__main__":
    unittest.main()
