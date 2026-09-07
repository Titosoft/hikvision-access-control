"""Local ISAPI client for Hikvision access-control terminals."""

from __future__ import annotations

import json
import logging
import re
import threading
import time
import xml.etree.ElementTree as ET
from asyncio import AbstractEventLoop
from collections.abc import Callable
from datetime import datetime
from typing import Any

import requests
from requests.auth import HTTPDigestAuth

from .const import AUTH_SUCCESS_EVENTS, EVENT_LABELS
from .parser import HikvisionMultipartParser

_LOGGER = logging.getLogger(__name__)

DOORBELL_EVENT = (5, 37)
DOORBELL_DEDUPLICATION_SECONDS = 5
DOORBELL_SNAPSHOT_DELAY_SECONDS = 1
SNAPSHOT_PATH = "/Streaming/channels/101/picture"


class HikvisionApiError(Exception):
    """Raised when an ISAPI request fails."""

    def __init__(
        self,
        message: str,
        *,
        http_status: int | None = None,
        isapi_status: str | None = None,
    ) -> None:
        super().__init__(message)
        self.http_status = http_status
        self.isapi_status = isapi_status


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
        self.door_control_supported: bool | None = None
        self.latest_picture: bytes | None = None
        self.latest_picture_time: datetime | None = None
        self.latest_visitor_picture: bytes | None = None
        self.latest_visitor_picture_time: datetime | None = None
        self._pending_picture_parts = 0
        self._pending_picture_target: str | None = None

        self._visitor_lock = threading.Lock()
        self._visitor_snapshot_timer: threading.Timer | None = None
        self._visitor_snapshot_token: object | None = None
        self._visitor_pending_event: dict[str, Any] | None = None
        self._last_doorbell_identity: tuple[str, str] | None = None
        self._last_doorbell_seen = 0.0

        self._listeners: set[Callable[[], None]] = set()
        self._listeners_lock = threading.Lock()
        self._loop: AbstractEventLoop | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._session: requests.Session | None = None
        self._response: requests.Response | None = None
        self._stream_lock = threading.Lock()

    def add_listener(self, listener: Callable[[], None]) -> Callable[[], None]:
        """Register a state listener."""
        with self._listeners_lock:
            self._listeners.add(listener)

        def remove_listener() -> None:
            with self._listeners_lock:
                self._listeners.discard(listener)

        return remove_listener

    def _notify(self) -> None:
        if self._loop is None:
            return
        if self._loop.is_closed():
            return
        with self._listeners_lock:
            listeners = tuple(self._listeners)
        for listener in listeners:
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

        values = {
            element.tag.rsplit("}", 1)[-1]: element.text for element in root.iter()
        }
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
        self._discover_door_control_capabilities()
        self.available = True
        return values

    def _discover_door_control_capabilities(self) -> None:
        """Discover whether the device exposes the documented door control API."""
        try:
            self._request(
                "GET",
                "/ISAPI/AccessControl/RemoteControl/door/capabilities",
                timeout=15,
            )
        except HikvisionAuthError:
            self.door_control_supported = None
            _LOGGER.warning(
                "The Hikvision user cannot read remote door control capabilities"
            )
        except HikvisionApiError as err:
            if err.http_status in (404, 405, 501) or err.isapi_status == "4":
                self.door_control_supported = False
            else:
                self.door_control_supported = None
            _LOGGER.debug("Could not read remote door control capabilities: %s", err)
        else:
            self.door_control_supported = True

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
        self._cancel_visitor_snapshot()
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
                f"ISAPI returned HTTP {response.status_code}",
                http_status=response.status_code,
            ) from err
        self._validate_response_status(response)
        return response

    @staticmethod
    def _validate_response_status(response: requests.Response) -> None:
        """Raise when an XML ResponseStatus reports an application-level error."""
        content = response.content.lstrip()
        if not content.startswith(b"<"):
            return
        try:
            root = ET.fromstring(content)
        except ET.ParseError:
            return
        if HikvisionAccessAPI._local_name(root.tag) != "ResponseStatus":
            return

        values = {
            HikvisionAccessAPI._local_name(element.tag): (element.text or "").strip()
            for element in root.iter()
        }
        status_code = values.get("statusCode")
        status_string = values.get("statusString", "Unknown error")
        sub_status = values.get("subStatusCode")
        if status_code in ("0", "1") and status_string.casefold() == "ok":
            return

        detail = f": {sub_status}" if sub_status else ""
        raise HikvisionApiError(
            f"ISAPI returned {status_string}{detail}",
            isapi_status=status_code,
        )

    def _stream_forever(self) -> None:
        delay = 2
        while not self._stop.is_set():
            try:
                self._consume_stream()
                if self._stop.is_set():
                    break
                raise HikvisionApiError("Event stream ended unexpectedly")
            except HikvisionAuthError:
                _LOGGER.error(
                    "Authentication failed for Hikvision terminal %s", self.host
                )
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
            parser = HikvisionMultipartParser.from_content_type(
                response.headers.get("Content-Type")
            )
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
        if "xml" in content_type or body.lstrip().startswith(b"<"):
            try:
                root = ET.fromstring(body)
            except ET.ParseError:
                _LOGGER.debug("Ignored malformed XML event part")
                return
            payload = self._xml_event_payload(root)
            if payload is not None:
                self._handle_event_payload(payload)
            return

        if "application/json" in content_type or "accesscontrollerevent" in disposition:
            try:
                payload = json.loads(body.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                _LOGGER.debug("Ignored malformed JSON event part")
                return
            self._handle_event_payload(payload)
            return

        if "image/jpeg" in content_type:
            if self._pending_picture_parts <= 0:
                return
            self._pending_picture_parts -= 1
            picture_target = self._pending_picture_target
            if self._pending_picture_parts == 0:
                self._pending_picture_target = None
            content_id = headers.get("content-id", "").lower()
            if "thermal" in disposition or "thermal" in content_id:
                return
            name_match = re.search(r'name\s*=\s*"?([^";]+)', disposition)
            if name_match and name_match.group(1).strip() != "picture":
                return
            if picture_target == "visitor":
                self._finish_visitor_event(body, "event_attachment")
            else:
                self.latest_picture = body
                self.latest_picture_time = datetime.now().astimezone()
                self._notify()

    def _handle_event_payload(self, payload: dict[str, Any]) -> None:
        """Route one decoded ISAPI event payload."""
        if payload.get("eventType") == "AccessControllerEvent":
            self._handle_event(payload)
        else:
            self._pending_picture_parts = 0
            self._pending_picture_target = None

    @staticmethod
    def _xml_event_payload(root: ET.Element) -> dict[str, Any] | None:
        """Convert an XML EventNotificationAlert access event to the JSON shape."""
        if HikvisionAccessAPI._local_name(root.tag) != "EventNotificationAlert":
            return None

        payload: dict[str, Any] = {}
        for child in root:
            name = HikvisionAccessAPI._local_name(child.tag)
            if name == "AccessControllerEvent":
                payload[name] = {
                    HikvisionAccessAPI._local_name(item.tag): item.text
                    for item in child
                }
            elif len(child) == 0:
                payload[name] = child.text
        return payload

    def _handle_event(self, payload: dict[str, Any]) -> None:
        detail = payload.get("AccessControllerEvent") or {}
        sub_event = self._to_int(detail.get("subEventType"))
        major_event = self._to_int(detail.get("majorEventType"))
        event_code = (major_event, sub_event)
        if event_code == DOORBELL_EVENT and self._is_duplicate_doorbell(
            payload, detail
        ):
            _LOGGER.debug("Ignored duplicate doorbell notification")
            return
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
            "active_post_count": payload.get("activePostCount"),
        }
        pictures_number = self._to_int(normalized["pictures_number"]) or 0
        self._pending_picture_parts = max(pictures_number, 0)
        self._pending_picture_target = (
            "visitor" if event_code == DOORBELL_EVENT else "access"
        )
        if self._pending_picture_parts == 0:
            self._pending_picture_target = None
        self.last_event = normalized

        if event_code == (5, 21):
            self.relay_unlocked = True
        elif event_code == (5, 22):
            self.relay_unlocked = False

        if event_code in AUTH_SUCCESS_EVENTS:
            self.last_auth = normalized
            self.last_result = "authorized"

        if event_code == DOORBELL_EVENT:
            normalized["picture_available"] = False
            normalized["picture_source"] = None
            self._schedule_visitor_snapshot(normalized)
            return

        self._notify()

    def _is_duplicate_doorbell(
        self, payload: dict[str, Any], detail: dict[str, Any]
    ) -> bool:
        """Suppress repeated active-post notifications for one button press."""
        serial_no = detail.get("serialNo")
        date_time = payload.get("dateTime")
        if serial_no not in (None, "", 0, "0"):
            identity = ("serial", str(serial_no))
        elif date_time:
            identity = ("time", f"{date_time}:{detail.get('doorNo')}")
        else:
            return False

        now = time.monotonic()
        duplicate = (
            identity == self._last_doorbell_identity
            and now - self._last_doorbell_seen < DOORBELL_DEDUPLICATION_SECONDS
        )
        self._last_doorbell_identity = identity
        self._last_doorbell_seen = now
        return duplicate

    def _schedule_visitor_snapshot(self, event: dict[str, Any]) -> None:
        """Wait briefly for an attached JPEG, then request a live snapshot."""
        token = object()
        timer = threading.Timer(
            DOORBELL_SNAPSHOT_DELAY_SECONDS,
            self._capture_visitor_snapshot,
            args=(token,),
        )
        timer.daemon = True
        with self._visitor_lock:
            previous_timer = self._visitor_snapshot_timer
            previous_event = self._visitor_pending_event
            self._visitor_snapshot_token = token
            self._visitor_pending_event = event
            self._visitor_snapshot_timer = timer
        if previous_timer is not None:
            previous_timer.cancel()
        if previous_event is not None:
            previous_event["picture_available"] = False
            previous_event["picture_source"] = None
            self.last_event = previous_event
            self._notify()
        timer.start()

    def _capture_visitor_snapshot(self, token: object) -> None:
        """Capture channel 101 when the doorbell event carried no JPEG."""
        picture: bytes | None = None
        try:
            response = self._request(
                "GET",
                SNAPSHOT_PATH,
                timeout=15,
                headers={"Accept": "image/jpeg"},
            )
            if not response.content.startswith(b"\xff\xd8"):
                raise HikvisionApiError("Snapshot response is not a JPEG image")
            picture = response.content
        except HikvisionApiError as err:
            _LOGGER.warning("Could not capture doorbell visitor picture: %s", err)

        self._finish_visitor_event(picture, "snapshot" if picture else None, token)

    def _finish_visitor_event(
        self,
        picture: bytes | None,
        source: str | None,
        token: object | None = None,
    ) -> None:
        """Publish the doorbell event after its visitor image is resolved."""
        with self._visitor_lock:
            if token is not None and token is not self._visitor_snapshot_token:
                return
            event = self._visitor_pending_event
            timer = self._visitor_snapshot_timer
            self._visitor_snapshot_token = None
            self._visitor_snapshot_timer = None
            self._visitor_pending_event = None
            if picture is not None:
                self.latest_visitor_picture = picture
                self.latest_visitor_picture_time = datetime.now().astimezone()
        if timer is not None and timer is not threading.current_thread():
            timer.cancel()
        if event is None:
            if picture is not None:
                self._notify()
            return
        event["picture_available"] = picture is not None
        event["picture_source"] = source
        self.last_event = event
        self._notify()

    def _cancel_visitor_snapshot(self) -> None:
        """Cancel an outstanding fallback snapshot without publishing it."""
        with self._visitor_lock:
            timer = self._visitor_snapshot_timer
            self._visitor_snapshot_token = None
            self._visitor_snapshot_timer = None
            self._visitor_pending_event = None
        if timer is not None:
            timer.cancel()

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

    @staticmethod
    def _local_name(tag: str) -> str:
        """Return an XML tag without its namespace."""
        return tag.rsplit("}", 1)[-1]
