"""Signed keyset cursors for integration list routes.

A cursor carries the org, the resource it pages (for example
``event_recipients:720``), the last sort key returned
and a fingerprint of the mapping or membership the pages were computed from.
It is signed with ``SECRET_KEY`` under its own salt, so a client cannot edit
the key or move a cursor to another org or resource. A cursor whose
fingerprint no longer matches yields 409 ``mapping_changed``: the client
restarts from the first page rather than silently crossing scopes.
Cursors are opaque, ASCII and at most ``MAX_CURSOR_BYTES`` long. Callers
never accept URLs in place of a cursor.
"""

from __future__ import annotations

from typing import Any

from django.core import signing

from org.integration.errors import IntegrationError

MAX_CURSOR_BYTES = 2048
_SALT = "org.integration.cursor.v1"
_VERSION = 1


def _invalid() -> IntegrationError:
    return IntegrationError("invalid_cursor", 400)


def encode_cursor(
    *, org_id: int, resource: str, key: list[Any], fingerprint: str
) -> str:
    """Sign the next-page position. ``key`` must be JSON-serializable.

    Raises ValueError if the result would exceed ``MAX_CURSOR_BYTES``: a sort
    key that large is a programming error, not a client error.
    """
    raw = signing.dumps(
        {"v": _VERSION, "o": org_id, "r": resource, "k": key, "f": fingerprint},
        salt=_SALT,
    )
    if len(raw) > MAX_CURSOR_BYTES:
        raise ValueError("cursor exceeds the maximum length")
    return raw


def decode_cursor(
    raw: str, *, org_id: int, resource: str, fingerprint: str
) -> list[Any]:
    """Return the sort key from a cursor issued for this org and resource.

    400 ``invalid_cursor`` for anything malformed, oversized, unsigned or
    issued for another org/resource; 409 ``mapping_changed`` when the
    fingerprint differs from the current one.
    """
    if not raw or len(raw) > MAX_CURSOR_BYTES or not raw.isascii():
        raise _invalid()
    try:
        payload = signing.loads(raw, salt=_SALT)
    except signing.BadSignature:
        raise _invalid() from None
    except ValueError:
        raise _invalid() from None
    if (
        not isinstance(payload, dict)
        or payload.get("v") != _VERSION
        or payload.get("o") != org_id
        or payload.get("r") != resource
        or not isinstance(payload.get("k"), list)
        or not isinstance(payload.get("f"), str)
    ):
        raise _invalid()
    if payload["f"] != fingerprint:
        raise IntegrationError("mapping_changed", 409)
    return payload["k"]
