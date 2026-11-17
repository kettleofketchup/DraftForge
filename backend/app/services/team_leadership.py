from django.db.models import Q, QuerySet

from app.models import LeadershipProblem, Team


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
