"""Washer cycle counts by temperature range."""

import math
from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from pyhon.appliance import HonAppliance

from .entity import HonEntity

TEMPERATURE_USAGE_SENSORS = tuple(
    SensorEntityDescription(
        key=key,
        translation_key=translation,
        native_unit_of_measurement="cycles",
        icon="mdi:thermometer",
    )
    for key, translation in (
        ("temp0to30", "temperature_usage_0_30"),
        ("temp40", "temperature_usage_40"),
        ("temp60to90", "temperature_usage_60_90"),
    )
)


def _count(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return (
        int(number)
        if math.isfinite(number) and number >= 0 and number.is_integer()
        else None
    )


class HonTemperatureUsageSensorEntity(HonEntity, SensorEntity):
    entity_description: SensorEntityDescription

    @property
    def available(self) -> bool:
        return super().available and self._attr_native_value is not None

    @callback
    def _handle_coordinator_update(self, update: bool = True) -> None:
        counts = {
            description.key: _count(self._device.get(description.key))
            for description in TEMPERATURE_USAGE_SENSORS
        }
        value = counts[self.entity_description.key]
        self._attr_native_value = value
        self._attr_extra_state_attributes = {}
        valid_counts = [count for count in counts.values() if count is not None]
        if len(valid_counts) == len(TEMPERATURE_USAGE_SENSORS) and value is not None:
            total = sum(valid_counts)
            if total > 0:
                self._attr_extra_state_attributes["percentage"] = round(
                    value / total * 100, 1
                )
        if update:
            self.schedule_update_ha_state()


def temperature_usage_entities(
    hass: HomeAssistant, entry: ConfigEntry, device: HonAppliance
) -> list[HonTemperatureUsageSensorEntity]:
    """Create only counters with a valid value at setup."""
    return [
        HonTemperatureUsageSensorEntity(hass, entry, device, description)
        for description in TEMPERATURE_USAGE_SENSORS
        if _count(device.get(description.key)) is not None
    ]
