"""Binary sensors for Hikvision Access Control."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import HikvisionConfigEntry
from .entity import HikvisionAccessEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HikvisionConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up relay status."""
    api = entry.runtime_data.api
    async_add_entities([HikvisionRelaySensor(api), HikvisionDoorbellSensor(api)])


class HikvisionRelaySensor(HikvisionAccessEntity, BinarySensorEntity):
    """Represent the lock relay pulse, not a physical door contact."""

    _attr_translation_key = "relay_unlocked"

    def __init__(self, api) -> None:
        super().__init__(api, "relay_unlocked")

    @property
    def is_on(self) -> bool | None:
        return self.api.relay_unlocked

    @property
    def icon(self) -> str:
        return "mdi:lock-open-variant" if self.is_on else "mdi:lock"


class HikvisionDoorbellSensor(HikvisionAccessEntity, BinarySensorEntity):
    """Represent the live doorbell ringing state."""

    _attr_translation_key = "doorbell_ringing"

    def __init__(self, api) -> None:
        super().__init__(api, "doorbell_ringing")

    @property
    def available(self) -> bool:
        return self.api.call_status_poll_available is not False

    @property
    def is_on(self) -> bool:
        return self.api.doorbell_ringing

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        return {
            "call_status": self.api.call_status,
            "poll_interval_seconds": self.api.call_status_poll_interval,
            "polling_available": self.api.call_status_poll_available,
            "polling_error": self.api.call_status_poll_error,
        }

    @property
    def icon(self) -> str:
        return "mdi:bell-ring" if self.is_on else "mdi:bell-outline"
