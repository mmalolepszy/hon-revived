"""Carbon filter / Smart Check Up entities (no cloud).

Fixture: ``tests.wine_cellar_data.MAINTENANCE`` follows the maintenance-cycle
payload of a live HWS77GDAU1 (``carbonFilter: {lastReplacement, percentage,
remainingTime}``) and ``lastCheckUp`` from the appliance list entry. The
hon-test-data dumps (Andre0512/hon-test-data, e.g. ``dw_509/maintenance.json``)
contain no wine cellar; their ``filterCleaning`` shape must be ignored.
"""

from __future__ import annotations

# pytest fixtures are injected by parameter name
# pylint: disable=redefined-outer-name

from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
from pytest_homeassistant.common import async_fire_time_changed

from custom_components.hon import maintenance
from custom_components.hon.const import DOMAIN
from tests.conftest import entity_id, make_appliance
from tests.wine_cellar_data import APPLIANCE, FakeApi

NOW = "2026-11-02T12:00:00+00:00"
KEYS = {
    "sensor": ("carbonFilter.lastReplacement", "carbonFilter.age", "lastCheckUp"),
    "binary_sensor": ("carbonFilter.due",),
}


@pytest.fixture
def api(request: pytest.FixtureRequest) -> FakeApi:
    params: dict[str, Any] = getattr(request, "param", {})
    return FakeApi(**params)


def test_parse_duration() -> None:
    overdue = maintenance.parse_duration("-PT15981H20M32.23S")
    assert overdue is not None and round(overdue.total_seconds() / 86400, 1) == -665.9
    assert maintenance.parse_duration("P1DT2H") == timedelta(days=1, hours=2)
    assert maintenance.parse_duration("PT") is None
    assert maintenance.parse_duration("soon") is None
    assert maintenance.parse_duration(None) is None


def test_parse_datetime() -> None:
    expected = datetime(2024, 1, 5, 9, 0, tzinfo=timezone.utc)
    assert maintenance.parse_datetime("2024-01-05T09:00:00.0Z") == expected
    assert maintenance.parse_datetime("2024-01-05T09:00:00.000Z") == expected
    assert maintenance.parse_datetime(int(expected.timestamp() * 1000)) == expected
    assert maintenance.parse_datetime("1970-01-01T00:00:00.0Z") is None
    assert maintenance.parse_datetime("") is None
    assert maintenance.parse_datetime("05/01/2024") is None
    assert maintenance.parse_datetime(None) is None


@pytest.mark.freeze_time(NOW)
async def test_carbon_filter_entities(hass: HomeAssistant, setup) -> None:
    replaced = hass.states.get(entity_id(hass, "sensor", KEYS["sensor"][0]))
    assert replaced.state == "2024-01-05T09:00:00+00:00"
    assert replaced.attributes["device_class"] == "timestamp"

    age = hass.states.get(entity_id(hass, "sensor", KEYS["sensor"][1]))
    assert float(age.state) == pytest.approx(33.9)
    assert age.attributes["unit_of_measurement"] == "months"
    assert age.attributes["percentage"] == 282
    assert age.attributes["remaining_days"] == -665.9

    due = hass.states.get(entity_id(hass, "binary_sensor", KEYS["binary_sensor"][0]))
    assert due.state == "on"
    assert due.attributes["device_class"] == "problem"

    check_up = hass.states.get(entity_id(hass, "sensor", KEYS["sensor"][2]))
    assert check_up.state == "2025-03-14T08:30:00+00:00"


async def test_entities_only_on_base_device(hass: HomeAssistant, setup) -> None:
    registry = er.async_get(hass)
    unique_ids = {
        entry.unique_id
        for entry in registry.entities.values()
        if entry.platform == DOMAIN
        and any(entry.unique_id.endswith(k) for keys in KEYS.values() for k in keys)
    }
    mac = APPLIANCE["macAddress"]
    assert unique_ids == {f"{mac}{k}" for keys in KEYS.values() for k in keys}


@pytest.mark.freeze_time(NOW)
@pytest.mark.parametrize(
    "api",
    [
        {
            "maintenance": {
                "carbonFilter": {
                    "lastReplacement": "2026-09-01T08:00:00.0Z",
                    "percentage": 17,
                    "remainingTime": "PT7300H",
                }
            }
        }
    ],
    indirect=True,
)
async def test_fresh_filter_is_not_due(hass: HomeAssistant, setup) -> None:
    due = hass.states.get(entity_id(hass, "binary_sensor", KEYS["binary_sensor"][0]))
    assert due.state == "off"
    age = hass.states.get(entity_id(hass, "sensor", KEYS["sensor"][1]))
    assert float(age.state) == pytest.approx(2.0)


@pytest.mark.freeze_time(NOW)
@pytest.mark.parametrize(
    "api", [{"maintenance": {"carbonFilter": {"percentage": 150}}}], indirect=True
)
async def test_percentage_only(hass: HomeAssistant, setup) -> None:
    """Without a date: age from the percentage, no last-replaced sensor."""
    registry = er.async_get(hass)
    mac = APPLIANCE["macAddress"]
    assert not registry.async_get_entity_id(
        "sensor", DOMAIN, f"{mac}{KEYS['sensor'][0]}"
    )
    age = hass.states.get(entity_id(hass, "sensor", KEYS["sensor"][1]))
    assert float(age.state) == 18.0
    due = hass.states.get(entity_id(hass, "binary_sensor", KEYS["binary_sensor"][0]))
    assert due.state == "on"


@pytest.mark.parametrize(
    "api",
    [
        {
            # dishwasher-style payload, no carbon filter, no lastCheckUp
            "maintenance": {
                "filterCleaning": {"tot": 15, "count": 3, "remaining": 12},
                "lastCheckup": None,
            },
            "appliance": {k: v for k, v in APPLIANCE.items() if k != "lastCheckUp"},
        }
    ],
    indirect=True,
)
async def test_missing_keys_create_nothing(
    hass: HomeAssistant, setup, caplog: pytest.LogCaptureFixture
) -> None:
    registry = er.async_get(hass)
    mac = APPLIANCE["macAddress"]
    for platform, keys in KEYS.items():
        for key in keys:
            assert not registry.async_get_entity_id(platform, DOMAIN, f"{mac}{key}")
    assert "Traceback" not in caplog.text
    # the regular wine cellar entities are still there
    assert hass.states.get(entity_id(hass, "sensor", "tempSel")).state == "16.1"


async def test_maintenance_is_not_polled(
    hass: HomeAssistant, setup, api: FakeApi
) -> None:
    sensor = entity_id(hass, "sensor", KEYS["sensor"][0])
    calls = api.maintenance_calls
    api.maintenance["carbonFilter"]["lastReplacement"] = "2026-11-01T10:00:00.0Z"
    api.appliance["lastCheckUp"] = "2026-11-01T11:00:00.0Z"

    now = dt_util.utcnow()
    for hours in (1, 6, 7, 24, 7 * 24):
        async_fire_time_changed(hass, now + timedelta(hours=hours, seconds=1))
        await hass.async_block_till_done()
    assert api.maintenance_calls == calls
    assert hass.states.get(sensor).state == "2024-01-05T09:00:00+00:00"

    # An explicit refresh (not scheduled by the integration) still works
    refresher = hass.data[DOMAIN][setup.unique_id]["maintenance"]
    assert await refresher.async_refresh(force=True)
    hass.data[DOMAIN][setup.unique_id]["coordinator"].async_set_updated_data({})
    await hass.async_block_till_done()
    assert api.maintenance_calls == calls + 1
    assert hass.states.get(sensor).state == "2026-11-01T10:00:00+00:00"
    check_up = entity_id(hass, "sensor", KEYS["sensor"][2])
    assert hass.states.get(check_up).state == "2026-11-01T11:00:00+00:00"
    assert api.sent == []


async def test_failed_refresh_keeps_values(hass: HomeAssistant, setup, api) -> None:
    async def broken(_appliance: Any) -> dict[str, Any]:
        raise RuntimeError("cloud down")

    api.load_maintenance = broken
    refresher = hass.data[DOMAIN][setup.unique_id]["maintenance"]
    assert await refresher.async_refresh(force=True)
    sensor = entity_id(hass, "sensor", KEYS["sensor"][0])
    hass.data[DOMAIN][setup.unique_id]["coordinator"].async_set_updated_data({})
    await hass.async_block_till_done()
    assert hass.states.get(sensor).state == "2024-01-05T09:00:00+00:00"


async def test_unit_helpers_without_data() -> None:
    device = await make_appliance(FakeApi(maintenance={}))
    assert not maintenance.has_carbon_filter(device)
    assert maintenance.filter_age_months(device) is None
    assert maintenance.filter_due(device) is None
    assert maintenance.filter_last_replaced(device) is None
