"""Parser for Hikvision multipart ISAPI event streams."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(slots=True)
class MultipartPart:
    """A decoded multipart part."""

    headers: dict[str, str]
    body: bytes


class HikvisionMultipartParser:
    """Incrementally decode Content-Length framed multipart messages."""

    def __init__(self, boundary: bytes = b"MIME_boundary") -> None:
        boundary = boundary.strip().strip(b'"')
        if boundary.startswith(b"--"):
            boundary = boundary[2:]
        if not boundary:
            raise ValueError("Multipart boundary cannot be empty")
        self._boundary = b"--" + boundary
        self._buffer = bytearray()

    @classmethod
    def from_content_type(cls, content_type: str | None) -> HikvisionMultipartParser:
        """Build a parser using a boundary from Content-Type."""
        if content_type:
            match = re.search(
                r"boundary\s*=\s*(?:\"([^\"]+)\"|([^;\s]+))", content_type
            )
            if match:
                return cls((match.group(1) or match.group(2)).encode())
        return cls()

    def feed(self, data: bytes) -> list[MultipartPart]:
        """Feed bytes and return every complete part."""
        if data:
            self._buffer.extend(data)

        parts: list[MultipartPart] = []
        while True:
            boundary_at = self._buffer.find(self._boundary)
            if boundary_at < 0:
                self._trim_preamble()
                break
            if boundary_at:
                del self._buffer[:boundary_at]

            header_start = len(self._boundary)
            if self._buffer[header_start : header_start + 2] == b"--":
                self._buffer.clear()
                break
            while len(self._buffer) > header_start and self._buffer[header_start] in (
                10,
                13,
            ):
                header_start += 1

            header_end, separator_length = self._find_header_end(header_start)
            if header_end < 0:
                break

            headers = self._parse_headers(bytes(self._buffer[header_start:header_end]))
            try:
                content_length = int(headers["content-length"])
            except (KeyError, ValueError):
                next_boundary = self._buffer.find(
                    self._boundary, header_end + separator_length
                )
                if next_boundary < 0:
                    break
                body = bytes(
                    self._buffer[header_end + separator_length : next_boundary]
                ).rstrip(b"\r\n")
                del self._buffer[:next_boundary]
                parts.append(MultipartPart(headers, body))
                continue

            body_start = header_end + separator_length
            body_end = body_start + content_length
            if len(self._buffer) < body_end:
                break

            body = bytes(self._buffer[body_start:body_end])
            del self._buffer[:body_end]
            parts.append(MultipartPart(headers, body))

        return parts

    def _find_header_end(self, start: int) -> tuple[int, int]:
        crlf = self._buffer.find(b"\r\n\r\n", start)
        lf = self._buffer.find(b"\n\n", start)
        if crlf >= 0 and (lf < 0 or crlf <= lf):
            return crlf, 4
        if lf >= 0:
            return lf, 2
        return -1, 0

    @staticmethod
    def _parse_headers(raw_headers: bytes) -> dict[str, str]:
        headers: dict[str, str] = {}
        for raw_line in raw_headers.replace(b"\r\n", b"\n").split(b"\n"):
            if b":" not in raw_line:
                continue
            key, value = raw_line.split(b":", 1)
            headers[key.decode("ascii", "ignore").strip().lower()] = value.decode(
                "utf-8", "replace"
            ).strip()
        return headers

    def _trim_preamble(self) -> None:
        keep = len(self._boundary) + 4
        if len(self._buffer) > keep:
            del self._buffer[:-keep]
