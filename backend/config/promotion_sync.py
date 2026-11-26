"""event-promotion bindings, parsed once from the environment.

`backend.settings` builds `PROMOTION_SYNC` through
`PromotionSyncConfig.from_env()`. The bindings are the only place DraftForge
learns which external guild an org maps to and which external occasion each event
maps to. Requests never supply these IDs and nothing is inferred from names
or dates; an org or event without a binding fails closed.

Environment variables:

    PROMOTION_SYNC_BINDINGS  JSON array, default empty. Each item is
        {"org_id": "41", "guild_id": "555000000000000001",
         "events": [{"event_id": "720", "occasion_id": "88"}]}
        IDs are canonical positive decimal strings. Every field is required,
        unknown fields are rejected, and an org, guild, event or occasion may
        appear only once (occasions once per org). Only occasion linkage is
        supported: there is no date fallback.

The configured guild is checked against the org's own Discord server when a
binding is used (`org.integration.bindings`), not here, because settings load
before the database is available. Errors name the bad field, never its value.

`backend.settings` also builds `PROMOTION_ADAPTOR` through
`PromotionAdaptorConfig.from_env()`: where the outbox dispatcher
(`python manage.py dispatch_promotion_contacts`) sends receipts.

    PROMOTION_ADAPTOR_ENABLED       default false. While false nothing is sent
                                    and the URL and key are not read.
    PROMOTION_ADAPTOR_BASE_URL      https://host[:port], no path, query or
                                    credentials. Plain http only for loopback
                                    test hosts.
    PROMOTION_ADAPTOR_API_KEY       the adaptor's promotion:write key,
    PROMOTION_ADAPTOR_API_KEY_FILE  or a file holding it (not both).
    PROMOTION_ADAPTOR_TIMEOUT       seconds per request, default 30.
    PROMOTION_ADAPTOR_MAX_ATTEMPTS  default 5; the last failure needs
                                    reconciliation.
    PROMOTION_ADAPTOR_RETRY_CAP     longest backoff in seconds, default 120.
"""

from __future__ import annotations

import math
import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any
from urllib.parse import urlsplit

from django.core.exceptions import ImproperlyConfigured

from common.strict_json import StrictJSONError, loads_strict, parse_canonical_id

ENV_KEY = "PROMOTION_SYNC_BINDINGS"
_BINDING_KEYS = frozenset({"org_id", "guild_id", "events"})
_EVENT_KEYS = frozenset({"event_id", "occasion_id"})


@dataclass(frozen=True)
class OrgPromotionBinding:
    org_id: int
    guild_id: int
    events: Mapping[int, int] = field(default_factory=lambda: MappingProxyType({}))


@dataclass(frozen=True)
class PromotionSyncConfig:
    bindings: tuple[OrgPromotionBinding, ...] = ()

    def for_org(self, org_id: int) -> OrgPromotionBinding | None:
        for binding in self.bindings:
            if binding.org_id == org_id:
                return binding
        return None

    @classmethod
    def from_env(
        cls, *, environ: Mapping[str, str] | None = None
    ) -> PromotionSyncConfig:
        env = os.environ if environ is None else environ
        raw = env.get(ENV_KEY, "").strip()
        if not raw:
            return cls()
        try:
            items = loads_strict(raw)
        except StrictJSONError as exc:
            raise _error(f"invalid JSON ({exc.reason})") from None
        if not isinstance(items, list):
            raise _error("must be a JSON array")
        return cls(
            bindings=_validate([_binding(i, item) for i, item in enumerate(items)])
        )


def _error(message: str) -> ImproperlyConfigured:
    return ImproperlyConfigured(f"{ENV_KEY}: {message}")


def _exact(obj: Any, keys: frozenset[str], where: str) -> dict[str, Any]:
    if not isinstance(obj, dict):
        raise _error(f"{where} must be an object")
    missing = sorted(keys - obj.keys())
    unknown = sorted(obj.keys() - keys)
    if missing:
        raise _error(f"{where} is missing {', '.join(missing)}")
    if unknown:
        raise _error(f"{where} has unknown field(s) {', '.join(unknown)}")
    return obj


def _id(obj: dict[str, Any], key: str, where: str) -> int:
    number = parse_canonical_id(obj[key])
    if number is None:
        raise _error(f"{where}.{key} must be a canonical positive decimal string")
    return number


def _binding(index: int, item: Any) -> OrgPromotionBinding:
    where = f"[{index}]"
    obj = _exact(item, _BINDING_KEYS, where)
    if not isinstance(obj["events"], list):
        raise _error(f"{where}.events must be an array")
    events: dict[int, int] = {}
    occasions: set[int] = set()
    for e_index, event in enumerate(obj["events"]):
        e_where = f"{where}.events[{e_index}]"
        pair = _exact(event, _EVENT_KEYS, e_where)
        event_id = _id(pair, "event_id", e_where)
        occasion_id = _id(pair, "occasion_id", e_where)
        if event_id in events:
            raise _error(f"{e_where}.event_id is bound more than once")
        if occasion_id in occasions:
            raise _error(f"{e_where}.occasion_id is bound to more than one event")
        events[event_id] = occasion_id
        occasions.add(occasion_id)
    return OrgPromotionBinding(
        org_id=_id(obj, "org_id", where),
        guild_id=_id(obj, "guild_id", where),
        events=MappingProxyType(events),
    )


def _validate(
    bindings: list[OrgPromotionBinding],
) -> tuple[OrgPromotionBinding, ...]:
    orgs: set[int] = set()
    guilds: set[int] = set()
    events: set[int] = set()
    for index, binding in enumerate(bindings):
        if binding.org_id in orgs:
            raise _error(f"[{index}].org_id is bound more than once")
        if binding.guild_id in guilds:
            raise _error(f"[{index}].guild_id is bound to more than one org")
        if events & binding.events.keys():
            raise _error(f"[{index}].events reuse an event bound by another org")
        orgs.add(binding.org_id)
        guilds.add(binding.guild_id)
        events.update(binding.events.keys())
    return tuple(bindings)


ADAPTOR_ENV_PREFIX = "PROMOTION_ADAPTOR_"
# DraftForge's own app tokens; the dispatcher must hold the adaptor's key instead.
DRAFTFORGE_TOKEN_PREFIX = "dfk_"
# Plain http is allowed only for isolated test hosts on loopback.
INSECURE_TEST_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})
_TRUE = frozenset({"1", "true", "yes", "on"})
_FALSE = frozenset({"", "0", "false", "no", "off"})


@dataclass(frozen=True)
class PromotionAdaptorConfig:
    """Outbound outbox dispatch to the adaptor. Off unless configured."""

    enabled: bool = False
    base_url: str = ""
    api_key: str = field(default="", repr=False)
    timeout: float = 30.0
    max_attempts: int = 5
    retry_cap: float = 120.0

    @classmethod
    def from_env(
        cls, *, environ: Mapping[str, str] | None = None
    ) -> PromotionAdaptorConfig:
        env = os.environ if environ is None else environ

        def get(name: str) -> str:
            return env.get(ADAPTOR_ENV_PREFIX + name, "").strip()

        enabled = _flag(get("ENABLED"), "ENABLED")
        timeout = _positive(get("TIMEOUT"), "TIMEOUT", 30.0)
        max_attempts = int(
            _positive(get("MAX_ATTEMPTS"), "MAX_ATTEMPTS", 5, whole=True)
        )
        retry_cap = _positive(get("RETRY_CAP"), "RETRY_CAP", 120.0)
        if not enabled:
            # Off: the URL and credential are not read at all.
            return cls(timeout=timeout, max_attempts=max_attempts, retry_cap=retry_cap)
        return cls(
            enabled=True,
            base_url=_base_url(get("BASE_URL")),
            api_key=_api_key(get("API_KEY"), get("API_KEY_FILE")),
            timeout=timeout,
            max_attempts=max_attempts,
            retry_cap=retry_cap,
        )


def _adaptor_error(name: str, message: str) -> ImproperlyConfigured:
    return ImproperlyConfigured(f"{ADAPTOR_ENV_PREFIX}{name}: {message}")


def _flag(raw: str, name: str) -> bool:
    value = raw.lower()
    if value in _TRUE:
        return True
    if value in _FALSE:
        return False
    raise _adaptor_error(name, "must be true or false")


def _positive(raw: str, name: str, default: float, *, whole: bool = False) -> float:
    if not raw:
        return default
    try:
        value = float(int(raw)) if whole else float(raw)
    except ValueError:
        raise _adaptor_error(name, "must be a positive number") from None
    if not math.isfinite(value) or value <= 0:
        raise _adaptor_error(name, "must be a positive number")
    return value


def _base_url(raw: str) -> str:
    if not raw:
        raise _adaptor_error("BASE_URL", "is required when enabled")
    try:
        parts = urlsplit(raw)
        host = parts.hostname or ""
        _ = parts.port  # raises on a malformed port
    except ValueError:
        raise _adaptor_error("BASE_URL", "is not a valid URL") from None
    if parts.scheme not in ("https", "http") or not host:
        raise _adaptor_error("BASE_URL", "must be an https URL")
    if parts.scheme == "http" and host not in INSECURE_TEST_HOSTS:
        raise _adaptor_error(
            "BASE_URL", "plain http is allowed only for loopback test hosts"
        )
    if parts.username is not None or parts.password is not None:
        raise _adaptor_error("BASE_URL", "must not contain credentials")
    if parts.path not in ("", "/") or "?" in raw or "#" in raw:
        raise _adaptor_error("BASE_URL", "must not contain a path, query or fragment")
    return f"{parts.scheme}://{parts.netloc}"


def _api_key(raw: str, path: str) -> str:
    if raw and path:
        raise _adaptor_error("API_KEY", "set API_KEY or API_KEY_FILE, not both")
    if path:
        try:
            with open(path, encoding="utf-8") as fh:
                raw = fh.read().strip()
        except (OSError, UnicodeDecodeError):
            raise _adaptor_error("API_KEY_FILE", "could not be read") from None
    if not raw:
        raise _adaptor_error("API_KEY", "is required when enabled")
    if raw.startswith(DRAFTFORGE_TOKEN_PREFIX):
        raise _adaptor_error(
            "API_KEY", "must be the adaptor's key, not a DraftForge token"
        )
    if not (raw.isascii() and raw.isprintable() and " " not in raw):
        raise _adaptor_error("API_KEY", "must be printable ASCII with no spaces")
    return raw
