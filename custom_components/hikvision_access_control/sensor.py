"""Sensors for Hikvision Access Control."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from . import HikvisionConfigEntry
from .const import EVENT_LABELS
from .entity import HikvisionAccessEntity

EVENT_OPTIONS = sorted(
    set(EVENT_LABELS.values()) | {"unknown_access_event", "unknown_isapi_event"}
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HikvisionConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Hikvision sensors."""
    api = entry.runtime_data.api
    async_add_entities(
        [
            HikvisionConnectionSensor(api),
            HikvisionLastAuthSensor(api, "last_user", "mdi:account"),
            HikvisionLastAuthSensor(api, "employee_id", "mdi:identifier"),
            HikvisionLastAuthSensor(api, "verify_mode", "mdi:face-recognition"),
            HikvisionResultSensor(api),
            HikvisionLastAccessTimeSensor(api),
            HikvisionLastEventSensor(api),
        ]
    )


class HikvisionConnectionSensor(HikvisionAccessEntity, SensorEntity):
    """Connection status sensor."""

    _attr_translation_key = "connection"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = ["offline", "online"]
    _attr_icon = "mdi:lan-connect"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, api) -> None:
        super().__init__(api, "connection")

    @property
    def available(self) -> bool:
        return True

    @property
    def native_value(self) -> str:
        return "online" if self.api.available else "offline"


class HikvisionLastAuthSensor(HikvisionAccessEntity, SensorEntity):
    """Expose a field from the latest authentication event."""

    def __init__(self, api, key: str, icon: str) -> None:
        super().__init__(api, key)
        self._key = key
        self._attr_translation_key = key
        self._attr_icon = icon

    @property
    def native_value(self) -> Any:
        if not self.api.last_auth:
            return None
        if self._key == "last_user":
            return self.api.last_auth.get("name") or self.api.last_auth.get(
                "employee_id"
            )
        return self.api.last_auth.get(self._key)


class HikvisionResultSensor(HikvisionAccessEntity, SensorEntity):
    """Expose the result of the latest confirmed authentication event."""

    _attr_translation_key = "last_result"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = ["authorized"]
    _attr_icon = "mdi:shield-account"

    def __init__(self, api) -> None:
        super().__init__(api, "last_result")

    @property
    def native_value(self) -> str | None:
        return self.api.last_result


class HikvisionLastAccessTimeSensor(HikvisionAccessEntity, SensorEntity):
    """Expose the device timestamp of the latest authentication event."""

    _attr_translation_key = "last_access_time"
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, api) -> None:
        super().__init__(api, "last_access_time")

    @property
    def native_value(self) -> datetime | None:
        value = self.api.last_auth.get("date_time") if self.api.last_auth else None
        if not value:
            return None
        try:
            parsed = datetime.fromisoformat(value)
        except (TypeError, ValueError):
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt_util.DEFAULT_TIME_ZONE)
        return parsed


class HikvisionLastEventSensor(HikvisionAccessEntity, SensorEntity):
    """Expose the latest access-control event and its metadata."""

    _attr_translation_key = "last_event"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = EVENT_OPTIONS
    _attr_icon = "mdi:door"

    def __init__(self, api) -> None:
        super().__init__(api, "last_event")

    @property
    def native_value(self) -> str | None:
        return self.api.last_event.get("event") if self.api.last_event else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return dict(self.api.last_event or {})
