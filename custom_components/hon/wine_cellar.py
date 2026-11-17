"""Wine cellar (WC) helpers: send only what changes, never the 5 °C defaults.

A two-zone Haier wine cellar (e.g. HWS42GDAU1 / WC127, HWS77GDAU1 / WC128,
WC666) gets loaded by pyhon as a base appliance plus Z1/Z2 clones. pyhon syncs
the reported values into ``settings`` before the attributes are loaded, so
``settings.tempSel`` / ``settings.tempSelZ2`` keep their 5 °C default; MQTT
pushes go to the first clone, never to the base appliance, and nothing polls.
A full ``settings`` send then resets *both* zones to 5 °C (issues #56, #85).
Even when pyhon does sync, it truncates the whole-°F round trip the cellar
reports (16 °C -> 61 °F -> 16.1 °C; 8 °C -> 46 °F -> 7.8 °C becomes 7).

The hOn app never does that. Its command history shows:

* light: ``startProgram`` with only ``{lightStatus}``, no program name and no
  ancillary parameters;
* one zone: ``startProgram`` with only that zone's ``{prCode, tempSel}`` or
  ``{prCodeZ2, tempSelZ2}`` plus the program name and its ancillary parameters
  (``programFamily: [dashboard]``); recipes carry only the temperature.

Findings credited to @crivabene (#56, ha-hon-wine-cellar), @mkatwijk (#85) and
@alexw23 (PR #78).
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from pyhon.appliance import HonAppliance
from pyhon.commands import HonCommand
from pyhon.parameter.fixed import HonParameterFixed
from pyhon.parameter.range import HonParameterRange

_LOGGER = logging.getLogger(__name__)

WINE_CELLAR = "WC"
# Fallback polling when MQTT push does not arrive (60 s, see crivabene/ha-hon-wine-cellar)
REFRESH_INTERVAL = timedelta(seconds=60)
# Re-read the cloud this long after a command instead of waiting for the next poll
CONFIRM_DELAY = 15

# Climate entity key -> (program code parameter, target temperature parameter)
ZONES: dict[str, tuple[str, str]] = {
    "settings.tempSel": ("prCode", "tempSel"),
    "settings.tempSelZ2": ("prCodeZ2", "tempSelZ2"),
}
TEMPERATURE_KEYS = tuple(temp for _, temp in ZONES.values())


def is_wine_cellar(device: HonAppliance) -> bool:
    return device.appliance_type == WINE_CELLAR


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


def _snap(parameter: HonParameterRange, value: float) -> float:
    steps = round((value - parameter.min) / parameter.step)
    return min(
        max(parameter.min + steps * parameter.step, parameter.min), parameter.max
    )


def seed_settings(device: HonAppliance, skip: tuple[str, ...] = ()) -> list[str]:
    """Copy reported values into the settings command (rounded to the step).

    Returns the temperature keys that could not be seeded from a reported value.
    """
    missing: list[str] = []
    if not (command := device.commands.get("settings")):
        return missing
    for key, parameter in command.parameters.items():
        if key in skip:
            continue
        value = reported(device, key)
        if value is None:
            if key in TEMPERATURE_KEYS:
                missing.append(key)
            continue
        try:
            if isinstance(parameter, HonParameterRange):
                parameter.value = _snap(parameter, float(value))
            else:
                parameter.value = str(value)
        except ValueError as error:
            _LOGGER.debug("Can't seed %s: %s", key, error)
            if key in TEMPERATURE_KEYS:
                missing.append(key)
    return missing


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


async def async_set_light(device: HonAppliance, parameter: str, on: bool) -> None:
    """Light exactly like the hOn app: startProgram {lightStatus} only."""
    await _async_send(device, {parameter: "1" if on else "0"})


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


def zone_command(
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


async def async_send_settings(device: HonAppliance, changed: dict[str, Any]) -> None:
    """Send `settings` with every other parameter seeded from reported values.

    Refuses to send when a zone target cannot be seeded, instead of letting
    the 5 °C defaults through.
    """
    if missing := seed_settings(device, skip=tuple(changed)):
        raise HomeAssistantError(
            f"Wine cellar targets {missing} unknown, refusing to reset them"
        )
    command = device.commands["settings"]
    for key, value in changed.items():
        command.parameters[key].value = value
    if not await command.send():
        raise HomeAssistantError("hOn refused the wine cellar command")
    _apply_optimistic(device, changed)


_CONFIRM = "_hon_wine_cellar_confirm"


def cancel_confirm(coordinator: DataUpdateCoordinator[dict[str, Any]]) -> None:
    if cancel := getattr(coordinator, _CONFIRM, None):
        cancel()
        setattr(coordinator, _CONFIRM, None)


def schedule_confirm(
    hass: HomeAssistant, coordinator: DataUpdateCoordinator[dict[str, Any]]
) -> None:
    """Push the optimistic state now and re-read the cloud shortly after."""
    coordinator.async_set_updated_data({})
    cancel_confirm(coordinator)

    async def _confirm(_now: Any) -> None:
        setattr(coordinator, _CONFIRM, None)
        await coordinator.async_request_refresh()

    setattr(coordinator, _CONFIRM, async_call_later(hass, CONFIRM_DELAY, _confirm))


def prefer_base_appliances(appliances: list[HonAppliance]) -> None:
    """Put WC base appliances before their zone clones (in place).

    pyhon appends the Z1/Z2 clones before the base appliance and routes an MQTT
    update to the *first* appliance subscribed to the topic, so the base device,
    which carries the real entities, never received pushes. The list is mutated
    in place because pyhon's MQTT client holds a reference to it (PR #78).
    """
    ordered = sorted(appliances, key=lambda a: bool(is_wine_cellar(a) and a.zone))
    appliances[:] = ordered


async def async_refresh(appliances: list[HonAppliance]) -> dict[str, Any]:
    """Polling fallback: re-read WC base appliances from the cloud."""
    for device in appliances:
        if not is_wine_cellar(device) or device.zone:
            continue
        try:
            await device.update(force=True)
            seed_settings(device)
        except Exception as error:  # pylint: disable=broad-except
            _LOGGER.warning("Wine cellar refresh failed: %s", error)
    return {}
