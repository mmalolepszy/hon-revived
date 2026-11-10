import logging
from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorEntityDescription,
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import callback
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .entity import HonEntity
from .util import unique_entities

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class HonBinarySensorEntityDescription(BinarySensorEntityDescription):
    """Description for hOn binary sensors."""
    on_value: str | float = ""
    # Support multiple 'ON' values for specific mode sensors
    on_values: tuple[str, ...] = ()


BINARY_SENSORS: dict[str, tuple[HonBinarySensorEntityDescription, ...]] = {
    "WM": (
        HonBinarySensorEntityDescription(
            key="attributes.lastConnEvent.category",
            name="Remote Control",
            device_class=BinarySensorDeviceClass.CONNECTIVITY,
            on_value="CONNECTED",
            icon="mdi:remote",
            translation_key="remote_control",
        ),
        HonBinarySensorEntityDescription(
            key="doorLockStatus",
            name="Door Lock",
            device_class=BinarySensorDeviceClass.LOCK,
            on_value=0,
            translation_key="door_lock",
        ),
        HonBinarySensorEntityDescription(
            key="doorStatus",
            name="Door",
            device_class=BinarySensorDeviceClass.DOOR,
            on_value=1,
            translation_key="door_open",
        ),
        HonBinarySensorEntityDescription(
            key="prewash",
            icon="mdi:tshirt-crew",
            name="Pre Wash",
            translation_key="prewash",
        ),
        HonBinarySensorEntityDescription(
            key="extraRinse1",
            icon="mdi:numeric-1-box-multiple-outline",
            name="Extra Rinse 1",
            translation_key="extra_rinse_1",
        ),
        HonBinarySensorEntityDescription(
            key="extraRinse2",
            icon="mdi:numeric-2-box-multiple-outline",
            name="Extra Rinse 2",
            translation_key="extra_rinse_2",
        ),
        HonBinarySensorEntityDescription(
            key="extraRinse3",
            icon="mdi:numeric-3-box-multiple-outline",
            name="Extra Rinse 3",
            translation_key="extra_rinse_3",
        ),
        HonBinarySensorEntityDescription(
            key="goodNight",
            icon="mdi:weather-night",
            name="Good Night Mode",
            translation_key="good_night",
        ),
        HonBinarySensorEntityDescription(
            key="acquaplus",
            icon="mdi:water-plus",
            name="Acqua Plus",
            translation_key="acqua_plus",
        ),
        HonBinarySensorEntityDescription(
            key="energySavingStatus",
            name="Energy Saving Mode",
            on_value=1,
            icon="mdi:leaf",
            translation_key="energy_saving",
        ),
        HonBinarySensorEntityDescription(
            key="buzzerDisabled",
            name="Buzzer Disabled",
            on_value=1,
            icon="mdi:volume-off",
            translation_key="buzzer_disabled",
        ),
        HonBinarySensorEntityDescription(
            key="lockStatus",
            name="Child Lock",
            device_class=BinarySensorDeviceClass.LOCK,
            on_value=0,
            icon="mdi:lock",
            translation_key="child_lock",
        ),
    ),
    "TD": (
        HonBinarySensorEntityDescription(
            key="attributes.lastConnEvent.category",
            name="Connection",
            device_class=BinarySensorDeviceClass.CONNECTIVITY,
            on_value="CONNECTED",
            translation_key="connection",
        ),
        HonBinarySensorEntityDescription(
            key="doorStatus",
            name="Door",
            device_class=BinarySensorDeviceClass.DOOR,
            on_value=1,
            translation_key="door_open",
        ),
        HonBinarySensorEntityDescription(
            key="anticrease",
            name="Anti-Crease",
            icon="mdi:iron",
            translation_key="anti_crease",
        ),
    ),
    "OV": (
        HonBinarySensorEntityDescription(
            key="attributes.lastConnEvent.category",
            name="Connection",
            device_class=BinarySensorDeviceClass.CONNECTIVITY,
            on_value="CONNECTED",
            icon="mdi:wifi",
            translation_key="connection",
        ),
        HonBinarySensorEntityDescription(
            key="attributes.parameters.onOffStatus",
            name="On",
            device_class=BinarySensorDeviceClass.RUNNING,
            on_value=1,
            icon="mdi:power-cycle",
            translation_key="on",
        ),
        HonBinarySensorEntityDescription(
            key="attributes.parameters.preheatStatus",
            name="Pre-Heat",
            device_class=BinarySensorDeviceClass.RUNNING,
            on_value=1,
            icon="mdi:thermometer-chevron-up",
            translation_key="pre_heat",
        ),
        HonBinarySensorEntityDescription(
            key="tempStatus",
            name="Temperature Reached",
            device_class=BinarySensorDeviceClass.HEAT,
            on_value=1,
            icon="mdi:thermometer-check",
            translation_key="temp_reached",
        ),
        HonBinarySensorEntityDescription(
            key="lockStatus",
            name="Child Lock",
            device_class=BinarySensorDeviceClass.LOCK,
            on_value=0,
            icon="mdi:lock",
            translation_key="child_lock",
        ),
        HonBinarySensorEntityDescription(
            key="turnspitStatus",
            name="Turnspit",
            on_value=1,
            icon="mdi:rotate-3d-variant",
            translation_key="turnspit",
        ),
        HonBinarySensorEntityDescription(
            key="steamStatus",
            name="Steam Active",
            on_value=1,
            icon="mdi:weather-fog",
            translation_key="steam_active",
        ),
        HonBinarySensorEntityDescription(
            key="descalingRequiredStatus",
            name="Descaling Required",
            device_class=BinarySensorDeviceClass.PROBLEM,
            on_value=1,
            icon="mdi:alert-circle",
            translation_key="descaling_required",
        ),
    ),
    "IH": (
        HonBinarySensorEntityDescription(
            key="attributes.lastConnEvent.category",
            name="Connection",
            device_class=BinarySensorDeviceClass.CONNECTIVITY,
            on_value="CONNECTED",
            icon="mdi:wifi",
            translation_key="connection",
        ),
        HonBinarySensorEntityDescription(
            key="attributes.parameters.onOffStatus",
            name="On",
            device_class=BinarySensorDeviceClass.RUNNING,
            on_value=1,
            icon="mdi:power-cycle",
            translation_key="on",
        ),
        HonBinarySensorEntityDescription(
            key="hotStatus",
            name="Hot Status",
            device_class=BinarySensorDeviceClass.HEAT,
            on_value=1,
            translation_key="still_hot",
        ),
        HonBinarySensorEntityDescription(
            key="panStatus",
            name="Pan Status",
            on_value=1,
            icon="mdi:pot-mix",
            translation_key="pan_status",
        ),
        HonBinarySensorEntityDescription(
            key="hobLockStatus",
            name="Hob Lock",
            device_class=BinarySensorDeviceClass.LOCK,
            on_value=0,
            translation_key="child_lock",
        ),
    ),
    "DW": (
        HonBinarySensorEntityDescription(
            key="saltStatus",
            name="Salt",
            device_class=BinarySensorDeviceClass.PROBLEM,
            on_value=1,
            icon="mdi:shaker-outline",
            translation_key="salt_level",
        ),
        HonBinarySensorEntityDescription(
            key="rinseAidStatus",
            name="Rinse Aid",
            device_class=BinarySensorDeviceClass.PROBLEM,
            on_value=1,
            icon="mdi:spray-bottle",
            translation_key="rinse_aid",
        ),
        HonBinarySensorEntityDescription(
            key="attributes.lastConnEvent.category",
            name="Connection",
            device_class=BinarySensorDeviceClass.CONNECTIVITY,
            on_value="CONNECTED",
            translation_key="connection",
        ),
        HonBinarySensorEntityDescription(
            key="doorStatus",
            name="Door",
            device_class=BinarySensorDeviceClass.DOOR,
            on_value=1,
            translation_key="door_open",
        ),
        HonBinarySensorEntityDescription(
            key="addDishStatus",
            translation_key="add_dish",
            icon="mdi:silverware-fork-knife",
            on_value=1,
        ),
        HonBinarySensorEntityDescription(
            key="lastCycleSavingStatus",
            translation_key="last_cycle_saving",
            icon="mdi:leaf",
            on_value=1,
        ),
        HonBinarySensorEntityDescription(
            key="tabStatus",
            translation_key="detergent_tab",
            icon="mdi:cube",
            on_value=1,
        ),
    ),
    "AC": (
        HonBinarySensorEntityDescription(
            key="filterChangeStatusLocal",
            name="Filter Replacement",
            device_class=BinarySensorDeviceClass.PROBLEM,
            on_value=1,
            translation_key="filter_replacement",
        ),
        HonBinarySensorEntityDescription(
            key="ch2oCleaningStatus",
            name="Ch2O Cleaning",
            on_value=1,
        ),
        HonBinarySensorEntityDescription(
            key="defrostStatus",
            name="Defrost Status",
            icon="mdi:snowflake-melt",
            on_value=1,
        ),
    ),
    "REF": (
        HonBinarySensorEntityDescription(
            key="quickModeZ1",
            name="Super Cool",
            icon="mdi:snowflake",
            device_class=BinarySensorDeviceClass.RUNNING,
            on_value=1,
            translation_key="super_cool",
        ),
        HonBinarySensorEntityDescription(
            key="quickModeZ2",
            name="Super Freeze",
            icon="mdi:snowflake-variant",
            device_class=BinarySensorDeviceClass.RUNNING,
            on_value=1,
            translation_key="super_freeze",
        ),
        HonBinarySensorEntityDescription(
            key="doorStatusZ1",
            name="Door1 Status Fridge",
            device_class=BinarySensorDeviceClass.DOOR,
            icon="mdi:fridge-top",
            on_value=1,
            translation_key="fridge_door",
        ),
        HonBinarySensorEntityDescription(
            key="door2StatusZ1",
            name="Door2 Status Fridge",
            icon="mdi:fridge-top",
            device_class=BinarySensorDeviceClass.DOOR,
            on_value=1,
            translation_key="fridge_door",
        ),
        HonBinarySensorEntityDescription(
            key="doorStatusZ2",
            name="Door1 Status Freezer",
            icon="mdi:fridge-bottom",
            device_class=BinarySensorDeviceClass.DOOR,
            on_value=1,
            translation_key="freezer_door",
        ),
        HonBinarySensorEntityDescription(
            key="door2StatusZ2",
            name="Door2 Status Freezer",
            icon="mdi:fridge-bottom",
            device_class=BinarySensorDeviceClass.DOOR,
            on_value=1,
            translation_key="freezer_door",
        ),
        HonBinarySensorEntityDescription(
            key="intelligenceMode",
            name="Auto-Set Mode",
            icon="mdi:thermometer-auto",
            device_class=BinarySensorDeviceClass.RUNNING,
            on_value=1,
            translation_key="auto_set",
        ),
        HonBinarySensorEntityDescription(
            key="holidayMode",
            name="Holiday Mode",
            icon="mdi:palm-tree",
            device_class=BinarySensorDeviceClass.RUNNING,
            on_value=1,
            translation_key="holiday_mode",
        ),
    ),
    "AP": (
        HonBinarySensorEntityDescription(
            key="attributes.parameters.onOffStatus",
            name="On",
            device_class=BinarySensorDeviceClass.RUNNING,
            on_value="1",
            icon="mdi:power-cycle",
            translation_key="on",
        ),
    ),
    "FRE": (
        HonBinarySensorEntityDescription(
            key="quickModeZ1",
            name="Super Cool",
            icon="mdi:snowflake",
            device_class=BinarySensorDeviceClass.RUNNING,
            on_value=1,
            translation_key="super_cool",
        ),
        HonBinarySensorEntityDescription(
            key="quickModeZ2",
            name="Super Freeze",
            icon="mdi:snowflake-variant",
            device_class=BinarySensorDeviceClass.RUNNING,
            on_value=1,
            translation_key="super_freeze",
        ),
        HonBinarySensorEntityDescription(
            key="doorStatusZ2",
            name="Door Status",
            icon="mdi:fridge",
            device_class=BinarySensorDeviceClass.DOOR,
            on_value=1,
            translation_key="door_open",
        ),
    ),
    # --- HEAT PUMP (AW) SECTION ---
    "AW": (
        HonBinarySensorEntityDescription(
            key="heatingStatus",
            name="Heating Mode",
            icon="mdi:radiator",
            on_values=("2", "8"),  # machMode 2=Heat, 8=Auto (Heat+DHW)
            device_class=BinarySensorDeviceClass.RUNNING,
            translation_key="heating_mode",
        ),
        HonBinarySensorEntityDescription(
            key="dhwStatus",
            name="DHW Mode",
            icon="mdi:water-boiler",
            on_values=("3", "8"),  # machMode 3=DHW, 8=Auto (Heat+DHW)
            device_class=BinarySensorDeviceClass.RUNNING,
            translation_key="dhw_mode",
        ),
        HonBinarySensorEntityDescription(
            key="sgReady",
            name="Smart Grid Ready",
            icon="mdi:solar-power",
            entity_category=EntityCategory.DIAGNOSTIC,
            on_value="1",
            translation_key="sg_ready",
        ),
        HonBinarySensorEntityDescription(
            key="dhwPriorityStatus",
            name="DHW Priority",
            icon="mdi:water-plus",
            entity_category=EntityCategory.DIAGNOSTIC,
            on_value="1",
            translation_key="dhw_priority",
        ),
        HonBinarySensorEntityDescription(
            key="boilerActState",
            name="Boiler Status",
            icon="mdi:heating-coil",
            device_class=BinarySensorDeviceClass.HEAT,
            on_value="1",
            translation_key="boiler_status",
        ),
        HonBinarySensorEntityDescription(
            key="iduElectricHeaterActState1",
            name="Heater 1 Status",
            icon="mdi:heating-coil",
            device_class=BinarySensorDeviceClass.HEAT,
            entity_category=EntityCategory.DIAGNOSTIC,
            on_value="1",
            translation_key="heater1_status",
        ),
        HonBinarySensorEntityDescription(
            key="iduElectricHeaterActState2",
            name="Heater 2 Status",
            icon="mdi:heating-coil",
            device_class=BinarySensorDeviceClass.HEAT,
            entity_category=EntityCategory.DIAGNOSTIC,
            on_value="1",
            translation_key="heater2_status",
        ),
        HonBinarySensorEntityDescription(
            key="holidayActState",
            name="Holiday Mode",
            icon="mdi:island",
            on_value="1",
            translation_key="holiday_mode",
        ),
        HonBinarySensorEntityDescription(
            key="sterilizationModeStatus",
            name="Sterilization",
            icon="mdi:shield-check",
            device_class=BinarySensorDeviceClass.HEAT,
            on_value="1",
            translation_key="sterilization",
        ),
        HonBinarySensorEntityDescription(
            key="attributes.lastConnEvent.category",
            name="Remote Control",
            device_class=BinarySensorDeviceClass.CONNECTIVITY,
            on_value="CONNECTED",
            icon="mdi:remote",
            translation_key="remote_control",
        ),
    ),
    "HW": (
        HonBinarySensorEntityDescription(
            key="onOffStatus",
            name="Power Status",
            device_class=BinarySensorDeviceClass.RUNNING,
            on_value=1,
            icon="mdi:power",
            translation_key="power_status",
        ),
        HonBinarySensorEntityDescription(
            key="compressorHeatingCurrentStatus",
            name="Compressor Heating",
            device_class=BinarySensorDeviceClass.HEAT,
            on_value=1,
            icon="mdi:heat-pump",
            translation_key="compressor_heating",
        ),
        HonBinarySensorEntityDescription(
            key="electricHeatingCurrentStatus",
            name="Electric Heating",
            device_class=BinarySensorDeviceClass.HEAT,
            on_value=1,
            icon="mdi:radiator",
            translation_key="electric_heating",
        ),
        HonBinarySensorEntityDescription(
            key="auxElecHeatingStatus",
            name="Auxiliary Electric Heating",
            device_class=BinarySensorDeviceClass.HEAT,
            on_value=1,
            icon="mdi:heating-coil",
            translation_key="aux_electric_heating",
        ),
        HonBinarySensorEntityDescription(
            key="boilerHeatingCurrentStatus",
            name="Boiler Heating",
            device_class=BinarySensorDeviceClass.HEAT,
            on_value=1,
            icon="mdi:water-boiler",
            translation_key="boiler_heating",
        ),
        HonBinarySensorEntityDescription(
            key="solarHeatingCurrentStatus",
            name="Solar Heating",
            device_class=BinarySensorDeviceClass.HEAT,
            on_value=1,
            icon="mdi:solar-power",
            translation_key="solar_heating",
        ),
        HonBinarySensorEntityDescription(
            key="antifreezingStatus",
            name="Antifreeze Protection",
            device_class=BinarySensorDeviceClass.PROBLEM,
            on_value=1,
            icon="mdi:snowflake-alert",
            translation_key="antifreeze_protection",
        ),
        HonBinarySensorEntityDescription(
            key="autoDefrostStatus",
            name="Defrosting",
            device_class=BinarySensorDeviceClass.HEAT,
            on_value=1,
            icon="mdi:snowflake-melt",
            translation_key="defrosting",
        ),
        HonBinarySensorEntityDescription(
            key="silentCurrentStatus",
            name="Silent Mode Status",
            on_value=1,
            icon="mdi:volume-off",
            translation_key="silent_status",
        ),
        HonBinarySensorEntityDescription(
            key="sterilizationCurrentStatus",
            name="Disinfection Status",
            on_value=1,
            icon="mdi:shield-bug",
            translation_key="disinfection_status",
        ),
    ),
}

BINARY_SENSORS["WD"] = unique_entities(BINARY_SENSORS["WM"], BINARY_SENSORS["TD"])


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the hOn binary sensors."""
    entities = []
    for device in hass.data[DOMAIN][entry.unique_id]["hon"].appliances:
        for description in BINARY_SENSORS.get(device.appliance_type, []):
            # Check if key exists or if it is a special mode sensor relying on machMode
            if (device.get(description.key) is not None) or \
               (description.key in ["heatingStatus", "dhwStatus"] and device.get("machMode") is not None):
                
                if description.key in ["heatingStatus", "dhwStatus"]:
                    entities.append(HonBinaryModeSensorEntity(hass, entry, device, description))
                else:
                    entities.append(HonBinarySensorEntity(hass, entry, device, description))
                    
    async_add_entities(entities)


class HonBinarySensorEntity(HonEntity, BinarySensorEntity):
    """Representation of a standard hOn binary sensor."""
    entity_description: HonBinarySensorEntityDescription

    def __init__(self, hass, entry, device, description) -> None:
        super().__init__(hass, entry, device, description)
        self._attr_unique_id = f"{device.unique_id}_{description.key}"
        self._attr_name = f"{device.nick_name} {description.name}"

    @property
    def is_on(self) -> bool:
        """Return true if the binary sensor is on."""
        attr = self._device.get(self.entity_description.key, None)
        value = attr.value if hasattr(attr, "value") else attr
        
        if value is None:
            return False
            
        str_val = str(value).lower()
        target_val = str(self.entity_description.on_value).lower()
        
        if str_val == target_val:
            return True
            
        if str_val in ["true", "on", "yes", "1"] and target_val in ["1", "true"]:
            return True
            
        return False

    @callback
    def _handle_coordinator_update(self, update: bool = True) -> None:
        """Handle updated data from the coordinator."""
        if update:
            self.schedule_update_ha_state()


class HonBinaryModeSensorEntity(HonBinarySensorEntity):
    """Special binary sensor that reacts to machMode (e.g. for Heating/DHW status)."""
    
    @property
    def is_on(self) -> bool:
        """Determine state based on machMode and onOffStatus."""
        # Ensure modes report False if the entire machine is powered off
        if str(self._device.get("onOffStatus", "1")) == "0":
            return False
            
        mode = self._device.get("machMode")
        if mode is None:
            return False
            
        str_mode = str(mode)
        # Check against list of valid 'ON' values (e.g. "2" and "8" for heating)
        return any(str_mode == str(val) for val in self.entity_description.on_values)

