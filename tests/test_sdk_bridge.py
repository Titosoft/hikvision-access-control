"""Tests for the isolated HCNetSDK bridge callback decoder."""

from __future__ import annotations

import base64
import ctypes
import json
import sys
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

MODULE_PATH = Path(__file__).parents[1] / "hikvision_sdk_bridge" / "bridge.py"
APP_PATH = MODULE_PATH.parent
SPEC = spec_from_file_location("hikvision_sdk_bridge_test", MODULE_PATH)
assert SPEC and SPEC.loader
BRIDGE = module_from_spec(SPEC)
sys.modules[SPEC.name] = BRIDGE
SPEC.loader.exec_module(BRIDGE)


def test_app_packages_native_sdk_for_each_supported_architecture() -> None:
    expected_machine = {"amd64": b"\x3e\x00", "aarch64": b"\xb7\x00"}

    for architecture, machine in expected_machine.items():
        library = APP_PATH / f"lib-{architecture}" / "libhcnetsdk.so"
        header = library.read_bytes()[:20]
        assert header[:4] == b"\x7fELF"
        assert header[18:20] == machine
        assert (library.parent / "HCNetSDKCom").is_dir()


def test_app_uses_prebuilt_image_without_share_library_option() -> None:
    config = (APP_PATH / "config.yaml").read_text()
    dockerfile = (APP_PATH / "Dockerfile").read_text()
    run_script = (APP_PATH / "run.sh").read_text()

    assert "image: ghcr.io/titosoft/hikvision-sdk-bridge" in config
    assert "/share/hikvision_sdk" not in config
    assert "share:ro" not in config
    assert "COPY lib-${BUILD_ARCH}/" in dockerfile
    assert "/opt/hikvision_sdk_bridge/lib/libhcnetsdk.so" in run_script
    assert ".sdk_library" not in run_script


class CapturingPublisher:
    """Capture events without contacting Home Assistant."""

    def __init__(self) -> None:
        self.events: list[dict] = []

    def publish(self, event: dict) -> None:
        self.events.append(event)


def _client() -> tuple[object, CapturingPublisher]:
    publisher = CapturingPublisher()
    client = object.__new__(BRIDGE.HikvisionSdkClient)
    client._publisher = publisher
    return client, publisher


def _isapi_alarm(raw: bytes):
    buffer = ctypes.create_string_buffer(raw)
    info = BRIDGE.NetDvrAlarmIsapiInfo()
    info.alarm_data = ctypes.addressof(buffer)
    info.alarm_data_length = len(raw)
    info.data_type = 2
    return buffer, info


def test_button_callback_is_forwarded_without_binary_payload() -> None:
    client, publisher = _client()

    client._handle_alarm(
        BRIDGE.COMM_ALARM_BUTTON_DOWN_EXCEPTION,
        0,
        0,
        0,
        0,
    )

    assert len(publisher.events) == 1
    assert publisher.events[0]["command"] == 0x1152
    assert publisher.events[0]["command_hex"] == "0x1152"
    assert "payload_b64" not in publisher.events[0]


def test_call_status_isapi_payload_is_copied_before_callback_returns() -> None:
    client, publisher = _client()
    payload = json.dumps(
        {
            "eventType": "changedCallStatus",
            "ChangedCallStatus": {"CallStatus": {"status": "ring"}},
        }
    ).encode()
    buffer, info = _isapi_alarm(payload)

    client._handle_alarm(
        BRIDGE.COMM_ISAPI_ALARM,
        0,
        ctypes.addressof(info),
        ctypes.sizeof(info),
        0,
    )

    assert buffer.raw
    assert len(publisher.events) == 1
    event = publisher.events[0]
    assert event["payload_type"] == "json"
    assert base64.b64decode(event["payload_b64"]) == payload


def test_unrelated_isapi_payload_is_not_forwarded() -> None:
    client, publisher = _client()
    payload = b'{"eventType":"AccessControllerEvent"}'
    _buffer, info = _isapi_alarm(payload)

    client._handle_alarm(
        BRIDGE.COMM_ISAPI_ALARM,
        0,
        ctypes.addressof(info),
        ctypes.sizeof(info),
        0,
    )

    assert publisher.events == []


def test_direct_vca_call_payload_is_forwarded() -> None:
    client, publisher = _client()
    payload = b'{"eventType":"changedCallStatus"}'
    buffer = ctypes.create_string_buffer(payload)

    client._handle_alarm(
        BRIDGE.COMM_VCA_ALARM,
        0,
        ctypes.addressof(buffer),
        len(payload),
        0,
    )

    assert len(publisher.events) == 1
    assert base64.b64decode(publisher.events[0]["payload_b64"]) == payload


def test_multipart_vca_call_payload_is_extracted() -> None:
    client, publisher = _client()
    document = {"eventType": "changedCallStatus"}
    payload = (
        b"--boundary\r\nContent-Type: application/json\r\n\r\n"
        + json.dumps(document).encode()
        + b"\r\n--boundary\r\nContent-Type: image/jpeg\r\n\r\n\xff\xd8"
    )
    buffer = ctypes.create_string_buffer(payload)

    client._handle_alarm(
        BRIDGE.COMM_VCA_ALARM,
        0,
        ctypes.addressof(buffer),
        len(payload),
        0,
    )

    decoded = base64.b64decode(publisher.events[0]["payload_b64"])
    assert json.loads(decoded) == document


def test_acs_doorbell_event_is_forwarded() -> None:
    client, publisher = _client()
    info = BRIDGE.NetDvrAcsAlarmPrefix()
    info.size = ctypes.sizeof(info)
    info.major = 5
    info.minor = 0x25

    acknowledged = client._handle_alarm(
        BRIDGE.COMM_ALARM_ACS,
        0,
        ctypes.addressof(info),
        ctypes.sizeof(info),
        0,
    )

    assert acknowledged == 1
    assert publisher.events[0]["major"] == 5
    assert publisher.events[0]["minor"] == 37


def test_unrelated_acs_event_is_acknowledged_but_not_forwarded() -> None:
    client, publisher = _client()
    info = BRIDGE.NetDvrAcsAlarmPrefix()
    info.size = ctypes.sizeof(info)
    info.major = 5
    info.minor = 75

    acknowledged = client._handle_alarm(
        BRIDGE.COMM_ALARM_ACS,
        0,
        ctypes.addressof(info),
        ctypes.sizeof(info),
        0,
    )

    assert acknowledged == 1
    assert publisher.events == []


def test_unknown_sdk_command_is_ignored() -> None:
    client, publisher = _client()

    acknowledged = client._handle_alarm(0x7777, 0, 0, 0, 0)

    assert acknowledged == 1
    assert publisher.events == []


def test_sdk_disconnect_and_reconnect_exceptions_update_status() -> None:
    client, publisher = _client()

    client._handle_exception(0x8002, 42, 7, 0)
    client._handle_exception(0x8016, 42, 7, 0)

    assert [event["status"] for event in publisher.events] == ["offline", "online"]
    assert client.connected is True
    assert publisher.events[0]["exception_name"] == "alarm_callback_disconnected"
    assert publisher.events[1]["exception_name"] == "alarm_channel_reconnected"


def test_unknown_sdk_exception_is_ignored() -> None:
    client, publisher = _client()

    client._handle_exception(0xDEAD, 42, 7, 0)

    assert publisher.events == []
