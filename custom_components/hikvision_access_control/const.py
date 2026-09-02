"""Constants for Hikvision Access Control."""

from __future__ import annotations

DOMAIN = "hikvision_access_control"

CONF_USE_HTTPS = "use_https"
CONF_VERIFY_SSL = "verify_ssl"
CONF_DEVICE_NAME = "device_name"

DEFAULT_NAME = "Hikvision Access Control"
DEFAULT_PORT = 443

PLATFORMS = ["binary_sensor", "button", "camera", "event", "sensor"]

EVENT_LABELS: dict[tuple[int, int], str] = {
    (5, 21): "door_unlocked",
    (5, 22): "door_locked",
    (5, 75): "face_authenticated",
}

AUTH_SUCCESS_EVENTS = {(5, 75)}
