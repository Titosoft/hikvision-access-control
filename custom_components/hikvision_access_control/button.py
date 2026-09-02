"""Door controls for Hikvision Access Control."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import HikvisionConfigEntry
from .entity import HikvisionAccessEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HikvisionConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the open-door button."""
    async_add_entities([HikvisionOpenDoorButton(entry.runtime_data.api)])


class HikvisionOpenDoorButton(HikvisionAccessEntity, ButtonEntity):
    """Pulse door 1 through ISAPI."""

    _attr_translation_key = "open_door"
    _attr_icon = "mdi:door-open"

    def __init__(self, api) -> None:
        super().__init__(api, "open_door")

    async def async_press(self) -> None:
        await self.hass.async_add_executor_job(self.api.open_door, 1)
