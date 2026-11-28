"""Made-up hOn data for a two-zone wine cellar: only what the tests use.

Identifiers (MAC, serial, code) are fabricated; nothing here comes from a real account.
"""

from __future__ import annotations

import copy
from typing import Any

MAC = "aa-bb-cc-dd-ee-ff"

APPLIANCE: dict[str, Any] = {
    "macAddress": MAC,
    "applianceTypeName": "WC",
    "applianceTypeId": 6,
    "applianceModelId": 128,
    "modelName": "HWS77GDAU1",
    "brand": "haier",
    "code": "TESTCODE000",
    "fwVersion": "5.30.0",
    "nickName": "Test cellar",
    "serialNumber": "SERIAL123456",
    "zone": "2",
    "topics": {"subscribe": [f"haier/things/{MAC}/event/appliancestatus/update"]},
    "lastCheckUp": "2025-03-14T08:30:00.0Z",
}

# commands/v1/maintenance-cycle payload of a HWS77GDAU1 (shape and counters from
# the live appliance's anonymised hOn dump, Nov 2026; date as shown in the hOn app)
MAINTENANCE: dict[str, Any] = {
    "carbonFilter": {
        "lastReplacement": "2024-01-05T09:00:00.000Z",
        "percentage": 282,
        "remainingTime": "-PT15981H20M32.23S",
    },
    "resultCode": "0",
}


def _fixed(value: str) -> dict[str, Any]:
    return {"typology": "fixed", "fixedValue": value}


def _range(default: str, low: str, high: str) -> dict[str, Any]:
    return {
        "typology": "range",
        "defaultValue": default,
        "minimumValue": low,
        "maximumValue": high,
    }


def _family(family: str) -> dict[str, Any]:
    return {
        "programFamily": {
            "typology": "enum",
            "enumValues": [family],
            "defaultValue": f"[{family}]",
        }
    }


def _command(parameters: dict[str, Any], family: str = "") -> dict[str, Any]:
    # pyhon only parses dicts with a description and a protocolType as commands
    command = {"description": "", "protocolType": "MQTT", "parameters": parameters}
    if family:
        command["ancillaryParameters"] = _family(family)
    return command


def _program(code: str, default: str, low: str, high: str) -> dict[str, Any]:
    return _command(
        {
            "prCode": _fixed(code),
            "prCodeZ2": _fixed(code),
            "tempSel": _range(default, low, high),
            "tempSelZ2": _range(default, low, high),
        },
        "dashboard",
    )


def _recipe(temperature: str) -> dict[str, Any]:
    return _command(
        {"tempSel": _fixed(temperature), "tempSelZ2": _fixed(temperature)},
        "download",
    )


COMMANDS: dict[str, Any] = {
    "settings": _command(
        {
            "lightStatus": _range("0", "0", "1"),
            "sabbathStatus": _range("0", "0", "1"),
            "tempSel": _range("5", "5", "20"),
            "tempSelZ2": _range("5", "5", "20"),
            "tempUnit": _range("0", "0", "1"),
        }
    ),
    "startProgram": {
        "PROGRAMS.WC.SPARKLING": _program("3", "8", "5", "8"),
        "PROGRAMS.WC.WHITE": _program("2", "12", "9", "12"),
        "PROGRAMS.WC.RED": _program("1", "16", "13", "20"),
        "PROGRAMS.WC.IOT_ROSE": _recipe("6"),
        "PROGRAMS.WC.IOT_WHISKY": _recipe("17"),
    },
}

# Zone 1 red at 16 °C (reported 16.1), zone 2 sparkling at 8 °C (reported 7.8)
STATE: dict[str, str] = {
    "errors": "00",
    "humidityZ1": "47",
    "humidityZ2": "69",
    "lightStatus": "0",
    "onOffStatus": "1",
    "prCode": "1",
    "prCodeZ2": "3",
    "sabbathStatus": "0",
    "temp": "14.4",
    "tempEnv": "22.2",
    "tempSel": "16.1",
    "tempSelZ2": "7.8",
    "tempUnit": "0",
    "tempZ2": "7.8",
}


class FakeApi:
    """Stands in for pyhon's HonAPI: no network, records every command."""

    def __init__(
        self,
        state: dict[str, str] | None = None,
        maintenance: dict[str, Any] | None = None,
        appliance: dict[str, Any] | None = None,
    ) -> None:
        self.state = dict(state or STATE)
        self.maintenance = copy.deepcopy(
            MAINTENANCE if maintenance is None else maintenance
        )
        self.appliance = dict(APPLIANCE if appliance is None else appliance)
        self.sent: list[dict[str, Any]] = []
        self.history: list[dict[str, Any]] = []
        self.accept = True
        self.maintenance_calls = 0
        # Every read of appliance state from the cloud (must not grow after setup)
        self.reads = 0

    async def load_commands(self, appliance: Any) -> dict[str, Any]:
        return copy.deepcopy(COMMANDS)

    async def load_favourites(self, appliance: Any) -> list[Any]:
        return []

    async def load_command_history(self, appliance: Any) -> list[Any]:
        return copy.deepcopy(self.history)

    async def load_attributes(self, appliance: Any) -> dict[str, Any]:
        self.reads += 1
        return {
            "shadow": {
                "parameters": {k: {"parNewVal": v} for k, v in self.state.items()}
            },
            "lastConnEvent": {"category": "CONNECTED"},
        }

    async def load_statistics(self, appliance: Any) -> dict[str, Any]:
        self.reads += 1
        return {}

    async def load_maintenance(self, appliance: Any) -> dict[str, Any]:
        self.maintenance_calls += 1
        self.reads += 1
        return copy.deepcopy(self.maintenance)

    async def load_appliances(self) -> list[dict[str, Any]]:
        self.reads += 1
        return [dict(self.appliance)]

    async def send_command(
        self,
        appliance: Any,
        command: str,
        parameters: dict[str, Any],
        ancillary_parameters: dict[str, Any],
        program_name: str = "",
    ) -> bool:
        self.sent.append(
            {
                "command": command,
                "parameters": dict(parameters),
                "ancillary": dict(ancillary_parameters),
                "program": program_name.upper() if program_name else "",
            }
        )
        return self.accept
