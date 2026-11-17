"""Anonymised hOn data for a two-zone wine cellar (WC128, HWS77GDAU1 family).

Structure adapted from the HWS42GDAU1 fixtures of crivabene/ha-hon-wine-cellar
(MIT). Identifiers are made up; nothing here comes from a real account.
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
}


def _fixed(value: str) -> dict[str, Any]:
    return {
        "category": "command",
        "typology": "fixed",
        "mandatory": 0,
        "fixedValue": value,
    }


def _range(default: str, low: str, high: str) -> dict[str, Any]:
    return {
        "category": "command",
        "typology": "range",
        "mandatory": 0,
        "defaultValue": default,
        "minimumValue": low,
        "maximumValue": high,
        "incrementValue": "1",
    }


def _ancillary(family: str) -> dict[str, Any]:
    return {
        "programFamily": {
            "category": "cluster",
            "typology": "enum",
            "mandatory": 1,
            "enumValues": [family],
            "defaultValue": f"[{family}]",
        },
        "remoteActionable": {
            "category": "general",
            "typology": "fixed",
            "mandatory": 0,
            "fixedValue": "1",
        },
        "remoteVisible": {
            "category": "general",
            "typology": "fixed",
            "mandatory": 0,
            "fixedValue": "1",
        },
    }


def _program(code: str, default: str, low: str, high: str) -> dict[str, Any]:
    return {
        "description": "The command allows to start a program",
        "protocolType": "MQTT",
        "parameters": {
            "prCode": _fixed(code),
            "prCodeZ2": _fixed(code),
            "tempSel": _range(default, low, high),
            "tempSelZ2": _range(default, low, high),
        },
        "ancillaryParameters": _ancillary("dashboard"),
    }


def _recipe(temperature: str) -> dict[str, Any]:
    return {
        "description": "The command allows to start a program",
        "protocolType": "MQTT",
        "parameters": {
            "tempSel": _fixed(temperature),
            "tempSelZ2": _fixed(temperature),
        },
        "ancillaryParameters": _ancillary("download"),
    }


COMMANDS: dict[str, Any] = {
    "resultCode": "0",
    "applianceModel": {"options": {}},
    "settings": {
        "description": "Set parameters",
        "protocolType": "MQTT",
        "parameters": {
            "lightStatus": _range("0", "0", "1"),
            "sabbathStatus": _range("0", "0", "1"),
            "tempSel": _range("5", "5", "20"),
            "tempSelZ2": _range("5", "5", "20"),
            "tempUnit": _range("0", "0", "1"),
        },
    },
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

    def __init__(self, state: dict[str, str] | None = None) -> None:
        self.state = dict(state or STATE)
        self.sent: list[dict[str, Any]] = []
        self.accept = True

    async def load_commands(self, appliance: Any) -> dict[str, Any]:
        return copy.deepcopy(COMMANDS)

    async def load_favourites(self, appliance: Any) -> list[Any]:
        return []

    async def load_command_history(self, appliance: Any) -> list[Any]:
        return []

    async def load_attributes(self, appliance: Any) -> dict[str, Any]:
        return {
            "shadow": {
                "parameters": {k: {"parNewVal": v} for k, v in self.state.items()}
            },
            "lastConnEvent": {"category": "CONNECTED"},
        }

    async def load_statistics(self, appliance: Any) -> dict[str, Any]:
        return {}

    async def load_maintenance(self, appliance: Any) -> dict[str, Any]:
        return {}

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
