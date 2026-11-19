from django.db.models import Q, QuerySet

from app.models import CustomUser, LeadershipProblem, Team
from org.models import OrgUser


def teams_with_leadership_problems(
    qs: QuerySet[Team] | None = None,
) -> list[tuple[Team, LeadershipProblem]]:
    base = Team.objects.all() if qs is None else qs
    teams = (
        base.nocache()
        .filter(Q(captain__isnull=False) | Q(deputy_captain__isnull=False))
        .prefetch_related("members")
        .order_by("pk")
    )
    rows: list[tuple[Team, LeadershipProblem]] = []
    for team in teams:
        member_pks = {member.pk for member in team.members.all()}
        problems = Team.leadership_problems(
            member_pks, team.captain_id, team.deputy_captain_id
        )
        rows.extend((team, problem) for problem in problems.values())
    return rows


def successor_after_removal(
    team: Team, removed_pks: set[int]
) -> tuple[CustomUser | None, CustomUser | None, str]:
    """Leadership after removing removed_pks: (captain, deputy, how). Works before or after removal."""
    captain_removed = team.captain_id is not None and team.captain_id in removed_pks
    deputy_removed = (
        team.deputy_captain_id is not None and team.deputy_captain_id in removed_pks
    )
    if not captain_removed:
        if deputy_removed:
            return team.captain, None, "deputy_cleared"
        return team.captain, team.deputy_captain, "unchanged"

    remaining = team.members.nocache().exclude(pk__in=removed_pks).order_by("pk")
    if (
        team.deputy_captain_id is not None
        and not deputy_removed
        and remaining.filter(pk=team.deputy_captain_id).exists()
    ):
        return team.deputy_captain, None, "deputy"

    league = team.tournament.league if team.tournament else None
    org_id = league.organization_id if league else None
    if org_id is not None:
        best = (
            OrgUser.objects.nocache()
            .filter(user__in=remaining, organization_id=org_id)
            .select_related("user")
            .order_by("-mmr")
            .first()
        )
        if best:
            return best.user, None, "org_mmr"
    return remaining.first(), None, "lowest_pk"
