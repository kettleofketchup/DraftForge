from __future__ import annotations

from dataclasses import dataclass

from django.db import transaction
from django.utils import timezone

from app.cache_utils import invalidate_after_commit
from app.models import CustomUser
from common.game import GameType
from events.eligibility.store import refresh_unmet_requirements
from league.models import LeagueUser
from org.mmr import (
    invalidate_org_user_tournaments,
    mark_org_mmr_verified,
    set_org_mmr,
    validate_org_mmr,
)
from org.mmr_requests.permissions import may_verify_org_mmr
from org.models import MmrChangeRequest, OrgLog, OrgUser, OrgUserGameMmr
from telemetry.logging import get_logger

log = get_logger(__name__)


@dataclass(frozen=True)
class OrgMmrWriteResult:
    value: int
    previous: int
    verified: bool
    changed: bool
    superseded_ids: list[int]


def _supersede_pending(
    org_user: OrgUser,
    game_type: int,
    value: int,
    actor: CustomUser | None,
    request: MmrChangeRequest | None,
) -> list[int]:
    qs = MmrChangeRequest.objects.filter(
        status=MmrChangeRequest.Status.PENDING,
        target=MmrChangeRequest.Target.ORG,
        org_user_id=org_user.pk,
        game_type=game_type,
    )
    if request is not None:
        qs = qs.exclude(pk=request.pk)
    ids = list(qs.select_for_update().values_list("pk", flat=True))
    if not ids:
        return []
    MmrChangeRequest.objects.filter(
        pk__in=ids, status=MmrChangeRequest.Status.PENDING
    ).update(
        status=MmrChangeRequest.Status.SUPERSEDED,
        reviewed_by=actor,
        reviewed_at=timezone.now(),
        approved_mmr=value,
        updated_at=timezone.now(),
    )
    return ids


def apply_official_org_mmr(
    org_user: OrgUser,
    game_type: int,
    value: int,
    *,
    actor: CustomUser | None,
    source: str,
    request: MmrChangeRequest | None = None,
    extra_log: dict[str, object] | None = None,
    log_unchanged: bool = False,
) -> OrgMmrWriteResult:
    validate_org_mmr(game_type, value)
    verified = may_verify_org_mmr(actor, org_user)
    with transaction.atomic():
        previous = (
            OrgUserGameMmr.objects.nocache()
            .select_for_update()
            .filter(org_user_id=org_user.pk, game_type=game_type)
            .values_list("mmr", flat=True)
            .first()
        ) or 0
        changed = value != previous
        noop = not changed and value == 0 and game_type != GameType.DOTA2
        if changed:
            set_org_mmr(
                org_user,
                game_type,
                value,
                mark_verified=verified,
                verified_by=actor if verified else None,
            )
        elif verified and not noop:
            mark_org_mmr_verified(org_user, game_type, actor)

        superseded_ids = (
            _supersede_pending(org_user, game_type, value, actor, request)
            if verified and not noop
            else []
        )

        if changed or log_unchanged or request is not None:
            details: dict[str, object] = {
                "game_type": int(game_type),
                "mmr": value,
                "source": source,
                "previous_mmr": previous,
                "verified": verified,
            }
            if request is not None:
                details["request_id"] = request.pk
            details.update(extra_log or {})
            OrgLog.objects.create(
                organization_id=org_user.organization_id,
                actor=actor,
                action="set_mmr",
                target_user_id=org_user.user_id,
                details=details,
            )
        elif verified and not noop:
            log.info(
                "org_mmr_reverified",
                system="org",
                subsystem="mmr",
                org_user_id=org_user.pk,
                game_type=game_type,
                source=source,
                actor_id=actor.pk if actor is not None else None,
            )

        if superseded_ids:
            log.info(
                "mmr_requests_superseded",
                system="org",
                subsystem="mmr_requests",
                org_user_id=org_user.pk,
                game_type=game_type,
                request_ids=superseded_ids,
            )

        if not noop or log_unchanged or request is not None:
            refresh_unmet_requirements(org_user)
            league_users = list(
                LeagueUser.objects.filter(org_user=org_user).select_related("league")
            )
            invalidate_after_commit(
                org_user,
                org_user.organization,
                *league_users,
                *(lu.league for lu in league_users),
            )
            invalidate_org_user_tournaments(org_user)

    return OrgMmrWriteResult(
        value=value,
        previous=previous,
        verified=verified,
        changed=changed,
        superseded_ids=superseded_ids,
    )
