"""Exercise program-name fallback without contacting hOn."""

# pylint: disable=protected-access

from types import SimpleNamespace
import unittest

from custom_components.hon.sensor import HonSensorEntity


class Device(dict):
    def __init__(self, values, options):
        super().__init__(values)
        self.settings = {"startProgram.program": options}


class ProgramNameFallbackTests(unittest.TestCase):
    def read_program(self, mode=2, code=225, value="No Program", **overrides):
        options = SimpleNamespace(
            values=["all_in_one_49", "cottons"], ids={225: "all_in_one_49"}
        )
        options.ids = overrides.get("ids", options.ids)
        if overrides.get("missing_ids"):
            del options.ids
        entity = HonSensorEntity.__new__(HonSensorEntity)
        entity._device = Device(
            {"programName": value, "machMode": mode, "prCode": code}, options
        )
        entity.entity_description = SimpleNamespace(
            key="programName",
            translation_key=overrides.get("translation_key", "programs_wm"),
            state_class=None,
        )
        entity._handle_coordinator_update(update=False)
        self.assertIn(entity._attr_native_value, entity._attr_options)
        return entity._attr_native_value

    def test_active_program_is_recovered_from_integer_or_string_code(self):
        for mode in (2, "2", 3, "3"):
            for code in (225, "225"):
                with self.subTest(mode=mode, code=code):
                    self.assertEqual("all_in_one_49", self.read_program(mode, code))

    def test_scheduled_program_is_recovered_from_integer_or_string_code(self):
        for mode in (4, "4", 5, "5"):
            for code in (225, "225"):
                with self.subTest(mode=mode, code=code):
                    self.assertEqual("all_in_one_49", self.read_program(mode, code))

    def test_valid_api_name_is_preserved(self):
        self.assertEqual("cottons", self.read_program(value="cottons"))

    def test_non_active_modes_preserve_no_program(self):
        for mode in (0, 1, 6, 7, 8, 9, 99):
            with self.subTest(mode=mode):
                self.assertEqual("No Program", self.read_program(mode=mode))

    def test_invalid_mode_or_code_preserves_no_program(self):
        for invalid in (None, "", "invalid", float("inf")):
            with self.subTest(invalid=invalid):
                self.assertEqual("No Program", self.read_program(mode=invalid))
                self.assertEqual("No Program", self.read_program(code=invalid))

    def test_missing_or_unselectable_mapping_preserves_no_program(self):
        for ids in ({}, {225: "unavailable_program"}):
            with self.subTest(ids=ids):
                self.assertEqual("No Program", self.read_program(ids=ids))

    def test_missing_program_ids_preserves_no_program(self):
        self.assertEqual("No Program", self.read_program(missing_ids=True))

    def test_other_appliance_profiles_are_unchanged(self):
        for profile in ("programs_td", "programs_dw", "programs_ov"):
            with self.subTest(profile=profile):
                self.assertEqual(
                    "No Program", self.read_program(translation_key=profile)
                )


if __name__ == "__main__":
    unittest.main()
