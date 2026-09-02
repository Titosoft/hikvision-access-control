"""Standalone parser tests."""

import sys
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

MODULE_PATH = (
    Path(__file__).parents[1]
    / "custom_components"
    / "hikvision_access_control"
    / "parser.py"
)
SPEC = spec_from_file_location("hikvision_multipart_parser", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)
HikvisionMultipartParser = MODULE.HikvisionMultipartParser


def test_chunked_json_and_jpeg() -> None:
    event = (
        b'{"eventType":"AccessControllerEvent",'
        b'"AccessControllerEvent":{"subEventType":75}}'
    )
    jpeg = b"\xff\xd8test-image\xff\xd9"
    payload = (
        b"--MIME_boundary\r\n"
        b'Content-Disposition: form-data; name="AccessControllerEvent"\r\n'
        b"Content-Type: application/json\r\nContent-Length: "
        + str(len(event)).encode()
        + b"\r\n\r\n"
        + event
        + b'\r\n--MIME_boundary\r\nContent-Disposition: form-data; name="Picture"\r\n'
        b"Content-Type: image/jpeg\r\nContent-Length: "
        + str(len(jpeg)).encode()
        + b"\r\n\r\n"
        + jpeg
        + b"\r\n"
    )
    parser = HikvisionMultipartParser()
    parts = []
    for start in range(0, len(payload), 7):
        parts.extend(parser.feed(payload[start : start + 7]))
    assert [part.body for part in parts] == [event, jpeg]


def test_every_byte_can_arrive_in_a_separate_chunk() -> None:
    body = b'{"eventType":"AccessControllerEvent"}'
    payload = (
        b"preamble\r\n--device-boundary\r\n"
        b"Content-Type: application/json\r\n"
        b"Content-Length: "
        + str(len(body)).encode()
        + b"\r\n\r\n"
        + body
        + b"\r\n--device-boundary--\r\n"
    )
    parser = HikvisionMultipartParser.from_content_type(
        'multipart/mixed; boundary="device-boundary"'
    )

    parts = []
    for byte in payload:
        parts.extend(parser.feed(bytes([byte])))

    assert len(parts) == 1
    assert parts[0].headers["content-type"] == "application/json"
    assert parts[0].body == body


def test_part_without_content_length_uses_next_boundary() -> None:
    body = b'{"ok":true}'
    payload = (
        b"--MIME_boundary\nContent-Type: application/json\n\n"
        + body
        + b"\n--MIME_boundary--\n"
    )

    parts = HikvisionMultipartParser().feed(payload)

    assert len(parts) == 1
    assert parts[0].body == body


def test_rejects_empty_boundary() -> None:
    try:
        HikvisionMultipartParser(b"")
    except ValueError as err:
        assert "boundary" in str(err).lower()
    else:
        raise AssertionError("An empty boundary must be rejected")
