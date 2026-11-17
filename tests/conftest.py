"""Shared fixtures: a fake hOn account with one two-zone wine cellar (no network)."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, AsyncGenerator, Callable
from unittest.mock import patch

import pytest
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pyhon.appliance import HonAppliance
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.hon.const import DOMAIN
from tests.wine_cellar_data import APPLIANCE, FakeApi

pytest_plugins = "pytest_homeassistant_custom_component"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Load custom_components/hon from this repository."""


async def make_appliance(api: FakeApi, zone: int = 0) -> HonAppliance:
    appliance = await HonAppliance(api, dict(APPLIANCE), zone=zone).create()  # type: ignore
    await appliance.load_commands()
    await appliance.load_attributes()
    await appliance.load_statistics()
    return appliance


class FakeHon:
    """pyhon.Hon replacement: same appliance order as pyhon (zone clones first)."""

    instance: "FakeHon"

    def __init__(self, appliances: list[HonAppliance]) -> None:
        self.appliances = appliances
        self.api = SimpleNamespace(auth=SimpleNamespace(refresh_token="test-token"))
        self._notify: Callable[[Any], None] | None = None

    async def create(self) -> "FakeHon":
        return self

    def subscribe_updates(self, notify: Callable[[Any], None]) -> None:
        self._notify = notify

    def notify(self) -> None:
        if self._notify:
            self._notify(None)


@pytest.fixture
async def api() -> FakeApi:
    return FakeApi()


@pytest.fixture
async def hon(api: FakeApi) -> FakeHon:
    appliances = [
        await make_appliance(api, zone=1),
        await make_appliance(api, zone=2),
        await make_appliance(api),
    ]
    return FakeHon(appliances)


@pytest.fixture
async def setup(
    hass: HomeAssistant, hon: FakeHon
) -> AsyncGenerator[MockConfigEntry, None]:
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="test@example.invalid",
        data={CONF_EMAIL: "test@example.invalid", CONF_PASSWORD: "x"},
    )
    entry.add_to_hass(hass)
    with patch("custom_components.hon.Hon", lambda **_: hon):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    yield entry
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


def entity_id(hass: HomeAssistant, platform: str, unique_id: str) -> str:
    """Entity of the base (zone 0) appliance with this unique-id suffix."""
    registry = er.async_get(hass)
    result = registry.async_get_entity_id(
        platform, DOMAIN, f"{APPLIANCE['macAddress']}{unique_id}"
    )
    assert result, unique_id
    return result
