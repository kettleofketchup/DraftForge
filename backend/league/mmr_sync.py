from __future__ import annotations

from collections import defaultdict

from django.db import transaction
from django.db.models import F

from app.cache_utils import invalidate_after_commit
from league.models import LeagueUser
from telemetry.logging import get_logger

log = get_logger(__name__)


def sync_league_mmrs_from_org(org_mmrs: dict[int, int]) -> list[int]:
    """Map OrgUser pk -> org MMR onto unverified league MMRs in that org's leagues."""
    if not org_mmrs:
        return []
    with transaction.atomic():
        rows = list(
            LeagueUser.objects.nocache()
            .filter(
                org_user_id__in=list(org_mmrs),
                league__organization_id=F("org_user__organization_id"),
                mmr_verified_at__isnull=True,
            )
            .select_related("league")
        )
        stale = [row for row in rows if row.mmr != org_mmrs[row.org_user_id]]
        if not stale:
            return []
        by_value: dict[int, list[int]] = defaultdict(list)
        for row in stale:
            by_value[org_mmrs[row.org_user_id]].append(row.pk)
        for value, pks in by_value.items():
            LeagueUser.objects.filter(pk__in=pks, mmr_verified_at__isnull=True).update(
                mmr=value
            )
        for row in stale:
            row.mmr = org_mmrs[row.org_user_id]
        league_user_ids = [row.pk for row in stale]
        log.info(
            "league_mmr_synced_from_org",
            system="league",
            subsystem="mmr",
            league_user_ids=league_user_ids,
            league_ids=sorted({row.league_id for row in stale}),
            org_user_ids=sorted({row.org_user_id for row in stale}),
        )
        leagues = {row.league_id: row.league for row in stale}
        invalidate_after_commit(*stale, *leagues.values())
    return league_user_ids
