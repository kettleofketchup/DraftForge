"""The authorized subject universe for one bound event, and its keyset pages.

A subject is someone DraftForge would let a promoter contact for the event,
written as ``(user_id, org_user_id, discord_id)``. The universe is the union
of these sources, ignoring any viewer, search, hide or contacted filter:

- the org's members (``OrgUser``);
- the recent-tournament pool at ``MAX_POOL_N`` tournaments and the active
  pool at ``MAX_DAYS``, as the promoter UI computes them;
- guild members who joined within ``MAX_DAYS`` (bots excluded), with no
  ``MAX_DISCORD_ROWS`` truncation, matching ``in_pool``'s send rule;
- recipients of local sends for this event;
- Discord IDs of receipts already imported for this event.

Discord-only identities resolve to the account that owns the Discord ID when
one exists, otherwise they stay ``(null, null, discord_id)``. Nothing here
creates a ``CustomUser`` or ``OrgUser``. A known account whose Discord ID is
missing or not a canonical snowflake is reported with ``discord_id`` null
(unresolved) rather than guessed.

``mapping_version`` is the SHA-256 of the event's binding plus every subject
tuple. Cursors are bound to it, so any change to the universe or binding
makes an in-flight read 409 ``mapping_changed`` and the client restarts from
the first page. An unavailable guild source is 503
``subject_source_unavailable``, never a falsely complete universe.
"""

from __future__ import annotations

import bisect
import hashlib
import json
from collections.abc import Iterable
from dataclasses import dataclass
from functools import cached_property
from typing import Any

from django.db.models import OuterRef, Q, Subquery

from app.models import CustomUser
from common.strict_json import parse_canonical_id
from discordbot.services.discord_members import DiscordMembersFetchError
from events.models import Event
from org.integration.bindings import EventBinding, get_event_binding
from org.integration.cursors import decode_cursor, encode_cursor
from org.integration.errors import IntegrationError
from org.integration.parsers import format_id
from org.models import Organization, OrgUser, PromoSend
from org.models_promotion_sync import ExternalPromotionReceipt
from org.promotion.recipients import (
    MAX_DAYS,
    MAX_POOL_N,
    active_pool,
    fetch_guild_members,
    joiners_since,
    recent_org_tournaments,
)
from telemetry.logging import get_logger

log = get_logger(__name__)

_VERSION_SCHEMA = 1
_HAS_DISCORD = 0
_NO_DISCORD = 1
_DISCORD_LOOKUP_CHUNK = 1000


@dataclass(frozen=True)
class Subject:
    user_id: int | None
    org_user_id: int | None
    discord_id: str | None

    def sort_key(self) -> tuple[int, int]:
        """Canonical numeric Discord ID first; unresolved accounts after, by user."""
        if self.discord_id is not None:
            return (_HAS_DISCORD, int(self.discord_id))
        assert self.user_id is not None
        return (_NO_DISCORD, self.user_id)

    def as_wire(self) -> dict[str, str | None]:
        return {
            "user_id": format_id(self.user_id),
            "org_user_id": format_id(self.org_user_id),
            "discord_id": self.discord_id,
        }


@dataclass(frozen=True)
class SubjectUniverse:
    binding: EventBinding
    subjects: tuple[Subject, ...]
    mapping_version: str

    @cached_property
    def _by_discord_id(self) -> dict[str, Subject]:
        return {s.discord_id: s for s in self.subjects if s.discord_id is not None}

    def by_discord_id(self, discord_id: str) -> Subject | None:
        return self._by_discord_id.get(discord_id)


def resource_for(event_id: int) -> str:
    return f"event_recipients:{event_id}"


def _canonical_discord(value: str | None) -> str | None:
    return value if parse_canonical_id(value) is not None else None


def _unavailable(org: Organization, event: Event) -> IntegrationError:
    log.warning(
        "integration_subject_source_unavailable",
        system="org",
        subsystem="integration",
        org_id=org.pk,
        event_id=event.pk,
        source="discord_guild",
    )
    return IntegrationError("subject_source_unavailable", 503)


def _guild_discord_ids(org: Organization, event: Event) -> set[str]:
    try:
        members = fetch_guild_members(org)
    except DiscordMembersFetchError:
        raise _unavailable(org, event) from None
    return {j["member"]["user"]["id"] for j in joiners_since(members, days=MAX_DAYS)}


def _chunks(values: list[str], size: int) -> Iterable[list[str]]:
    for start in range(0, len(values), size):
        yield values[start : start + size]


def _accounts(
    org: Organization, event: Event, discord_ids: set[str]
) -> list[tuple[int, str | None, int | None]]:
    """``(user_pk, discordId, org_user_pk)`` for every account in the universe.

    ``discord_ids`` are the guild and imported-receipt Discord IDs; an
    account that owns one of them is included as that subject.

    One query, plus one per extra chunk of a very large guild ID list, so the
    cost does not grow with the number of subjects.
    """
    recent = (
        CustomUser.objects.filter(
            tournaments__pk__in=recent_org_tournaments(
                org, exclude_event=event, n=MAX_POOL_N
            )
        )
        .filter(discordId__isnull=False)
        .exclude(discordId="")
    )
    by_source = (
        Q(pk__in=OrgUser.objects.filter(organization=org).values("user_id"))
        | Q(pk__in=recent.values("pk"))
        | Q(pk__in=active_pool(org, event, days=MAX_DAYS).values("pk"))
        | Q(
            pk__in=PromoSend.objects.filter(
                organization=org, event=event, recipient__isnull=False
            ).values("recipient_id")
        )
    )
    org_user = Subquery(
        OrgUser.objects.filter(user=OuterRef("pk"), organization=org).values("pk")[:1]
    )
    chunks = list(_chunks(sorted(discord_ids), _DISCORD_LOOKUP_CHUNK)) or [[]]
    rows: dict[int, tuple[int, str | None, int | None]] = {}
    for index, chunk in enumerate(chunks):
        where = Q(discordId__in=chunk)
        if index == 0:
            where |= by_source
        for row in (
            CustomUser.objects.nocache()
            .filter(where)
            .annotate(org_user_pk=org_user)
            .values_list("pk", "discordId", "org_user_pk")
        ):
            rows[row[0]] = row
    return list(rows.values())


def _identity_conflict(org: Organization, event: Event) -> IntegrationError:
    log.error(
        "integration_subject_identity_conflict",
        system="org",
        subsystem="integration",
        org_id=org.pk,
        event_id=event.pk,
    )
    return IntegrationError("identity_conflict", 409)


def _mapping_version(binding: EventBinding, subjects: tuple[Subject, ...]) -> str:
    document: dict[str, Any] = {
        "v": _VERSION_SCHEMA,
        "binding": {
            "org_id": str(binding.org_id),
            "guild_id": str(binding.guild_id),
            "event_id": str(binding.event_id),
            "occasion_id": str(binding.occasion_id),
        },
        "subjects": [
            [s.as_wire()["user_id"], s.as_wire()["org_user_id"], s.discord_id]
            for s in subjects
        ],
    }
    raw = json.dumps(
        document, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(raw.encode()).hexdigest()


def authorized_event_subjects(org: Organization, event: Event) -> SubjectUniverse:
    """Every subject authorized for ``event``, sorted, with its mapping version.

    Raises ``IntegrationError``: 403/404 from the binding lookup, 503
    ``subject_source_unavailable`` if the guild cannot be read, 409
    ``identity_conflict`` if two subjects would share a sort key.
    """
    binding = get_event_binding(org.pk, event.pk)
    discord_only = _guild_discord_ids(org, event)
    discord_only.update(
        ExternalPromotionReceipt.objects.filter(organization=org, event=event)
        .values_list("discord_id", flat=True)
        .distinct()
    )

    by_key: dict[tuple[int, int], Subject] = {}

    def add(subject: Subject) -> None:
        key = subject.sort_key()
        if key in by_key:
            raise _identity_conflict(org, event)
        by_key[key] = subject

    linked: set[str] = set()
    for user_pk, discord_id, org_user_pk in _accounts(org, event, discord_only):
        canonical = _canonical_discord(discord_id)
        add(Subject(user_pk, org_user_pk, canonical))
        if discord_id:
            linked.add(discord_id)
    for discord_id in discord_only - linked:
        canonical = _canonical_discord(discord_id)
        if canonical is not None:
            add(Subject(None, None, canonical))

    subjects = tuple(by_key[key] for key in sorted(by_key))
    return SubjectUniverse(
        binding=binding,
        subjects=subjects,
        mapping_version=_mapping_version(binding, subjects),
    )


def _cursor_key(key: list[Any]) -> tuple[int, int]:
    if (
        len(key) != 2
        or not all(type(part) is int for part in key)
        or key[0] not in (_HAS_DISCORD, _NO_DISCORD)
        or key[1] < 1
    ):
        raise IntegrationError("invalid_cursor", 400)
    return (key[0], key[1])


def list_event_recipients(
    org: Organization, event: Event, *, limit: int, cursor: str | None
) -> dict[str, Any]:
    """One keyset page of the event's authorized subjects.

    The universe is recomputed on every page, so a cursor issued under a
    different ``mapping_version`` is 409 ``mapping_changed``.
    """
    universe = authorized_event_subjects(org, event)
    resource = resource_for(event.pk)
    keys = [s.sort_key() for s in universe.subjects]
    start = 0
    if cursor is not None:
        after = _cursor_key(
            decode_cursor(
                cursor,
                org_id=org.pk,
                resource=resource,
                fingerprint=universe.mapping_version,
            )
        )
        start = bisect.bisect_right(keys, after)
    page = universe.subjects[start : start + limit]
    next_cursor = None
    if start + limit < len(keys):
        next_cursor = encode_cursor(
            org_id=org.pk,
            resource=resource,
            key=list(page[-1].sort_key()),
            fingerprint=universe.mapping_version,
        )
    return {
        "mapping_version": universe.mapping_version,
        "recipients": [s.as_wire() for s in page],
        "next_cursor": next_cursor,
    }
