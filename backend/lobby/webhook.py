"""dota_lobby webhook signatures.

`X-Dota-Lobby-Signature` is `v1=` and the hex HMAC-SHA256 of
`"<X-Dota-Lobby-Timestamp>.<raw body>"` under the webhook's secret. During a
rotation the header carries several comma-separated signatures, and
DOTA_LOBBY_WEBHOOK_SECRET may list several secrets: any secret matching any
signature is accepted. The timestamp must be within the tolerance of this
host's clock, which stops replays.
"""

from __future__ import annotations

import hashlib
import hmac
import time
from collections.abc import Iterable

SIGNATURE_VERSION = "v1="


def sign(secret: str, timestamp: str, body: bytes) -> str:
    mac = hmac.new(secret.encode(), timestamp.encode() + b"." + body, hashlib.sha256)
    return SIGNATURE_VERSION + mac.hexdigest()


def verify_signature(
    secrets: Iterable[str],
    timestamp: str | None,
    signature_header: str | None,
    body: bytes,
    *,
    tolerance_seconds: int,
    now: float | None = None,
) -> bool:
    timestamp = (timestamp or "").strip()
    if not timestamp.isascii() or not timestamp.isdigit():
        return False
    now = time.time() if now is None else now
    if abs(now - int(timestamp)) > tolerance_seconds:
        return False
    sent = [s.strip() for s in (signature_header or "").split(",") if s.strip()]
    if not sent:
        return False
    matched = False
    for secret in secrets:
        expected = sign(secret, timestamp, body)
        for candidate in sent:
            # No early exit: the comparison count does not depend on which
            # secret or signature matched.
            matched |= hmac.compare_digest(expected, candidate)
    return matched
