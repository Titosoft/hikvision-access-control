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
    (5, 1): "card_authenticated",
    (5, 2): "card_pin_authenticated",
    (5, 16): "multi_factor_authenticated",
    (5, 21): "door_unlocked",
    (5, 22): "door_locked",
    (5, 37): "doorbell_ringing",
    (5, 38): "fingerprint_authenticated",
    (5, 54): "face_fingerprint_authenticated",
    (5, 57): "face_pin_authenticated",
    (5, 60): "face_card_authenticated",
    (5, 75): "face_authenticated",
    (5, 101): "pin_authenticated",
    (5, 153): "combined_authenticated",
}

AUTH_SUCCESS_EVENTS = {
    event_code
    for event_code, event_name in EVENT_LABELS.items()
    if event_name.endswith("_authenticated")
}
