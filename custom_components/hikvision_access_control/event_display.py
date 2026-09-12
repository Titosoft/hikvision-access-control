"""Readable unknown event types for Home Assistant entity displays."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

UNKNOWN_EVENT_LABELS = {
    "unknown_access_event": "Unknown access event",
    "unknown_isapi_event": "Unknown ISAPI event",
    "unknown_sdk_event": "Unknown SDK event",
}


def event_display_type(
    event: Mapping[str, Any] | None, labels: Mapping[str, str]
) -> str | None:
    """Keep known types stable and append the source of unknown events."""
    if not event:
        return None
    event_code = event.get("event", "unknown_access_event")
    if event_code not in UNKNOWN_EVENT_LABELS:
        return event_code
    if event_code == "unknown_isapi_event":
        detail = str(event.get("raw_event_type") or "unknown")
    elif event_code == "unknown_sdk_event":
        detail = str(
            event.get("sdk_command_hex") or event.get("sdk_command") or "unknown"
        )
    else:
        major = event.get("major")
        sub_event = event.get("sub_event")
        detail = f"{major if major is not None else '?'}/"
        detail += str(sub_event if sub_event is not None else "?")
    detail = " ".join(detail.split()) or "unknown"
    label = labels.get(event_code, UNKNOWN_EVENT_LABELS[event_code])
    # Sensor states are limited to 255 characters. Keep the full source in
    # raw_event_type; only shorten the presentation, including its parentheses.
    label = label[:200]
    budget = 255 - len(label) - 3
    if len(detail) > budget:
        detail = detail[: budget - 1] + "…"
    return f"{label} ({detail})"
