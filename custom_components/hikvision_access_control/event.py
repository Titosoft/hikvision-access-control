"""Event entity for Hikvision Access Control."""

from __future__ import annotations

from typing import Any

from homeassistant.components.event import EventEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import HikvisionConfigEntry
from .const import EVENT_LABELS
from .entity import HikvisionAccessEntity

EVENT_TYPES = sorted(
    set(EVENT_LABELS.values()) | {"unknown_access_event", "unknown_isapi_event"}
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HikvisionConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up access event entity."""
    async_add_entities([HikvisionAccessEvent(entry.runtime_data.api)])


class HikvisionAccessEvent(HikvisionAccessEntity, EventEntity):
    """Fire a Home Assistant event entity for each unique ISAPI event."""

    _attr_icon = "mdi:badge-account-horizontal"
    _attr_event_types = EVENT_TYPES

    def __init__(self, api) -> None:
        super().__init__(api, "access_event")
        self._last_event: dict[str, Any] | None = None
        self._attr_translation_key = "access_event"

    def _handle_api_update(self) -> None:
        event = self.api.last_event
        if not event:
            self.async_write_ha_state()
            return
        if event is self._last_event:
            self.async_write_ha_state()
            return
        self._last_event = event
        event_type = event.get("event", "unknown_access_event")
        if event_type not in EVENT_TYPES:
            event_type = "unknown_access_event"
        attributes = {
            key: value
            for key, value in event.items()
            if key != "event" and value is not None
        }
        self._trigger_event(event_type, attributes)
        self.async_write_ha_state()
