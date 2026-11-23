from __future__ import annotations

from collections import defaultdict
from collections.abc import Collection, Iterable
from typing import Literal

from django.db import transaction
from django.db.models import F, Max

from app.cache_utils import invalidate_after_commit
from league.models import LeagueUser
from steam.models import LeaguePlayerStats
from telemetry.logging import get_logger

log = get_logger(__name__)

RecomputeTrigger = Literal["org_mmr", "adjustment"]


def best_mmr_adjustments(user_ids: Iterable[int]) -> dict[int, int]:
    ids = list(user_ids)
    if not ids:
        return {}
    return {
        row["user_id"]: row["best"] or 0
        for row in LeaguePlayerStats.objects.filter(user_id__in=ids)
        .values("user_id")
        .annotate(best=Max("mmr_adjustment"))
    }


def league_mmr(base_mmr: int, best_adjustment: int) -> int | None:
    """League MMR is org MMR plus best league adjustment; None without a base."""
    if not base_mmr:
        return None
    return base_mmr + best_adjustment


def league_mmr_seeds(org_mmrs: dict[int, int]) -> dict[int, int]:
    """Map user pk -> org MMR onto starting league MMRs (0 without a base)."""
    based = [uid for uid, base in org_mmrs.items() if base]
    adjustments = best_mmr_adjustments(based)
    return {
        uid: league_mmr(base, adjustments.get(uid, 0)) or 0
        for uid, base in org_mmrs.items()
    }


def recompute_league_mmrs(
    base_mmrs: dict[int, int],
    *,
    trigger: RecomputeTrigger,
    league_id: int | None = None,
    exclude_league_user_ids: Collection[int] = (),
) -> list[int]:
    """Map OrgUser pk -> org MMR onto unverified league MMRs in that org's leagues."""
    if not base_mmrs:
        return []
    with transaction.atomic():
        rows_qs = (
            LeagueUser.objects.nocache()
            .filter(
                org_user_id__in=list(base_mmrs),
                league__organization_id=F("org_user__organization_id"),
                mmr_verified_at__isnull=True,
            )
            .exclude(pk__in=list(exclude_league_user_ids))
            .select_related("league")
        )
        if league_id is not None:
            rows_qs = rows_qs.filter(league_id=league_id)
        rows = list(rows_qs)
        adjustments = best_mmr_adjustments({row.user_id for row in rows})
        targets: dict[int, int] = {}
        for row in rows:
            value = league_mmr(
                base_mmrs[row.org_user_id], adjustments.get(row.user_id, 0)
            )
            if value is not None and value != row.mmr:
                targets[row.pk] = value
        stale = [row for row in rows if row.pk in targets]
        if not stale:
            return []
        by_value: dict[int, list[int]] = defaultdict(list)
        for row in stale:
            by_value[targets[row.pk]].append(row.pk)
        for value, pks in by_value.items():
            LeagueUser.objects.filter(pk__in=pks, mmr_verified_at__isnull=True).update(
                mmr=value
            )
        for row in stale:
            row.mmr = targets[row.pk]
        league_user_ids = [row.pk for row in stale]
        log.info(
            "league_mmr_recomputed",
            system="league",
            subsystem="mmr",
            trigger=trigger,
            league_user_ids=league_user_ids,
            league_ids=sorted({row.league_id for row in stale}),
            org_user_ids=sorted({row.org_user_id for row in stale}),
        )
        leagues = {row.league_id: row.league for row in stale}
        invalidate_after_commit(*stale, *leagues.values())
    return league_user_ids


def sync_league_mmrs_from_org(
    org_mmrs: dict[int, int], *, exclude_league_user_ids: Collection[int] = ()
) -> list[int]:
    return recompute_league_mmrs(
        org_mmrs, trigger="org_mmr", exclude_league_user_ids=exclude_league_user_ids
    )
