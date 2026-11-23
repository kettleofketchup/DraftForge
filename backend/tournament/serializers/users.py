from collections.abc import Collection
from dataclasses import dataclass
from typing import Any

from django.db.models import Prefetch, QuerySet
from rest_framework.utils.serializer_helpers import ReturnList

from app.models import CustomUser, Team, Tournament
from app.serializers import TournamentUserSerializer
from league.models import LeagueUser
from org.mmr import game_for_tournament, game_mmrs_prefetch
from org.models import Organization, OrgUser
from org.serializers import OrgUserSerializer
from user.querysets import with_user_profiles


def tournament_organization(
    tournament: Tournament | None, *, fresh: bool = False
) -> Organization | None:
    """League's org, else the org of the event that spawned the tournament."""
    if tournament is None:
        return None
    if tournament.league and tournament.league.organization:
        return tournament.league.organization
    events = tournament.source_event.select_related("organization")
    event = (events.nocache() if fresh else events).first()
    return event.organization if event else None


def _serialize_users_with_mmr(
    users_qs: QuerySet[CustomUser],
    tournament: Tournament | None,
    *,
    game_type: int | None = None,
    fresh: bool = False,
) -> ReturnList:
    """Serialize users with org-scoped MMR if tournament has a league/org."""
    league = tournament.league if tournament else None
    org = tournament_organization(tournament, fresh=fresh)

    if not org:
        return TournamentUserSerializer(users_qs, many=True).data

    if fresh:
        users_qs = users_qs.nocache()
    org_user_qs = OrgUser.objects.nocache() if fresh else OrgUser.objects.all()
    league_user_qs = LeagueUser.objects.nocache() if fresh else LeagueUser.objects.all()
    # Auto-create OrgUser records for tournament users missing from the org
    existing_user_pks = set(
        org_user_qs.filter(user__in=users_qs, organization=org).values_list(
            "user_id", flat=True
        )
    )
    missing_users = users_qs.exclude(pk__in=existing_user_pks)
    if missing_users.exists():
        OrgUser.objects.bulk_create(
            [OrgUser(user=u, organization=org) for u in missing_users],
            ignore_conflicts=True,
        )

    org_users = with_user_profiles(
        OrgUser.objects.filter(user__in=users_qs, organization=org),
        "user",
        dota=True,
    ).prefetch_related(
        Prefetch(
            "league_memberships",
            queryset=league_user_qs.filter(league_id=league.pk if league else None),
        ),
        game_mmrs_prefetch(fresh=fresh),
    )
    if game_type is None:
        game_type = game_for_tournament(tournament)
    return OrgUserSerializer(
        org_users,
        many=True,
        context={"league_id": league.pk if league else None, "game_type": game_type},
    ).data


def serialize_user_with_mmr(
    user: CustomUser | None,
    tournament: Tournament | None,
    game_type: int | None = None,
) -> dict | None:
    """Serialize a single user with org-scoped MMR. Returns None if user is None."""
    if user is None:
        return None
    results = _serialize_users_with_mmr(
        type(user).objects.filter(pk=user.pk), tournament, game_type=game_type
    )
    return results[0] if results else TournamentUserSerializer(user).data


TEAM_USER_INDEX = "team_user_index"
TEAM_MMR_MAPS = "team_mmr_maps"
TEAM_ROSTER_FIELDS: tuple[str, ...] = ("members", "dropin_members", "left_members")


@dataclass(frozen=True)
class TeamUserIndex:
    """Users of many teams, serialized once, for TeamSerializerForTournament.

    Pass it in serializer context under TEAM_USER_INDEX. Entries match the
    per-team _serialize_users_with_mmr output; rosters are sorted by user pk,
    the order that path returns.
    """

    users: dict[int, dict[str, Any]]
    rosters: dict[int, dict[str, list[int]]]


def build_team_user_index(
    tournament: Tournament, teams: Collection[Team]
) -> TeamUserIndex:
    """Bulk version of _serialize_users_with_mmr for every user on `teams`."""
    team_ids = {team.pk for team in teams}
    rosters: dict[int, dict[str, list[int]]] = {
        pk: {field: [] for field in TEAM_ROSTER_FIELDS} for pk in team_ids
    }
    user_pks: set[int] = set()
    for team in teams:
        user_pks.update(pk for pk in (team.captain_id, team.deputy_captain_id) if pk)
    for field in TEAM_ROSTER_FIELDS:
        m2m = Team._meta.get_field(field)
        team_col = f"{m2m.m2m_field_name()}_id"
        user_col = f"{m2m.m2m_reverse_field_name()}_id"
        rows = (
            m2m.remote_field.through.objects.filter(**{f"{team_col}__in": team_ids})
            .order_by(team_col, user_col)
            .values_list(team_col, user_col)
        )
        for team_id, user_id in rows:
            rosters[team_id][field].append(user_id)
            user_pks.add(user_id)

    if not user_pks:
        return TeamUserIndex({}, rosters)
    org = tournament_organization(tournament)
    if not org:
        users_qs = with_user_profiles(
            CustomUser.objects.filter(pk__in=user_pks), dota=True
        ).order_by("pk")
        serialized = TournamentUserSerializer(users_qs, many=True).data
        return TeamUserIndex({row["pk"]: row for row in serialized}, rosters)

    league_id = tournament.league_id
    org_users_qs = (
        with_user_profiles(
            OrgUser.objects.filter(organization=org, user_id__in=user_pks),
            "user",
            dota=True,
        )
        .prefetch_related(
            Prefetch(
                "league_memberships",
                queryset=LeagueUser.objects.filter(league_id=league_id),
            ),
            game_mmrs_prefetch(fresh=False),
        )
        .order_by("user_id")
    )
    org_users = list(org_users_qs)
    missing = user_pks - {ou.user_id for ou in org_users}
    if missing:
        OrgUser.objects.bulk_create(
            [OrgUser(user_id=pk, organization=org) for pk in sorted(missing)],
            ignore_conflicts=True,
        )
        org_users = list(org_users_qs.all())
    serialized = OrgUserSerializer(
        org_users,
        many=True,
        context={"league_id": league_id, "game_type": game_for_tournament(tournament)},
    ).data
    return TeamUserIndex({row["pk"]: row for row in serialized}, rosters)


def collect_tournament_user_pks(tournament: Tournament) -> set[int]:
    """Collect all unique user PKs from a tournament and its teams.

    Includes: users, team members, captains, deputy captains,
    dropin members, and left members.
    """
    seen_pks = set()
    for user in tournament.users.all():
        seen_pks.add(user.pk)
    for team in tournament.teams.all():
        for m in team.members.all():
            seen_pks.add(m.pk)
        if team.captain_id:
            seen_pks.add(team.captain_id)
        if team.deputy_captain_id:
            seen_pks.add(team.deputy_captain_id)
        for m in team.dropin_members.all():
            seen_pks.add(m.pk)
        for m in team.left_members.all():
            seen_pks.add(m.pk)
    return seen_pks


# Org-context-only keys that OrgUserSerializer adds on top of the cached core
# (which already carries discordNickname).
_CONTEXT_MMR_KEYS = ("orgUserPk", "guildNickname", "mmr", "league_mmr", "mmr_game_type")


def collect_org_mmr(
    tournament: Tournament | None,
    org: Organization | None,
    seen_pks: set[int],
    *,
    fresh: bool,
) -> dict:
    """``{pk: {orgUserPk, guildNickname, mmr, league_mmr, mmr_game_type}}``, or {} without an org."""
    if not org:
        return {}
    league = tournament.league if tournament else None

    user_qs = CustomUser.objects.filter(pk__in=seen_pks)
    org_user_qs = OrgUser.objects.all()
    league_user_qs = LeagueUser.objects.all()
    if fresh:
        user_qs, org_user_qs = user_qs.nocache(), org_user_qs.nocache()
        league_user_qs = league_user_qs.nocache()

    # Auto-create OrgUser records for tournament users missing from the org
    # (preserves the side-effect of the legacy _serialize_users_with_mmr path).
    existing_user_pks = set(
        org_user_qs.filter(user__in=user_qs, organization=org).values_list(
            "user_id", flat=True
        )
    )
    missing_users = user_qs.exclude(pk__in=existing_user_pks)
    if missing_users.exists():
        OrgUser.objects.bulk_create(
            [OrgUser(user=u, organization=org) for u in missing_users],
            ignore_conflicts=True,
        )

    org_users = with_user_profiles(
        OrgUser.objects.filter(user__in=user_qs, organization=org),
        "user",
        dota=True,
    ).prefetch_related(
        Prefetch(
            "league_memberships",
            queryset=league_user_qs.filter(league_id=league.pk if league else None),
        ),
        game_mmrs_prefetch(fresh=fresh),
    )
    serialized = OrgUserSerializer(
        org_users,
        many=True,
        context={
            "league_id": league.pk if league else None,
            "game_type": game_for_tournament(tournament),
        },
    ).data
    return {row["pk"]: {k: row[k] for k in _CONTEXT_MMR_KEYS} for row in serialized}


def build_users_dict(tournament: Tournament, *, fresh: bool = False) -> dict:
    """Build a deduplicated ``{pk: serialized_user}`` dict for a tournament."""
    return build_users_dict_with_org(tournament, fresh=fresh)[0]


def build_users_dict_with_org(
    tournament: Tournament, *, fresh: bool = False
) -> tuple[dict, Organization | None]:
    """``build_users_dict`` plus the organization its overlay used.

    Shape-preserving: the CORE half comes from one bulk uncached query
    (``serialize_users_core``, same shape as the per-user ``serialize_user_core``)
    and the contextual MMR half is merged per-request.
    Output JSON is byte-identical to the legacy _serialize_users_with_mmr path —
    org entries carry core + MMR (orgUserPk/mmr/league_mmr/guildNickname);
    non-org entries carry core only. ``fresh=True`` reads the organization and
    MMR overlay past cacheops too.
    """
    # local: app.user_cache imports user.models, which is not in MODEL_APPS (celery path via draft.services.team_state)
    from app.user_cache import serialize_users_core

    seen_pks = collect_tournament_user_pks(tournament)
    org = tournament_organization(tournament, fresh=fresh)
    mmr_map = collect_org_mmr(tournament, org, seen_pks, fresh=fresh)
    cores = serialize_users_core(seen_pks)

    result: dict = {}
    for pk in seen_pks:
        core = cores.get(pk)
        if not core:
            continue
        entry = dict(core)
        if org is not None:
            entry.update(mmr_map.get(pk, {}))
        result[pk] = entry
    return result, org
