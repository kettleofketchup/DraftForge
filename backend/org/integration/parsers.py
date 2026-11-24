"""Strict request parsing and field validation for the integration routes.

``IntegrationJSONParser`` refuses anything the contract forbids at the
document level (size, content type, UTF-8, duplicate keys, non-finite
numbers, trailing data, non-object top level). The ``parse_*`` helpers then
check each field: exact key sets at every level, canonical decimal-string
IDs, UTC ``Z`` timestamps, lowercase UUIDs and hashes, enums and batch
bounds. Every failure is an ``IntegrationError`` that names the field path
and never the value.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

from django.utils import timezone
from django.utils.http import parse_header_parameters
from rest_framework.parsers import BaseParser
from rest_framework.request import Request

from common.strict_json import StrictJSONError, loads_strict, parse_canonical_id
from org.integration.errors import IntegrationError, invalid

MAX_BODY_BYTES = 65_536
MAX_BATCH = 100
DEFAULT_LIMIT = 100
MAX_FUTURE = timedelta(minutes=5)

_TIMESTAMP = re.compile(
    r"(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.(\d{1,6}))?Z", re.ASCII
)
_UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
_HASH = re.compile(r"[0-9a-f]{64}")
_JSON_PROBLEMS = {
    "invalid_utf8": "is not valid UTF-8",
    "duplicate_key": "has a duplicate object key",
    "non_finite_number": "has a non-finite number",
    "invalid_string": "has an invalid string",
    "too_deep": "is nested too deeply",
}


class StrictObject(dict):
    """A request body that went through ``IntegrationJSONParser``."""


def _too_large() -> IntegrationError:
    return IntegrationError("request_too_large", 413)


class IntegrationJSONParser(BaseParser):
    media_type = "application/json"

    def parse(
        self,
        stream: Any,
        media_type: str | None = None,
        parser_context: dict[str, Any] | None = None,
    ) -> StrictObject:
        _, params = parse_header_parameters(media_type or "")
        charset = params.get("charset")
        if charset is not None and charset.lower() not in ("utf-8", "utf8"):
            raise IntegrationError("unsupported_media_type", 415)
        request = (parser_context or {}).get("request")
        declared = request.META.get("CONTENT_LENGTH") if request is not None else None
        if declared and declared.isdigit() and int(declared) > MAX_BODY_BYTES:
            raise _too_large()
        data = stream.read(MAX_BODY_BYTES + 1)
        if len(data) > MAX_BODY_BYTES:
            raise _too_large()
        try:
            value = loads_strict(data)
        except StrictJSONError as exc:
            raise invalid(
                "body", _JSON_PROBLEMS.get(exc.reason, "is not valid JSON")
            ) from None
        if not isinstance(value, dict):
            raise invalid("body", "must be a JSON object")
        return StrictObject(value)


def json_body(request: Request) -> StrictObject:
    """The parsed body, refusing a POST that skipped the strict parser.

    DRF hands views ``{}`` for an empty body or one with no content type
    instead of calling a parser, so views read the body through this.
    """
    data = request.data
    if not isinstance(data, StrictObject):
        if not request.content_type:
            raise IntegrationError("unsupported_media_type", 415)
        raise invalid("body", "must be a JSON object")
    return data


def expect_object(value: Any, path: str, keys: Iterable[str]) -> dict[str, Any]:
    """``value`` must be an object with exactly ``keys``: none missing, none extra."""
    if not isinstance(value, dict):
        raise invalid(path, "must be an object")
    expected = set(keys)
    missing = sorted(expected - value.keys())
    if missing:
        raise invalid(_join(path, missing[0]), "is required")
    unknown = value.keys() - expected
    if unknown:
        raise invalid(path, "has an unknown field")
    return value


def _join(path: str, key: str) -> str:
    return f"{path}.{key}" if path else key


def parse_id(value: Any, path: str, *, nullable: bool = False) -> int | None:
    """A canonical positive decimal string within signed int64."""
    if value is None and nullable:
        return None
    number = parse_canonical_id(value)
    if number is None:
        raise invalid(path, "must be a canonical positive decimal string")
    return number


def format_id(value: int | None) -> str | None:
    return None if value is None else str(value)


def parse_timestamp(value: Any, path: str, *, now: datetime | None = None) -> datetime:
    """RFC 3339 UTC with a ``Z`` suffix, at most six fractional digits and
    at most five minutes in the future."""
    match = _TIMESTAMP.fullmatch(value) if isinstance(value, str) else None
    if match is None:
        raise invalid(path, "must be a UTC timestamp like 2026-11-24T11:30:00Z")
    year, month, day, hour, minute, second, fraction = match.groups()
    try:
        parsed = datetime(
            int(year),
            int(month),
            int(day),
            int(hour),
            int(minute),
            int(second),
            int((fraction or "").ljust(6, "0")),
            tzinfo=UTC,
        )
    except ValueError:
        raise invalid(path, "is not a real date and time") from None
    if parsed > (now or timezone.now()) + MAX_FUTURE:
        raise invalid(path, "is too far in the future")
    return parsed


def parse_uuid(value: Any, path: str) -> str:
    if not isinstance(value, str) or not _UUID.fullmatch(value):
        raise invalid(path, "must be a canonical lowercase UUID")
    return value


def parse_hash(value: Any, path: str) -> str:
    if not isinstance(value, str) or not _HASH.fullmatch(value):
        raise invalid(path, "must be 64 lowercase hex characters")
    return value


def parse_choice(value: Any, path: str, choices: Sequence[str]) -> str:
    if not isinstance(value, str) or value not in choices:
        raise invalid(path, "is not an allowed value")
    return value


def parse_batch(
    value: Any, path: str, *, min_items: int = 1, max_items: int = MAX_BATCH
) -> list[Any]:
    if not isinstance(value, list):
        raise invalid(path, "must be an array")
    if not min_items <= len(value) <= max_items:
        raise invalid(path, f"must hold {min_items} to {max_items} items")
    return value


def parse_limit(raw: str | None) -> int:
    """The ``limit`` query parameter: 1 to ``MAX_BATCH``, default ``DEFAULT_LIMIT``."""
    if raw is None:
        return DEFAULT_LIMIT
    number = parse_canonical_id(raw)
    if number is None or number > MAX_BATCH:
        raise invalid("limit", f"must be a whole number from 1 to {MAX_BATCH}")
    return number
