"""Display and automation contracts with lightweight Home Assistant boundaries."""

from __future__ import annotations

import asyncio
import json
import sys
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

COMPONENT_PATH = (
    Path(__file__).parents[1] / "custom_components" / "hikvision_access_control"
)


@pytest.fixture
def display_modules(monkeypatch):
    """Load real entity code while isolating Home Assistant runtime services."""

    class Entity:
        def async_write_ha_state(self):
            self.writes = getattr(self, "writes", 0) + 1

    class EventEntity(Entity):
        def _trigger_event(self, event_type, attributes):
            # Home Assistant rejects event types not declared by the entity.
            assert event_type in self._attr_event_types
            self.fired = (event_type, attributes)

    modules = {
        "homeassistant": {},
        "homeassistant.components": {},
        "homeassistant.components.event": {"EventEntity": EventEntity},
        "homeassistant.components.sensor": {
            "SensorEntity": Entity,
            "SensorDeviceClass": SimpleNamespace(ENUM="enum", TIMESTAMP="timestamp"),
        },
        "homeassistant.const": {
            "EntityCategory": SimpleNamespace(DIAGNOSTIC="diagnostic")
        },
        "homeassistant.core": {"HomeAssistant": object},
        "homeassistant.helpers": {},
        "homeassistant.helpers.entity": {"Entity": Entity},
        "homeassistant.helpers.entity_platform": {
            "AddConfigEntryEntitiesCallback": object
        },
        "homeassistant.helpers.device_registry": {"DeviceInfo": dict},
        "homeassistant.util": {"dt": SimpleNamespace()},
    }

    async def translations(hass, language, category, integrations):
        assert language == hass.config.language
        assert category == "entity"
        assert integrations == {"hikvision_access_control"}
        values = json.loads(
            (COMPONENT_PATH / "translations" / f"{language}.json").read_text()
        )["entity"]["sensor"]["last_event"]["state"]
        prefix = "component.hikvision_access_control.entity.sensor.last_event.state."
        return {f"{prefix}{key}": value for key, value in values.items()}

    modules["homeassistant.helpers.translation"] = {
        "async_get_translations": translations
    }
    for name, attributes in modules.items():
        module = ModuleType(name)
        module.__dict__.update(attributes)
        monkeypatch.setitem(sys.modules, name, module)

    package_name = "hikvision_display_test"
    package = ModuleType(package_name)
    package.__path__ = [str(COMPONENT_PATH)]
    package.HikvisionConfigEntry = object
    monkeypatch.setitem(sys.modules, package_name, package)
    loaded = {}
    names = ("const", "parser", "api", "event_display", "entity", "event", "sensor")
    for name in names:
        qualified_name = f"{package_name}.{name}"
        spec = spec_from_file_location(qualified_name, COMPONENT_PATH / f"{name}.py")
        module = module_from_spec(spec)
        monkeypatch.setitem(sys.modules, qualified_name, module)
        spec.loader.exec_module(module)
        loaded[name] = module
    return SimpleNamespace(**loaded)


@pytest.mark.parametrize("language", ["pt-BR", "en"])
def test_unknown_source_is_visible_and_automation_code_is_stable(
    display_modules, language
):
    modules = display_modules
    api = modules.api.HikvisionAccessAPI(
        host="192.168.1.100",
        port=443,
        username="test",
        password="test",
        use_https=True,
        verify_ssl=False,
        configured_name="Gate",
    )
    labels = asyncio.run(
        modules.entity.async_get_unknown_event_labels(
            SimpleNamespace(config=SimpleNamespace(language=language))
        )
    )
    entity = modules.event.HikvisionAccessEvent(api, labels)
    sensor = modules.sensor.HikvisionLastEventSensor(api, labels)
    other_entity = modules.event.HikvisionAccessEvent(api, labels)

    for raw_type in ("changedCallStatus", "VideoIntercomEvent", "videoloss"):
        api._handle_event_payload({"eventType": raw_type, "eventState": "active"})
        entity._handle_api_update()
        expected = f"{labels['unknown_isapi_event']} ({raw_type})"
        assert entity.fired[0] == sensor.native_value == expected
        assert sensor.native_value in sensor.options
        assert len(entity._attr_event_types) == len(modules.event.EVENT_TYPES) + 1
        assert len(sensor.options) == len(modules.sensor.EVENT_OPTIONS) + 1
        for attributes in (entity.fired[1], sensor.extra_state_attributes):
            assert attributes["event_code"] == "unknown_isapi_event"
            assert attributes["raw_event_type"] == raw_type
        assert api.last_event["event"] == "unknown_isapi_event"
    assert other_entity._attr_event_types == modules.event.EVENT_TYPES

    api._handle_event_payload(
        {
            "eventType": "AccessControllerEvent",
            "AccessControllerEvent": {"majorEventType": 5, "subEventType": 999},
        }
    )
    entity._handle_api_update()
    assert entity.fired[0] == f"{labels['unknown_access_event']} (5/999)"
    assert sensor.native_value == entity.fired[0]
    assert entity.fired[1]["event_code"] == "unknown_access_event"

    api._handle_event_payload(
        {
            "eventType": "AccessControllerEvent",
            "AccessControllerEvent": {"majorEventType": 5, "subEventType": 75},
        }
    )
    entity._handle_api_update()
    assert entity.fired[0] == sensor.native_value == "face_authenticated"
    assert entity.fired[1]["event_code"] == "face_authenticated"
    assert entity._attr_event_types == modules.event.EVENT_TYPES
    assert sensor.options == modules.sensor.EVENT_OPTIONS


def test_display_handles_missing_codes_and_limits_long_names(display_modules):
    display = display_modules.event_display.event_display_type
    assert display(None, {}) is None
    assert display({"event": "unknown_access_event", "major": 0}, {}) == (
        "Unknown access event (0/?)"
    )
    assert display({"event": "unknown_isapi_event"}, {}) == (
        "Unknown ISAPI event (unknown)"
    )
    payload = {"event": "unknown_isapi_event", "raw_event_type": "x" * 400}
    formatted = display(payload, {})
    assert len(formatted) == 255
    assert formatted.endswith("…)")
    assert payload["raw_event_type"] == "x" * 400
