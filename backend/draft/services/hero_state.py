from django.db.models import Prefetch, QuerySet

from app.models import CustomUser, DraftTeam, HeroDraft
from user.querysets import with_user_profiles


def herodraft_state_queryset() -> QuerySet[HeroDraft]:
    """HeroDraft loader whose HeroDraftSerializer cost is fixed per draft."""
    users = with_user_profiles(CustomUser.objects.all(), dota=True)
    return HeroDraft.objects.select_related(
        "game__tournament__league__organization"
    ).prefetch_related(
        Prefetch(
            "draft_teams", queryset=DraftTeam.objects.select_related("tournament_team")
        ),
        Prefetch("draft_teams__tournament_team__captain", queryset=users),
        Prefetch("draft_teams__tournament_team__members", queryset=users),
        "rounds",
    )
