"""Canonical hashes shared with the adaptor's Go golden fixtures.

Canonical form: UTF-8 JSON with sorted keys, compact separators, no ASCII or
HTML escaping, and timestamps rewritten to six fractional digits with a
``Z`` suffix. The digest is lowercase SHA-256 hex. Callers hash only values
that already passed strict validation.

``canonical_receipt_hash`` covers the whole outbound DraftForge -> adaptor
receipt, delivery UUID included. ``import_source_hash`` covers only the
immutable SFG source facts of an inbound contact: never ``user_id`` or
``org_user_id``, which are mutable DraftForge associations.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from org.models_promotion_sync import ImmutableFieldError

__all__ = [
    "ImmutableFieldError",
    "IMPORT_SOURCE_FIELDS",
    "canonical_json",
    "canonical_receipt_hash",
    "canonical_receipt_json",
    "format_timestamp",
    "import_source_hash",
]

IMPORT_SOURCE_FIELDS = (
    "source_contact_id",
    "event_id",
    "discord_id",
    "recorded_at",
    "contact_method",
    "linkage",
)

_WIRE_TIMESTAMP = re.compile(
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z", re.ASCII
)


def format_timestamp(value: datetime | str) -> str:
    """``YYYY-MM-DDTHH:MM:SS.ffffffZ`` for an aware datetime or a wire string."""
    if isinstance(value, str):
        if not _WIRE_TIMESTAMP.fullmatch(value):
            raise ValueError("timestamp is not a UTC Z timestamp")
        value = datetime.fromisoformat(value[:-1] + "+00:00")
    if value.tzinfo is None:
        raise ValueError("timestamp must be timezone-aware")
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def canonical_receipt_json(payload: Mapping[str, Any]) -> str:
    return canonical_json({**payload, "sent_at": format_timestamp(payload["sent_at"])})


def canonical_receipt_hash(payload: Mapping[str, Any]) -> str:
    return _sha256(canonical_receipt_json(payload))


def import_source_hash(entry: Mapping[str, Any], *, source: str = "sfg") -> str:
    facts: dict[str, Any] = {field: entry[field] for field in IMPORT_SOURCE_FIELDS}
    facts["recorded_at"] = format_timestamp(facts["recorded_at"])
    facts["source"] = source
    return _sha256(canonical_json(facts))
