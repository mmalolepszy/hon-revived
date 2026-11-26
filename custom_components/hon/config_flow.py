import logging
from typing import TYPE_CHECKING, Any

from homeassistant import config_entries
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD

from .const import CONF_INTEGRATION, DOMAIN, INTEGRATION

if TYPE_CHECKING:
    # HA >= 2026.9 replaces voluptuous with probatio at runtime
    import probatio as vol

    # HA >= 2024.4
    from homeassistant.config_entries import ConfigFlowResult
else:
    import voluptuous as vol

_LOGGER = logging.getLogger(__name__)


class HonFlowHandler(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._email: str | None = None
        self._password: str | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> "ConfigFlowResult":
        if user_input is None:
            return self.async_show_form(
                step_id="user",
                data_schema=vol.Schema(
                    {vol.Required(CONF_EMAIL): str, vol.Required(CONF_PASSWORD): str}
                ),
            )

        self._email = user_input[CONF_EMAIL]
        self._password = user_input[CONF_PASSWORD]

        if self._email is None or self._password is None:
            return self.async_show_form(
                step_id="user",
                data_schema=vol.Schema(
                    {vol.Required(CONF_EMAIL): str, vol.Required(CONF_PASSWORD): str}
                ),
            )

        # Check if already configured
        await self.async_set_unique_id(self._email)
        self._abort_if_unique_id_configured()

        return self.async_create_entry(
            title=self._email,
            data={
                CONF_EMAIL: self._email,
                CONF_PASSWORD: self._password,
                CONF_INTEGRATION: INTEGRATION,
            },
        )

    async def async_step_import(self, user_input: dict[str, str]) -> "ConfigFlowResult":
        return await self.async_step_user(user_input)
