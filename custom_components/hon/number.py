from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.number import (
    NumberEntity,
    NumberEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTime, UnitOfTemperature
from homeassistant.core import callback
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.core import HomeAssistant
from pyhon.appliance import HonAppliance
from pyhon.parameter.range import HonParameterRange

from .const import DOMAIN
from .entity import HonEntity
from .util import unique_entities


@dataclass(frozen=True)
class HonConfigNumberEntityDescription(NumberEntityDescription):
    entity_category: EntityCategory = EntityCategory.CONFIG


@dataclass(frozen=True)
class HonNumberEntityDescription(NumberEntityDescription):
    pass


NUMBERS: dict[str, tuple[NumberEntityDescription, ...]] = {
    "WM": (
        HonConfigNumberEntityDescription(
            key="startProgram.delayTime",
            name="Delay Time",
            icon="mdi:timer-plus",
            native_unit_of_measurement=UnitOfTime.MINUTES,
            translation_key="delay_time",
        ),
        HonConfigNumberEntityDescription(
            key="startProgram.rinseIterations",
            name="Rinse Iterations",
            icon="mdi:rotate-right",
            translation_key="rinse_iterations",
        ),
        HonConfigNumberEntityDescription(
            key="startProgram.mainWashTime",
            name="Main Wash Time",
            icon="mdi:clock-start",
            native_unit_of_measurement=UnitOfTime.MINUTES,
            translation_key="wash_time",
        ),
        HonConfigNumberEntityDescription(
            key="startProgram.waterHard",
            name="Water hard",
            icon="mdi:water",
            translation_key="water_hard",
        ),
        HonNumberEntityDescription(
            key="settings.waterHard",
            name="Water hard",
            icon="mdi:water",
            translation_key="water_hard",
        ),
        HonConfigNumberEntityDescription(
            key="startProgram.lang",
            name="lang",
        ),
    ),
    "TD": (
        HonConfigNumberEntityDescription(
            key="startProgram.delayTime",
            name="Delay time",
            icon="mdi:timer-plus",
            native_unit_of_measurement=UnitOfTime.MINUTES,
            translation_key="delay_time",
        ),
        HonConfigNumberEntityDescription(
            key="startProgram.tempLevel",
            name="Temperature level",
            icon="mdi:thermometer",
            translation_key="tumbledryertemplevel",
        ),
        HonConfigNumberEntityDescription(
            key="startProgram.dryTime",
            name="Dry Time",
            translation_key="dry_time",
        ),
    ),
    "OV": (
        HonConfigNumberEntityDescription(
            key="startProgram.delayTime",
            name="Delay time",
            icon="mdi:timer-plus",
            native_unit_of_measurement=UnitOfTime.MINUTES,
            translation_key="delay_time",
        ),
        HonConfigNumberEntityDescription(
            key="startProgram.tempSel",
            name="Target Temperature",
            icon="mdi:thermometer",
            native_unit_of_measurement=UnitOfTemperature.CELSIUS,
            translation_key="target_temperature",
        ),
        HonConfigNumberEntityDescription(
            key="startProgram.prTime",
            name="Program Duration",
            icon="mdi:timelapse",
            native_unit_of_measurement=UnitOfTime.MINUTES,
            translation_key="program_duration",
        ),
    ),
    "IH": (
        HonConfigNumberEntityDescription(
            key="startProgram.temp",
            name="Temperature",
            icon="mdi:thermometer",
            translation_key="temperature",
        ),
        HonConfigNumberEntityDescription(
            key="startProgram.powerManagement",
            name="Power Management",
            icon="mdi:timelapse",
            translation_key="power_management",
        ),
    ),
    "DW": (
        HonConfigNumberEntityDescription(
            key="startProgram.delayTime",
            name="Delay time",
            icon="mdi:timer-plus",
            native_unit_of_measurement=UnitOfTime.MINUTES,
            translation_key="delay_time",
        ),
        HonConfigNumberEntityDescription(
            key="startProgram.waterHard",
            name="Water hard",
            icon="mdi:water",
            translation_key="water_hard",
        ),
        HonNumberEntityDescription(
            key="settings.waterHard",
            name="Water hard",
            icon="mdi:water",
            translation_key="water_hard",
        ),
    ),
    "AC": (
        HonNumberEntityDescription(
            key="settings.tempSel",
            name="Target Temperature",
            icon="mdi:thermometer",
            native_unit_of_measurement=UnitOfTemperature.CELSIUS,
            translation_key="target_temperature",
        ),
    ),
    "REF": (
        HonNumberEntityDescription(
            key="settings.tempSelZ1",
            name="Fridge Temperature",
            icon="mdi:thermometer",
            native_unit_of_measurement=UnitOfTemperature.CELSIUS,
            translation_key="fridge_temp_sel",
        ),
        HonNumberEntityDescription(
            key="settings.tempSelZ2",
            name="Freezer Temperature",
            icon="mdi:thermometer",
            native_unit_of_measurement=UnitOfTemperature.CELSIUS,
            translation_key="freezer_temp_sel",
        ),
        HonNumberEntityDescription(
            key="settings.tempSelZ3",
            name="MyZone Temperature",
            icon="mdi:thermometer",
            native_unit_of_measurement=UnitOfTemperature.CELSIUS,
            translation_key="my_zone_temp_sel",
        ),
    ),
    "AP": (
        HonNumberEntityDescription(
            key="settings.aromaTimeOn",
            name="Aroma Time On",
            icon="mdi:scent",
            native_unit_of_measurement=UnitOfTime.SECONDS,
            translation_key="aroma_time_on",
        ),
        HonNumberEntityDescription(
            key="settings.aromaTimeOff",
            name="Aroma Time Off",
            icon="mdi:scent-off",
            native_unit_of_measurement=UnitOfTime.SECONDS,
            translation_key="aroma_time_off",
        ),
        HonNumberEntityDescription(
            key="settings.pollenLevel",
            name="Pollen Level",
            icon="mdi:flower-pollen",
            translation_key="pollen_level",
        ),
    ),
    "AW": (
        HonNumberEntityDescription(
            key="settings.tempSelDhw",
            name="Target Temperature DHW",
            icon="mdi:water-boiler",
            native_unit_of_measurement=UnitOfTemperature.CELSIUS,
            translation_key="target_temp_dhw",
        ),
        HonNumberEntityDescription(
            key="settings.tempSelZ1",
            name="Target Temperature Zone 1",
            icon="mdi:thermometer",
            native_unit_of_measurement=UnitOfTemperature.CELSIUS,
            translation_key="target_temp_z1",
        ),
        HonNumberEntityDescription(
            key="settings.tempSelZ2",
            name="Target Temperature Zone 2",
            icon="mdi:thermometer",
            native_unit_of_measurement=UnitOfTemperature.CELSIUS,
            translation_key="target_temp_z2",
        ),
        HonNumberEntityDescription(
            key="settings.tempSelHolidayModeZ1",
            name="Holiday Target Temperature Zone 1",
            icon="mdi:island",
            native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        ),
        HonNumberEntityDescription(
            key="settings.tempSelHolidayModeZ2",
            name="Holiday Target Temperature Zone 2",
            icon="mdi:island",
            native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        ),
        HonNumberEntityDescription(
            key="settings.tempSelEcoMode",
            name="Eco Mode Target Temperature",
            icon="mdi:leaf",
            native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        ),
        HonNumberEntityDescription(
            key="settings.tempSelPool",
            name="Pool Target Temperature",
            icon="mdi:pool",
            native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        ),
        HonNumberEntityDescription(
            key="settings.tempSelSterilizationMode",
            name="Sterilization Target Temperature",
            icon="mdi:shield-check",
            native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        ),
        HonConfigNumberEntityDescription(
            key="settings.tempDeltaDhw",
            name="DHW Delta Temperature",
            icon="mdi:thermometer-minus",
            native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        ),
        HonConfigNumberEntityDescription(
            key="settings.turboModeTime",
            name="Turbo Mode Duration",
            icon="mdi:timer",
            native_unit_of_measurement=UnitOfTime.MINUTES,
        ),
        *[HonConfigNumberEntityDescription(
            key=f"settings.highOutdoorTempCurve{i}",
            name=f"High Outdoor Temp Curve {i}",
            icon="mdi:chart-bell-curve-cumulative",
            native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        ) for i in range(1, 5)],
        *[HonConfigNumberEntityDescription(
            key=f"settings.lowOutdoorTempCurve{i}",
            name=f"Low Outdoor Temp Curve {i}",
            icon="mdi:chart-bell-curve-cumulative",
            native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        ) for i in range(1, 5)],
        *[HonConfigNumberEntityDescription(
            key=f"settings.highWaterTempCurve{i}",
            name=f"High Water Temp Curve {i}",
            icon="mdi:chart-bell-curve-cumulative",
            native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        ) for i in range(1, 5)],
        *[HonConfigNumberEntityDescription(
            key=f"settings.lowWaterTempCurve{i}",
            name=f"Low Water Temp Curve {i}",
            icon="mdi:chart-bell-curve-cumulative",
            native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        ) for i in range(1, 5)],
    ),
}

NUMBERS["WD"] = unique_entities(NUMBERS["WM"], NUMBERS["TD"])


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    entities = []
    entity: HonNumberEntity | HonConfigNumberEntity
    for device in hass.data[DOMAIN][entry.unique_id]["hon"].appliances:
        for description in NUMBERS.get(device.appliance_type, []):
            if description.key not in device.available_settings:
                continue
            if isinstance(description, HonNumberEntityDescription):
                entity = HonNumberEntity(hass, entry, device, description)
            elif isinstance(description, HonConfigNumberEntityDescription):
                entity = HonConfigNumberEntity(hass, entry, device, description)
            else:
                continue
            entities.append(entity)
    async_add_entities(entities)


class HonNumberEntity(HonEntity, NumberEntity):
    entity_description: HonNumberEntityDescription

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        device: HonAppliance,
        description: HonNumberEntityDescription,
    ) -> None:
        super().__init__(hass, entry, device, description)

        self._data = device.settings[description.key]
        if isinstance(self._data, HonParameterRange):
            self._attr_native_max_value = self._data.max
            self._attr_native_min_value = self._data.min
            self._attr_native_step = self._data.step

    @property
    def native_value(self) -> float | None:
        if value := self._device.get(self.entity_description.key.split(".")[-1]):
            return float(value)
        return None

    async def async_set_native_value(self, value: float) -> None:
        setting = self._device.settings[self.entity_description.key]
        if isinstance(setting, HonParameterRange):
            # Formatiere den Wert korrekt als Integer oder Float um API-Abstürze zu verhindern
            step = float(setting.step)
            setting.value = int(value) if step % 1 == 0 else float(value)
            
        command = self.entity_description.key.split(".")[0]
        await self._device.commands[command].send()
        if command != "settings":
            self._device.sync_command(command, "settings")
        self.coordinator.async_set_updated_data({})

    @callback
    def _handle_coordinator_update(self, update: bool = True) -> None:
        setting = self._device.settings[self.entity_description.key]
        if isinstance(setting, HonParameterRange):
            self._attr_native_max_value = setting.max
            self._attr_native_min_value = setting.min
            self._attr_native_step = setting.step
        self._attr_native_value = self.native_value
        if update:
            self.schedule_update_ha_state()

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return (
            super().available
            and int(self._device.get("remoteCtrValid", 1)) == 1
            and self._device.connection
        )


class HonConfigNumberEntity(HonEntity, NumberEntity):
    entity_description: HonConfigNumberEntityDescription

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        device: HonAppliance,
        description: HonConfigNumberEntityDescription,
    ) -> None:
        super().__init__(hass, entry, device, description)

        self._data = device.settings[description.key]
        if isinstance(self._data, HonParameterRange):
            self._attr_native_max_value = self._data.max
            self._attr_native_min_value = self._data.min
            self._attr_native_step = self._data.step

    @property
    def native_value(self) -> float | None:
        if (value := self._device.settings[self.entity_description.key].value) != "":
            return float(value)
        return None

    async def async_set_native_value(self, value: float) -> None:
        setting = self._device.settings[self.entity_description.key]
        if isinstance(setting, HonParameterRange):
            # Formatiere den Wert korrekt als Integer oder Float
            step = float(setting.step)
            setting.value = int(value) if step % 1 == 0 else float(value)
        self.coordinator.async_set_updated_data({})

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return super(NumberEntity, self).available

    @callback
    def _handle_coordinator_update(self, update: bool = True) -> None:
        setting = self._device.settings[self.entity_description.key]
        if isinstance(setting, HonParameterRange):
            self._attr_native_max_value = setting.max
            self._attr_native_min_value = setting.min
            self._attr_native_step = setting.step
        self._attr_native_value = self.native_value
        if update:
            self.schedule_update_ha_state()