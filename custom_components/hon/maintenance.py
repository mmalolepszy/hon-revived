"""Maintenance data (carbon filter, Smart Check Up) from the hOn cloud.

pyhon merges the ``commands/v1/maintenance-cycle`` payload into
``appliance.statistics``. A two-zone Haier wine cellar (HWS77GDAU1, WC128)
reports there::

    "carbonFilter": {
        "lastReplacement": "2024-01-05T10:00:00.000Z",
        "percentage": 282,                      # of the 12-month filter life
        "remainingTime": "-PT15981H20M32.23S",  # ISO 8601, negative = overdue
    }

and the date of the last Smart Check Up as ``lastCheckUp`` in the appliance
list entry (``appliance.info``). Washing machines, dryers and dishwashers use a
different shape (``filterCleaning: {tot, count, remaining, percentage}``, see
the hon-test-data dumps), which this module ignores.

Every value is optional: an entity is only created when its source key exists.
The data is read when the integration loads. Nothing polls it periodically:
polling the hOn cloud is what led to Haier's takedown request in 2024.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any

from pyhon.appliance import HonAppliance

_LOGGER = logging.getLogger(__name__)

CARBON_FILTER = "carbonFilter"
LAST_REPLACEMENT = "lastReplacement"
PERCENTAGE = "percentage"
REMAINING_TIME = "remainingTime"
LAST_CHECK_UP = "lastCheckUp"
# Haier recommends a new carbon filter every 12 months (hOn app gauge 0-12)
FILTER_LIFETIME_MONTHS = 12
REFRESH_INTERVAL = timedelta(hours=6)
_DAYS_PER_MONTH = 365.2425 / 12
_DURATION = re.compile(
    r"^(?P<sign>[-+])?P(?:(?P<days>\d+(?:[.,]\d+)?)D)?"
    r"(?:T(?:(?P<hours>\d+(?:[.,]\d+)?)H)?(?:(?P<minutes>\d+(?:[.,]\d+)?)M)?"
    r"(?:(?P<seconds>\d+(?:[.,]\d+)?)S)?)?$"
)


def parse_datetime(value: Any) -> datetime | None:
    """ISO string or epoch (s/ms) -> aware UTC datetime; empty or 1970 -> None."""
    if value is None or value == "" or isinstance(value, bool):
        return None
    result: datetime | None = None
    if isinstance(value, (int, float)):
        seconds = value / 1000 if value > 1e11 else value
        result = datetime.fromtimestamp(seconds, tz=timezone.utc)
    elif isinstance(value, str):
        text = value.strip().replace("Z", "+00:00")
        # Python < 3.11 wants 0, 3 or 6 fraction digits (hOn sends ".0")
        text = re.sub(
            r"\.(\d+)", lambda m: "." + (m.group(1) + "000000")[:6], text, count=1
        )
        try:
            result = datetime.fromisoformat(text)
        except ValueError:
            return None
        if result.tzinfo is None:
            result = result.replace(tzinfo=timezone.utc)
    if result is None or result.year <= 1970:
        return None
    return result


def parse_duration(value: Any) -> timedelta | None:
    """ISO 8601 duration like ``-PT15981H20M32.23S`` -> timedelta."""
    if not isinstance(value, str) or not (match := _DURATION.match(value.strip())):
        return None
    parts = {
        key: float(number.replace(",", "."))
        for key, number in match.groupdict().items()
        if key != "sign" and number
    }
    if not parts:
        return None
    result = timedelta(**parts)
    return -result if match.group("sign") == "-" else result


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        return float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return None


def carbon_filter(device: HonAppliance) -> dict[str, Any] | None:
    block = device.statistics.get(CARBON_FILTER)
    return block if isinstance(block, dict) else None


def has_carbon_filter(device: HonAppliance) -> bool:
    return carbon_filter(device) is not None


def filter_last_replaced(device: HonAppliance) -> datetime | None:
    if (block := carbon_filter(device)) is None:
        return None
    return parse_datetime(block.get(LAST_REPLACEMENT))


def filter_percentage(device: HonAppliance) -> float | None:
    if (block := carbon_filter(device)) is None:
        return None
    return _number(block.get(PERCENTAGE))


def filter_remaining(device: HonAppliance) -> timedelta | None:
    if (block := carbon_filter(device)) is None:
        return None
    return parse_duration(block.get(REMAINING_TIME))


def filter_age_months(
    device: HonAppliance, now: datetime | None = None
) -> float | None:
    """Months since the last replacement (falls back to the reported percentage)."""
    now = now or datetime.now(timezone.utc)
    if (last := filter_last_replaced(device)) is not None:
        return round(max((now - last).days, 0) / _DAYS_PER_MONTH, 1)
    if (percentage := filter_percentage(device)) is not None:
        return round(percentage * FILTER_LIFETIME_MONTHS / 100, 1)
    return None


def filter_due(device: HonAppliance, now: datetime | None = None) -> bool | None:
    """Replacement due: age >= 12 months or hOn's own counters say so."""
    signals: list[bool] = []
    if (age := filter_age_months(device, now)) is not None:
        signals.append(age >= FILTER_LIFETIME_MONTHS)
    if (remaining := filter_remaining(device)) is not None:
        signals.append(remaining <= timedelta(0))
    if (percentage := filter_percentage(device)) is not None:
        signals.append(percentage >= 100)
    return any(signals) if signals else None


def filter_attributes(device: HonAppliance) -> dict[str, Any]:
    attributes: dict[str, Any] = {}
    if (percentage := filter_percentage(device)) is not None:
        attributes["percentage"] = percentage
    if (remaining := filter_remaining(device)) is not None:
        attributes["remaining_days"] = round(remaining.total_seconds() / 86400, 1)
    attributes["lifetime_months"] = FILTER_LIFETIME_MONTHS
    return attributes


def has_check_up(device: HonAppliance) -> bool:
    return device.appliance_type == "WC" and LAST_CHECK_UP in device.info


def last_check_up(device: HonAppliance) -> datetime | None:
    return parse_datetime(device.info.get(LAST_CHECK_UP))


class MaintenanceRefresher:  # pylint: disable=too-few-public-methods
    """Re-reads maintenance data at most every REFRESH_INTERVAL."""

    def __init__(self, hon: Any, interval: timedelta = REFRESH_INTERVAL) -> None:
        self._hon = hon
        self._interval = interval
        # pyhon loaded everything during setup
        self.last_refresh: datetime = datetime.now(timezone.utc)

    def _devices(self) -> list[HonAppliance]:
        return [
            device
            for device in self._hon.appliances
            if not device.zone and (has_carbon_filter(device) or has_check_up(device))
        ]

    async def async_refresh(self, force: bool = False) -> bool:
        """Returns True when the cloud was re-read."""
        now = datetime.now(timezone.utc)
        if not force and now - self.last_refresh < self._interval:
            return False
        if not (devices := self._devices()):
            return False
        self.last_refresh = now
        for device in devices:
            if not has_carbon_filter(device):
                continue
            try:
                statistics = await device.api.load_statistics(device)
                statistics |= await device.api.load_maintenance(device)
            except Exception as error:  # pylint: disable=broad-except
                _LOGGER.warning("hOn maintenance refresh failed: %s", error)
                continue
            if isinstance(statistics, dict) and statistics:
                device.statistics.clear()
                device.statistics.update(statistics)
        if any(has_check_up(device) for device in devices):
            await self._async_refresh_check_up(devices)
        return True

    async def _async_refresh_check_up(self, devices: list[HonAppliance]) -> None:
        try:
            appliances = await self._hon.api.load_appliances()
        except Exception as error:  # pylint: disable=broad-except
            _LOGGER.warning("hOn appliance list refresh failed: %s", error)
            return
        by_mac = {
            data.get("macAddress"): data
            for data in appliances or []
            if isinstance(data, dict)
        }
        for device in devices:
            data = by_mac.get(device.mac_address)
            if data is not None and LAST_CHECK_UP in data:
                device.info[LAST_CHECK_UP] = data[LAST_CHECK_UP]
