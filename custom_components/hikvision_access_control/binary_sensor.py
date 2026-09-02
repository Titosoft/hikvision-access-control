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
    async_add_entities([HikvisionRelaySensor(entry.runtime_data.api)])


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
