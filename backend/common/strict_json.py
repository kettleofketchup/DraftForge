"""Strict JSON decoding and canonical integer IDs, with no Django imports.

Plain ``json.loads`` keeps the last of two duplicate keys, accepts ``NaN``
and ``Infinity`` and lets ``"\\ud800"`` through as a lone surrogate. The
integration contract forbids all three, so both the settings loader
(``config.promotion_sync``) and the request parser (``org.integration``) go
through ``loads_strict``. Settings import this module, so it must stay free
of Django and DRF.
"""

import json
import re
from typing import Any

MAX_DEPTH = 32
INT64_MAX = 2**63 - 1
_CANONICAL_ID = re.compile(r"[1-9][0-9]{0,18}")


class StrictJSONError(ValueError):
    """Rejected document. ``reason`` is a fixed word, never document text."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    obj: dict[str, Any] = {}
    for key, value in pairs:
        if key in obj:
            raise StrictJSONError("duplicate_key")
        obj[key] = value
    return obj


def _non_finite(_: str) -> Any:
    raise StrictJSONError("non_finite_number")


def _check_strings_and_depth(root: Any) -> None:
    stack: list[tuple[Any, int]] = [(root, 1)]
    while stack:
        node, depth = stack.pop()
        if isinstance(node, str):
            _check_string(node)
            continue
        if not isinstance(node, dict | list):
            continue
        if depth > MAX_DEPTH:
            raise StrictJSONError("too_deep")
        if isinstance(node, dict):
            for key, value in node.items():
                _check_string(key)
                stack.append((value, depth + 1))
        else:
            stack.extend((value, depth + 1) for value in node)


def _check_string(value: str) -> None:
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        raise StrictJSONError("invalid_string") from None


def loads_strict(data: bytes | str) -> Any:
    """Decode one JSON value, rejecting anything the contract forbids.

    Refuses invalid UTF-8 (including a BOM), duplicate object keys at any
    depth, ``NaN``/``Infinity``, lone surrogate escapes, trailing data and
    nesting deeper than ``MAX_DEPTH``.
    """
    if isinstance(data, bytes):
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            raise StrictJSONError("invalid_utf8") from None
    else:
        text = data
    try:
        value = json.loads(text, object_pairs_hook=_pairs, parse_constant=_non_finite)
    except StrictJSONError:
        raise
    except RecursionError:
        raise StrictJSONError("too_deep") from None
    except ValueError:
        raise StrictJSONError("malformed") from None
    _check_strings_and_depth(value)
    return value


def parse_canonical_id(value: Any) -> int | None:
    """A positive signed-int64 written as a canonical decimal string, else None.

    No JSON numbers, signs, leading zeros, whitespace, exponents or non-ASCII
    digits.
    """
    if not isinstance(value, str) or not _CANONICAL_ID.fullmatch(value):
        return None
    number = int(value)
    return number if number <= INT64_MAX else None
