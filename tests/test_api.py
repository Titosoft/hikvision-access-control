"""Tests for the local ISAPI client without importing Home Assistant."""

from __future__ import annotations

import asyncio
import sys
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import ModuleType
from typing import Any

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
    response = FakeResponse(
        content=(
            b'<DeviceInfo xmlns="http://www.isapi.org/ver20/XMLSchema">'
            b"<deviceName>Terminal</deviceName><model>DS-K1T344MX-E1</model>"
            b"<serialNumber>TEST-SERIAL</serialNumber>"
            b"<firmwareVersion>V1.0.0</firmwareVersion></DeviceInfo>"
        )
    )
    captured: dict[str, Any] = {}

    def fake_request(method: str, url: str, **kwargs: Any) -> FakeResponse:
        captured.update({"method": method, "url": url, **kwargs})
        return response

    monkeypatch.setattr(API_MODULE.requests, "request", fake_request)
    api = _api()

    api.get_device_info()

    assert captured["method"] == "GET"
    assert captured["url"].endswith("/ISAPI/System/deviceInfo")
    assert isinstance(captured["auth"], HTTPDigestAuth)
    assert captured["auth"].username == "isapi-user"
    assert api.unique_id == "TEST-SERIAL"
    assert api.model == "DS-K1T344MX-E1"


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
