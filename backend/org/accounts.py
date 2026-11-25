from collections.abc import Callable

from django.db.models import Model

from app.cache_utils import invalidate_after_commit
from app.models import CustomUser
from discordbot.models import DiscordEventDM
from league.mmr import merge_league_users
from league.models import LeagueUser
from org.models import (
    OrgFeature,
    OrgUser,
    PlayerDeadlockProfile,
    PlayerDotaProfile,
    PromoTemplate,
)

Discard = Callable[[Model], None]


def repoint_org_attribution(drop: CustomUser, keep: CustomUser) -> int:
    return OrgFeature.objects.nocache().filter(enabled_by=drop).update(
        enabled_by=keep
    ) + PromoTemplate.objects.nocache().filter(created_by=drop).update(created_by=keep)


def delete_counts(obj: Model) -> dict[str, int]:
    """Delete ``obj`` and return the rows removed per model, cascades included."""
    result = obj.delete()
    # Some models override delete() without returning Django's counts.
    return dict(result[1]) if result else {}


def merge_member_dependents(
    drop_ou: OrgUser, keep_ou: OrgUser, *, discard: Discard
) -> None:
    """Move rows hanging off ``drop_ou`` onto ``keep_ou`` before it is deleted.

    A league membership ``keep`` already holds prefers Official MMR, then higher MMR, and
    takes over the dropped row's teams; an org game profile ``keep_ou``
    already has wins. Rows that cannot move go through ``discard``.
    """
    for lu in LeagueUser.objects.nocache().filter(org_user=drop_ou):
        existing = (
            LeagueUser.objects.nocache()
            .filter(user_id=keep_ou.user_id, league_id=lu.league_id)
            .first()
        )
        if existing is None:
            lu.user_id = keep_ou.user_id
            lu.org_user = keep_ou
            lu.save(update_fields=["user", "org_user"])
            invalidate_after_commit(lu)
            continue
        merge_league_users(lu, existing)
        for team in lu.teams.all():
            team.league_users.add(existing)
            invalidate_after_commit(team)
        invalidate_after_commit(existing)
        discard(lu)

    for dm in DiscordEventDM.objects.nocache().filter(org_user=drop_ou):
        dm.org_user = keep_ou
        dm.save(update_fields=["org_user"])
        invalidate_after_commit(dm)

    for model in (PlayerDotaProfile, PlayerDeadlockProfile):
        profile = model.objects.nocache().filter(org_user=drop_ou).first()
        if profile is None:
            continue
        if model.objects.nocache().filter(org_user=keep_ou).exists():
            discard(profile)
            continue
        profile.org_user = keep_ou
        profile.save(update_fields=["org_user"])
        invalidate_after_commit(profile)
