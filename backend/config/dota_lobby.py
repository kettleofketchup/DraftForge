"""dota_lobby integration settings, parsed once from the environment.

Three places read these values: `backend.settings` (the web process),
`config.settings_celery` (the worker, which has no DB) and `lobby.client`,
which reads the environment directly like `app.internal_client` does so it
works in both processes. They all go through `DotaLobbyConfig.from_env()` so
the parsing cannot drift.

Environment variables:

    DOTA_LOBBY_ENABLED                    global switch, default off
    DOTA_LOBBY_URL                        service base URL, without /v1
    DOTA_LOBBY_API_KEY                    sent as X-API-Key (secret)
    DOTA_LOBBY_WEBHOOK_SECRET             webhook HMAC secret(s), comma-separated
                                          during rotation (secret)
    DOTA_LOBBY_TIMEOUT_SECONDS            per-request timeout, default 15
    DOTA_LOBBY_REF_PREFIX                 external_ref prefix, default "game"
    DOTA_LOBBY_WEBHOOK_TOLERANCE_SECONDS  webhook clock skew allowed, default 300
    DOTA_LOBBY_REGION                     default region name, default none
"""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from dataclasses import dataclass, field

from django.core.exceptions import ImproperlyConfigured

DEFAULT_TIMEOUT_SECONDS = 15.0
DEFAULT_REF_PREFIX = "game"
DEFAULT_WEBHOOK_TOLERANCE_SECONDS = 300

# dota_lobby allows external_ref = [A-Za-z0-9._:-]{1,128}. The prefix may not
# contain ":", which separates it from the game pk.
_REF_PREFIX_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
_TRUE = ("1", "true", "yes", "on")


def _bool(env: Mapping[str, str], key: str) -> bool:
    return env.get(key, "").strip().lower() in _TRUE


def _number(env: Mapping[str, str], key: str, default: float, cast: type) -> float:
    raw = env.get(key, "").strip()
    if not raw:
        return default
    try:
        value = cast(raw)
    except ValueError:
        raise ImproperlyConfigured(f"{key} must be a number, got {raw!r}") from None
    if value <= 0:
        raise ImproperlyConfigured(f"{key} must be greater than 0, got {raw!r}")
    return value


def _base_url(raw: str) -> str:
    url = raw.strip().rstrip("/")
    # Accept a URL copied with the API prefix; the client adds /v1 itself.
    if url.endswith("/v1"):
        url = url[: -len("/v1")]
    return url


@dataclass(frozen=True)
class DotaLobbyConfig:
    enabled: bool = False
    url: str = ""
    api_key: str = field(default="", repr=False)
    webhook_secrets: tuple[str, ...] = field(default=(), repr=False)
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    ref_prefix: str = DEFAULT_REF_PREFIX
    webhook_tolerance_seconds: int = DEFAULT_WEBHOOK_TOLERANCE_SECONDS
    region: str = ""

    @property
    def is_configured(self) -> bool:
        """True when a client can be built (a URL is set)."""
        return bool(self.url)

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> DotaLobbyConfig:
        env = os.environ if env is None else env
        prefix = env.get("DOTA_LOBBY_REF_PREFIX", "").strip() or DEFAULT_REF_PREFIX
        if not _REF_PREFIX_RE.match(prefix):
            raise ImproperlyConfigured(
                "DOTA_LOBBY_REF_PREFIX must be 1-64 letters, digits, '.', '_' or '-'"
            )
        secrets = tuple(
            s.strip()
            for s in env.get("DOTA_LOBBY_WEBHOOK_SECRET", "").split(",")
            if s.strip()
        )
        return cls(
            enabled=_bool(env, "DOTA_LOBBY_ENABLED"),
            url=_base_url(env.get("DOTA_LOBBY_URL", "")),
            api_key=env.get("DOTA_LOBBY_API_KEY", "").strip(),
            webhook_secrets=secrets,
            timeout_seconds=float(
                _number(
                    env, "DOTA_LOBBY_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS, float
                )
            ),
            ref_prefix=prefix,
            webhook_tolerance_seconds=int(
                _number(
                    env,
                    "DOTA_LOBBY_WEBHOOK_TOLERANCE_SECONDS",
                    DEFAULT_WEBHOOK_TOLERANCE_SECONDS,
                    int,
                )
            ),
            region=env.get("DOTA_LOBBY_REGION", "").strip(),
        )
