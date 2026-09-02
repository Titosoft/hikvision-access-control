"""Config flow for Hikvision Access Control."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT, CONF_USERNAME
from homeassistant.core import callback

from .api import HikvisionAccessAPI, HikvisionApiError, HikvisionAuthError
from .const import (
    CONF_DEVICE_NAME,
    CONF_USE_HTTPS,
    CONF_VERIFY_SSL,
    DEFAULT_NAME,
    DEFAULT_PORT,
    DOMAIN,
)


class HikvisionAccessControlConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for a Hikvision access-control terminal."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        """Set up the integration from the UI."""
        errors: dict[str, str] = {}
        if user_input is not None:
            api = HikvisionAccessAPI(
                host=user_input[CONF_HOST],
                port=user_input[CONF_PORT],
                username=user_input[CONF_USERNAME],
                password=user_input[CONF_PASSWORD],
                use_https=user_input[CONF_USE_HTTPS],
                verify_ssl=user_input[CONF_VERIFY_SSL],
                configured_name=user_input[CONF_DEVICE_NAME],
            )
            try:
                await self.hass.async_add_executor_job(api.get_device_info)
            except HikvisionAuthError:
                errors["base"] = "invalid_auth"
            except HikvisionApiError:
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(api.unique_id)
                self._abort_if_unique_id_configured(updates={CONF_HOST: user_input[CONF_HOST]})
                return self.async_create_entry(title=user_input[CONF_DEVICE_NAME], data=user_input)

        return self.async_show_form(
            step_id="user",
            data_schema=self._schema(user_input or {}),
            errors=errors,
        )

    @staticmethod
    @callback
    def _schema(defaults: dict[str, Any]) -> vol.Schema:
        return vol.Schema(
            {
                vol.Required(CONF_DEVICE_NAME, default=defaults.get(CONF_DEVICE_NAME, "Portão Social")): str,
                vol.Required(CONF_HOST, default=defaults.get(CONF_HOST, "192.168.0.186")): str,
                vol.Required(CONF_PORT, default=defaults.get(CONF_PORT, DEFAULT_PORT)): int,
                vol.Required(CONF_USERNAME, default=defaults.get(CONF_USERNAME, "admin")): str,
                vol.Required(CONF_PASSWORD): str,
                vol.Required(CONF_USE_HTTPS, default=defaults.get(CONF_USE_HTTPS, True)): bool,
                vol.Required(CONF_VERIFY_SSL, default=defaults.get(CONF_VERIFY_SSL, False)): bool,
            }
        )

