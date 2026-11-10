"""Lightweight mocks for homeassistant and pyhon for standalone test execution."""
import sys
import types
from dataclasses import dataclass
from unittest.mock import MagicMock

def ensure_module(name):
    parts = name.split(".")
    for i in range(1, len(parts) + 1):
        sub_name = ".".join(parts[:i])
        if sub_name not in sys.modules:
            mod = types.ModuleType(sub_name)
            sys.modules[sub_name] = mod
            if i > 1:
                setattr(sys.modules[".".join(parts[:i-1])], parts[i-1], mod)
    return sys.modules[name]

# Setup module hierarchy
for mod_name in [
    "voluptuous",
    "homeassistant",
    "homeassistant.core",
    "homeassistant.config_entries",
    "homeassistant.const",
    "homeassistant.data_entry_flow",
    "homeassistant.helpers",
    "homeassistant.helpers.config_validation",
    "homeassistant.helpers.aiohttp_client",
    "homeassistant.helpers.entity",
    "homeassistant.helpers.entity_platform",
    "homeassistant.helpers.update_coordinator",
    "homeassistant.helpers.event",
    "homeassistant.components",
    "homeassistant.components.persistent_notification",
    "homeassistant.components.binary_sensor",
    "homeassistant.components.sensor",
    "homeassistant.components.select",
    "homeassistant.components.number",
    "homeassistant.components.switch",
    "homeassistant.components.climate",
    "homeassistant.components.climate.const",
    "homeassistant.components.fan",
    "homeassistant.components.light",
    "homeassistant.components.lock",
    "homeassistant.components.button",
    "homeassistant.util",
    "homeassistant.util.percentage",
    "pyhon",
    "pyhon.parameter",
    "pyhon.parameter.base",
    "pyhon.parameter.range",
    "pyhon.appliance",
    "pyhon.connection",
    "pyhon.connection.api",
]:
    ensure_module(mod_name)

class VolMock:
    @staticmethod
    def Schema(*args, **kwargs):
        return MagicMock()
    @staticmethod
    def Required(*args, **kwargs):
        return MagicMock()
    @staticmethod
    def Optional(*args, **kwargs):
        return MagicMock()
    @staticmethod
    def All(*args, **kwargs):
        return MagicMock()
    ALLOW_EXTRA = 1
for k, v in VolMock.__dict__.items():
    if not k.startswith("__"):
        setattr(sys.modules["voluptuous"], k, v)

# Helpers aliases
sys.modules["homeassistant.helpers"].config_validation = sys.modules["homeassistant.helpers.config_validation"]
sys.modules["homeassistant.helpers"].aiohttp_client = sys.modules["homeassistant.helpers.aiohttp_client"]
sys.modules["homeassistant.helpers.config_validation"].string = str
sys.modules["homeassistant.helpers.config_validation"].boolean = bool
sys.modules["homeassistant.helpers.config_validation"].ensure_list = list
sys.modules["homeassistant.helpers.event"].async_track_time_interval = MagicMock(return_value=MagicMock())

class HonAPI:
    @staticmethod
    async def load_statistics(*args, **kwargs):
        return {}
sys.modules["pyhon.connection.api"].HonAPI = HonAPI

class AddEntitiesCallback:
    pass
sys.modules["homeassistant.helpers.entity_platform"].AddEntitiesCallback = AddEntitiesCallback

# Config entries
class ConfigEntry:
    def __init__(self, entry_id="test_entry", data=None):
        self.entry_id = entry_id
        self.unique_id = entry_id
        self.data = data or {}
sys.modules["homeassistant.config_entries"].ConfigEntry = ConfigEntry

# Helpers Entity
ha_entity = sys.modules["homeassistant.helpers.entity"]
class EntityCategory:
    CONFIG = "config"
    DIAGNOSTIC = "diagnostic"
ha_entity.EntityCategory = EntityCategory

class DeviceInfo(dict):
    pass
ha_entity.DeviceInfo = DeviceInfo

class Entity:
    def __init__(self, *args, **kwargs):
        self.hass = None
        self._attr_native_value = None
        self._attr_options = []
        self._attr_available = True
    def schedule_update_ha_state(self):
        pass
    def async_write_ha_state(self):
        pass
ha_entity.Entity = Entity

# Base description dataclass
@dataclass(frozen=True, kw_only=True)
class _BaseEntityDescription:
    key: str = ""
    device_class: str | None = None
    state_class: str | None = None
    native_unit_of_measurement: str | None = None
    unit_of_measurement: str | None = None
    name: str | None = None
    icon: str | None = None
    translation_key: str | None = None
    entity_category: str | None = None
    options: list | None = None
    entity_registry_enabled_default: bool = True

# Components
ha_sensor = sys.modules["homeassistant.components.sensor"]
class SensorEntity(Entity):
    @property
    def native_value(self):
        return getattr(self, "_attr_native_value", None)

    @property
    def native_unit_of_measurement(self):
        if hasattr(self, "_attr_native_unit_of_measurement"):
            return self._attr_native_unit_of_measurement
        if hasattr(self, "entity_description") and self.entity_description:
            return getattr(self.entity_description, "native_unit_of_measurement", None)
        return None
class SensorDeviceClass:
    TEMPERATURE = "temperature"
    POWER = "power"
    ENERGY = "energy"
    WATER = "water"
    ENUM = "enum"
    VOLUME = "volume"
    DURATION = "duration"
    FREQUENCY = "frequency"
    HUMIDITY = "humidity"
    CO = "carbon_monoxide"
    PM10 = "pm10"
    PM25 = "pm25"
    VOLATILE_ORGANIC_COMPOUNDS = "volatile_organic_compounds"
class SensorStateClass:
    MEASUREMENT = "measurement"
    TOTAL_INCREASING = "total_increasing"
@dataclass(frozen=True, kw_only=True)
class SensorEntityDescription(_BaseEntityDescription):
    pass
ha_sensor.SensorEntity = SensorEntity
ha_sensor.SensorDeviceClass = SensorDeviceClass
ha_sensor.SensorStateClass = SensorStateClass
ha_sensor.SensorEntityDescription = SensorEntityDescription

ha_bs = sys.modules["homeassistant.components.binary_sensor"]
class BinarySensorEntity(Entity):
    pass
class BinarySensorDeviceClass:
    CONNECTIVITY = "connectivity"
    DOOR = "door"
    LOCK = "lock"
    RUNNING = "running"
    HEAT = "heat"
    PROBLEM = "problem"
@dataclass(frozen=True, kw_only=True)
class BinarySensorEntityDescription(_BaseEntityDescription):
    pass
ha_bs.BinarySensorEntity = BinarySensorEntity
ha_bs.BinarySensorDeviceClass = BinarySensorDeviceClass
ha_bs.BinarySensorEntityDescription = BinarySensorEntityDescription

ha_sel = sys.modules["homeassistant.components.select"]
class SelectEntity(Entity):
    pass
@dataclass(frozen=True, kw_only=True)
class SelectEntityDescription(_BaseEntityDescription):
    pass
ha_sel.SelectEntity = SelectEntity
ha_sel.SelectEntityDescription = SelectEntityDescription

ha_num = sys.modules["homeassistant.components.number"]
class NumberEntity(Entity):
    pass
@dataclass(frozen=True, kw_only=True)
class NumberEntityDescription(_BaseEntityDescription):
    pass
ha_num.NumberEntity = NumberEntity
ha_num.NumberEntityDescription = NumberEntityDescription

ha_sw = sys.modules["homeassistant.components.switch"]
class SwitchEntity(Entity):
    pass
@dataclass(frozen=True, kw_only=True)
class SwitchEntityDescription(_BaseEntityDescription):
    pass
ha_sw.SwitchEntity = SwitchEntity
ha_sw.SwitchEntityDescription = SwitchEntityDescription

ha_btn = sys.modules["homeassistant.components.button"]
class ButtonEntity(Entity):
    pass
@dataclass(frozen=True, kw_only=True)
class ButtonEntityDescription(_BaseEntityDescription):
    pass
ha_btn.ButtonEntity = ButtonEntity
ha_btn.ButtonEntityDescription = ButtonEntityDescription

ha_lock = sys.modules["homeassistant.components.lock"]
class LockEntity(Entity):
    pass
@dataclass(frozen=True, kw_only=True)
class LockEntityDescription(_BaseEntityDescription):
    pass
ha_lock.LockEntity = LockEntity
ha_lock.LockEntityDescription = LockEntityDescription

ha_light = sys.modules["homeassistant.components.light"]
class LightEntity(Entity):
    pass
@dataclass(frozen=True, kw_only=True)
class LightEntityDescription(_BaseEntityDescription):
    pass
ha_light.LightEntity = LightEntity
ha_light.LightEntityDescription = LightEntityDescription

ha_fan = sys.modules["homeassistant.components.fan"]
class FanEntity(Entity):
    pass
@dataclass(frozen=True, kw_only=True)
class FanEntityDescription(_BaseEntityDescription):
    pass
ha_fan.FanEntity = FanEntity
ha_fan.FanEntityDescription = FanEntityDescription

ha_climate = sys.modules["homeassistant.components.climate"]
class ClimateEntity(Entity):
    pass
@dataclass(frozen=True, kw_only=True)
class ClimateEntityDescription(_BaseEntityDescription):
    pass
ha_climate.ClimateEntity = ClimateEntity
ha_climate.ClimateEntityDescription = ClimateEntityDescription

ha_const = sys.modules["homeassistant.const"]
class UnitOfTemperature:
    CELSIUS = "°C"
class UnitOfPower:
    WATT = "W"
    KILO_WATT = "kW"
class UnitOfEnergy:
    KILO_WATT_HOUR = "kWh"
class UnitOfTime:
    MINUTES = "min"
    HOURS = "h"
    SECONDS = "s"
class UnitOfVolume:
    LITERS = "L"
class UnitOfMass:
    GRAMS = "g"
    KILOGRAMS = "kg"
class UnitOfDensity:
    MICROGRAMS_PER_CUBIC_METER = "µg/m³"
class UnitOfRatio:
    PARTS_PER_MILLION = "ppm"

ha_const.UnitOfTemperature = UnitOfTemperature
ha_const.UnitOfPower = UnitOfPower
ha_const.UnitOfEnergy = UnitOfEnergy
ha_const.UnitOfTime = UnitOfTime
ha_const.UnitOfVolume = UnitOfVolume
ha_const.UnitOfMass = UnitOfMass
ha_const.UnitOfDensity = UnitOfDensity
ha_const.UnitOfRatio = UnitOfRatio
ha_const.PERCENTAGE = "%"
ha_const.REVOLUTIONS_PER_MINUTE = "rpm"
ha_const.CONF_EMAIL = "email"
ha_const.CONF_PASSWORD = "password"

class HVACMode:
    AUTO = "auto"
    COOL = "cool"
    DRY = "dry"
    HEAT = "heat"
    FAN_ONLY = "fan_only"
ha_climate.HVACMode = HVACMode
ha_climate.FAN_LOW = "low"
ha_climate.FAN_MEDIUM = "medium"
ha_climate.FAN_HIGH = "high"
ha_climate.FAN_AUTO = "auto"

ha_core = sys.modules["homeassistant.core"]
def callback(func):
    return func
ha_core.callback = callback
class HomeAssistant:
    def __init__(self):
        self.data = {}
ha_core.HomeAssistant = HomeAssistant

ha_coord = sys.modules["homeassistant.helpers.update_coordinator"]
class DataUpdateCoordinator:
    def __class_getitem__(cls, item):
        return cls
    def __init__(self, *args, **kwargs):
        pass
    def async_set_updated_data(self, data):
        pass
ha_coord.DataUpdateCoordinator = DataUpdateCoordinator
class CoordinatorEntity(Entity):
    def __class_getitem__(cls, item):
        return cls
    def __init__(self, coordinator, *args, **kwargs):
        super().__init__()
        self.coordinator = coordinator
ha_coord.CoordinatorEntity = CoordinatorEntity

# pyhon parameters
class HonParameter:
    def __init__(self, value=None):
        self.value = value
class HonParameterRange(HonParameter):
    def __init__(self, value=None, min_val=0, max_val=100, step=1):
        super().__init__(value)
        self.min = min_val
        self.max = max_val
        self.step = step
        self.values = []

sys.modules["pyhon.parameter.base"].HonParameter = HonParameter
sys.modules["pyhon.parameter.range"].HonParameterRange = HonParameterRange

class Hon:
    pass
sys.modules["pyhon"].Hon = Hon
class HonAppliance:
    pass
sys.modules["pyhon.appliance"].HonAppliance = HonAppliance
