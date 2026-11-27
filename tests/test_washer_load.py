"""Verify washer load parameters and their sensor metadata."""

# pylint: disable=protected-access

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from homeassistant.const import UnitOfMass

from custom_components.hon.sensor import HonConfigSensorEntity, SENSORS


def description(profile, key):
    return next(item for item in SENSORS[profile] if item.key == key)


def read_setting(profile, key, value, *, missing=False):
    entity = HonConfigSensorEntity.__new__(HonConfigSensorEntity)
    entity.entity_description = description(profile, key)
    entity._device = SimpleNamespace(
        settings={} if missing else {key: SimpleNamespace(value=value)}
    )
    entity.schedule_update_ha_state = MagicMock()
    entity._handle_coordinator_update(False)
    return entity._attr_native_value


def test_program_weight_is_an_unscaled_unitless_parameter():
    key = "startProgram.weight"
    for profile in ("WM", "WD"):
        item = description(profile, key)
        assert item.native_unit_of_measurement is None
        assert item.state_class is None
        assert item.translation_key == "program_load_parameter"
        assert read_setting(profile, key, 40) == 40
        assert read_setting(profile, key, "40") == "40"
        assert read_setting(profile, key, "") is None
        assert read_setting(profile, key, None, missing=True) is None


@pytest.mark.parametrize(
    ("profile", "key", "translation"),
    [
        ("WM", "startProgram.suggestedLoadW", "wash_load_limit"),
        ("TD", "startProgram.suggestedLoadD", "dry_load_limit"),
        ("WD", "startProgram.suggestedLoadW", "wash_load_limit"),
        ("WD", "startProgram.suggestedLoadD", "dry_load_limit"),
        ("WD", "startProgram.suggestedLoadWD", "wash_dry_load_limit"),
    ],
)
def test_suggested_load_is_a_validated_mass_limit(profile, key, translation):
    item = description(profile, key)
    assert item.native_unit_of_measurement == UnitOfMass.KILOGRAMS
    assert item.translation_key == translation
    for raw, expected in ((12, 12), ("8", 8), ("2.5", 2.5)):
        assert read_setting(profile, key, raw) == expected
    for raw in (None, "", True, 0, -1, "bad", "nan", float("inf")):
        assert read_setting(profile, key, raw) is None
    assert read_setting(profile, key, None, missing=True) is None


def test_unrelated_config_sensor_is_unchanged():
    key = "startProgram.remainingTime"
    assert read_setting("WM", key, "45") == 45
    assert read_setting("WM", key, None, missing=True) == 0
