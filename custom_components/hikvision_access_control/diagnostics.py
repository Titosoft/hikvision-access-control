"""Diagnostics for Hikvision Access Control."""

from __future__ import annotations

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from . import HikvisionConfigEntry

TO_REDACT = {"password", "username", "host"}
EVENT_TO_REDACT = {
    "cardNo",
    "callerId",
    "caller_id",
    "employeeNoString",
    "employee_id",
    "name",
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: HikvisionConfigEntry
) -> dict:
    """Return safe diagnostics without pictures or credentials."""
    api = entry.runtime_data.api
    return {
        "config": async_redact_data(dict(entry.data), TO_REDACT),
        "device": {
            "model": api.model,
            "firmware": api.firmware_version,
            "available": api.available,
            "call_status_poll_available": api.call_status_poll_available,
            "call_status_poll_error": api.call_status_poll_error,
            "call_status_poll_interval": api.call_status_poll_interval,
            "call_status": api.call_status,
            "doorbell_ringing": api.doorbell_ringing,
        },
        "last_event": async_redact_data(dict(api.last_event or {}), EVENT_TO_REDACT),
    }
