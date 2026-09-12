"""Event entity for Hikvision Access Control."""

from __future__ import annotations

from typing import Any

from homeassistant.components.event import EventEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import HikvisionConfigEntry
from .const import EVENT_LABELS
from .entity import HikvisionAccessEntity, async_get_unknown_event_labels
from .event_display import event_display_type

EVENT_TYPES = sorted(
    set(EVENT_LABELS.values())
    | {"unknown_access_event", "unknown_isapi_event", "unknown_sdk_event"}
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HikvisionConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up access event entity."""
    labels = await async_get_unknown_event_labels(hass)
    async_add_entities([HikvisionAccessEvent(entry.runtime_data.api, labels)])


class HikvisionAccessEvent(HikvisionAccessEntity, EventEntity):
    """Fire a Home Assistant event entity for each unique ISAPI event."""

    _attr_icon = "mdi:badge-account-horizontal"
    _attr_event_types = EVENT_TYPES

    def __init__(self, api, unknown_event_labels: dict[str, str]) -> None:
        super().__init__(api, "access_event")
        self._unknown_event_labels = unknown_event_labels
        self._attr_event_types = list(EVENT_TYPES)
        self._last_event: dict[str, Any] | None = None
        self._attr_translation_key = "access_event"

    @property
    def available(self) -> bool:
        return self.api.available or self.api.sdk_connected is True

    def _handle_api_update(self) -> None:
        event = self.api.last_event
        if not event:
            self.async_write_ha_state()
            return
        if event is self._last_event:
            self.async_write_ha_state()
            return
        self._last_event = event
        event_code = event.get("event", "unknown_access_event")
        event_type = event_display_type(event, self._unknown_event_labels)
        # Declare the displayed type before firing it, without accumulating
        # arbitrary device-supplied names or modifying another terminal's list.
        self._attr_event_types = list(EVENT_TYPES)
        if event_type not in self._attr_event_types:
            self._attr_event_types = [*EVENT_TYPES, event_type]
        attributes = {
            key: value
            for key, value in event.items()
            if key != "event" and value is not None
        }
        attributes["event_code"] = event_code
        self._trigger_event(event_type, attributes)
        self.async_write_ha_state()
