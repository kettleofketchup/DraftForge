"""SFG event-promotion bindings, parsed once from the environment.

`backend.settings` builds `SFG_PROMOTION_SYNC` through
`PromotionSyncConfig.from_env()`. The bindings are the only place DraftForge
learns which SFG guild (PwR) an org maps to and which SFG occasion each event
maps to. Requests never supply these IDs and nothing is inferred from names
or dates; an org or event without a binding fails closed.

Environment variables:

    SFG_PROMOTION_BINDINGS  JSON array, default empty. Each item is
        {"org_id": "41", "guild_id": "555000000000000001",
         "events": [{"event_id": "720", "occasion_id": "88"}]}
        IDs are canonical positive decimal strings. Every field is required,
        unknown fields are rejected, and an org, guild, event or occasion may
        appear only once (occasions once per org). Only occasion linkage is
        supported: there is no date fallback.

The configured guild is checked against the org's own Discord server when a
binding is used (`org.integration.bindings`), not here, because settings load
before the database is available. Errors name the bad field, never its value.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any

from django.core.exceptions import ImproperlyConfigured

from common.strict_json import StrictJSONError, loads_strict, parse_canonical_id

ENV_KEY = "SFG_PROMOTION_BINDINGS"
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
