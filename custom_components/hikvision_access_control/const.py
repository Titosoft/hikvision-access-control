"""Constants for Hikvision Access Control."""

from __future__ import annotations

DOMAIN = "hikvision_access_control"
SDK_EVENT_TYPE = f"{DOMAIN}_sdk_event"

SDK_COMMAND_BUTTON_DOWN = 0x1152
SDK_COMMAND_VIDEO_INTERCOM_EVENT = 0x1132
SDK_COMMAND_VIDEO_INTERCOM_ALARM = 0x1133
SDK_COMMAND_CONFERENCE_CALL = 0x5012
SDK_COMMAND_ACS_ALARM = 0x5002
SDK_COMMAND_VCA_ALARM = 0x4993
SDK_COMMAND_ISAPI_ALARM = 0x6009

CONF_USE_HTTPS = "use_https"
CONF_VERIFY_SSL = "verify_ssl"
CONF_DEVICE_NAME = "device_name"

DEFAULT_NAME = "Hikvision Access Control"
DEFAULT_PORT = 443

PLATFORMS = ["binary_sensor", "button", "camera", "event", "sensor"]

EVENT_LABELS: dict[tuple[int, int], str] = {
    (1, 0x404): "device_tamper_alarm",
    (1, 0x405): "device_tamper_restored",
    (1, 0x406): "card_reader_tamper_alarm",
    (1, 0x407): "card_reader_tamper_restored",
    (1, 0x40A): "duress_alarm",
    (1, 0x40C): "authentication_attempts_exceeded",
    (1, 0x40F): "security_module_tamper_alarm",
    (1, 0x410): "security_module_tamper_restored",
    (2, 0x27): "network_disconnected",
    (2, 0x407): "network_restored",
    (2, 0x410): "security_module_online",
    (3, 0x70): "remote_login",
    (5, 1): "card_authenticated",
    (5, 2): "card_pin_authenticated",
    (5, 3): "authentication_failed",
    (5, 4): "authentication_timeout",
    (5, 5): "authentication_attempts_exceeded",
    (5, 6): "access_denied",
    (5, 7): "access_denied",
    (5, 8): "access_denied",
    (5, 9): "authentication_failed",
    (5, 10): "anti_passback_denied",
    (5, 11): "access_denied",
    (5, 12): "access_denied",
    (5, 13): "access_denied",
    (5, 14): "access_denied",
    (5, 15): "access_denied",
    (5, 16): "multi_factor_authenticated",
    (5, 21): "door_unlocked",
    (5, 22): "door_locked",
    (5, 23): "exit_button_pressed",
    (5, 24): "exit_button_released",
    (5, 25): "door_opened",
    (5, 26): "door_closed",
    (5, 27): "door_forced_open",
    (5, 28): "door_open_too_long",
    (5, 37): "doorbell_ringing",
    (5, 38): "fingerprint_authenticated",
    (5, 39): "authentication_failed",
    (5, 41): "authentication_failed",
    (5, 42): "authentication_timeout",
    (5, 44): "authentication_failed",
    (5, 45): "authentication_timeout",
    (5, 47): "authentication_failed",
    (5, 48): "authentication_timeout",
    (5, 51): "doorbell_ringing",
    (5, 54): "face_fingerprint_authenticated",
    (5, 55): "authentication_failed",
    (5, 56): "authentication_timeout",
    (5, 57): "face_pin_authenticated",
    (5, 58): "authentication_failed",
    (5, 59): "authentication_timeout",
    (5, 60): "face_card_authenticated",
    (5, 61): "authentication_failed",
    (5, 62): "authentication_timeout",
    (5, 64): "authentication_failed",
    (5, 65): "authentication_timeout",
    (5, 67): "authentication_failed",
    (5, 68): "authentication_timeout",
    (5, 70): "authentication_failed",
    (5, 71): "authentication_timeout",
    (5, 73): "authentication_failed",
    (5, 74): "authentication_timeout",
    (5, 75): "face_authenticated",
    (5, 76): "authentication_failed",
    (5, 78): "authentication_failed",
    (5, 79): "authentication_timeout",
    (5, 80): "authentication_failed",
    (5, 83): "door_lock_input_alarm",
    (5, 84): "door_lock_input_alarm",
    (5, 85): "door_lock_input_alarm",
    (5, 86): "door_contact_input_alarm",
    (5, 87): "door_contact_input_alarm",
    (5, 88): "door_contact_input_alarm",
    (5, 89): "exit_button_input_alarm",
    (5, 90): "exit_button_input_alarm",
    (5, 91): "exit_button_input_alarm",
    (5, 92): "door_lock_abnormal",
    (5, 93): "door_lock_open_too_long",
    (5, 101): "pin_authenticated",
    (5, 102): "authentication_failed",
    (5, 103): "authentication_timeout",
    (5, 153): "combined_authenticated",
}

DOORBELL_EVENTS = {(5, 37), (5, 51)}

AUTH_SUCCESS_EVENTS = {
    event_code
    for event_code, event_name in EVENT_LABELS.items()
    if event_name.endswith("_authenticated")
}
