from dataclasses import dataclass, field, replace
from typing import Any

from django.db import transaction
from django.db.models import Q

from app.models import CustomUser
from common.game import GameType
from events.eligibility import refresh_members_eligibility
from org.api_connections.mutations import (
    MmrMutationContext,
    MmrRevisionConflict,
    check_expected_revision,
    lock_memberships,
)
from org.mmr import (
    OrgMmrError,
    bulk_set_org_mmrs,
    game_mmrs_prefetch,
    get_org_mmr,
    validate_org_mmr,
)
from org.mmr_official import apply_official_org_mmr
from org.mmr_requests.permissions import may_verify_org_mmr
from org.models import Organization, OrgLog, OrgMmrSyncState, OrgUser
from telemetry.logging import get_logger

log = get_logger(__name__)

MAX_ENTRIES = 500
STEAM_ID_64_BASE = CustomUser.STEAM_ID_64_BASE


@dataclass
class SyncResult:
    updated: int = 0
    unchanged: int = 0
    unmatched: list[dict[str, Any]] = field(default_factory=list)
    invalid: list[dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "updated": self.updated,
            "unchanged": self.unchanged,
            "unmatched": self.unmatched,
            "invalid": self.invalid,
        }


@dataclass(frozen=True)
class _Entry:
    index: int
    steam_account_id: int | None
    discord_id: str | None
    mmr: int | None
    expected_revision: int | None = None

    def ref(self) -> dict[str, Any]:
        ref: dict[str, Any] = {"index": self.index}
        if self.steam_account_id is not None:
            ref["steam_id"] = self.steam_account_id
        if self.discord_id is not None:
            ref["discord_id"] = self.discord_id
        return ref


def to_account_id(steam_id: int) -> int:
    return steam_id - STEAM_ID_64_BASE if steam_id >= STEAM_ID_64_BASE else steam_id


def _parse_int(value: Any) -> int | None:
    if isinstance(value, bool):
        raise ValueError
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    raise ValueError


def _parse(index: int, raw: Any, game_type: int) -> _Entry | str:
    if not isinstance(raw, dict):
        return "entry must be an object"
    steam_raw = raw.get("steam_id")
    discord_raw = raw.get("discord_id")
    if steam_raw is None and discord_raw in (None, ""):
        return "steam_id or discord_id is required"
    try:
        steam = to_account_id(_parse_int(steam_raw)) if steam_raw is not None else None
    except ValueError:
        return "steam_id must be an integer"
    if steam is not None and steam <= 0:
        return "steam_id must be positive"
    discord = str(discord_raw).strip() if discord_raw not in (None, "") else None
    if "mmr" not in raw:
        return "mmr is required"
    mmr = raw["mmr"]
    try:
        validate_org_mmr(game_type, mmr)
    except OrgMmrError as exc:
        return str(exc)
    revision = raw.get("expected_revision")
    if revision is not None and (type(revision) is not int or revision < 0):
        return "expected_revision must be a nonnegative integer"
    return _Entry(
        index=index,
        steam_account_id=steam,
        discord_id=discord,
        mmr=mmr,
        expected_revision=revision,
    )


def _members(org: Organization, entries: list[_Entry]) -> list[OrgUser]:
    steam_ids = {e.steam_account_id for e in entries if e.steam_account_id is not None}
    discord_ids = {e.discord_id for e in entries if e.discord_id is not None}
    matching = Q(user__steam_account_id__in=steam_ids) | Q(
        user__discordId__in=discord_ids
    )
    candidates = list(
        OrgUser.objects.nocache()
        .filter(organization=org)
        .filter(matching)
        .values_list("pk", flat=True)
    )
    locked = lock_memberships(candidates, required=False)
    return list(
        OrgUser.objects.nocache()
        .filter(pk__in=[member.pk for member in locked], organization=org)
        .filter(matching)
        .order_by("pk")
        .select_related("user")
        .prefetch_related(game_mmrs_prefetch(fresh=True))
    )


def _match(
    entry: _Entry, by_steam: dict[int, OrgUser], by_discord: dict[str, OrgUser]
) -> OrgUser | None | str:
    via_steam = by_steam.get(entry.steam_account_id) if entry.steam_account_id else None
    via_discord = by_discord.get(entry.discord_id) if entry.discord_id else None
    if via_steam and via_discord and via_steam.pk != via_discord.pk:
        return "steam_id and discord_id belong to different members"
    return via_steam or via_discord


@transaction.atomic
def sync_mmrs(
    org: Organization,
    actor: CustomUser,
    raw_entries: list[Any],
    *,
    game_type: int = GameType.DOTA2,
    mark_verified: bool = True,
    sync_context: MmrMutationContext | None = None,
) -> SyncResult:
    if len(raw_entries) > MAX_ENTRIES:
        raise OrgMmrError("Too many entries")
    result = SyncResult()
    entries: list[_Entry] = []
    for index, raw in enumerate(raw_entries):
        parsed = _parse(index, raw, game_type)
        if isinstance(parsed, str):
            result.invalid.append({"index": index, "error": parsed})
        else:
            entries.append(parsed)

    members = _members(org, entries)
    by_steam = {m.user.steam_account_id: m for m in members if m.user.steam_account_id}
    by_discord = {m.user.discordId: m for m in members if m.user.discordId}

    targets: dict[int, tuple[OrgUser, int | None]] = {}
    contexts: dict[int, MmrMutationContext] = {}
    seen: set[int] = set()
    for entry in entries:
        matched = _match(entry, by_steam, by_discord)
        if isinstance(matched, str):
            result.invalid.append({"index": entry.index, "error": matched})
        elif matched is None:
            result.unmatched.append(entry.ref())
        elif matched.user_id in seen:
            result.invalid.append(
                {"index": entry.index, "error": "duplicate entry for this member"}
            )
        elif mark_verified and not may_verify_org_mmr(actor, matched):
            result.invalid.append(
                {
                    "index": entry.index,
                    "error": "Not permitted to verify this member's MMR.",
                }
            )
        else:
            seen.add(matched.user_id)
            context = sync_context or MmrMutationContext()
            if entry.expected_revision is not None:
                context = replace(context, expected_revision=entry.expected_revision)
            try:
                check_expected_revision(matched, game_type, context)
            except MmrRevisionConflict:
                result.invalid.append({"index": entry.index, "error": "conflict"})
                continue
            contexts[matched.user_id] = context
            targets[matched.user_id] = (matched, entry.mmr)

    changed: dict[int, int | None] = {}
    old_values: dict[int, int] = {}
    for user_id, (org_user, mmr) in targets.items():
        old = get_org_mmr(org_user, game_type)
        if (mmr or 0) == old:
            result.unchanged += 1
        else:
            changed[user_id] = mmr
            old_values[user_id] = old
    result.updated = len(changed)

    with transaction.atomic():
        if mark_verified:
            for user_id, (org_user, mmr) in targets.items():
                apply_official_org_mmr(
                    org_user,
                    game_type,
                    mmr or 0,
                    actor=actor,
                    source="api_sync",
                    extra_log={"old_mmr": old_values.get(user_id, mmr or 0)},
                    sync_context=contexts[user_id],
                )
        elif changed:
            bulk_set_org_mmrs(
                org.pk,
                game_type,
                changed,
                sync_context=replace(
                    sync_context or MmrMutationContext(), expected_revision=None
                ),
            )
            OrgLog.objects.bulk_create(
                OrgLog(
                    organization=org,
                    actor=actor,
                    action="set_mmr",
                    target_user_id=user_id,
                    details={
                        "game_type": game_type,
                        "mmr": mmr,
                        "old_mmr": old_values[user_id],
                        "source": "api_sync",
                    },
                )
                for user_id, mmr in changed.items()
            )
        touched = [org_user for org_user, _ in targets.values()]
        if changed or (mark_verified and touched):
            refresh_members_eligibility(touched)

    log.info(
        "org_mmr_api_sync",
        system="org",
        subsystem="api_tokens",
        org_id=org.pk,
        actor_id=actor.pk,
        game_type=game_type,
        received=len(raw_entries),
        updated=result.updated,
        unchanged=result.unchanged,
        unmatched=len(result.unmatched),
        invalid=len(result.invalid),
    )
    return result


def member_rows(org: Organization, game_type: int) -> list[dict[str, Any]]:
    members = (
        OrgUser.objects.filter(organization=org)
        .select_related("user")
        .prefetch_related(game_mmrs_prefetch(fresh=False))
        .order_by("pk")
    )
    revisions = dict(
        OrgMmrSyncState.objects.filter(
            org_user__organization=org, game_type=game_type
        ).values_list("org_user_id", "revision")
    )
    return [
        {
            "revision": revisions.get(m.pk, 0),
            "user_id": m.user_id,
            "username": m.user.username,
            "steam_id": m.user.steam_account_id,
            "discord_id": m.user.discordId,
            "mmr": get_org_mmr(m, game_type),
        }
        for m in members
    ]
