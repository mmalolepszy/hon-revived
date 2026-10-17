"""Exercise the sensor update callback without importing HA or contacting hOn."""

import ast
from pathlib import Path
from types import SimpleNamespace
import unittest


ROOT = Path(__file__).resolve().parents[1]
COMPONENT = ROOT / "custom_components" / "hon"


def load_callback():
    """Compile the production callback and mode table in isolation."""
    source = ast.parse((COMPONENT / "sensor.py").read_text(encoding="utf-8"))
    entity = next(
        node
        for node in source.body
        if isinstance(node, ast.ClassDef) and node.name == "HonSensorEntity"
    )
    callback = next(
        node
        for node in entity.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "_handle_coordinator_update"
    )
    callback.decorator_list = []
    constants = ast.parse((COMPONENT / "const.py").read_text(encoding="utf-8"))
    modes = next(
        ast.literal_eval(node.value)
        for node in constants.body
        if isinstance(node, ast.AnnAssign)
        and getattr(node.target, "id", None) == "MACH_MODE"
    )
    namespace = {"const": SimpleNamespace(MACH_MODE=modes)}
    module = ast.Module(body=[callback], type_ignores=[])
    exec(compile(module, str(COMPONENT / "sensor.py"), "exec"), namespace)
    return namespace["_handle_coordinator_update"]


class Device(dict):
    def __init__(self, values, options):
        super().__init__(values)
        self.settings = {"startProgram.program": options}


class ProgramNameFallbackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.update = staticmethod(load_callback())

    def read_program(self, mode=2, code=225, value="No Program", **overrides):
        options = SimpleNamespace(
            values=["all_in_one_49", "cottons"], ids={225: "all_in_one_49"}
        )
        options.ids = overrides.get("ids", options.ids)
        entity = SimpleNamespace(
            _device=Device(
                {"programName": value, "machMode": mode, "prCode": code}, options
            ),
            entity_description=SimpleNamespace(
                key="programName",
                translation_key=overrides.get("translation_key", "programs_wm"),
                state_class=None,
            ),
        )
        self.update(entity, update=False)
        self.assertIn(entity._attr_native_value, entity._attr_options)
        return entity._attr_native_value

    def test_active_program_is_recovered_from_integer_or_string_code(self):
        for mode in (2, "2", 3, "3"):
            for code in (225, "225"):
                with self.subTest(mode=mode, code=code):
                    self.assertEqual("all_in_one_49", self.read_program(mode, code))

    def test_valid_api_name_is_preserved(self):
        self.assertEqual("cottons", self.read_program(value="cottons"))

    def test_non_active_modes_preserve_no_program(self):
        for mode in (0, 1, 4, 5, 6, 7, 8, 9, 99):
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

    def test_other_appliance_profiles_are_unchanged(self):
        for profile in ("programs_td", "programs_dw", "programs_ov"):
            with self.subTest(profile=profile):
                self.assertEqual(
                    "No Program", self.read_program(translation_key=profile)
                )


if __name__ == "__main__":
    unittest.main()
