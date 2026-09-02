"""Entity base for Hikvision Access Control."""

from __future__ import annotations

from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.entity import Entity

from .api import HikvisionAccessAPI
from .const import DOMAIN


class HikvisionAccessEntity(Entity):
    """Base entity linked to one Hikvision terminal."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, api: HikvisionAccessAPI, key: str) -> None:
        self.api = api
        self._attr_unique_id = f"{api.unique_id}_{key}"
        self._attr_device_info = dr.DeviceInfo(
            identifiers={(DOMAIN, api.unique_id)},
            name=api.device_name,
            manufacturer="Hikvision",
            model=api.model,
            serial_number=api.serial_number,
            sw_version=api.firmware_version,
            connections={
                (dr.CONNECTION_NETWORK_MAC, dr.format_mac(api.mac_address))
            }
            if api.mac_address
            else set(),
        )
        self._remove_listener = None

    @property
    def available(self) -> bool:
        """Return stream availability."""
        return self.api.available

    async def async_added_to_hass(self) -> None:
        """Register for API updates."""
        await super().async_added_to_hass()
        self._remove_listener = self.api.add_listener(self._handle_api_update)

    async def async_will_remove_from_hass(self) -> None:
        """Remove API listener."""
        if self._remove_listener:
            self._remove_listener()
            self._remove_listener = None
        await super().async_will_remove_from_hass()

    def _handle_api_update(self) -> None:
        self.async_write_ha_state()
