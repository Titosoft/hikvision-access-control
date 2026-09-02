"""Local ISAPI client for Hikvision access-control terminals."""

from __future__ import annotations

from asyncio import AbstractEventLoop
from collections.abc import Callable
from datetime import datetime
import json
import logging
import threading
from typing import Any
import xml.etree.ElementTree as ET

import requests
from requests.auth import HTTPDigestAuth

from .const import AUTH_SUCCESS_EVENTS, EVENT_LABELS
from .parser import HikvisionMultipartParser

_LOGGER = logging.getLogger(__name__)


class HikvisionApiError(Exception):
    """Raised when an ISAPI request fails."""


class HikvisionAuthError(HikvisionApiError):
    """Raised when credentials are rejected."""


class HikvisionAccessAPI:
    """Maintain an ISAPI event stream and expose the latest state."""

    def __init__(
        self,
        host: str,
        port: int,
        username: str,
        password: str,
        use_https: bool,
        verify_ssl: bool,
        configured_name: str,
    ) -> None:
        scheme = "https" if use_https else "http"
        self.base_url = f"{scheme}://{host}:{port}"
        self.host = host
        self.username = username
        self.password = password
        self.verify_ssl = verify_ssl
        self.configured_name = configured_name

        self.device_name = configured_name
        self.model = "Hikvision access-control terminal"
        self.serial_number: str | None = None
        self.mac_address: str | None = None
        self.firmware_version: str | None = None
        self.unique_id = host

        self.available = False
        self.last_event: dict[str, Any] | None = None
        self.last_auth: dict[str, Any] | None = None
        self.last_result: str | None = None
        self.relay_unlocked: bool | None = None
        self.latest_picture: bytes | None = None
        self.latest_picture_time: datetime | None = None

        self._listeners: set[Callable[[], None]] = set()
        self._loop: AbstractEventLoop | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._session: requests.Session | None = None
        self._response: requests.Response | None = None
        self._stream_lock = threading.Lock()

    def add_listener(self, listener: Callable[[], None]) -> Callable[[], None]:
        """Register a state listener."""
        self._listeners.add(listener)

        def remove_listener() -> None:
            self._listeners.discard(listener)

        return remove_listener

    def _notify(self) -> None:
        if self._loop is None:
            return
        if self._loop.is_closed():
            return
        for listener in tuple(self._listeners):
            try:
                self._loop.call_soon_threadsafe(listener)
            except RuntimeError:
                return

    def get_device_info(self) -> dict[str, Any]:
        """Validate credentials and populate device metadata."""
        response = self._request("GET", "/ISAPI/System/deviceInfo", timeout=15)
        try:
            root = ET.fromstring(response.content)
        except ET.ParseError as err:
            raise HikvisionApiError("Invalid device information response") from err

        values = {element.tag.rsplit("}", 1)[-1]: element.text for element in root.iter()}
        self.model = values.get("model") or values.get("deviceType") or self.model
        self.serial_number = values.get("serialNumber")
        self.mac_address = values.get("macAddress")
        self.firmware_version = values.get("firmwareVersion")
        reported_name = values.get("deviceName")
        if self.configured_name.strip():
            self.device_name = self.configured_name.strip()
        elif reported_name:
            self.device_name = reported_name
        self.unique_id = self.serial_number or self.mac_address or self.host
        self.available = True
        return values

    def start(self, loop: AbstractEventLoop) -> None:
        """Start the background event stream."""
        if self._thread and self._thread.is_alive():
            return
        self._loop = loop
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._stream_forever,
            name=f"hikvision-access-{self.host}",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        """Stop the event stream."""
        self._stop.set()
        with self._stream_lock:
            response = self._response
            session = self._session
        if response is not None:
            response.close()
        if session is not None:
            session.close()
        thread = self._thread
        if thread and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=15)
        if thread is None or not thread.is_alive():
            self._thread = None
        self._set_available(False)

    def open_door(self, door_no: int = 1) -> None:
        """Pulse the configured door relay."""
        body = (
            '<RemoteControlDoor version="2.0" '
            'xmlns="http://www.isapi.org/ver20/XMLSchema">'
            "<cmd>open</cmd></RemoteControlDoor>"
        )
        self._request(
            "PUT",
            f"/ISAPI/AccessControl/RemoteControl/door/{door_no}",
            data=body.encode(),
            headers={"Content-Type": "application/xml"},
            timeout=15,
        )

    def _request(self, method: str, path: str, **kwargs: Any) -> requests.Response:
        try:
            response = requests.request(
                method,
                self.base_url + path,
                auth=HTTPDigestAuth(self.username, self.password),
                verify=self.verify_ssl,
                **kwargs,
            )
        except requests.RequestException as err:
            raise HikvisionApiError(str(err)) from err
        if response.status_code in (401, 403):
            raise HikvisionAuthError("Invalid username, password, or permissions")
        try:
            response.raise_for_status()
        except requests.HTTPError as err:
            raise HikvisionApiError(
                f"ISAPI returned HTTP {response.status_code}: {response.text[:200]}"
            ) from err
        return response

    def _stream_forever(self) -> None:
        delay = 2
        while not self._stop.is_set():
            try:
                self._consume_stream()
                if self._stop.is_set():
                    break
                raise HikvisionApiError("Event stream ended unexpectedly")
            except HikvisionAuthError:
                _LOGGER.error("Authentication failed for Hikvision terminal %s", self.host)
                self._set_available(False)
                return
            except (HikvisionApiError, requests.RequestException, OSError) as err:
                was_connected = self.available
                if not self._stop.is_set():
                    _LOGGER.warning("Hikvision event stream disconnected: %s", err)
                    self._set_available(False)
                if was_connected:
                    delay = 2
            if self._stop.wait(delay):
                break
            delay = min(delay * 2, 30)

    def _consume_stream(self) -> None:
        session = requests.Session()
        response: requests.Response | None = None
        with self._stream_lock:
            self._session = session
        try:
            response = session.get(
                self.base_url + "/ISAPI/Event/notification/alertStream",
                auth=HTTPDigestAuth(self.username, self.password),
                verify=self.verify_ssl,
                stream=True,
                timeout=(10, 60),
                headers={"Accept": "multipart/mixed, multipart/form-data"},
            )
            with self._stream_lock:
                self._response = response
            if response.status_code in (401, 403):
                raise HikvisionAuthError("Event-stream authentication failed")
            response.raise_for_status()
            parser = HikvisionMultipartParser.from_content_type(response.headers.get("Content-Type"))
            self._set_available(True)
            for chunk in response.iter_content(chunk_size=8192):
                if self._stop.is_set():
                    break
                for part in parser.feed(chunk):
                    self._handle_part(part.headers, part.body)
        except requests.HTTPError as err:
            raise HikvisionApiError(str(err)) from err
        finally:
            if response is not None:
                response.close()
            session.close()
            with self._stream_lock:
                self._response = None
                self._session = None

    def _handle_part(self, headers: dict[str, str], body: bytes) -> None:
        content_type = headers.get("content-type", "").lower()
        disposition = headers.get("content-disposition", "").lower()
        if "application/json" in content_type or "accesscontrollerevent" in disposition:
            try:
                payload = json.loads(body.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                _LOGGER.debug("Ignored malformed JSON event part")
                return
            if payload.get("eventType") == "AccessControllerEvent":
                self._handle_event(payload)
            return

        if "image/jpeg" in content_type or "name=\"picture\"" in disposition:
            self.latest_picture = body
            self.latest_picture_time = datetime.now().astimezone()
            self._notify()

    def _handle_event(self, payload: dict[str, Any]) -> None:
        detail = payload.get("AccessControllerEvent") or {}
        sub_event = self._to_int(detail.get("subEventType"))
        major_event = self._to_int(detail.get("majorEventType"))
        event_code = (major_event, sub_event)
        normalized = {
            "event": EVENT_LABELS.get(event_code, "unknown_access_event"),
            "major": major_event,
            "sub_event": sub_event,
            "serial_no": detail.get("serialNo"),
            "date_time": payload.get("dateTime"),
            "door_no": detail.get("doorNo"),
            "name": detail.get("name"),
            "employee_id": detail.get("employeeNoString"),
            "verify_mode": detail.get("currentVerifyMode"),
            "user_type": detail.get("userType"),
            "mask": detail.get("mask"),
            "pictures_number": detail.get("picturesNumber", 0),
        }
        self.last_event = normalized

        if event_code == (5, 21):
            self.relay_unlocked = True
        elif event_code == (5, 22):
            self.relay_unlocked = False

        if event_code in AUTH_SUCCESS_EVENTS:
            self.last_auth = normalized
            self.last_result = "authorized"

        self._notify()

    def _set_available(self, available: bool) -> None:
        if self.available == available:
            return
        self.available = available
        self._notify()

    @staticmethod
    def _to_int(value: Any) -> int | None:
        try:
            return int(value)
        except (TypeError, ValueError):
            return None
