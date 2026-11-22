from __future__ import annotations

from dataclasses import dataclass

from django.db import transaction
from django.utils import timezone

from app.cache_utils import invalidate_after_commit
from app.models import CustomUser
from league.models import LeagueLog, LeagueUser
from org.mmr import LEAGUE_GAME, invalidate_org_user_tournaments, validate_org_mmr
from org.mmr_requests.permissions import may_self_verify
from org.models import MmrChangeRequest, OrgLog, OrgUser
from telemetry.logging import get_logger

log = get_logger(__name__)


@dataclass(frozen=True)
class LeagueMmrWriteResult:
    value: int
    previous: int
    verified: bool
    superseded_ids: list[int]


def _supersede_pending_league(
    league_user: LeagueUser,
    value: int,
    actor: CustomUser | None,
    request_id: int | None,
) -> list[int]:
    qs = MmrChangeRequest.objects.filter(
        status=MmrChangeRequest.Status.PENDING,
        target=MmrChangeRequest.Target.LEAGUE,
        league_user_id=league_user.pk,
    )
    if request_id is not None:
        qs = qs.exclude(pk=request_id)
    ids = list(qs.select_for_update().values_list("pk", flat=True))
    if not ids:
        return []
    now = timezone.now()
    MmrChangeRequest.objects.filter(
        pk__in=ids, status=MmrChangeRequest.Status.PENDING
    ).update(
        status=MmrChangeRequest.Status.SUPERSEDED,
        reviewed_by=actor,
        reviewed_at=now,
        approved_mmr=value,
        updated_at=now,
    )
    return ids


def set_league_mmr(
    league_user: LeagueUser,
    mmr: int,
    *,
    actor: CustomUser | None,
    verified: bool,
    source: str,
    request_id: int | None = None,
) -> LeagueMmrWriteResult:
    if mmr != 0:
        validate_org_mmr(LEAGUE_GAME, mmr)
    verified = verified and may_self_verify(actor, league_user.user_id) and mmr > 0
    with transaction.atomic():
        row = (
            LeagueUser.objects.nocache()
            .select_for_update()
            .select_related("league", "org_user")
            .get(pk=league_user.pk)
        )
        previous = row.mmr
        row.mmr = mmr
        row.mmr_verified_at = timezone.now() if verified else None
        row.mmr_verified_by = actor if verified else None
        row.save(update_fields=["mmr", "mmr_verified_at", "mmr_verified_by"])
        league_user.mmr = row.mmr
        league_user.mmr_verified_at = row.mmr_verified_at
        league_user.mmr_verified_by = row.mmr_verified_by

        superseded_ids = (
            _supersede_pending_league(row, mmr, actor, request_id) if verified else []
        )

        details: dict[str, object] = {
            "game_type": int(LEAGUE_GAME),
            "mmr": mmr,
            "previous_mmr": previous,
            "source": source,
            "verified": verified,
        }
        if request_id is not None:
            details["request_id"] = request_id
        LeagueLog.objects.create(
            league_id=row.league_id,
            actor=actor,
            action="set_mmr",
            target_user_id=row.user_id,
            details=details,
        )
        OrgLog.objects.create(
            organization_id=row.org_user.organization_id,
            actor=actor,
            action="set_mmr",
            target_user_id=row.user_id,
            details={**details, "league_id": row.league_id},
        )
        log.info(
            "league_mmr_set",
            system="league",
            subsystem="mmr",
            league_user_id=row.pk,
            league_id=row.league_id,
            mmr=mmr,
            previous_mmr=previous,
            verified=verified,
            source=source,
            request_id=request_id,
            superseded_ids=superseded_ids,
            actor_id=actor.pk if actor is not None else None,
        )
        invalidate_after_commit(row, row.league)
        invalidate_org_user_tournaments(row.org_user)

    return LeagueMmrWriteResult(
        value=mmr,
        previous=previous,
        verified=verified,
        superseded_ids=superseded_ids,
    )


def _loser_wins(loser: LeagueUser, keeper: LeagueUser) -> bool:
    loser_verified = loser.mmr_verified_at is not None
    keeper_verified = keeper.mmr_verified_at is not None
    if loser_verified != keeper_verified:
        return loser_verified
    return loser.mmr > keeper.mmr


def merge_league_users(loser: LeagueUser, keeper: LeagueUser) -> None:
    raised = _loser_wins(loser, keeper)
    if raised:
        keeper.mmr = loser.mmr
        keeper.mmr_verified_at = loser.mmr_verified_at
        keeper.mmr_verified_by_id = loser.mmr_verified_by_id
        keeper.save(update_fields=["mmr", "mmr_verified_at", "mmr_verified_by"])
        invalidate_after_commit(keeper)
    log.info(
        "league_mmr_merged",
        system="league",
        subsystem="mmr",
        loser_league_user_id=loser.pk,
        keeper_league_user_id=keeper.pk,
        league_id=keeper.league_id,
        raised=raised,
    )


def merge_user_league_memberships(
    loser_user: CustomUser,
    keeper_user: CustomUser,
    org_user_pairs: list[tuple[OrgUser, OrgUser]],
) -> list[tuple[LeagueUser, LeagueUser]]:
    keeper_org_user = {loser.pk: keeper for loser, keeper in org_user_pairs}
    keeper_rows = {
        row.league_id: row
        for row in LeagueUser.objects.nocache().filter(user=keeper_user)
    }
    pairs: list[tuple[LeagueUser, LeagueUser]] = []
    for row in LeagueUser.objects.nocache().filter(user=loser_user):
        existing = keeper_rows.get(row.league_id)
        if existing is not None:
            merge_league_users(row, existing)
            pairs.append((row, existing))
            continue
        row.user = keeper_user
        fields = ["user"]
        new_org_user = keeper_org_user.get(row.org_user_id)
        if new_org_user is not None:
            row.org_user = new_org_user
            fields.append("org_user")
        row.save(update_fields=fields)
        invalidate_after_commit(row)
    return pairs
