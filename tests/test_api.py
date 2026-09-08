"""Tests for the local ISAPI client without importing Home Assistant."""

from __future__ import annotations

import asyncio
import sys
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
import requests
from requests.auth import HTTPDigestAuth

COMPONENT_PATH = (
    Path(__file__).parents[1] / "custom_components" / "hikvision_access_control"
)
PACKAGE_NAME = "hikvision_access_control_test"
PACKAGE = ModuleType(PACKAGE_NAME)
PACKAGE.__path__ = [str(COMPONENT_PATH)]
sys.modules.setdefault(PACKAGE_NAME, PACKAGE)


def _load_module(name: str) -> ModuleType:
    qualified_name = f"{PACKAGE_NAME}.{name}"
    module = sys.modules.get(qualified_name)
    if module is not None:
        return module
    spec = spec_from_file_location(qualified_name, COMPONENT_PATH / f"{name}.py")
    assert spec and spec.loader
    module = module_from_spec(spec)
    sys.modules[qualified_name] = module
    spec.loader.exec_module(module)
    return module


_load_module("const")
_load_module("parser")
API_MODULE = _load_module("api")
HikvisionAccessAPI = API_MODULE.HikvisionAccessAPI
HikvisionApiError = API_MODULE.HikvisionApiError
HikvisionAuthError = API_MODULE.HikvisionAuthError


class FakeResponse:
    """Small requests.Response substitute for deterministic stream tests."""

    def __init__(
        self,
        *,
        status_code: int = 200,
        content: bytes = b"",
        headers: dict[str, str] | None = None,
        chunks: list[bytes] | None = None,
    ) -> None:
        self.status_code = status_code
        self.content = content
        self.headers = headers or {}
        self.chunks = chunks or []
        self.text = content.decode("utf-8", "replace")
        self.closed = False

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")

    def iter_content(self, chunk_size: int) -> list[bytes]:
        return self.chunks

    def close(self) -> None:
        self.closed = True


class FakeSession:
    """Record the arguments used to open an alert stream."""

    def __init__(self, response: FakeResponse) -> None:
        self.response = response
        self.get_kwargs: dict[str, Any] | None = None
        self.closed = False

    def get(self, url: str, **kwargs: Any) -> FakeResponse:
        self.get_kwargs = {"url": url, **kwargs}
        return self.response

    def close(self) -> None:
        self.closed = True


class InlineLoop:
    """Run callbacks immediately, like a live Home Assistant loop would schedule."""

    def is_closed(self) -> bool:
        return False

    def call_soon_threadsafe(self, callback) -> None:
        callback()


class ControlledTimer:
    """Timer substitute that only runs when a test explicitly fires it."""

    created: list[ControlledTimer] = []

    def __init__(self, interval: float, function, args: tuple[Any, ...]) -> None:
        self.interval = interval
        self.function = function
        self.args = args
        self.daemon = False
        self.started = False
        self.cancelled = False
        self.created.append(self)

    def start(self) -> None:
        self.started = True

    def cancel(self) -> None:
        self.cancelled = True

    def fire(self) -> None:
        self.function(*self.args)


def _api() -> Any:
    return HikvisionAccessAPI(
        host="192.168.1.100",
        port=443,
        username="isapi-user",
        password="not-a-real-password",
        use_https=True,
        verify_ssl=False,
        configured_name="Gate",
    )


def _multipart_payload() -> tuple[bytes, bytes, bytes]:
    event = (
        b'{"eventType":"AccessControllerEvent","dateTime":"2026-09-02T12:00:00-03:00",'
        b'"AccessControllerEvent":{"majorEventType":5,"subEventType":75,'
        b'"serialNo":42,"name":"Example User","employeeNoString":"123",'
        b'"currentVerifyMode":"face","picturesNumber":1}}'
    )
    jpeg = b"\xff\xd8synthetic-jpeg\xff\xd9"
    payload = (
        b"--stream-boundary\r\nContent-Type: application/json\r\nContent-Length: "
        + str(len(event)).encode()
        + b"\r\n\r\n"
        + event
        + b'\r\n--stream-boundary\r\nContent-Disposition: form-data; name="Picture"\r\n'
        b"Content-Type: image/jpeg\r\nContent-Length: "
        + str(len(jpeg)).encode()
        + b"\r\n\r\n"
        + jpeg
        + b"\r\n--stream-boundary--\r\n"
    )
    return payload, event, jpeg


def test_device_info_uses_digest_auth(monkeypatch) -> None:
    device_response = FakeResponse(
        content=(
            b'<DeviceInfo xmlns="http://www.isapi.org/ver20/XMLSchema">'
            b"<deviceName>Terminal</deviceName><model>DS-K1T344MX-E1</model>"
            b"<serialNumber>TEST-SERIAL</serialNumber>"
            b"<firmwareVersion>V1.0.0</firmwareVersion></DeviceInfo>"
        )
    )
    capability_response = FakeResponse(
        content=(
            b'<RemoteControlDoorCap xmlns="http://www.isapi.org/ver20/XMLSchema">'
            b"<isSupport>true</isSupport></RemoteControlDoorCap>"
        )
    )
    captured: list[dict[str, Any]] = []

    def fake_request(method: str, url: str, **kwargs: Any) -> FakeResponse:
        captured.append({"method": method, "url": url, **kwargs})
        if url.endswith("/ISAPI/System/deviceInfo"):
            return device_response
        return capability_response

    monkeypatch.setattr(API_MODULE.requests, "request", fake_request)
    api = _api()

    api.get_device_info()

    assert captured[0]["method"] == "GET"
    assert captured[0]["url"].endswith("/ISAPI/System/deviceInfo")
    assert isinstance(captured[0]["auth"], HTTPDigestAuth)
    assert captured[0]["auth"].username == "isapi-user"
    assert captured[1]["url"].endswith(
        "/ISAPI/AccessControl/RemoteControl/door/capabilities"
    )
    assert api.door_control_supported is True
    assert api.unique_id == "TEST-SERIAL"
    assert api.model == "DS-K1T344MX-E1"


def test_missing_door_capability_is_recorded(monkeypatch) -> None:
    device_response = FakeResponse(
        content=(
            b'<DeviceInfo xmlns="http://www.isapi.org/ver20/XMLSchema">'
            b"<serialNumber>TEST-SERIAL</serialNumber></DeviceInfo>"
        )
    )

    def fake_request(method: str, url: str, **kwargs: Any) -> FakeResponse:
        if url.endswith("/ISAPI/System/deviceInfo"):
            return device_response
        return FakeResponse(status_code=404)

    monkeypatch.setattr(API_MODULE.requests, "request", fake_request)
    api = _api()

    api.get_device_info()

    assert api.door_control_supported is False


def test_authentication_error_is_distinct(monkeypatch) -> None:
    monkeypatch.setattr(
        API_MODULE.requests,
        "request",
        lambda *args, **kwargs: FakeResponse(status_code=401),
    )

    try:
        _api().get_device_info()
    except HikvisionAuthError:
        pass
    else:
        raise AssertionError("HTTP 401 must raise HikvisionAuthError")


def test_open_door_validates_isapi_response_status(monkeypatch) -> None:
    response = FakeResponse(
        content=(
            b'<ResponseStatus xmlns="http://www.isapi.org/ver20/XMLSchema">'
            b"<statusCode>4</statusCode>"
            b"<statusString>Invalid Operation</statusString>"
            b"<subStatusCode>methodNotAllowed</subStatusCode>"
            b"</ResponseStatus>"
        )
    )
    monkeypatch.setattr(
        API_MODULE.requests, "request", lambda *args, **kwargs: response
    )

    with pytest.raises(HikvisionApiError, match="methodNotAllowed"):
        _api().open_door()


def test_open_door_accepts_successful_isapi_response(monkeypatch) -> None:
    response = FakeResponse(
        content=(
            b'<ResponseStatus xmlns="http://www.isapi.org/ver20/XMLSchema">'
            b"<statusCode>1</statusCode><statusString>OK</statusString>"
            b"<subStatusCode>ok</subStatusCode></ResponseStatus>"
        )
    )
    monkeypatch.setattr(
        API_MODULE.requests, "request", lambda *args, **kwargs: response
    )

    _api().open_door()


def test_fragmented_alert_stream_decodes_json_and_jpeg(monkeypatch) -> None:
    payload, _, jpeg = _multipart_payload()
    response = FakeResponse(
        headers={"Content-Type": "multipart/mixed; boundary=stream-boundary"},
        chunks=[payload[index : index + 3] for index in range(0, len(payload), 3)],
    )
    session = FakeSession(response)
    monkeypatch.setattr(API_MODULE.requests, "Session", lambda: session)
    api = _api()
    api._loop = InlineLoop()
    updates: list[bool] = []
    api.add_listener(lambda: updates.append(True))

    api._consume_stream()

    assert api.available is True
    assert api.last_result == "authorized"
    assert api.last_auth["name"] == "Example User"
    assert api.latest_picture == jpeg
    assert isinstance(session.get_kwargs["auth"], HTTPDigestAuth)
    assert session.get_kwargs["stream"] is True
    assert response.closed is True
    assert session.closed is True
    assert updates


def test_only_confirmed_major_and_sub_event_pairs_are_classified() -> None:
    api = _api()
    api._handle_event(
        {
            "eventType": "AccessControllerEvent",
            "AccessControllerEvent": {"majorEventType": 4, "subEventType": 75},
        }
    )
    assert api.last_event["event"] == "unknown_access_event"
    assert api.last_auth is None

    api._handle_event(
        {
            "eventType": "AccessControllerEvent",
            "AccessControllerEvent": {"majorEventType": 5, "subEventType": 21},
        }
    )
    assert api.last_event["event"] == "door_unlocked"
    assert api.relay_unlocked is True


def test_documented_card_and_pin_events_are_authorized() -> None:
    api = _api()

    api._handle_event(
        {
            "eventType": "AccessControllerEvent",
            "AccessControllerEvent": {"majorEventType": 5, "subEventType": 1},
        }
    )
    assert api.last_auth["event"] == "card_authenticated"

    api._handle_event(
        {
            "eventType": "AccessControllerEvent",
            "AccessControllerEvent": {"majorEventType": 5, "subEventType": 101},
        }
    )
    assert api.last_auth["event"] == "pin_authenticated"


def test_xml_access_event_is_decoded() -> None:
    api = _api()
    body = (
        b'<EventNotificationAlert xmlns="http://www.isapi.org/ver20/XMLSchema">'
        b"<dateTime>2026-09-02T12:00:00-03:00</dateTime>"
        b"<eventType>AccessControllerEvent</eventType>"
        b"<AccessControllerEvent><majorEventType>5</majorEventType>"
        b"<subEventType>75</subEventType><employeeNoString>123</employeeNoString>"
        b"<name>Example User</name><picturesNumber>1</picturesNumber>"
        b"</AccessControllerEvent></EventNotificationAlert>"
    )

    api._handle_part({"content-type": "application/xml"}, body)

    assert api.last_auth["event"] == "face_authenticated"
    assert api.last_auth["employee_id"] == "123"
    assert api.last_auth["name"] == "Example User"


def test_non_access_json_event_is_exposed_for_diagnostics() -> None:
    api = _api()
    body = (
        b'{"eventType":"VideoIntercomEvent","eventState":"active",'
        b'"eventDescription":"Video intercom event",'
        b'"VideoIntercomEvent":{"eventType":1,"callType":2}}'
    )

    api._handle_part({"content-type": "text/json"}, body)

    assert api.last_event == {
        "event": "unknown_isapi_event",
        "raw_event_type": "VideoIntercomEvent",
        "event_state": "active",
        "event_description": "Video intercom event",
        "date_time": None,
        "active_post_count": None,
        "event_data": {"VideoIntercomEvent": {"eventType": 1, "callType": 2}},
    }


def test_non_access_xml_event_preserves_nested_diagnostic_fields() -> None:
    api = _api()
    body = (
        b'<EventNotificationAlert xmlns="http://www.isapi.org/ver20/XMLSchema">'
        b"<dateTime>2026-09-07T14:00:00-03:00</dateTime>"
        b"<eventType>VideoIntercomEvent</eventType><eventState>active</eventState>"
        b"<VideoIntercomEvent><callType>visitor</callType>"
        b"<keyNo>1</keyNo></VideoIntercomEvent></EventNotificationAlert>"
    )

    api._handle_part({"content-type": "application/xml"}, body)

    assert api.last_event["event"] == "unknown_isapi_event"
    assert api.last_event["raw_event_type"] == "VideoIntercomEvent"
    assert api.last_event["event_data"] == {
        "VideoIntercomEvent": {"callType": "visitor", "keyNo": "1"}
    }


def test_heartbeat_is_not_exposed_as_diagnostic_event() -> None:
    api = _api()
    api._handle_event_payload(
        {"eventType": "heartBeat", "eventState": "active"}
    )

    assert api.last_event is None


def test_thermal_image_does_not_replace_visible_access_picture() -> None:
    api = _api()
    api._handle_event(
        {
            "eventType": "AccessControllerEvent",
            "AccessControllerEvent": {
                "majorEventType": 5,
                "subEventType": 75,
                "picturesNumber": 2,
            },
        }
    )
    visible = b"visible-jpeg"
    thermal = b"thermal-jpeg"

    api._handle_part(
        {
            "content-type": "image/jpeg",
            "content-disposition": 'form-data; name="Picture"',
            "content-id": "pictureImage",
        },
        visible,
    )
    api._handle_part(
        {
            "content-type": "image/jpeg",
            "content-disposition": 'form-data; name="Thermal"',
            "content-id": "thermal_image",
        },
        thermal,
    )

    assert api.latest_picture == visible


def test_doorbell_attachment_becomes_visitor_picture(monkeypatch) -> None:
    ControlledTimer.created.clear()
    monkeypatch.setattr(API_MODULE.threading, "Timer", ControlledTimer)
    api = _api()
    api._loop = InlineLoop()
    updates: list[bool] = []
    api.add_listener(lambda: updates.append(True))

    api._handle_event(
        {
            "eventType": "AccessControllerEvent",
            "dateTime": "2026-09-07T12:00:00-03:00",
            "AccessControllerEvent": {
                "majorEventType": 5,
                "subEventType": 37,
                "serialNo": 100,
                "picturesNumber": 1,
            },
        }
    )

    assert api.last_event["event"] == "doorbell_ringing"
    assert updates == []
    assert len(ControlledTimer.created) == 1

    jpeg = b"\xff\xd8visitor-from-event\xff\xd9"
    api._handle_part(
        {
            "content-type": "image/jpeg",
            "content-disposition": 'form-data; name="Picture"',
        },
        jpeg,
    )

    assert api.latest_visitor_picture == jpeg
    assert api.latest_picture is None
    assert api.last_event["picture_available"] is True
    assert api.last_event["picture_source"] == "event_attachment"
    assert ControlledTimer.created[0].cancelled is True
    assert updates == [True]


def test_doorbell_without_attachment_uses_snapshot_fallback(monkeypatch) -> None:
    ControlledTimer.created.clear()
    monkeypatch.setattr(API_MODULE.threading, "Timer", ControlledTimer)
    captured: list[dict[str, Any]] = []
    jpeg = b"\xff\xd8visitor-from-snapshot\xff\xd9"

    def fake_request(method: str, url: str, **kwargs: Any) -> FakeResponse:
        captured.append({"method": method, "url": url, **kwargs})
        return FakeResponse(content=jpeg, headers={"Content-Type": "image/jpeg"})

    monkeypatch.setattr(API_MODULE.requests, "request", fake_request)
    api = _api()
    api._loop = InlineLoop()
    updates: list[bool] = []
    api.add_listener(lambda: updates.append(True))

    api._handle_event(
        {
            "eventType": "AccessControllerEvent",
            "dateTime": "2026-09-07T12:00:01-03:00",
            "AccessControllerEvent": {
                "majorEventType": 5,
                "subEventType": 37,
                "serialNo": 101,
                "picturesNumber": 0,
            },
        }
    )
    ControlledTimer.created[0].fire()

    assert captured[0]["method"] == "GET"
    assert captured[0]["url"].endswith("/Streaming/channels/101/picture")
    assert isinstance(captured[0]["auth"], HTTPDigestAuth)
    assert api.latest_visitor_picture == jpeg
    assert api.last_event["picture_available"] is True
    assert api.last_event["picture_source"] == "snapshot"
    assert updates == [True]


def test_doorbell_is_published_when_snapshot_fails(monkeypatch) -> None:
    ControlledTimer.created.clear()
    monkeypatch.setattr(API_MODULE.threading, "Timer", ControlledTimer)
    monkeypatch.setattr(
        API_MODULE.requests,
        "request",
        lambda *args, **kwargs: FakeResponse(status_code=404),
    )
    api = _api()
    api._loop = InlineLoop()
    updates: list[bool] = []
    api.add_listener(lambda: updates.append(True))

    api._handle_event(
        {
            "eventType": "AccessControllerEvent",
            "dateTime": "2026-09-07T12:00:03-03:00",
            "AccessControllerEvent": {
                "majorEventType": 5,
                "subEventType": 37,
                "serialNo": 103,
            },
        }
    )
    ControlledTimer.created[0].fire()

    assert api.last_event["event"] == "doorbell_ringing"
    assert api.last_event["picture_available"] is False
    assert api.last_event["picture_source"] is None
    assert api.latest_visitor_picture is None
    assert updates == [True]


def test_duplicate_doorbell_notification_is_suppressed(monkeypatch) -> None:
    ControlledTimer.created.clear()
    monkeypatch.setattr(API_MODULE.threading, "Timer", ControlledTimer)
    api = _api()
    event = {
        "eventType": "AccessControllerEvent",
        "dateTime": "2026-09-07T12:00:02-03:00",
        "activePostCount": 1,
        "AccessControllerEvent": {
            "majorEventType": 5,
            "subEventType": 37,
            "serialNo": 102,
        },
    }

    api._handle_event(event)
    first_event = api.last_event
    event["activePostCount"] = 2
    api._handle_event(event)

    assert api.last_event is first_event
    assert len(ControlledTimer.created) == 1


def test_unrelated_jpeg_is_not_used_as_access_picture() -> None:
    api = _api()

    api._handle_part({"content-type": "image/jpeg"}, b"unrelated-jpeg")

    assert api.latest_picture is None


def test_stream_reconnects_after_disconnect() -> None:
    api = _api()
    calls = 0
    waits: list[float] = []

    class FastStop:
        stopped = False

        def is_set(self) -> bool:
            return self.stopped

        def set(self) -> None:
            self.stopped = True

        def clear(self) -> None:
            self.stopped = False

        def wait(self, delay: float) -> bool:
            waits.append(delay)
            return self.stopped

    stop = FastStop()
    api._stop = stop

    def consume() -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise HikvisionApiError("synthetic disconnect")
        stop.set()

    api._consume_stream = consume
    api._stream_forever()

    assert calls == 2
    assert waits == [2]


def test_stop_closes_active_stream_resources() -> None:
    api = _api()
    response = FakeResponse()
    session = FakeSession(response)
    api._response = response
    api._session = session
    api.available = True

    api.stop()

    assert response.closed is True
    assert session.closed is True
    assert api.available is False


def test_started_stream_thread_stops_cleanly() -> None:
    api = _api()
    loop = asyncio.new_event_loop()
    api._stream_forever = lambda: api._stop.wait()

    try:
        api.start(loop)
        api.stop()
        assert api._thread is None
    finally:
        loop.close()
