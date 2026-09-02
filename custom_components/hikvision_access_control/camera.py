"""Latest access picture for Hikvision Access Control."""

from __future__ import annotations

from homeassistant.components.camera import Camera
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import HikvisionConfigEntry
from .entity import HikvisionAccessEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HikvisionConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up latest-picture camera."""
    async_add_entities([HikvisionLastAccessCamera(entry.runtime_data.api)])


class HikvisionLastAccessCamera(HikvisionAccessEntity, Camera):
    """Expose the JPEG attached to the latest access event."""

    _attr_translation_key = "last_access_picture"
    _attr_icon = "mdi:camera-account"

    def __init__(self, api) -> None:
        HikvisionAccessEntity.__init__(self, api, "last_access_picture")
        Camera.__init__(self)

    async def async_camera_image(
        self, width: int | None = None, height: int | None = None
    ) -> bytes | None:
        """Return the latest JPEG received from the event stream."""
        return self.api.latest_picture
