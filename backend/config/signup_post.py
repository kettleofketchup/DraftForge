"""Discord signup-post serialisation settings, parsed once from the environment.

`backend.settings` (web) and `config.settings_celery` (worker) both build
`SIGNUP_POST` through `SignupPostConfig.from_env()`, so the two processes agree
on the debounce and lock timings.

Environment variables:

    SIGNUP_POST_DEBOUNCE_SECONDS  delay before a queued post edit runs, default 2
    SIGNUP_POST_LOCK_SECONDS      per-event edit lock lifetime, default 90
    SIGNUP_POST_READ_RETRIES      retries when the signup list cannot be read,
                                  default 3
    SIGNUP_POST_DISABLED          skip the pending flag and lock (every change
                                  edits the post directly); DISABLE_CACHE also
                                  disables it
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass

from django.core.exceptions import ImproperlyConfigured

DEFAULT_DEBOUNCE_SECONDS = 2
DEFAULT_LOCK_SECONDS = 90
DEFAULT_READ_RETRIES = 3
PENDING_TTL_MARGIN_SECONDS = 10
_TRUE = ("1", "true", "yes", "on")


def _bool(env: Mapping[str, str], key: str, default: bool) -> bool:
    raw = env.get(key)
    if raw is None or not raw.strip():
        return default
    return raw.strip().lower() in _TRUE


def _whole(env: Mapping[str, str], key: str, default: int, *, minimum: int) -> int:
    raw = env.get(key, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        raise ImproperlyConfigured(
            f"{key} must be a whole number, got {raw!r}"
        ) from None
    if value < minimum:
        raise ImproperlyConfigured(f"{key} must be at least {minimum}, got {raw!r}")
    return value


@dataclass(frozen=True)
class SignupPostConfig:
    debounce_seconds: int = DEFAULT_DEBOUNCE_SECONDS
    lock_seconds: int = DEFAULT_LOCK_SECONDS
    disabled: bool = False
    read_retries: int = DEFAULT_READ_RETRIES

    @property
    def pending_ttl_seconds(self) -> int:
        """How long a lost queued edit can suppress further notifications."""
        return self.debounce_seconds + self.lock_seconds + PENDING_TTL_MARGIN_SECONDS

    @classmethod
    def from_env(
        cls,
        *,
        environ: Mapping[str, str] | None = None,
        disabled_default: bool = False,
    ) -> SignupPostConfig:
        env = os.environ if environ is None else environ
        return cls(
            debounce_seconds=_whole(
                env, "SIGNUP_POST_DEBOUNCE_SECONDS", DEFAULT_DEBOUNCE_SECONDS, minimum=0
            ),
            lock_seconds=_whole(
                env, "SIGNUP_POST_LOCK_SECONDS", DEFAULT_LOCK_SECONDS, minimum=1
            ),
            disabled=_bool(env, "SIGNUP_POST_DISABLED", disabled_default)
            or _bool(env, "DISABLE_CACHE", False),
            read_retries=_whole(
                env, "SIGNUP_POST_READ_RETRIES", DEFAULT_READ_RETRIES, minimum=0
            ),
        )
