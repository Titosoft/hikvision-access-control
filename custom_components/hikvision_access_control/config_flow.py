"""Config flow for Hikvision Access Control."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult
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

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Set up the integration from the UI."""
        errors: dict[str, str] = {}
        if user_input is not None:
            data = self._normalize(user_input)
            api, error = await self._async_validate(data)
            if error:
                errors["base"] = error
            else:
                assert api is not None
                await self.async_set_unique_id(api.unique_id)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title=data[CONF_DEVICE_NAME], data=data)

        return self.async_show_form(
            step_id="user",
            data_schema=self._schema(user_input or {}),
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Allow all connection settings to be changed from the UI."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            updates = dict(user_input)
            if not updates.get(CONF_PASSWORD):
                updates.pop(CONF_PASSWORD, None)
            data = self._normalize({**entry.data, **updates})
            api, error = await self._async_validate(data)
            if error:
                errors["base"] = error
            else:
                assert api is not None
                await self.async_set_unique_id(api.unique_id)
                self._abort_if_unique_id_mismatch()
                return self.async_update_reload_and_abort(
                    entry,
                    data_updates=data,
                    title=data[CONF_DEVICE_NAME],
                )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self._schema(
                user_input or dict(entry.data), require_password=False
            ),
            errors=errors,
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Start reauthentication after the terminal rejects credentials."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Validate and store replacement credentials."""
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            data = self._normalize({**entry.data, **user_input})
            api, error = await self._async_validate(data)
            if error:
                errors["base"] = error
            else:
                assert api is not None
                await self.async_set_unique_id(api.unique_id)
                self._abort_if_unique_id_mismatch()
                return self.async_update_reload_and_abort(
                    entry,
                    data_updates={
                        CONF_USERNAME: data[CONF_USERNAME],
                        CONF_PASSWORD: data[CONF_PASSWORD],
                    },
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_USERNAME,
                        default=(user_input or entry.data).get(CONF_USERNAME, "admin"),
                    ): str,
                    vol.Required(CONF_PASSWORD): str,
                }
            ),
            errors=errors,
        )

    async def _async_validate(
        self, data: dict[str, Any]
    ) -> tuple[HikvisionAccessAPI | None, str | None]:
        api = HikvisionAccessAPI(
            host=data[CONF_HOST],
            port=data[CONF_PORT],
            username=data[CONF_USERNAME],
            password=data[CONF_PASSWORD],
            use_https=data[CONF_USE_HTTPS],
            verify_ssl=data[CONF_VERIFY_SSL],
            configured_name=data[CONF_DEVICE_NAME],
        )
        try:
            await self.hass.async_add_executor_job(api.get_device_info)
        except HikvisionAuthError:
            return None, "invalid_auth"
        except HikvisionApiError:
            return None, "cannot_connect"
        return api, None

    @staticmethod
    def _normalize(data: Mapping[str, Any]) -> dict[str, Any]:
        normalized = dict(data)
        normalized[CONF_HOST] = str(normalized[CONF_HOST]).strip()
        normalized[CONF_USERNAME] = str(normalized[CONF_USERNAME]).strip()
        normalized[CONF_DEVICE_NAME] = (
            str(normalized[CONF_DEVICE_NAME]).strip() or DEFAULT_NAME
        )
        return normalized

    @staticmethod
    @callback
    def _schema(
        defaults: Mapping[str, Any], *, require_password: bool = True
    ) -> vol.Schema:
        password = (
            vol.Required(CONF_PASSWORD)
            if require_password
            else vol.Optional(CONF_PASSWORD)
        )
        return vol.Schema(
            {
                vol.Required(
                    CONF_DEVICE_NAME,
                    default=defaults.get(CONF_DEVICE_NAME, DEFAULT_NAME),
                ): str,
                vol.Required(
                    CONF_HOST, default=defaults.get(CONF_HOST, "192.168.1.100")
                ): str,
                vol.Required(
                    CONF_PORT, default=defaults.get(CONF_PORT, DEFAULT_PORT)
                ): vol.All(vol.Coerce(int), vol.Range(min=1, max=65535)),
                vol.Required(
                    CONF_USERNAME, default=defaults.get(CONF_USERNAME, "admin")
                ): str,
                password: str,
                vol.Required(
                    CONF_USE_HTTPS, default=defaults.get(CONF_USE_HTTPS, True)
                ): bool,
                vol.Required(
                    CONF_VERIFY_SSL, default=defaults.get(CONF_VERIFY_SSL, False)
                ): bool,
            }
        )
