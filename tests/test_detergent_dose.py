"""Prepared detergent dose fractions are displayed as percentages."""

# pylint: disable=protected-access

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from homeassistant.const import PERCENTAGE

from custom_components.hon.sensor import HonConfigSensorEntity, SENSORS


@pytest.mark.parametrize(
    "key", ["startProgram.liquidDetergentDose", "startProgram.powderDetergentDose"]
)
def test_dose_fractions_and_invalid_values(key):
    for profile in ("WM", "WD"):
        description = next(item for item in SENSORS[profile] if item.key == key)
        assert description.native_unit_of_measurement == PERCENTAGE
        assert description.state_class is None
        setting = SimpleNamespace(value=None)
        entity = HonConfigSensorEntity.__new__(HonConfigSensorEntity)
        entity.entity_description = description
        entity._device = SimpleNamespace(settings={key: setting})
        entity.schedule_update_ha_state = MagicMock()
        for raw, expected in (
            (1, 25),
            (2, 50),
            (3, 75),
            (4, 100),
            ("1", 25),
            ("4.0", 100),
            (2.0, 50),
        ):
            setting.value = raw
            entity._handle_coordinator_update(False)
            assert entity._attr_native_value == expected
            assert setting.value == raw
        for raw in (
            None,
            True,
            False,
            0,
            -1,
            5,
            1.5,
            "2.5",
            "",
            "bad",
            "nan",
            float("inf"),
            {},
            [],
        ):
            setting.value = raw
            entity._handle_coordinator_update(False)
            assert entity._attr_native_value is None
        entity._device.settings.clear()
        entity._handle_coordinator_update(False)
        assert entity._attr_native_value is None


def test_unrelated_config_and_tank_sensor_metadata_are_unchanged():
    description = next(
        item for item in SENSORS["WM"] if item.key == "startProgram.weight"
    )
    entity = HonConfigSensorEntity.__new__(HonConfigSensorEntity)
    entity.entity_description = description
    entity._device = SimpleNamespace(
        settings={description.key: SimpleNamespace(value="40")}
    )
    entity._handle_coordinator_update(False)
    assert entity._attr_native_value == 40
    tank = next(item for item in SENSORS["WM"] if item.key == "detergentPercent")
    assert tank.translation_key == "detergent_level"
    assert tank.native_unit_of_measurement == PERCENTAGE
