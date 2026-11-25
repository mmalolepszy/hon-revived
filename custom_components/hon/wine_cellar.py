"""Wine cellar (WC) helpers: zone commands like the hOn app.

A two-zone Haier wine cellar (e.g. HWS42GDAU1 / WC127, HWS77GDAU1 / WC128,
WC666) has two independent temperature zones. The hOn app sends per-zone
startProgram commands:

* one zone: ``startProgram`` with only that zone's ``{prCode, tempSel}`` or
  ``{prCodeZ2, tempSelZ2}`` plus the program name and its ancillary parameters
  (``programFamily: [dashboard]``); recipes carry only the temperature.

v0.19.8 sends ``settings`` with only the changed parameter (#85); this module
adds the app's program handling: a target outside the current program's range
switches to a program whose range fits. State is confirmed by the appliance
over MQTT; there is no REST re-read after a command.

Findings credited to @crivabene (#56, ha-hon-wine-cellar), @mkatwijk (#85) and
@alexw23 (PR #78).
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from pyhon.appliance import HonAppliance
from pyhon.commands import HonCommand
from pyhon.parameter.fixed import HonParameterFixed
from pyhon.parameter.range import HonParameterRange

_LOGGER = logging.getLogger(__name__)

WINE_CELLAR = "WC"

# Climate entity key -> (program code parameter, target temperature parameter)
ZONES: dict[str, tuple[str, str]] = {
    "settings.tempSel": ("prCode", "tempSel"),
    "settings.tempSelZ2": ("prCodeZ2", "tempSelZ2"),
}


def is_wine_cellar(device: HonAppliance) -> bool:
    return getattr(device, "appliance_type", None) == WINE_CELLAR


def reported(device: HonAppliance, key: str) -> float | str | None:
    """Value the appliance reported (never a command default)."""
    attribute = device.attributes.get("parameters", {}).get(key)
    if attribute is None or str(attribute) == "":
        return None
    value: float | str = attribute.value
    return value


def whole(value: Any) -> int | None:
    """Whole °C: undoes the °F round trip (16.1 -> 16, 7.8 -> 8)."""
    try:
        return round(float(str(value).replace(",", ".")))
    except (TypeError, ValueError):
        return None


def target_temperature(device: HonAppliance, key: str) -> float | None:
    """Reported zone target in whole °C, for a climate key like settings.tempSel."""
    temp_key = key.split(".")[-1]
    if (value := whole(reported(device, temp_key))) is None:
        return None
    return float(value)


def _apply_optimistic(device: HonAppliance, parameters: dict[str, Any]) -> None:
    """Show the sent values until the cloud confirms (pyhon locks them ~10 s)."""
    attributes = device.attributes.setdefault("parameters", {})
    for key, value in parameters.items():
        if (attribute := attributes.get(key)) is not None:
            attribute.update(str(value), shield=True)


async def _async_send(
    device: HonAppliance,
    parameters: dict[str, Any],
    ancillary: dict[str, Any] | None = None,
    program_name: str = "",
) -> None:
    _LOGGER.debug("WC startProgram %s %s %s", program_name, parameters, ancillary or {})
    if not await device.api.send_command(
        device, "startProgram", parameters, ancillary or {}, program_name
    ):
        raise HomeAssistantError("hOn refused the wine cellar command")
    _apply_optimistic(device, parameters)


def _programs(device: HonAppliance) -> dict[str, HonCommand]:
    """startProgram categories, without user favourites (copies of programs)."""
    if not (command := device.commands.get("startProgram")):
        return {}
    return {
        name: category
        for name, category in command.categories.items()
        if "favourite" not in category.parameters
    }


def _fixed(command: HonCommand, *keys: str) -> str | None:
    for key in keys:
        if isinstance(parameter := command.parameters.get(key), HonParameterFixed):
            return str(parameter.value)
    return None


def _fits(command: HonCommand, temp_key: str, temperature: int) -> bool:
    parameter = command.parameters.get(temp_key)
    if isinstance(parameter, HonParameterRange):
        return parameter.min <= temperature <= parameter.max
    if isinstance(parameter, HonParameterFixed):
        return whole(parameter.value) == temperature
    return False


def _ancillary(command: HonCommand) -> dict[str, Any]:
    ancillary = dict(command.parameter_groups.get("ancillaryParameters", {}))
    ancillary.pop("programRules", None)
    return ancillary


def zone_program(device: HonAppliance, key: str) -> str | None:
    """Name of the base program a zone runs, from its reported program code."""
    if key not in ZONES:
        return None
    code_key, _ = ZONES[key]
    if (code := whole(reported(device, code_key))) is None:
        return None
    return next(
        (
            name
            for name, command in _programs(device).items()
            if isinstance(command.parameters.get(code_key), HonParameterFixed)
            and whole(_fixed(command, code_key)) == code
        ),
        None,
    )


# pylint: disable-next=too-many-locals
def zone_command(  # noqa: C901 - mirrors the app's program/zone rules
    device: HonAppliance,
    key: str,
    temperature: float | None = None,
    program: str | None = None,
) -> tuple[str, dict[str, str], dict[str, Any]]:
    """Build (programName, parameters, ancillary) for one zone, as the app does."""
    if key not in ZONES:
        raise ServiceValidationError(f"Unknown wine cellar zone {key}")
    code_key, temp_key = ZONES[key]
    programs = _programs(device)
    current_code = whole(reported(device, code_key))
    current_target = whole(reported(device, temp_key))
    target = whole(temperature) if temperature is not None else None

    if program is not None:
        if (command := programs.get(program)) is None:
            raise ServiceValidationError(f"Unknown wine cellar program {program}")
        if target is None:
            parameter = command.parameters.get(temp_key)
            if current_target is not None and _fits(command, temp_key, current_target):
                target = current_target
            elif isinstance(parameter, HonParameterFixed):
                target = whole(parameter.value)
            elif isinstance(parameter, HonParameterRange):
                target = whole(getattr(parameter, "_default", parameter.min))
    else:
        if target is None:
            raise ServiceValidationError("Missing target temperature")
        base = {
            name: command
            for name, command in programs.items()
            if _fixed(command, code_key, "prCode") is not None
            and isinstance(command.parameters.get(temp_key), HonParameterRange)
        }
        current = [
            c
            for c in base.values()
            if whole(_fixed(c, code_key, "prCode")) == current_code
        ]
        fitting = [
            c for c in current + list(base.values()) if _fits(c, temp_key, target)
        ]
        if not fitting:
            raise ServiceValidationError(
                f"{target} °C is outside every wine cellar program range"
            )
        command = fitting[0]

    if target is None or not _fits(command, temp_key, target):
        raise ServiceValidationError(
            f"{target} °C does not fit program {command.category}"
        )
    parameters: dict[str, str] = {}
    if (code := _fixed(command, code_key, "prCode")) is not None:
        parameters[code_key] = code
    parameters[temp_key] = str(target)
    return command.category, parameters, _ancillary(command)


async def async_set_zone(
    device: HonAppliance,
    key: str,
    temperature: float | None = None,
    program: str | None = None,
) -> None:
    program_name, parameters, ancillary = zone_command(
        device, key, temperature, program
    )
    await _async_send(device, parameters, ancillary, program_name)


def push_optimistic(coordinator: DataUpdateCoordinator[dict[str, Any]]) -> None:
    """Show the sent values now; the appliance confirms them over MQTT.

    No REST re-read after a command: polling the hOn cloud is what led to
    Haier's takedown request in 2024 (takedown_faq.md).
    """
    coordinator.async_set_updated_data({})
