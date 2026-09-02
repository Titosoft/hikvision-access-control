"""Standalone parser tests."""

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys


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
    event = b'{"eventType":"AccessControllerEvent","AccessControllerEvent":{"subEventType":75}}'
    jpeg = b"\xff\xd8test-image\xff\xd9"
    payload = (
        b"--MIME_boundary\r\nContent-Disposition: form-data; name=\"AccessControllerEvent\"\r\n"
        b"Content-Type: application/json\r\nContent-Length: "
        + str(len(event)).encode()
        + b"\r\n\r\n"
        + event
        + b"\r\n--MIME_boundary\r\nContent-Disposition: form-data; name=\"Picture\"\r\n"
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
