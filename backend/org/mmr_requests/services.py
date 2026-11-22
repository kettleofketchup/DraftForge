from __future__ import annotations

from django.utils import timezone

from app.models import CustomUser
from league.models import LeagueUser
from org.models import MmrChangeRequest, OrgUser
from telemetry.logging import get_logger

log = get_logger(__name__)


def _supersede_for_merge(ids: list[int]) -> None:
    if not ids:
        return
    now = timezone.now()
    MmrChangeRequest.objects.filter(
        pk__in=ids, status=MmrChangeRequest.Status.PENDING
    ).update(
        status=MmrChangeRequest.Status.SUPERSEDED,
        reviewed_at=now,
        updated_at=now,
    )


def repoint_mmr_requests(
    claimer: CustomUser,
    target_user: CustomUser,
    org_user_pairs: list[tuple[OrgUser, OrgUser]],
    league_user_pairs: list[tuple[LeagueUser, LeagueUser]],
) -> None:
    pending = MmrChangeRequest.Status.PENDING
    superseded: list[int] = []

    for loser, keeper in org_user_pairs:
        keeper_games = set(
            MmrChangeRequest.objects.filter(
                org_user=keeper, target=MmrChangeRequest.Target.ORG, status=pending
            ).values_list("game_type", flat=True)
        )
        if keeper_games:
            superseded += list(
                MmrChangeRequest.objects.filter(
                    org_user=loser,
                    target=MmrChangeRequest.Target.ORG,
                    status=pending,
                    game_type__in=keeper_games,
                ).values_list("pk", flat=True)
            )

    for loser_lu, keeper_lu in league_user_pairs:
        if MmrChangeRequest.objects.filter(
            league_user=keeper_lu, status=pending
        ).exists():
            superseded += list(
                MmrChangeRequest.objects.filter(
                    league_user=loser_lu, status=pending
                ).values_list("pk", flat=True)
            )

    _supersede_for_merge(superseded)

    now = timezone.now()
    for loser, keeper in org_user_pairs:
        MmrChangeRequest.objects.filter(org_user=loser).update(
            org_user=keeper, updated_at=now
        )
    for loser_lu, keeper_lu in league_user_pairs:
        MmrChangeRequest.objects.filter(league_user=loser_lu).update(
            league_user=keeper_lu, updated_at=now
        )
    for field in ("subject_user", "requester", "reviewed_by"):
        MmrChangeRequest.objects.filter(**{field: target_user}).update(
            **{field: claimer}
        )

    log.info(
        "mmr_requests_repointed",
        system="org",
        subsystem="mmr_requests",
        claimer_id=claimer.pk,
        target_user_id=target_user.pk,
        org_user_pairs=[(a.pk, b.pk) for a, b in org_user_pairs],
        league_user_pairs=[(a.pk, b.pk) for a, b in league_user_pairs],
        superseded_ids=superseded,
    )
