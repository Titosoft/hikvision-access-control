"""Parse the optional ISAPI status documents used for diagnostics."""

from __future__ import annotations

import json
import math
import re
import threading
import time
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import UTC, datetime
from typing import Any

from .const import AUTH_FAILURE_RESULTS, AUTH_SUCCESS_EVENTS, EVENT_LABELS

ACCESS_STATUS = "access_status"
SYSTEM_STATUS = "system_status"
OPEN_CONTACT_WINDOW = 60
SIP_CALL_STAGES = ("received", "connected", "ended")
VERIFY_MODE_TOKEN = re.compile(r"[a-zA-Z0-9_+-]{1,40}")

# Capability and inventory reads are kept off the doorbell polling path.
STATUS_PROBES = {
    "access_capabilities": (
        "/ISAPI/AccessControl/AcsWorkStatus/capabilities?format=json",
        "AcsWorkStatus",
        None,
    ),
    "intercom_capabilities": (
        "/ISAPI/VideoIntercom/capabilities",
        "VideoIntercomCap",
        None,
    ),
    "two_way_audio": (
        "/ISAPI/System/TwoWayAudio/channels",
        "TwoWayAudioChannelList",
        None,
    ),
    ACCESS_STATUS: (
        "/ISAPI/AccessControl/AcsWorkStatus?format=json",
        "AcsWorkStatus",
        30,
    ),
    SYSTEM_STATUS: ("/ISAPI/System/status", "DeviceStatus", 60),
    "user_count": (
        "/ISAPI/AccessControl/UserInfo/Count?format=json",
        "UserInfoCount",
        300,
    ),
}

DOOR_MODES = {1: "sleep", 2: "always_unlocked", 3: "always_locked", 4: "normal"}
CIRCUIT_STATES = {
    0: "closed",
    1: "open",
    2: "short_circuit",
    3: "open_circuit",
    4: "fault",
}
ACCESS_ENUMS = {
    "power_supply": (
        "powerSupplyStatus",
        {"acpowersupply": "ac", "batterypowersupply": "battery"},
    ),
    "battery_charge": (
        "batteryChargeStatus",
        {"charging": "charging", "uncharged": "not_charging"},
    ),
    "sip_registration": (
        "sipStatus",
        {
            "connect": "connected",
            "disconnect": "disconnected",
            "unregistered": "unregistered",
        },
    ),
    "voip_registration": (
        "voipStatus",
        {
            "connect": "connected",
            "disconnect": "disconnected",
            "unregistered": "unregistered",
        },
    ),
    "network_status": (
        "netStatus",
        {
            "connect": "connected",
            "disconnect": "disconnected",
            "ipconflict": "ip_conflict",
        },
    ),
    "storage_status": (
        "TFCardStatus",
        {
            "mounted": "mounted",
            "unmounted": "unmounted",
        },
    ),
}
ACCESS_PORT_LISTS = {
    "caseStatus": "active_triggers",
    "setupAlarmStatus": "armed_alarm_inputs",
    "alarmInStatus": "active_alarm_inputs",
    "alarmOutStatus": "active_alarm_outputs",
    "cardReaderOnlineStatus": "online_readers",
    "netReaderOnlineStatus": "online_network_readers",
}


def decode_document(content: bytes, root_name: str) -> dict[str, Any]:
    """Read the expected JSON or namespaced XML document."""
    content = content.lstrip()
    if content.startswith(b"<"):
        root = ET.fromstring(content)
        if root.tag.rsplit("}", 1)[-1] == root_name:
            document = _xml_value(root)
            if document is None or isinstance(document, dict):
                return document or {}
    else:
        payload = json.loads(content)
        if isinstance(payload, dict) and isinstance(payload.get(root_name), dict):
            return payload[root_name]
    raise ValueError(f"Expected an ISAPI {root_name} document")


def _xml_value(element: ET.Element) -> Any:
    if not len(element):
        return (element.text or "").strip() or None
    grouped: dict[str, list[Any]] = {}
    for child in element:
        grouped.setdefault(child.tag.rsplit("}", 1)[-1], []).append(_xml_value(child))
    return {
        name: items if len(items) > 1 else items[0] for name, items in grouped.items()
    }


def integer(value: Any) -> int | None:
    """Parse a decimal ISAPI field without treating a boolean as an integer."""
    if type(value) is int:
        return value
    if isinstance(value, str):
        try:
            return int(value, 10)
        except ValueError:
            pass
    return None


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return None
    try:
        number = float(value)
    except (ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def _boolean(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return {"true": True, "false": False}.get(value.strip().casefold())
    return None


def _items(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    return [] if value is None else [value]


def _access_values(document: dict[str, Any]) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for field, key, codes in (
        ("magneticStatus", "door_contact_circuit", CIRCUIT_STATES),
        ("doorLockStatus", "door_relay_circuit", CIRCUIT_STATES),
        ("doorStatus", "door_mode", DOOR_MODES),
    ):
        channels = _items(document.get(field))
        if channels and (code := integer(channels[0])) in codes:
            values[key] = codes[code]
            if field == "magneticStatus":
                # A fault reports an input without a known position.
                values["door_contact"] = {0: False, 1: True}.get(code)
    for key, (field, codes) in ACCESS_ENUMS.items():
        if (value := str(document.get(field, "")).strip().casefold()) in codes:
            values[key] = codes[value]
    for field, key in ACCESS_PORT_LISTS.items():
        ports = document.get(field)
        if isinstance(ports, list) or integer(ports) is not None:
            values[key] = sorted(
                {
                    port
                    for item in _items(ports)
                    if (port := integer(item)) is not None and port > 0
                }
            )
    if (low := _boolean(document.get("batteryLowVoltage"))) is not None:
        values["battery_low"] = low
    if (raw := integer(document.get("batteryVoltage"))) is not None and raw >= 0:
        values["battery_voltage_raw"] = raw
    if (count := integer(document.get("cardNum"))) is not None and count >= 0:
        values["card_count"] = count
    return values


def _system_values(document: dict[str, Any]) -> dict[str, Any]:
    values: dict[str, Any] = {}
    if (uptime := integer(document.get("deviceUpTime"))) is not None and uptime >= 0:
        values["uptime"] = uptime
    if isinstance(device_time := document.get("currentDeviceTime"), str):
        try:
            values["device_time"] = datetime.fromisoformat(device_time).isoformat()
        except ValueError:
            pass
    for list_key, item_key, field, key in (
        ("CPUList", "CPU", "cpuUtilization", "cpu_usage"),
        ("MemoryList", "Memory", "memoryUsage", "memory_used"),
        ("MemoryList", "Memory", "memoryAvailable", "memory_available"),
        ("TemperatureList", "Temperature", "temperature", "device_temperature"),
    ):
        group = document.get(list_key)
        items = (
            _items(group.get(item_key)) if isinstance(group, dict) else _items(group)
        )
        for item in items:
            if (
                isinstance(item, dict)
                and (value := _number(item.get(field))) is not None
            ):
                if key == "cpu_usage" and not 0 <= value <= 100:
                    continue
                if key.startswith("memory_") and value < 0:
                    continue
                values[key] = value
                break
    return values


def status_values(probe: str, document: dict[str, Any]) -> dict[str, Any]:
    """Select the documented fields that are safe to store and expose."""
    if probe == ACCESS_STATUS:
        return _access_values(document)
    if probe == SYSTEM_STATUS:
        return _system_values(document)
    if probe == "access_capabilities":
        return {
            "advertised_fields": sorted(
                key
                for key in (
                    "magneticStatus",
                    "doorLockStatus",
                    "doorStatus",
                    "batteryVoltage",
                    "batteryLowVoltage",
                    "batteryChargeStatus",
                    "powerSupplyStatus",
                    "sipStatus",
                    "voipStatus",
                    "netStatus",
                    "cardReaderOnlineStatus",
                    "alarmInStatus",
                    "alarmOutStatus",
                    "TFCardStatus",
                )
                if key in document
            )
        }
    if probe == "intercom_capabilities":
        return {
            key: value
            for key in (
                "isSupportCallStatus",
                "isSupportCallSignal",
                "isSupportKeyCfg",
                "isSupportVoiceConfiguration",
                "isSupportRingBackTone",
            )
            if (value := _boolean(document.get(key))) is not None
        }
    if probe == "two_way_audio":
        return {
            "channels": [
                channel_id
                for channel in _items(document.get("TwoWayAudioChannel"))
                if isinstance(channel, dict)
                and (channel_id := integer(channel.get("id"))) is not None
                and channel_id > 0
            ]
        }
    count = integer(document.get("userNumber"))
    return {"user_count": count} if count is not None and count >= 0 else {}


def history_record(record: dict[str, Any]) -> dict[str, Any]:
    """Return event metadata without credentials, media or personal identifiers."""
    event_code = (integer(record.get("major")), integer(record.get("minor")))
    values: dict[str, Any] = {
        "event_code": EVENT_LABELS.get(event_code, "unknown_access_event"),
        "major": event_code[0],
        "sub_event": event_code[1],
    }
    if event_code in AUTH_SUCCESS_EVENTS:
        values["result"] = "authorized"
    elif result := AUTH_FAILURE_RESULTS.get(values["event_code"]):
        values["result"] = result
    if isinstance(event_time := record.get("time"), str):
        try:
            values["date_time"] = datetime.fromisoformat(event_time).isoformat()
        except ValueError:
            pass
    for field, key in (("doorNo", "door_no"), ("serialNo", "serial_no")):
        if (value := integer(record.get(field))) is not None:
            values[key] = value
    if mode := verification_mode(record.get("currentVerifyMode")):
        values["verify_mode"] = mode
    return values


def verification_mode(value: Any) -> str | None:
    """Keep short protocol method tokens for aggregate authentication metrics."""
    if isinstance(value, str) and VERIFY_MODE_TOKEN.fullmatch(value):
        return value
    return None


class HikvisionObservations:
    """Store sanitized status shared by the ISAPI workers and entity listeners."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._samples: dict[str, dict[str, Any]] = {}
        self._probes: dict[str, dict[str, Any]] = {}
        self._door_event: tuple[bool, float] | None = None
        self._module_online: bool | None = None
        self._opening: tuple[float, datetime] | None = None
        self._command_started = float("-inf")
        self._command: dict[str, Any] = {}
        self._stream: dict[str, Any] = {"reconnections": 0}
        self._intercom: dict[str, Any] = {}
        self._last_intercom_event = float("-inf")
        self._sip_call_id: str | None = None
        self._sip_call: dict[str, str] = {}
        self._auth_counts: Counter[str] = Counter()
        self._auth_counts_by_method: dict[str, Counter[str]] = {}

    def _door_contact(self) -> bool | None:
        if self._door_event is not None:
            return self._door_event[0]
        return self._samples.get(ACCESS_STATUS, {}).get("door_contact")

    def _record_contact_open(self, at: float) -> None:
        self._opening = (at, datetime.now(UTC))
        self._confirm_contact()

    def _confirm_contact(self) -> None:
        if (
            self._command.get("door_no") != 1
            or self._opening is None
            or "contact_observed_at" in self._command
        ):
            return
        opened_at, observed = self._opening
        if 0 <= opened_at - self._command_started <= OPEN_CONTACT_WINDOW:
            self._command["contact_observed_at"] = observed.isoformat()

    def record_command(self, door_no: int, started: float) -> None:
        """Record an accepted unlock and correlate a near-term contact transition."""
        with self._lock:
            if started < self._command_started:
                return
            self._command_started = started
            self._command = {
                "door_no": door_no,
                "accepted_at": datetime.now(UTC).isoformat(),
                "request_latency_ms": round((time.monotonic() - started) * 1000),
            }
            self._confirm_contact()

    def record_access_event(self, event: str, door_no: int | None) -> None:
        """Apply explicit contact and secure-module events for the installed lock."""
        with self._lock:
            if event in ("security_module_online", "security_module_offline"):
                self._module_online = event == "security_module_online"
            if door_no in (None, 1) and event in (
                "door_opened",
                "door_closed",
                "door_forced_open",
                "door_open_too_long",
            ):
                previous_contact = self._door_contact()
                is_open = event != "door_closed"
                now = time.monotonic()
                self._door_event = (is_open, now)
                if (
                    event in ("door_opened", "door_forced_open")
                    and previous_contact is not True
                ):
                    self._record_contact_open(now)

    def record_auth_result(self, result: str, method: str | None) -> None:
        with self._lock:
            self._auth_counts[result] += 1
            if method is not None and (
                method in self._auth_counts_by_method
                or len(self._auth_counts_by_method) < 64
            ):
                self._auth_counts_by_method.setdefault(method, Counter())[result] += 1

    def record_probe(
        self, probe: str, started: float, values: dict[str, Any], error: str | None
    ) -> None:
        """Replace a complete reading and retain safe request diagnostics."""
        with self._lock:
            now = time.monotonic()
            metrics = self._probes.setdefault(probe, {"failures": 0})
            metrics["error"] = error
            metrics["latency_ms"] = round((now - started) * 1000)
            if error is None:
                metrics["last_success"] = datetime.now(UTC).isoformat()
            else:
                metrics["failures"] += 1
            previous_contact = self._door_contact()
            if probe == ACCESS_STATUS and "door_contact" in values:
                if self._door_event and self._door_event[1] > started:
                    # Discard a contact sample that may predate a newer live event.
                    values = {
                        key: value
                        for key, value in values.items()
                        if key not in ("door_contact", "door_contact_circuit")
                    }
                else:
                    self._door_event = None
                    if previous_contact is False and values["door_contact"] is True:
                        self._record_contact_open(now)
            self._samples[probe] = values

    def record_intercom_status(
        self, status: str, source: str, started: float | None = None
    ) -> bool:
        """Record genuine terminal signals independently of the ring timeout."""
        with self._lock:
            if started is not None and self._last_intercom_event > started:
                return False
            if source == "stream":
                self._last_intercom_event = time.monotonic()
            if self._intercom.get("status") != status:
                self._intercom["changed_at"] = datetime.now(UTC).isoformat()
            self._intercom.update(status=status, source=source)
            return True

    def record_sip_call(self, call_id: str, stage: str) -> bool:
        """Track the latest call reported by an external SIP server automation."""
        with self._lock:
            current_stage = self._sip_call.get("stage")
            if stage == "received":
                if call_id == self._sip_call_id:
                    return False
                self._sip_call_id = call_id
                self._sip_call = {}
            elif call_id != self._sip_call_id or current_stage in (stage, "ended"):
                return False
            now = datetime.now(UTC).isoformat()
            self._sip_call["stage"] = stage
            self._sip_call[f"{stage}_at"] = now
            return True

    def stream_connected(self) -> None:
        with self._lock:
            now = datetime.now(UTC).isoformat()
            if "disconnected_at" in self._stream:
                self._stream["reconnections"] += 1
                self._stream["last_gap"] = {
                    "start_time": self._stream.pop("disconnected_at"),
                    "end_time": now,
                }
            self._stream["connected_at"] = now

    def stream_disconnected(self) -> None:
        with self._lock:
            if "connected_at" in self._stream:
                self._stream.setdefault(
                    "disconnected_at", datetime.now(UTC).isoformat()
                )
            if self._door_event is not None:
                # The most recent state came from the stream. Wait for a fresh read.
                access = self._samples.get(ACCESS_STATUS, {})
                access.pop("door_contact", None)
                access.pop("door_contact_circuit", None)
            self._door_event = None
            self._module_online = None

    def stream_message(self, heartbeat: bool) -> None:
        with self._lock:
            now = datetime.now(UTC).isoformat()
            self._stream["last_message_at"] = now
            if heartbeat:
                self._stream["last_heartbeat_at"] = now

    def clear_samples(self) -> None:
        with self._lock:
            self._samples.clear()

    @property
    def intercom(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._intercom)

    @property
    def stream(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._stream)

    @property
    def last_command(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._command)

    @property
    def sip_call(self) -> dict[str, str]:
        with self._lock:
            return dict(self._sip_call)

    @property
    def readings(self) -> dict[str, Any]:
        """Expose a snapshot for Home Assistant entities."""
        with self._lock:
            readings = {
                key: value
                for probe in (ACCESS_STATUS, SYSTEM_STATUS, "user_count")
                for key, value in self._samples.get(probe, {}).items()
            }
            if self._door_event is not None:
                readings["door_contact"] = self._door_event[0]
            if self._module_online is not None:
                readings["security_module"] = self._module_online
            if self._sip_call:
                readings["sip_call_stage"] = self._sip_call["stage"]
            return readings

    @property
    def diagnostics(self) -> dict[str, Any]:
        """Return summary data without any raw device response bodies."""
        with self._lock:
            return {
                "probes": {key: dict(values) for key, values in self._probes.items()},
                "capabilities": {
                    probe: dict(self._samples[probe])
                    for probe in (
                        "access_capabilities",
                        "intercom_capabilities",
                        "two_way_audio",
                    )
                    if probe in self._samples
                },
                "stream": dict(self._stream),
                "intercom": dict(self._intercom),
                "sip_call": dict(self._sip_call),
                "last_open_command": dict(self._command),
                "authentication_counts_since_startup": dict(self._auth_counts),
                "authentication_counts_by_method": {
                    method: dict(counts)
                    for method, counts in self._auth_counts_by_method.items()
                },
            }
