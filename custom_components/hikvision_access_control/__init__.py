"""Hikvision Access Control integration."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import cast

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.const import (
    CONF_HOST,
    CONF_PASSWORD,
    CONF_PORT,
    CONF_USERNAME,
    Platform,
)
from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
)
from homeassistant.exceptions import (
    ConfigEntryAuthFailed,
    ConfigEntryNotReady,
    HomeAssistantError,
    ServiceValidationError,
)
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType
from homeassistant.util import dt as dt_util

from .api import HikvisionAccessAPI, HikvisionApiError, HikvisionAuthError
from .const import (
    CONF_CALL_STATUS_POLL_INTERVAL,
    CONF_DEVICE_NAME,
    CONF_USE_HTTPS,
    CONF_VERIFY_SSL,
    DEFAULT_CALL_STATUS_POLL_INTERVAL,
    DOMAIN,
)
from .observability import SIP_CALL_STAGES

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.CAMERA,
    Platform.EVENT,
    Platform.SENSOR,
]


@dataclass(slots=True)
class HikvisionRuntimeData:
    """Runtime data stored on the config entry."""

    api: HikvisionAccessAPI


type HikvisionConfigEntry = ConfigEntry[HikvisionRuntimeData]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register actions for loaded terminals."""

    def get_api(call: ServiceCall) -> HikvisionAccessAPI:
        entry = hass.config_entries.async_get_entry(call.data["config_entry_id"])
        if (
            entry is None
            or entry.domain != DOMAIN
            or entry.state is not ConfigEntryState.LOADED
        ):
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="entry_not_loaded"
            )
        return cast(HikvisionConfigEntry, entry).runtime_data.api

    async def get_access_history(call: ServiceCall) -> ServiceResponse:
        api = get_api(call)
        start = dt_util.as_utc(call.data["start_time"])
        end = dt_util.as_utc(call.data["end_time"])
        if end <= start:
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="invalid_history_range"
            )
        try:
            return await hass.async_add_executor_job(
                api.get_access_history, start, end, call.data["limit"]
            )
        except HikvisionApiError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="history_failed"
            ) from err

    async def report_sip_call(call: ServiceCall) -> None:
        get_api(call).report_sip_call(call.data["call_id"], call.data["stage"])

    hass.services.async_register(
        DOMAIN,
        "get_access_history",
        get_access_history,
        schema=vol.Schema(
            {
                vol.Required("config_entry_id"): cv.string,
                vol.Required("start_time"): cv.datetime,
                vol.Required("end_time"): cv.datetime,
                vol.Optional("limit", default=30): vol.All(
                    vol.Coerce(int), vol.Range(min=1, max=100)
                ),
            }
        ),
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN,
        "report_sip_call",
        report_sip_call,
        schema=vol.Schema(
            {
                vol.Required("config_entry_id"): cv.string,
                vol.Required("call_id"): vol.All(
                    cv.string, str.strip, vol.Length(min=1, max=512)
                ),
                vol.Required("stage"): vol.In(SIP_CALL_STAGES),
            }
        ),
    )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: HikvisionConfigEntry) -> bool:
    """Set up Hikvision Access Control from a config entry."""
    data = entry.data
    api = HikvisionAccessAPI(
        host=data[CONF_HOST],
        port=data[CONF_PORT],
        username=data[CONF_USERNAME],
        password=data[CONF_PASSWORD],
        use_https=data[CONF_USE_HTTPS],
        verify_ssl=data[CONF_VERIFY_SSL],
        configured_name=data[CONF_DEVICE_NAME],
        call_status_poll_interval=data.get(
            CONF_CALL_STATUS_POLL_INTERVAL,
            entry.options.get(
                CONF_CALL_STATUS_POLL_INTERVAL,
                DEFAULT_CALL_STATUS_POLL_INTERVAL,
            ),
        ),
    )
    try:
        await hass.async_add_executor_job(api.get_device_info)
    except HikvisionAuthError as err:
        raise ConfigEntryAuthFailed(str(err)) from err
    except HikvisionApiError as err:
        raise ConfigEntryNotReady(str(err)) from err

    entry.runtime_data = HikvisionRuntimeData(api)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    api.start(hass.loop)
    _LOGGER.info("Hikvision Access Control setup completed for %s", api.device_name)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: HikvisionConfigEntry) -> bool:
    """Unload a config entry."""
    try:
        unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    finally:
        await hass.async_add_executor_job(entry.runtime_data.api.stop)
    if unloaded:
        _LOGGER.info(
            "Hikvision Access Control unloaded for %s",
            entry.runtime_data.api.device_name,
        )
    return unloaded
