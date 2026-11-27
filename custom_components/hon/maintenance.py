"""Washer maintenance counters and bounded statistics refresh."""

import asyncio
import logging
import math
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from functools import partial
from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from pyhon.appliance import HonAppliance

from .const import DOMAIN
from .entity import HonEntity

_LOGGER = logging.getLogger(__name__)

MAINTENANCE_SENSORS = tuple(
    SensorEntityDescription(
        key=f"statistics.{block}.remaining",
        translation_key=translation,
        native_unit_of_measurement="cycles",
        icon="mdi:counter",
    )
    for block, translation in (
        ("drawerCleaning", "drawer_cleaning_remaining"),
        ("drumCleaning", "drum_cleaning_remaining"),
        ("filterCleaning", "filter_cleaning_remaining"),
    )
)


@dataclass
class _RefreshState:
    snapshot: Any
    healthy: bool = True
    stopped: bool = False
    task: asyncio.Task[None] | None = None
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


def _number(value: Any, *, integer: bool = False) -> int | float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if not math.isfinite(number) or (integer and not number.is_integer()):
        return None
    return int(number) if integer else number


def _nested(data: Any, *keys: str) -> Any:
    for key in keys:
        if not isinstance(data, dict):
            return None
        data = data.get(key)
    return data


class HonMaintenanceSensorEntity(HonEntity, SensorEntity):
    entity_description: SensorEntityDescription

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        device: HonAppliance,
        description: SensorEntityDescription,
        state: _RefreshState,
    ) -> None:
        self._statistics_state = state
        super().__init__(hass, entry, device, description)

    @property
    def available(self) -> bool:
        return (
            super().available
            and self._statistics_state.healthy
            and self._attr_native_value is not None
        )

    @callback
    def _handle_coordinator_update(self, update: bool = True) -> None:
        block = _nested(
            self._statistics_state.snapshot, self.entity_description.key.split(".")[1]
        )
        self._attr_native_value = _number(_nested(block, "remaining"), integer=True)
        self._attr_extra_state_attributes = {
            key: number
            for key in ("count", "total", "percentage")
            if (
                number := _number(
                    _nested(block, "tot" if key == "total" else key),
                    integer=key != "percentage",
                )
            )
            is not None
        }
        if update:
            self.schedule_update_ha_state()


async def _refresh_statistics(
    device: HonAppliance,
    state: _RefreshState,
    coordinator: DataUpdateCoordinator[dict[str, Any]],
    _now: datetime | None = None,
) -> None:
    if state.stopped or state.lock.locked():
        return
    async with state.lock:
        state.task = asyncio.current_task()
        try:
            async with asyncio.timeout(30):
                await device.load_statistics()
            # Unload can run while the provider request is pending.
            if getattr(state, "stopped"):
                return
            state.snapshot = deepcopy(device.get("statistics"))
            state.healthy = True
        except Exception:  # pylint: disable=broad-exception-caught  # noqa: BLE001
            state.healthy = False
            _LOGGER.warning("Unable to refresh appliance statistics")
        finally:
            state.task = None
        if not state.stopped:
            coordinator.async_update_listeners()


def _setup_statistics_refresh(
    hass: HomeAssistant, entry: ConfigEntry, device: HonAppliance, initial: Any
) -> _RefreshState:
    data = hass.data[DOMAIN][entry.unique_id]
    registrations: dict[str, _RefreshState] = data.setdefault("maintenance_refresh", {})
    existing = registrations.get(device.unique_id)
    if existing is not None:
        return existing
    state = _RefreshState(snapshot=deepcopy(initial))
    registrations[device.unique_id] = state

    refresh = partial(_refresh_statistics, device, state, data["coordinator"])

    cancel_timer = async_track_time_interval(hass, refresh, timedelta(hours=1))

    @callback
    def unload() -> None:
        state.stopped = True
        cancel_timer()
        if state.task is not None:
            state.task.cancel()
        registrations.pop(device.unique_id, None)

    entry.async_on_unload(unload)
    return state


async def async_setup_maintenance(
    hass: HomeAssistant, entry: ConfigEntry, device: HonAppliance
) -> list[HonMaintenanceSensorEntity]:
    """Register one refresh per washer and create supported counters."""
    initial = device.get("statistics")
    if not isinstance(initial, dict) or not initial:
        try:
            async with asyncio.timeout(30):
                await device.load_statistics()
        except Exception:  # pylint: disable=broad-exception-caught  # noqa: BLE001
            _LOGGER.warning("Unable to discover appliance maintenance statistics")
            return []
        initial = device.get("statistics")
    descriptions = [
        description
        for description in MAINTENANCE_SENSORS
        if _number(
            _nested(initial, description.key.split(".")[1], "remaining"),
            integer=True,
        )
        is not None
    ]
    if not descriptions:
        return []
    state = _setup_statistics_refresh(hass, entry, device, initial)
    return [
        HonMaintenanceSensorEntity(hass, entry, device, description, state)
        for description in descriptions
    ]
