"""Hikvision Access Control integration."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_HOST,
    CONF_PASSWORD,
    CONF_PORT,
    CONF_USERNAME,
    Platform,
)
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady

from .api import HikvisionAccessAPI, HikvisionApiError, HikvisionAuthError
from .const import (
    CONF_DEVICE_NAME,
    CONF_USE_HTTPS,
    CONF_VERIFY_SSL,
    SDK_EVENT_TYPE,
)

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
    remove_sdk_listener: Callable[[], None] | None = None


type HikvisionConfigEntry = ConfigEntry[HikvisionRuntimeData]


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
    )
    try:
        await hass.async_add_executor_job(api.get_device_info)
    except HikvisionAuthError as err:
        raise ConfigEntryAuthFailed(str(err)) from err
    except HikvisionApiError as err:
        raise ConfigEntryNotReady(str(err)) from err

    @callback
    def handle_sdk_event(event: Event) -> None:
        event_host = str(event.data.get("device_host") or "").strip()
        if event_host != api.host:
            return
        api.handle_sdk_event(dict(event.data))

    entry.runtime_data = HikvisionRuntimeData(api)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.runtime_data.remove_sdk_listener = hass.bus.async_listen(
        SDK_EVENT_TYPE, handle_sdk_event
    )
    api.start(hass.loop)
    _LOGGER.info("Hikvision Access Control setup completed for %s", api.device_name)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: HikvisionConfigEntry) -> bool:
    """Unload a config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        if entry.runtime_data.remove_sdk_listener is not None:
            entry.runtime_data.remove_sdk_listener()
            entry.runtime_data.remove_sdk_listener = None
        await hass.async_add_executor_job(entry.runtime_data.api.stop)
        _LOGGER.info(
            "Hikvision Access Control unloaded for %s",
            entry.runtime_data.api.device_name,
        )
    return unloaded
