"""The current washer mode flags are distinct read-only binary sensors."""

# pylint: disable=protected-access

import asyncio
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from custom_components.hon.binary_sensor import (
    BINARY_SENSORS,
    HonBinarySensorEntity,
    async_setup_entry,
)
from custom_components.hon.const import DOMAIN

KEYS = ("nightWashStatus", "silentMode")


@pytest.mark.parametrize("profile", ["WM", "WD"])
@pytest.mark.parametrize("key", KEYS)
def test_mode_flag_states_and_invalid_values(profile, key):
    description = next(item for item in BINARY_SENSORS[profile] if item.key == key)
    values = {key: 0}
    entity = HonBinarySensorEntity.__new__(HonBinarySensorEntity)
    entity.entity_description = description
    entity._device = SimpleNamespace(get=values.get)
    entity.schedule_update_ha_state = Mock()
    for raw, expected in (
        (0, False),
        (1, True),
        ("0", False),
        ("1", True),
        (1.0, True),
    ):
        for wrapped in (False, True):
            values[key] = SimpleNamespace(value=raw) if wrapped else raw
            entity._handle_coordinator_update(False)
            assert entity.is_on is expected
            assert entity.state == ("on" if expected else "off")
    for raw in (None, True, False, 2, -1, 0.5, "bad", "nan", float("inf")):
        values[key] = raw
        entity._handle_coordinator_update(False)
        assert entity.is_on is None
        assert entity.state is None


@pytest.mark.parametrize("profile", ["WM", "WD", "TD"])
@pytest.mark.parametrize("raw", [None, 0, 1])
def test_discovery_only_for_reported_washer_flags(profile, raw):
    async def setup():
        data = {key: raw for key in KEYS}
        device = SimpleNamespace(appliance_type=profile, unique_id="test", get=data.get)
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
    assert len(entities) == (2 if expected else 0)
    if expected:
        assert {entity.entity_description.key for entity in entities} == set(KEYS)
        assert all(entity.is_on is bool(raw) for entity in entities)


def test_existing_remote_control_flag_keeps_its_behavior():
    description = next(
        item for item in BINARY_SENSORS["WM"] if item.key == "remoteCtrValid"
    )
    entity = HonBinarySensorEntity.__new__(HonBinarySensorEntity)
    entity.entity_description = description
    for raw, expected in ((1, True), (0, False), ("1", False), (None, False)):
        entity._device = SimpleNamespace(get=Mock(return_value=raw))
        assert entity.is_on is expected
