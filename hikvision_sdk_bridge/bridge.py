"""Isolated HCNetSDK alarm bridge for the Home Assistant add-on."""

from __future__ import annotations

import base64
import ctypes
import json
import logging
import os
import queue
import signal
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

LOGGER = logging.getLogger("hikvision_sdk_bridge")

HOME_ASSISTANT_EVENT = "hikvision_access_control_sdk_event"
DEFAULT_HOME_ASSISTANT_URL = f"http://supervisor/core/api/events/{HOME_ASSISTANT_EVENT}"

COMM_VCA_ALARM = 0x4993
COMM_ALARM_BUTTON_DOWN_EXCEPTION = 0x1152
COMM_UPLOAD_VIDEO_INTERCOM_EVENT = 0x1132
COMM_ALARM_VIDEO_INTERCOM = 0x1133
COMM_CONFERENCE_CALL_ALARM = 0x5012
COMM_ALARM_ACS = 0x5002
COMM_ISAPI_ALARM = 0x6009

INTERCOM_COMMANDS = {
    COMM_ALARM_BUTTON_DOWN_EXCEPTION,
    COMM_UPLOAD_VIDEO_INTERCOM_EVENT,
    COMM_ALARM_VIDEO_INTERCOM,
    COMM_CONFERENCE_CALL_ALARM,
    COMM_ALARM_ACS,
    COMM_ISAPI_ALARM,
    COMM_VCA_ALARM,
}
DOORBELL_ACS_EVENTS = {(5, 0x25), (5, 0x33)}
MAX_ALARM_PAYLOAD = 256 * 1024
NET_SDK_INIT_CFG_SDK_PATH = 2
STATUS_HEARTBEAT_SECONDS = 60

SDK_EXCEPTION_NAMES = {
    0x8002: "alarm_callback_disconnected",
    0x8006: "alarm_channel_reconnecting",
    0x8016: "alarm_channel_reconnected",
    0x8023: "alarm_channel_lost",
    0x8040: "device_relogin_started",
    0x8041: "device_relogin_succeeded",
    0x8044: "device_relogin_failed",
}
SDK_OFFLINE_EXCEPTIONS = {0x8002, 0x8006, 0x8023, 0x8040, 0x8044}
SDK_ONLINE_EXCEPTIONS = {0x8016, 0x8041}


class NetDvrLocalSdkPath(ctypes.Structure):
    """NET_DVR_LOCAL_SDK_PATH used before NET_DVR_Init on Linux."""

    _fields_ = [
        ("path", ctypes.c_char * 256),
        ("reserved", ctypes.c_uint8 * 128),
    ]


class NetDvrAlarmIsapiInfo(ctypes.Structure):
    """Pointer-safe prefix of NET_DVR_ALARM_ISAPI_INFO."""

    _fields_ = [
        ("alarm_data", ctypes.c_void_p),
        ("alarm_data_length", ctypes.c_uint32),
        ("data_type", ctypes.c_uint8),
        ("pictures_number", ctypes.c_uint8),
        ("reserved", ctypes.c_uint8 * 2),
        ("picture_data", ctypes.c_void_p),
        ("reserved2", ctypes.c_uint8 * 32),
    ]


class NetDvrAcsAlarmPrefix(ctypes.Structure):
    """Stable first fields of NET_DVR_ACS_ALARM_INFO."""

    _fields_ = [
        ("size", ctypes.c_uint32),
        ("major", ctypes.c_uint32),
        ("minor", ctypes.c_uint32),
    ]


AlarmCallback = ctypes.CFUNCTYPE(
    ctypes.c_int32,
    ctypes.c_int32,
    ctypes.c_void_p,
    ctypes.c_void_p,
    ctypes.c_uint32,
    ctypes.c_void_p,
)
ExceptionCallback = ctypes.CFUNCTYPE(
    None,
    ctypes.c_uint32,
    ctypes.c_int32,
    ctypes.c_int32,
    ctypes.c_void_p,
)


@dataclass(frozen=True, slots=True)
class Settings:
    """Runtime settings supplied by the add-on supervisor."""

    device_host: str
    device_port: int
    username: str
    password: str
    sdk_library: str
    supervisor_token: str
    home_assistant_url: str = DEFAULT_HOME_ASSISTANT_URL


def load_settings() -> Settings:
    """Load settings without ever logging the password or Supervisor token."""
    try:
        port = int(os.environ.get("DEVICE_PORT", "8000"))
    except ValueError as err:
        raise RuntimeError("DEVICE_PORT must be a number") from err
    if not 1 <= port <= 65535:
        raise RuntimeError("DEVICE_PORT must be between 1 and 65535")

    values = {
        "device_host": os.environ.get("DEVICE_HOST", "").strip(),
        "username": os.environ.get("DEVICE_USERNAME", "").strip(),
        "password": os.environ.get("DEVICE_PASSWORD", ""),
        "sdk_library": os.environ.get("SDK_LIBRARY", "").strip(),
        "supervisor_token": os.environ.get("SUPERVISOR_TOKEN", ""),
    }
    missing = [name for name, value in values.items() if not value]
    if missing:
        raise RuntimeError(f"Missing required setting: {', '.join(missing)}")

    return Settings(
        **values,
        device_port=port,
        home_assistant_url=os.environ.get(
            "HOME_ASSISTANT_EVENTS_URL", DEFAULT_HOME_ASSISTANT_URL
        ),
    )


class HomeAssistantPublisher:
    """Publish callbacks outside the HCNetSDK native callback thread."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._queue: queue.Queue[dict[str, Any] | None] = queue.Queue(maxsize=256)
        self._thread = threading.Thread(
            target=self._run,
            name="home-assistant-event-publisher",
            daemon=True,
        )

    def start(self) -> None:
        self._thread.start()

    def publish(self, event: dict[str, Any]) -> None:
        event["device_host"] = self._settings.device_host
        event["source"] = "hcnetsdk"
        try:
            self._queue.put_nowait(event)
        except queue.Full:
            LOGGER.error("Dropping SDK event because the publisher queue is full")

    def stop(self) -> None:
        self._queue.put(None)
        self._thread.join(timeout=15)

    def _run(self) -> None:
        while True:
            event = self._queue.get()
            try:
                if event is None:
                    return
                self._post_with_retry(event)
            finally:
                self._queue.task_done()

    def _post_with_retry(self, event: dict[str, Any]) -> None:
        body = json.dumps(event, separators=(",", ":")).encode()
        for attempt in range(1, 4):
            request = urllib.request.Request(
                self._settings.home_assistant_url,
                data=body,
                method="POST",
                headers={
                    "Authorization": f"Bearer {self._settings.supervisor_token}",
                    "Content-Type": "application/json",
                },
            )
            try:
                with urllib.request.urlopen(request, timeout=10) as response:
                    if 200 <= response.status < 300:
                        return
                    raise RuntimeError(f"Home Assistant returned {response.status}")
            except (OSError, RuntimeError, urllib.error.URLError) as err:
                if attempt == 3:
                    LOGGER.error("Could not publish SDK event: %s", err)
                    return
                time.sleep(attempt)


class HikvisionSdkClient:
    """Minimal dynamic binding for login and an armed alarm channel."""

    def __init__(self, settings: Settings, publisher: HomeAssistantPublisher) -> None:
        self._settings = settings
        self._publisher = publisher
        self._library = ctypes.CDLL(settings.sdk_library)
        self._login_id = -1
        self._alarm_handle = -1
        self._connected = False
        self._callback = AlarmCallback(self._handle_alarm)
        self._exception_callback = ExceptionCallback(self._handle_exception)
        self._set_exception_callback: Any | None = None
        self._configure_functions()
        self._configure_sdk_path()

    @property
    def connected(self) -> bool:
        """Return the connection state last reported by HCNetSDK."""
        return self._connected

    def _configure_functions(self) -> None:
        library = self._library
        library.NET_DVR_Init.argtypes = []
        library.NET_DVR_Init.restype = ctypes.c_int32
        library.NET_DVR_Cleanup.argtypes = []
        library.NET_DVR_Cleanup.restype = ctypes.c_int32
        library.NET_DVR_SetConnectTime.argtypes = [ctypes.c_uint32, ctypes.c_uint32]
        library.NET_DVR_SetConnectTime.restype = ctypes.c_int32
        library.NET_DVR_SetReconnect.argtypes = [ctypes.c_uint32, ctypes.c_int32]
        library.NET_DVR_SetReconnect.restype = ctypes.c_int32
        library.NET_DVR_Login_V30.argtypes = [
            ctypes.c_char_p,
            ctypes.c_uint16,
            ctypes.c_char_p,
            ctypes.c_char_p,
            ctypes.c_void_p,
        ]
        library.NET_DVR_Login_V30.restype = ctypes.c_int32
        library.NET_DVR_Logout.argtypes = [ctypes.c_int32]
        library.NET_DVR_Logout.restype = ctypes.c_int32
        library.NET_DVR_SetDVRMessageCallBack_V31.argtypes = [
            AlarmCallback,
            ctypes.c_void_p,
        ]
        library.NET_DVR_SetDVRMessageCallBack_V31.restype = ctypes.c_int32
        library.NET_DVR_SetupAlarmChan_V30.argtypes = [ctypes.c_int32]
        library.NET_DVR_SetupAlarmChan_V30.restype = ctypes.c_int32
        library.NET_DVR_CloseAlarmChan_V30.argtypes = [ctypes.c_int32]
        library.NET_DVR_CloseAlarmChan_V30.restype = ctypes.c_int32
        library.NET_DVR_GetLastError.argtypes = []
        library.NET_DVR_GetLastError.restype = ctypes.c_uint32
        try:
            self._set_exception_callback = library.NET_DVR_SetExceptionCallBack_V30
        except AttributeError:
            LOGGER.warning(
                "This HCNetSDK build has no exception callback; transient "
                "disconnects will not update the bridge connection sensor"
            )
        else:
            self._set_exception_callback.argtypes = [
                ctypes.c_uint32,
                ctypes.c_void_p,
                ExceptionCallback,
                ctypes.c_void_p,
            ]
            self._set_exception_callback.restype = ctypes.c_int32

    def _configure_sdk_path(self) -> None:
        """Point modern Linux SDK builds at their HCNetSDKCom directory."""
        try:
            set_init_config = self._library.NET_DVR_SetSDKInitCfg
        except AttributeError:
            return
        set_init_config.argtypes = [ctypes.c_int32, ctypes.c_void_p]
        set_init_config.restype = ctypes.c_int32
        sdk_path = os.path.dirname(os.path.abspath(self._settings.sdk_library))
        encoded = sdk_path.encode()
        if len(encoded) >= 256:
            raise RuntimeError("HCNetSDK library path is too long")
        path_config = NetDvrLocalSdkPath()
        path_config.path = encoded
        if not set_init_config(NET_SDK_INIT_CFG_SDK_PATH, ctypes.byref(path_config)):
            LOGGER.warning(
                "NET_DVR_SetSDKInitCfg could not set the component path; "
                "continuing with LD_LIBRARY_PATH"
            )

    def start(self) -> None:
        if not self._library.NET_DVR_Init():
            raise RuntimeError(f"NET_DVR_Init failed: {self._last_error()}")
        self._library.NET_DVR_SetConnectTime(5000, 2)
        self._library.NET_DVR_SetReconnect(10000, 1)
        if (
            self._set_exception_callback is not None
            and not self._set_exception_callback(
                0, None, self._exception_callback, None
            )
        ):
            LOGGER.warning(
                "NET_DVR_SetExceptionCallBack_V30 failed: %s; continuing without "
                "live disconnect status",
                self._last_error(),
            )

        device_info = ctypes.create_string_buffer(2048)
        self._login_id = self._library.NET_DVR_Login_V30(
            self._settings.device_host.encode(),
            self._settings.device_port,
            self._settings.username.encode(),
            self._settings.password.encode(),
            device_info,
        )
        if self._login_id < 0:
            error = self._last_error()
            self._library.NET_DVR_Cleanup()
            raise RuntimeError(f"NET_DVR_Login_V30 failed: {error}")

        if not self._library.NET_DVR_SetDVRMessageCallBack_V31(self._callback, None):
            error = self._last_error()
            self.stop()
            raise RuntimeError(f"SDK callback registration failed: {error}")

        self._alarm_handle = self._library.NET_DVR_SetupAlarmChan_V30(self._login_id)
        if self._alarm_handle < 0:
            error = self._last_error()
            self.stop()
            raise RuntimeError(f"NET_DVR_SetupAlarmChan_V30 failed: {error}")
        self._connected = True

    def stop(self) -> None:
        self._connected = False
        if self._alarm_handle >= 0:
            self._library.NET_DVR_CloseAlarmChan_V30(self._alarm_handle)
            self._alarm_handle = -1
        if self._login_id >= 0:
            self._library.NET_DVR_Logout(self._login_id)
            self._login_id = -1
        self._library.NET_DVR_Cleanup()

    def _last_error(self) -> int:
        return int(self._library.NET_DVR_GetLastError())

    def _handle_alarm(
        self,
        command: int,
        _alarmer: int,
        alarm_info: int,
        buffer_length: int,
        _user: int,
    ) -> int:
        if command not in INTERCOM_COMMANDS:
            return 1

        event: dict[str, Any] = {
            "kind": "alarm",
            "command": command,
            "command_hex": f"0x{command:04x}",
            "received_at": datetime.now(UTC).isoformat(),
        }
        if command == COMM_ISAPI_ALARM:
            payload = self._read_isapi_payload(alarm_info, buffer_length)
            if payload is not None and not self._is_call_payload(payload):
                return 1
            self._add_payload(event, payload)
        elif command == COMM_VCA_ALARM:
            payload = self._read_direct_payload(alarm_info, buffer_length)
            if payload is not None:
                if not self._is_call_payload(payload):
                    return 1
            self._add_payload(event, payload)
        elif command == COMM_ALARM_ACS:
            event_code = self._read_acs_event_code(alarm_info, buffer_length)
            if event_code not in DOORBELL_ACS_EVENTS:
                return 1
            event["major"], event["minor"] = event_code
        self._publisher.publish(event)
        return 1

    def _handle_exception(
        self,
        exception_type: int,
        _login_id: int,
        _handle: int,
        _user: int,
    ) -> None:
        if exception_type in SDK_OFFLINE_EXCEPTIONS:
            status = "offline"
            self._connected = False
        elif exception_type in SDK_ONLINE_EXCEPTIONS:
            status = "online"
            self._connected = True
        else:
            return
        exception_name = SDK_EXCEPTION_NAMES[exception_type]
        LOGGER.info("HCNetSDK connection status is %s: %s", status, exception_name)
        self._publisher.publish(
            {
                "kind": "bridge_status",
                "status": status,
                "exception_code": int(exception_type),
                "exception_name": exception_name,
            }
        )

    @staticmethod
    def _is_call_payload(payload: bytes) -> bool:
        lowered = payload.lower()
        return b"call" in lowered or b"intercom" in lowered

    @staticmethod
    def _add_payload(event: dict[str, Any], payload: bytes | None) -> None:
        if payload is None:
            return
        event["payload_type"] = "json" if payload.lstrip().startswith(b"{") else "xml"
        event["payload_b64"] = base64.b64encode(payload).decode("ascii")

    @staticmethod
    def _read_isapi_payload(alarm_info: int, buffer_length: int) -> bytes | None:
        if not alarm_info or buffer_length < ctypes.sizeof(NetDvrAlarmIsapiInfo):
            return None
        info = ctypes.cast(alarm_info, ctypes.POINTER(NetDvrAlarmIsapiInfo)).contents
        length = int(info.alarm_data_length)
        if not info.alarm_data or not 0 < length <= MAX_ALARM_PAYLOAD:
            return None
        return ctypes.string_at(info.alarm_data, length).rstrip(b"\x00")

    @staticmethod
    def _read_direct_payload(alarm_info: int, buffer_length: int) -> bytes | None:
        if not alarm_info or not 0 < buffer_length <= MAX_ALARM_PAYLOAD:
            return None
        payload = ctypes.string_at(alarm_info, buffer_length).rstrip(b"\x00")
        if payload.lstrip().startswith((b"{", b"<")):
            return payload
        # Without NET_DVR_LOCAL_GENERAL_CFG separation, some SDK builds wrap the
        # event and image bytes in one HTTP multipart buffer. Extract only the
        # first JSON/XML document while the native callback memory is valid.
        json_start = payload.find(b"{")
        if json_start >= 0:
            try:
                document, _end = json.JSONDecoder().raw_decode(
                    payload[json_start:].decode("utf-8", errors="ignore")
                )
            except json.JSONDecodeError:
                pass
            else:
                if isinstance(document, dict):
                    return json.dumps(document, separators=(",", ":")).encode()
        xml_start = payload.find(b"<?xml")
        if xml_start < 0:
            xml_start = payload.find(b"<EventNotificationAlert")
        xml_end_tag = b"</EventNotificationAlert>"
        xml_end = payload.find(xml_end_tag, max(xml_start, 0))
        if xml_start >= 0 and xml_end >= 0:
            return payload[xml_start : xml_end + len(xml_end_tag)]
        return None

    @staticmethod
    def _read_acs_event_code(
        alarm_info: int, buffer_length: int
    ) -> tuple[int, int] | None:
        if not alarm_info or buffer_length < ctypes.sizeof(NetDvrAcsAlarmPrefix):
            return None
        info = ctypes.cast(alarm_info, ctypes.POINTER(NetDvrAcsAlarmPrefix)).contents
        return int(info.major), int(info.minor)


def main() -> int:
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    publisher: HomeAssistantPublisher | None = None
    try:
        settings = load_settings()
        publisher = HomeAssistantPublisher(settings)
        publisher.start()
        client = HikvisionSdkClient(settings, publisher)
        client.start()
    except (AttributeError, OSError, RuntimeError) as err:
        LOGGER.critical("Could not start HCNetSDK bridge: %s", err)
        if publisher is not None:
            publisher.publish(
                {
                    "kind": "bridge_status",
                    "status": "offline",
                    "reason": "startup_failed",
                }
            )
            publisher.stop()
        return 1

    stop_event = threading.Event()

    def request_stop(_signum: int, _frame: Any) -> None:
        stop_event.set()

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    publisher.publish({"kind": "bridge_status", "status": "online"})
    LOGGER.info(
        "HCNetSDK alarm channel armed for %s:%s",
        settings.device_host,
        settings.device_port,
    )

    while not stop_event.wait(STATUS_HEARTBEAT_SECONDS):
        publisher.publish(
            {
                "kind": "bridge_status",
                "status": "online" if client.connected else "offline",
                "reason": "status_heartbeat",
            }
        )
    publisher.publish({"kind": "bridge_status", "status": "offline"})
    client.stop()
    publisher.stop()
    LOGGER.info("HCNetSDK bridge stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
