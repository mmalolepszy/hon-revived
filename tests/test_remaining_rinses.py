"""The current remaining rinse count is discovered and validated."""

# pylint: disable=protected-access

import asyncio
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from custom_components.hon.const import DOMAIN
from custom_components.hon.sensor import HonSensorEntity, SENSORS, async_setup_entry

KEY = "remainingRinseIterations"


@pytest.mark.parametrize("profile", ["WM", "WD"])
def test_remaining_rinse_counts(profile):
    description = next(item for item in SENSORS[profile] if item.key == KEY)
    assert description.translation_key == "remaining_rinses"
    assert description.state_class is None
    values = {KEY: 0}
    entity = HonSensorEntity.__new__(HonSensorEntity)
    entity.entity_description = description
    entity._device = SimpleNamespace(get=values.get)
    entity.schedule_update_ha_state = Mock()
    for raw, expected in ((0, 0), (2, 2), ("2.0", 2), (3.0, 3)):
        values[KEY] = raw
        entity._handle_coordinator_update(False)
        assert entity._attr_native_value == expected
        assert type(entity._attr_native_value) is int
    for raw in (None, True, -1, 1.5, "bad", "nan", float("inf")):
        values[KEY] = raw
        entity._handle_coordinator_update(False)
        assert entity._attr_native_value is None


@pytest.mark.parametrize("profile", ["WM", "WD", "TD"])
@pytest.mark.parametrize("raw", [None, 0, 2])
def test_discovery_only_when_reported(profile, raw):
    async def setup():
        data = {KEY: raw}
        device = SimpleNamespace(
            appliance_type=profile,
            unique_id="test",
            available_settings=[],
            get=data.get,
        )
        hass = SimpleNamespace(
            data={
                DOMAIN: {
                    "entry": {
                        "coordinator": None,
                        "hon": SimpleNamespace(appliances=[device]),
                    }
                }
            }
        )
        entities = []
        await async_setup_entry(
            hass, SimpleNamespace(unique_id="entry"), entities.extend
        )
        return entities

    entities = asyncio.run(setup())
    expected = raw is not None and profile in ("WM", "WD")
    assert len(entities) == int(expected)
    if expected:
        assert entities[0].native_value == raw
        assert entities[0].entity_description.key == KEY


def test_other_live_sensor_keeps_its_value():
    description = next(item for item in SENSORS["WM"] if item.key == "currentWaterUsed")
    entity = HonSensorEntity.__new__(HonSensorEntity)
    entity.entity_description = description
    entity._device = SimpleNamespace(get=lambda _key, _default=None: 12)
    entity._handle_coordinator_update(False)
    assert entity._attr_native_value == 12
