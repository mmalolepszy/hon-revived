import logging
import re
from typing import Any

import voluptuous as vol  # type: ignore[import-untyped]
from homeassistant import config_entries
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.data_entry_flow import FlowResult

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class HonFlowHandler(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_LOCAL_POLL

    def __init__(self) -> None:
        self._email: str | None = None
        self._password: str | None = None

    def _show_form(self, errors: dict[str, str] | None = None) -> FlowResult:
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {vol.Required(CONF_EMAIL): str, vol.Required(CONF_PASSWORD): str}
            ),
            errors=errors or {},
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        if user_input is None:
            return self._show_form()

        self._email = user_input[CONF_EMAIL]
        self._password = user_input[CONF_PASSWORD]

        if not EMAIL_RE.match(self._email or ""):
            return self._show_form({CONF_EMAIL: "invalid_email"})
        if not self._password:
            return self._show_form({CONF_PASSWORD: "invalid_password"})

        # Check if already configured
        await self.async_set_unique_id(self._email)
        self._abort_if_unique_id_configured()

        # Validate credentials against the hOn API before creating the entry
        from homeassistant.helpers import aiohttp_client
        from pyhon import Hon

        session = aiohttp_client.async_get_clientsession(self.hass)
        try:
            hon = await Hon(
                email=self._email,
                password=self._password,
                session=session,
            ).create()
            await hon.close()
        except Exception as exc:  # noqa: BLE001
            _LOGGER.warning("hOn login failed: %s", exc)
            return self._show_form({"base": "invalid_auth"})

        return self.async_create_entry(
            title=self._email,
            data={
                CONF_EMAIL: self._email,
                CONF_PASSWORD: self._password,
            },
        )

    async def async_step_import(self, user_input: dict[str, str]) -> FlowResult:
        return await self.async_step_user(user_input)
