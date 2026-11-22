from collections.abc import Collection
from dataclasses import dataclass
from typing import Any, ClassVar, Final

from django.db import transaction
from django.db.models import Prefetch, QuerySet
from rest_framework import serializers
from rest_framework.utils.serializer_helpers import ReturnList
from rest_framework.validators import UniqueValidator

from app.cache_utils import invalidate_after_commit
from app.permissions_tournament import (
    check_lobby_steam_league_id,
    request_user,
)
from app.services.team_references import team_references
from app.steam_accounts import log_steam_verification_change
from draft.models import Draft, DraftOptions, DraftRound
from events.eligibility.steam import apply_admin_steam_account_id
from events.overrides import (
    REASON_MAX_LENGTH,
    OverrideReasonRequired,
    OverrideRequestSerializer,
)
from league.models import League, LeagueUser
from org.mmr import LEAGUE_GAME, game_for_tournament, game_mmrs_prefetch, org_mmr_map
from org.models import Organization, OrgUser
from telemetry.logging import get_logger
from user.querysets import with_user_profiles

from .models import (
    CustomUser,
    Game,
    GameMode,
    GameType,
    Joke,
    PositionsModel,
    Team,
    TeamLog,
    Tournament,
)

log = get_logger(__name__)


class UserPkField(serializers.RelatedField):
    """Serialize a user relationship as just their pk integer.
    Handles nullable FKs (e.g., deputy_captain) via allow_null.
    """

    def __init__(self, **kwargs: object) -> None:
        kwargs.setdefault("read_only", True)
        kwargs.setdefault("allow_null", True)
        super().__init__(**kwargs)

    def to_representation(self, value: CustomUser | None) -> int | None:
        if value is None:
            return None
        return value.pk


class PositionsSerializer(serializers.ModelSerializer):
    pk = serializers.IntegerField(required=False)
    carry = serializers.IntegerField()
    mid = serializers.IntegerField()
    offlane = serializers.IntegerField()
    soft_support = serializers.IntegerField()
    hard_support = serializers.IntegerField()

    class Meta:
        model = PositionsModel
        fields = ["pk", "carry", "mid", "offlane", "soft_support", "hard_support"]


class TournamentUserSerializer(serializers.ModelSerializer):
    positions = PositionsSerializer(many=False, read_only=True)
    # Auto-computed 32-bit Steam Account ID from 64-bit Friend ID
    steam_account_id = serializers.IntegerField(read_only=True)
    # nickname/avatar live on BaseUserProfile (T1 epic). Use `source="nickname"`
    # so DRF goes through the CustomUser transitional @property — the getter
    # reads from base_profile, the setter writes to base_profile + invalidates
    # cacheops. Critically, this keeps PATCH /users/<pk>/ working for admin
    # user-edit flows (org / tournament pages), which would otherwise be a
    # silent no-op if the fields were read_only=True.
    nickname = serializers.CharField(
        allow_null=True,
        allow_blank=True,
        required=False,
    )
    avatar = serializers.CharField(
        allow_null=True,
        allow_blank=True,
        required=False,
    )

    class Meta:
        model = CustomUser
        fields = (
            "pk",
            "username",
            "nickname",
            "avatar",
            "discordId",
            "discordNickname",
            "positions",
            "steam_account_id",
            "avatarUrl",
            "positions",
        )


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
    # local: org.serializers imports app.serializers
    from org.serializers import OrgUserSerializer

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
    # local: org.serializers imports app.serializers
    from org.serializers import OrgUserSerializer

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
    # local: org.serializers imports app.serializers
    from org.serializers import OrgUserSerializer

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
    # local: app.user_cache imports app.serializers
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


class TournamentSerializerBase(serializers.ModelSerializer):
    users = serializers.SerializerMethodField()
    captains = UserPkField(many=True, read_only=True)
    tournament_type = serializers.CharField(read_only=False)

    def get_users(self, tournament: Tournament) -> list[int]:
        """Return user PKs only — full data provided via _users dict."""
        return [u.pk for u in tournament.users.all()]

    class Meta:
        model = Tournament
        fields = (
            "pk",
            "name",
            "date_played",
            "users",
            "captains",
            "tournament_type",
        )


class TeamSerializerForTournament(serializers.ModelSerializer):
    members = serializers.SerializerMethodField()
    dropin_members = serializers.SerializerMethodField()
    left_members = serializers.SerializerMethodField()
    captain = serializers.SerializerMethodField()
    deputy_captain = serializers.SerializerMethodField()
    draft_order = serializers.IntegerField()

    def _index(self, team: Team) -> TeamUserIndex | None:
        index: TeamUserIndex | None = self.context.get(TEAM_USER_INDEX)
        return index if index is not None and team.pk in index.rosters else None

    def _roster(self, team: Team, field: str) -> list[dict[str, Any]]:
        index = self._index(team)
        if index is None:
            return _serialize_users_with_mmr(
                getattr(team, field).all(), team.tournament
            )
        # users without an OrgUser are left out, as in _serialize_users_with_mmr
        return [
            index.users[pk] for pk in index.rosters[team.pk][field] if pk in index.users
        ]

    def _user(self, team: Team, field: str) -> dict | None:
        index = self._index(team)
        user_id = getattr(team, f"{field}_id")
        if user_id is None:
            return None
        if index is not None and user_id in index.users:
            return index.users[user_id]
        return serialize_user_with_mmr(getattr(team, field), team.tournament)

    def get_members(self, team: Team) -> list[dict[str, Any]]:
        return self._roster(team, "members")

    def get_dropin_members(self, team: Team) -> list[dict[str, Any]]:
        return self._roster(team, "dropin_members")

    def get_left_members(self, team: Team) -> list[dict[str, Any]]:
        return self._roster(team, "left_members")

    def get_captain(self, team: Team) -> dict | None:
        return self._user(team, "captain")

    def get_deputy_captain(self, team: Team) -> dict | None:
        return self._user(team, "deputy_captain")

    class Meta:
        model = Team
        fields = (
            "pk",
            "name",
            "members",
            "dropin_members",
            "left_members",
            "captain",
            "deputy_captain",
            "draft_order",
            "placement",
            "draft_reserve_ms",
            "draft_is_ready",
            "draft_is_connected",
        )


class TeamSerializerSlim(TeamSerializerForTournament):
    """Slim variant — inherits everything, overrides user fields to pk-only."""

    members = UserPkField(many=True, read_only=True)
    captain = UserPkField()
    deputy_captain = UserPkField()
    dropin_members = UserPkField(many=True, read_only=True)
    left_members = UserPkField(many=True, read_only=True)


# For tournaments page
class TournamentsSerializer(serializers.ModelSerializer):
    captains = TournamentUserSerializer(many=True, read_only=True)
    winner = TeamSerializerForTournament(many=False, read_only=True)

    class Meta:
        model = Tournament
        fields = (
            "pk",
            "name",
            "date_played",
            "timezone",
            "tournament_type",
            "state",
            "captains",
            "winner",
        )


class LeagueMinimalSerializer(serializers.ModelSerializer):
    """Minimal league info for tournament list cards."""

    organization_name = serializers.SerializerMethodField()
    organization_id = serializers.SerializerMethodField()
    organization_logo = serializers.SerializerMethodField()

    class Meta:
        model = League
        fields = (
            "pk",
            "name",
            "organization_name",
            "organization_id",
            "organization_logo",
        )

    def get_organization_name(self, obj: League) -> str | None:
        org = obj.organization
        return org.name if org else None

    def get_organization_id(self, obj: League) -> int | None:
        return obj.organization_id

    def get_organization_logo(self, obj: League) -> str | None:
        org = obj.organization
        return (org.logo or None) if org else None


class TournamentListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for tournament list page.

    Only includes basic scalar fields and minimal league info.
    No nested team/user data for fast performance.
    """

    league = LeagueMinimalSerializer(read_only=True)
    user_count = serializers.IntegerField(read_only=True)
    signups_open = serializers.BooleanField(read_only=True)

    class Meta:
        model = Tournament
        fields = (
            "pk",
            "name",
            "date_played",
            "timezone",
            "tournament_type",
            "state",
            "league",
            "user_count",
            "signups_open",
        )


class OrganizationsSerializer(serializers.ModelSerializer):
    """Lightweight serializer for organization list view."""

    league_count = serializers.IntegerField(read_only=True)
    users_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Organization
        fields = ("pk", "name", "logo", "league_count", "users_count", "created_at")
        read_only_fields = ("pk", "league_count", "users_count", "created_at")


class LeaguesSerializer(serializers.ModelSerializer):
    """Lightweight serializer for league list view."""

    tournament_count = serializers.IntegerField(read_only=True)
    users_count = serializers.IntegerField(read_only=True)
    organization = OrganizationsSerializer(read_only=True)
    organization_name = serializers.SerializerMethodField()
    # Expose admin/staff membership IDs so the frontend permission hook
    # (useIsLeagueStaff / useCanEditTournament) can recognize league-level
    # admins and staff when this serializer is embedded inside a tournament
    # payload (TournamentSerializer.league). Without these the hook can only
    # see org-level membership and would deny league-staff users edit access
    # to bracket controls. PrimaryKeyRelatedField with many=True is read-only
    # by default for the GET path here.
    admin_ids = serializers.PrimaryKeyRelatedField(
        source="admins", many=True, read_only=True
    )
    staff_ids = serializers.PrimaryKeyRelatedField(
        source="staff", many=True, read_only=True
    )

    class Meta:
        model = League
        fields = (
            "pk",
            "organization",
            "organization_name",
            "steam_league_id",
            "name",
            "tournament_count",
            "users_count",
            "admin_ids",
            "staff_ids",
        )
        read_only_fields = (
            "pk",
            "tournament_count",
            "users_count",
            "organization_name",
            "organization",
            "admin_ids",
            "staff_ids",
        )

    def get_organization_name(self, obj: League) -> str | None:
        """Return first organization name for backwards compatibility."""
        first_org = obj.organization
        return first_org.name if first_org else None


def users_remaining_pks(draft: Draft) -> list[int]:
    """``Draft.users_remaining`` pks, taking the exclusions from prefetched rounds/teams."""
    tournament = draft.tournament
    draft_cache = getattr(draft, "_prefetched_objects_cache", {})
    tournament_cache = getattr(tournament, "_prefetched_objects_cache", {})
    if "draft_rounds" not in draft_cache or "teams" not in tournament_cache:
        return [u.pk for u in draft.users_remaining]
    if not tournament.users.exists():
        return []
    teams = tournament.teams.all()
    excluded = (
        {r.choice_id for r in draft.draft_rounds.all() if r.choice_id}
        | {t.captain_id for t in teams if t.captain_id}
        | {m.pk for t in teams for m in t.members.all()}
        | {m.pk for t in teams for m in t.dropin_members.all()}
        | {m.pk for t in teams for m in t.left_members.all()}
    )
    remaining = (
        tournament.users.nocache()
        .exclude(id__in=excluded)
        .exclude(id__in=tournament.draft_locked_user_ids())
        .distinct()
    )
    return [u.pk for u in remaining]


def _shared_draft_options(
    serializer: serializers.BaseSerializer, tournament: Tournament
) -> DraftOptions:
    """``get_draft_options()`` once per tournament for a whole serializer tree.

    Reuses the ``draft_options`` prefetched by tournament_state_queryset (marked
    with ``loaded_uncached``); a fresh context only takes one loaded uncached.
    Any other cached relation may predate a write and is re-read.
    """
    context = serializer.root.context
    memo = context.setdefault("_draft_options", {})
    if tournament.pk not in memo:
        fresh = context.get("fresh", False)
        options = _prefetched_draft_options(tournament)
        loaded_uncached = getattr(options, "loaded_uncached", None)
        if loaded_uncached is None or (fresh and not loaded_uncached):
            options = tournament.get_draft_options(fresh=fresh)
        memo[tournament.pk] = options
    return memo[tournament.pk]


def _prefetched_draft_options(tournament: Tournament) -> DraftOptions | None:
    if not Tournament.draft_options.is_cached(tournament):
        return None
    try:
        return tournament.draft_options
    except DraftOptions.DoesNotExist:
        return None


class DraftRoundForDraftSerializer(serializers.ModelSerializer):
    captain = serializers.SerializerMethodField()
    pick_phase = serializers.IntegerField()
    pick_number = serializers.IntegerField()

    choice = serializers.SerializerMethodField()
    team = TeamSerializerForTournament(many=False, read_only=True)

    def get_captain(self, draft_round: DraftRound) -> dict | None:
        return serialize_user_with_mmr(
            draft_round.captain, draft_round.draft.tournament
        )

    def get_choice(self, draft_round: DraftRound) -> dict | None:
        return serialize_user_with_mmr(draft_round.choice, draft_round.draft.tournament)

    class Meta:
        model = DraftRound
        fields = (
            "pk",
            "captain",
            "pick_phase",
            "pick_number",
            "choice",
            "team",
            "started_at",
            "completed_at",
            "timed_out_at",
            "grace_time_ms",
            "pick_duration_ms",
            "reserve_used_ms",
            "skip_count",
        )


class DraftRoundSerializerSlim(DraftRoundForDraftSerializer):
    """Slim variant — user fields as pks."""

    captain = UserPkField()
    choice = UserPkField()
    team = TeamSerializerSlim(many=False, read_only=True)


class TournamentSerializerForWebSocket(serializers.ModelSerializer):
    """
    Minimal tournament serializer for WebSocket broadcasts.
    Includes teams with PK-only members for real-time state updates.
    Full user data provided via _users dict.
    """

    teams = TeamSerializerSlim(many=True, read_only=True)

    class Meta:
        model = Tournament
        fields = (
            "pk",
            "teams",
        )


class DraftOptionsSerializer(serializers.ModelSerializer):
    grace_time_ms = serializers.IntegerField(min_value=1000, required=False)
    reserve_time_ms = serializers.IntegerField(min_value=0, required=False)
    hero_grace_time_ms = serializers.IntegerField(min_value=1000, required=False)
    hero_reserve_time_ms = serializers.IntegerField(min_value=0, required=False)

    class Meta:
        model = DraftOptions
        fields = (
            "timer_enabled",
            "grace_time_ms",
            "reserve_time_ms",
            "timeout_action",
            "hero_timer_enabled",
            "hero_grace_time_ms",
            "hero_reserve_time_ms",
        )
        read_only_fields = ("timeout_action",)


class DraftSerializerForTournament(serializers.ModelSerializer):
    """
    Serializer for draft data used in WebSocket broadcasts.
    Includes tournament.teams for real-time team updates.
    Full user data provided via _users dict.
    """

    draft_rounds = DraftRoundSerializerSlim(
        many=True,
        read_only=True,
    )
    users_remaining = serializers.SerializerMethodField()
    # Include tournament with teams for WebSocket broadcasts
    # This allows clients to update team state without additional API calls
    tournament = TournamentSerializerForWebSocket(read_only=True)
    state = serializers.CharField(read_only=True)
    clock_armed = serializers.SerializerMethodField()
    paused_at = serializers.DateTimeField(read_only=True)
    resuming_until = serializers.DateTimeField(read_only=True)
    is_manual_pause = serializers.BooleanField(read_only=True)
    draft_options = serializers.SerializerMethodField()

    def get_users_remaining(self, draft: Draft) -> list[int]:
        """Return user PKs only — full data provided via _users dict."""
        return users_remaining_pks(draft)

    def get_clock_armed(self, draft: Draft) -> bool:
        return draft.is_clock_armed(
            lambda: _shared_draft_options(self, draft.tournament)
        )

    def get_draft_options(self, draft: Draft) -> dict:
        return DraftOptionsSerializer(
            _shared_draft_options(self, draft.tournament)
        ).data

    class Meta:
        model = Draft
        fields = (
            "pk",
            "draft_rounds",
            "users_remaining",
            "latest_round",
            "draft_style",
            "tournament",
            "state",
            "clock_armed",
            "paused_at",
            "resuming_until",
            "is_manual_pause",
            "draft_options",
        )


class DraftSerializerSlim(DraftSerializerForTournament):
    """Slim variant — user fields as PKs, uses slim nested serializers."""

    draft_rounds = DraftRoundSerializerSlim(many=True, read_only=True)
    users_remaining = serializers.SerializerMethodField()

    def get_users_remaining(self, draft: Draft) -> list[int]:
        return users_remaining_pks(draft)


class GameSerializerForTournament(serializers.ModelSerializer):
    """Used inside TournamentSerializer which provides _users dict."""

    dire_team = TeamSerializerSlim(many=False, read_only=True)
    radiant_team = TeamSerializerSlim(many=False, read_only=True)
    winning_team = TeamSerializerSlim(many=False, read_only=True)
    herodraft_id = serializers.SerializerMethodField()

    def get_herodraft_id(self, obj: Game) -> int | None:
        if hasattr(obj, "herodraft"):
            return obj.herodraft.id
        return None

    class Meta:
        model = Game

        fields = (
            "pk",
            "radiant_team",
            "dire_team",
            "gameid",
            "round",
            "winning_team",
            "herodraft_id",
        )


class TeamSerializer(serializers.ModelSerializer):
    tournament = TournamentSerializerBase(
        many=False,
        read_only=True,
    )
    members = serializers.SerializerMethodField()
    dropin_members = serializers.SerializerMethodField()
    draft_order = serializers.IntegerField(
        default=0,
        help_text="Order in which a team picks their players in the draft",
    )
    current_points = serializers.IntegerField(
        read_only=False, write_only=False, default=0
    )
    member_ids = serializers.PrimaryKeyRelatedField(
        source="members",
        many=True,
        queryset=CustomUser.objects.all(),
        write_only=True,
        required=False,
    )

    dropin_member_ids = serializers.PrimaryKeyRelatedField(
        source="dropin_members",
        many=True,
        queryset=CustomUser.objects.all(),
        write_only=True,
        required=False,
    )

    left_member_ids = serializers.PrimaryKeyRelatedField(
        source="left_members",
        many=True,
        queryset=CustomUser.objects.all(),
        write_only=True,
        required=False,
    )
    captain = serializers.SerializerMethodField()
    deputy_captain = serializers.SerializerMethodField()

    captain_id = serializers.PrimaryKeyRelatedField(
        source="captain",
        many=False,
        queryset=CustomUser.objects.all(),
        write_only=True,
        required=False,
        allow_null=True,
    )
    deputy_captain_id = serializers.PrimaryKeyRelatedField(
        source="deputy_captain",
        many=False,
        queryset=CustomUser.objects.all(),
        write_only=True,
        required=False,
        allow_null=True,
    )
    total_mmr = serializers.SerializerMethodField()

    def get_members(self, team: Team) -> ReturnList:
        return _serialize_users_with_mmr(team.members.all(), team.tournament)

    def get_dropin_members(self, team: Team) -> ReturnList:
        return _serialize_users_with_mmr(team.dropin_members.all(), team.tournament)

    def get_captain(self, team: Team) -> dict | None:
        return serialize_user_with_mmr(team.captain, team.tournament)

    def get_deputy_captain(self, team: Team) -> dict | None:
        return serialize_user_with_mmr(team.deputy_captain, team.tournament)

    tournament_id = serializers.PrimaryKeyRelatedField(
        source="tournament",
        many=False,
        queryset=Tournament.objects.all(),
        write_only=True,
        read_only=False,
        required=False,
    )

    _LEADERSHIP_ERROR_FIELDS: ClassVar[dict[str, str]] = {
        "captain": "captain_id",
        "deputy_captain": "deputy_captain_id",
    }

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        instance: Team | None = self.instance
        if "members" in attrs:
            member_pks = {user.pk for user in attrs["members"]}
        elif instance is not None:
            member_pks = set(instance.members.values_list("pk", flat=True))
        else:
            member_pks = set()

        def final_pk(field: str) -> int | None:
            if field in attrs:
                return getattr(attrs[field], "pk", None)
            return getattr(instance, f"{field}_id", None)

        errors = Team.leadership_errors(
            member_pks,
            final_pk("captain"),
            final_pk("deputy_captain"),
            check_captain="captain" in attrs,
            check_deputy="deputy_captain" in attrs,
        )
        if errors:
            raise serializers.ValidationError(
                {self._LEADERSHIP_ERROR_FIELDS[k]: v for k, v in errors.items()}
            )
        if (
            instance is not None
            and "members" in attrs
            and not attrs["members"]
            and team_references([instance])
        ):
            raise serializers.ValidationError(
                {
                    "member_ids": [
                        "This team is used by bracket games or hero drafts; "
                        "remove it from those first."
                    ]
                }
            )
        return attrs

    # Members last: emptying them may delete the team (see app.signals).
    _ROSTER_FIELDS: ClassVar[tuple[str, ...]] = (
        "dropin_members",
        "left_members",
        "members",
    )

    def update(self, instance: Team, validated_data: dict[str, Any]) -> Team:
        """Apply the roster adding before removing, so a swap never empties the team."""
        rosters = {
            name: {user.pk for user in validated_data.pop(name)}
            for name in self._ROSTER_FIELDS
            if name in validated_data
        }
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        removals: dict[str, set[int]] = {}
        for name, wanted in rosters.items():
            manager = getattr(instance, name)
            current = set(manager.nocache().values_list("pk", flat=True))
            if wanted - current:
                manager.add(*(wanted - current))
            removals[name] = current - wanted
        for name, gone in removals.items():
            if gone and instance.pk is not None:
                getattr(instance, name).remove(*gone)
        return instance

    def get_total_mmr(self, obj: Team) -> int:
        """Org MMR of the captain plus members, for the tournament's game."""
        tournament = obj.tournament
        org_id = (
            tournament.league.organization_id
            if tournament and tournament.league
            else None
        )
        if not org_id:
            return 0
        game = game_for_tournament(tournament)
        user_ids = team_mmr_user_ids(obj)
        maps: dict[tuple[int, int], dict[int, int]] | None = self.context.get(
            TEAM_MMR_MAPS
        )
        mmrs = maps.get((org_id, int(game))) if maps is not None else None
        if mmrs is None:
            mmrs = org_mmr_map(org_id, user_ids, game)
        return sum(mmrs.get(user_id, 0) for user_id in user_ids)

    class Meta:
        model = Team
        fields = (
            "pk",
            "name",
            "left_members",
            "left_member_ids",
            "captain",
            "captain_id",
            "deputy_captain",
            "deputy_captain_id",
            "member_ids",
            "dropin_member_ids",
            "tournament_id",
            "members",
            "dropin_members",
            "draft_order",
            "current_points",
            "tournament",
            "total_mmr",
            "placement",
        )


def team_mmr_user_ids(team: Team) -> set[int]:
    ids = {user.pk for user in team.members.all()}
    if team.captain_id:
        ids.add(team.captain_id)
    return ids


def build_team_mmr_maps(
    teams: Collection[Team],
) -> dict[tuple[int, int], dict[int, int]]:
    """One org_mmr_map per (org, game) over every captain/member of `teams`.

    Expects teams with `tournament__league` selected and `members` prefetched.
    """
    wanted: dict[tuple[int, int], set[int]] = {}
    for team in teams:
        tournament = team.tournament
        if (
            not tournament
            or not tournament.league
            or not tournament.league.organization_id
        ):
            continue
        key = (tournament.league.organization_id, int(game_for_tournament(tournament)))
        wanted.setdefault(key, set()).update(team_mmr_user_ids(team))
    return {
        (org_id, game): org_mmr_map(org_id, user_ids, game)
        for (org_id, game), user_ids in wanted.items()
    }


def _leadership_problem_rows(team: Team) -> list[dict[str, str]]:
    # members.all() so tournament payloads reuse the teams__members prefetch.
    member_pks = {user.pk for user in team.members.all()}
    problems = Team.leadership_problems(
        member_pks, team.captain_id, team.deputy_captain_id
    )
    return [
        {"field": field, "code": str(problem), "message": problem.message}
        for field, problem in problems.items()
    ]


class ManagedTeamSerializer(TeamSerializer):
    """Public team detail and staff action responses; never used for writes."""

    left_members = serializers.SerializerMethodField()
    leadership_problems = serializers.SerializerMethodField()

    def get_left_members(self, team: Team) -> ReturnList:
        return _serialize_users_with_mmr(team.left_members.all(), team.tournament)

    def get_leadership_problems(self, team: Team) -> list[dict[str, str]]:
        return _leadership_problem_rows(team)

    class Meta(TeamSerializer.Meta):
        fields = (*TeamSerializer.Meta.fields, "leadership_problems")


class TournamentTeamSerializer(TeamSerializerSlim):
    leadership_problems = serializers.SerializerMethodField()

    def get_leadership_problems(self, team: Team) -> list[dict[str, str]]:
        return _leadership_problem_rows(team)

    class Meta(TeamSerializerSlim.Meta):
        fields = (*TeamSerializerSlim.Meta.fields, "leadership_problems")


class TeamLogSerializer(serializers.ModelSerializer):
    actor = TournamentUserSerializer(read_only=True, allow_null=True)
    target = TournamentUserSerializer(
        source="target_user", read_only=True, allow_null=True
    )
    team_id = serializers.IntegerField(source="team_snapshot_id", read_only=True)

    class Meta:
        model = TeamLog
        fields = (
            "id",
            "action",
            "via",
            "actor",
            "target",
            "reason",
            "override_rules",
            "details",
            "team_name",
            "team_id",
            "created_at",
        )
        read_only_fields = fields


class TeamActionRequestSerializer(OverrideRequestSerializer):
    reason = serializers.CharField(
        required=False,
        allow_blank=True,
        allow_null=True,
        default="",
        trim_whitespace=True,
        max_length=REASON_MAX_LENGTH,
    )

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        attrs["reason"] = (attrs.get("reason") or "").strip()
        if not attrs["reason"]:
            if attrs.get("acknowledged_codes"):
                raise OverrideReasonRequired()
            raise serializers.ValidationError({"reason": ["This field is required."]})
        return attrs


class TeamUserActionRequestSerializer(TeamActionRequestSerializer):
    user_id = serializers.PrimaryKeyRelatedField(queryset=CustomUser.objects.all())


class TeamDeputyRequestSerializer(TeamActionRequestSerializer):
    user_id = serializers.PrimaryKeyRelatedField(
        queryset=CustomUser.objects.all(), allow_null=True
    )


class TeamSubInRequestSerializer(TeamActionRequestSerializer):
    standin_id = serializers.PrimaryKeyRelatedField(queryset=CustomUser.objects.all())
    replacing_id = serializers.PrimaryKeyRelatedField(
        queryset=CustomUser.objects.all(),
        required=False,
        allow_null=True,
        default=None,
    )


class TeamRenameRequestSerializer(TeamActionRequestSerializer):
    # Blank/length/unchanged checks belong to the service so codes have one source.
    name = serializers.CharField(allow_blank=True, trim_whitespace=False)


class TournamentSerializer(serializers.ModelSerializer):
    teams = TournamentTeamSerializer(many=True, read_only=True)
    users = serializers.SerializerMethodField()
    draft = DraftSerializerSlim(many=False, read_only=True)
    draft_options = DraftOptionsSerializer(required=False)

    user_ids = serializers.PrimaryKeyRelatedField(
        source="users",
        many=True,
        queryset=CustomUser.objects.all(),
        write_only=True,
        required=False,
    )
    tournament_type = serializers.CharField(read_only=False)
    captains = UserPkField(many=True, read_only=True)
    games = GameSerializerForTournament(many=True, read_only=True)
    league = LeaguesSerializer(read_only=True)
    league_id_write = serializers.PrimaryKeyRelatedField(
        queryset=League.objects.all(),
        write_only=True,
        source="league",
        required=False,
        allow_null=True,
    )
    organization_pk = serializers.SerializerMethodField()
    league_pk = serializers.SerializerMethodField()
    source_event = serializers.SerializerMethodField()

    def get_organization_pk(self, tournament: Tournament) -> int | None:
        """Return the primary organization's PK for this tournament."""
        org = tournament_organization(
            tournament, fresh=self.context.get("fresh", False)
        )
        return org.pk if org else None

    def get_league_pk(self, tournament: Tournament) -> int | None:
        """Return the league's PK for this tournament."""
        return tournament.league.pk if tournament.league else None

    def get_source_event(self, tournament: Tournament) -> dict | None:
        """Return lightweight source event data (event that spawned this tournament)."""
        events = tournament.source_event.all()
        if self.context.get("fresh", False):
            events = events.nocache().select_related("event_repeater")
        event = events.first()
        if not event:
            return None
        result = {
            "id": event.id,
            "name": event.name,
            "organization_id": event.organization_id,
            "event_repeater": None,
        }
        if event.event_repeater:
            result["event_repeater"] = {
                "id": event.event_repeater.id,
                "name": event.event_repeater.name,
            }
        return result

    def get_users(self, tournament: Tournament) -> list[int]:
        """Return user PKs only — full data provided via _users dict."""
        return [u.pk for u in tournament.users.all()]

    class Meta:
        model = Tournament
        fields = (
            "pk",
            "name",
            "draft",
            "date_played",
            "timezone",
            "users",
            "teams",
            "winning_team",
            "state",
            "games",
            "user_ids",
            "captains",
            "tournament_type",
            "league",
            "league_id_write",
            "organization_pk",
            "league_pk",
            "source_event",
            "auto_create_hero_drafts",
            "discord_send_draft_link",
            "discord_send_herodraft_link",
            "draft_options",
            "dota_lobby_mode",
            "dota_lobby_launch",
            "dota_lobby_region",
            "discord_send_lobby_info",
            "game_type",
            "game_mode",
            "lobby_steam_league_id",
            "captains_draft_time",
            "custom_game_name",
        )
        # The game is fixed at creation; everything else is editable.
        read_only_fields = ("game_type",)
        extra_kwargs = {"captains_draft_time": {"min_value": 1}}

    def validate(self, data: dict) -> dict:
        self._validate_game_mode(data)
        if "lobby_steam_league_id" in data and (
            self.instance is None
            or data["lobby_steam_league_id"] != self.instance.lobby_steam_league_id
        ):
            check_lobby_steam_league_id(
                request_user(self.context),
                data["lobby_steam_league_id"],
                data.get("league", self.instance.league if self.instance else None),
            )
        return data

    def _validate_game_mode(self, data: dict) -> None:
        mode = data.get("game_mode")
        if mode is None or (self.instance and mode == self.instance.game_mode):
            return
        game_type = (
            self.instance.game_type
            if self.instance
            else Tournament._meta.get_field("game_type").default
        )
        if game_type != GameType.DOTA2 and mode in (
            GameMode.CAPTAINS_MODE,
            GameMode.TURBO,
        ):
            raise serializers.ValidationError(
                {"game_mode": f"{mode} is only available for Dota 2."}
            )

    def to_representation(self, instance: Tournament) -> dict:
        data = super().to_representation(instance)
        data["draft_options"] = DraftOptionsSerializer(self._options_for(instance)).data
        return data

    def _options_for(self, instance: Tournament) -> DraftOptions:
        if isinstance(self.parent, serializers.ListSerializer):
            try:
                return instance.draft_options
            except DraftOptions.DoesNotExist:
                return DraftOptions(tournament=instance)
        return _shared_draft_options(self, instance)

    def update(self, instance: Tournament, validated_data: dict) -> Tournament:
        """
        Override update to handle:
        1. Captain removal when users are removed (delete their team)
        2. OrgUser/LeagueUser creation when users are added
        """
        with transaction.atomic():
            # Check if users are being updated
            if "users" in validated_data:
                new_users = set(validated_data["users"])
                current_users = set(instance.users.all())
                removed_users = current_users - new_users
                added_users = new_users - current_users

                # Bulk delete teams where removed users are captains
                if removed_users:
                    removed_user_ids = [u.pk for u in removed_users]
                    captain_teams = Team.objects.filter(
                        tournament=instance, captain_id__in=removed_user_ids
                    )
                    if captain_teams.exists():
                        log.info(
                            "captain_teams_removed",
                            system="api",
                            subsystem="serializer",
                            count=captain_teams.count(),
                            tournament_id=instance.pk,
                        )
                        captain_teams.delete()

                # Bulk create OrgUser and LeagueUser for added users
                if added_users and instance.league:
                    org = instance.league.organization
                    if org:
                        # Get existing OrgUsers for these users in this org
                        existing_org_users = {
                            ou.user_id: ou
                            for ou in OrgUser.objects.filter(
                                user__in=added_users, organization=org
                            )
                        }

                        # Create missing OrgUsers in bulk
                        new_org_users = []
                        for user in added_users:
                            if user.pk not in existing_org_users:
                                new_org_users.append(
                                    OrgUser(user=user, organization=org)
                                )
                        if new_org_users:
                            OrgUser.objects.bulk_create(new_org_users)
                            # Refresh existing_org_users with newly created ones
                            existing_org_users = {
                                ou.user_id: ou
                                for ou in OrgUser.objects.filter(
                                    user__in=added_users, organization=org
                                )
                            }

                        # Get existing LeagueUsers for these users in this league
                        existing_league_users = set(
                            LeagueUser.objects.filter(
                                user__in=added_users, league=instance.league
                            ).values_list("user_id", flat=True)
                        )

                        # Create missing LeagueUsers in bulk
                        league_mmrs = org_mmr_map(
                            org.pk,
                            [
                                u.pk
                                for u in added_users
                                if u.pk not in existing_league_users
                            ],
                            LEAGUE_GAME,
                        )
                        new_league_users = []
                        for user in added_users:
                            if user.pk not in existing_league_users:
                                org_user = existing_org_users.get(user.pk)
                                if org_user:
                                    new_league_users.append(
                                        LeagueUser(
                                            user=user,
                                            org_user=org_user,
                                            league=instance.league,
                                            mmr=league_mmrs.get(user.pk, 0),
                                        )
                                    )
                        if new_league_users:
                            LeagueUser.objects.bulk_create(new_league_users)

            return super().update(instance, validated_data)


class UserSerializer(serializers.ModelSerializer):
    teams = TeamSerializer(many=True, read_only=True)  # Associated teams
    positions = PositionsSerializer(many=False, read_only=False, required=False)
    default_organization = serializers.PrimaryKeyRelatedField(
        queryset=Organization.objects.all(),
        required=False,
        allow_null=True,
    )
    # Declaring the field explicitly drops the UniqueValidator ModelSerializer
    # would have built from unique=True, so re-attach it — without this a
    # collision reaches the DB and surfaces as a 500.
    steam_account_id = serializers.IntegerField(
        required=False,
        allow_null=True,
        validators=[
            UniqueValidator(
                queryset=CustomUser.objects.all(),
                message="This Friend ID is already assigned to another account.",
            )
        ],
    )
    # Role memberships used by frontend permission hooks to gate create
    # actions without needing a follow-up fetch (e.g. Create Tournament
    # button on the global /tournaments/ page). Empty lists for users with
    # no affiliations — never null.
    admin_organization_ids = serializers.SerializerMethodField()
    staff_organization_ids = serializers.SerializerMethodField()
    admin_league_ids = serializers.SerializerMethodField()
    staff_league_ids = serializers.SerializerMethodField()
    # nickname/avatar live on BaseUserProfile (T1 epic). Use `source="nickname"`
    # so DRF goes through the CustomUser transitional @property — the getter
    # reads from base_profile, the setter writes to base_profile + invalidates
    # cacheops. Keeps PATCH /users/<pk>/ working for admin user-edit flows
    # (org/tournament pages) which would otherwise be a silent no-op.
    nickname = serializers.CharField(
        allow_null=True,
        allow_blank=True,
        required=False,
    )
    avatar = serializers.CharField(
        allow_null=True,
        allow_blank=True,
        required=False,
    )

    class Meta:
        model = CustomUser
        fields = (
            "pk",
            "username",
            "nickname",
            "discordNickname",
            "is_staff",
            "is_active",
            "is_superuser",
            "avatar",
            "discordId",
            "steam_account_id",
            "avatarUrl",
            "email",
            "date_joined",
            "teams",  # Include associated teams
            "positions",
            "default_organization",
            "admin_organization_ids",
            "staff_organization_ids",
            "admin_league_ids",
            "staff_league_ids",
        )

    def get_admin_organization_ids(self, obj: CustomUser) -> list[int]:
        # Owner counts as admin in the hierarchy; merge both reverse
        # relations so the frontend gets one canonical "I can admin this
        # org" list. Dedupe via set in case an owner is also in admins.
        owned = obj.owned_organizations.values_list("pk", flat=True)
        admin = obj.admin_organizations.values_list("pk", flat=True)
        return sorted({*owned, *admin})

    def get_staff_organization_ids(self, obj: CustomUser) -> list[int]:
        return list(obj.staff_organizations.values_list("pk", flat=True))

    def get_admin_league_ids(self, obj: CustomUser) -> list[int]:
        return list(obj.admin_leagues.values_list("pk", flat=True))

    def get_staff_league_ids(self, obj: CustomUser) -> list[int]:
        return list(obj.staff_leagues.values_list("pk", flat=True))

    PRIVILEGE_FIELDS: Final[frozenset[str]] = frozenset(
        {"is_staff", "is_superuser", "is_active"}
    )

    def _strip_privilege_fields(
        self, validated_data: dict[str, Any], target_id: int | None
    ) -> None:
        request = self.context.get("request")
        actor = getattr(request, "user", None)
        if actor is not None and actor.is_superuser:
            return
        dropped = sorted(f for f in self.PRIVILEGE_FIELDS if f in validated_data)
        if not dropped:
            return
        for field in dropped:
            validated_data.pop(field)
        log.warning(
            "user_privilege_fields_ignored",
            system="user",
            subsystem="serializer",
            actor_id=getattr(actor, "pk", None),
            target_id=target_id,
            fields=dropped,
        )

    def _actor(self) -> CustomUser | None:
        actor = getattr(self.context.get("request"), "user", None)
        return actor if isinstance(actor, CustomUser) else None

    def update(self, instance: CustomUser, validated_data: dict) -> CustomUser:
        self._strip_privilege_fields(validated_data, instance.pk)
        validated_data.pop("discordNickname", None)
        with transaction.atomic():
            try:
                positions_data = validated_data.pop("positions", None)
                if positions_data:
                    if instance.positions is None:
                        # SET_NULL on DotaUserProfile.positions means the shim
                        # getter can return None — create on demand (the shim
                        # setter persists it onto the dota profile).
                        instance.positions = PositionsModel.objects.create()
                    positions_instance = instance.positions
                    for key, value in positions_data.items():
                        setattr(positions_instance, key, value)
                    positions_instance.save()
                    log.debug(
                        "positions_updated",
                        system="api",
                        subsystem="serializer",
                    )
            except KeyError:
                pass
            has_steam_id = "steam_account_id" in validated_data
            new_steam_id = validated_data.pop("steam_account_id", None)
            for key, value in validated_data.items():
                setattr(instance, key, value)
            grant = (
                apply_admin_steam_account_id(
                    instance, new_steam_id, actor=self._actor()
                )
                if has_steam_id
                else None
            )

            instance.save()
            if grant is not None:
                log_steam_verification_change(
                    instance, self._actor(), grant.org_id, True
                )
            log.debug(
                "user_updated",
                system="api",
                subsystem="serializer",
                user_id=instance.pk,
            )

            # Invalidate all cached views that include this user.
            # Deferred until after commit so cacheops sees committed state.
            invalidate_after_commit(
                *instance.tournaments.all(),
                *instance.org_memberships.select_related("organization").all(),
                *(
                    mu.organization
                    for mu in instance.org_memberships.select_related(
                        "organization"
                    ).all()
                ),
                *instance.league_memberships.select_related("league").all(),
                *(
                    mu.league
                    for mu in instance.league_memberships.select_related("league").all()
                ),
            )

        return instance

    def create(self, validated_data: dict) -> CustomUser:
        self._strip_privilege_fields(validated_data, None)
        fields = self.Meta.fields

        with transaction.atomic():
            for key in validated_data.keys():
                if key not in fields:
                    raise KeyError(f"Invalid field: {key}")

            has_steam_id = "steam_account_id" in validated_data
            new_steam_id = validated_data.pop("steam_account_id", None)
            if "positions" in validated_data:
                positions_data = validated_data.pop("positions")
                positions = PositionsModel.objects.create(**positions_data)
            else:
                log.debug(
                    "user_create_no_positions", system="api", subsystem="serializer"
                )
                positions = PositionsModel.objects.create()
            user = CustomUser(positions=positions, **validated_data)
            grant = (
                apply_admin_steam_account_id(user, new_steam_id, actor=self._actor())
                if has_steam_id
                else None
            )

            user.save()
            if grant is not None:
                log_steam_verification_change(user, self._actor(), grant.org_id, True)
            return user


class GameSerializer(serializers.ModelSerializer):
    tournament_id = serializers.PrimaryKeyRelatedField(
        source="tournament",
        many=False,
        queryset=Tournament.objects.all(),
        write_only=True,
        required=False,
    )
    dire_team = TeamSerializerForTournament(many=False, read_only=True)
    radiant_team = TeamSerializerForTournament(many=False, read_only=True)
    radiant_team_id = serializers.PrimaryKeyRelatedField(
        source="radiant_team",
        many=False,
        queryset=Team.objects.all(),
        write_only=True,
        required=False,
    )
    dire_team_id = radiant_team_id = serializers.PrimaryKeyRelatedField(
        source="dire_team",
        many=False,
        queryset=Team.objects.all(),
        write_only=True,
        required=False,
    )

    winning_team = TeamSerializerForTournament(many=False, read_only=True)
    winning_team_id = serializers.PrimaryKeyRelatedField(
        source="winning_team",
        many=False,
        queryset=Team.objects.all(),
        write_only=True,
        required=False,
    )
    herodraft_id = serializers.SerializerMethodField()

    def get_herodraft_id(self, obj: Game) -> int | None:
        if hasattr(obj, "herodraft"):
            return obj.herodraft.id
        return None

    class Meta:
        model = Game

        fields = (
            "pk",
            "tournament_id",
            "radiant_team",
            "radiant_team_id",
            "dire_team",
            "dire_team_id",
            "gameid",
            "round",
            "winning_team",
            "winning_team_id",
            "herodraft_id",
        )


class BracketGameSerializer(serializers.ModelSerializer):
    """Serializer for bracket view with full team details."""

    radiant_team = TeamSerializerForTournament(read_only=True)
    dire_team = TeamSerializerForTournament(read_only=True)
    winning_team = TeamSerializerForTournament(read_only=True)
    herodraft_id = serializers.SerializerMethodField()
    lobby_state = serializers.SerializerMethodField()

    def get_herodraft_id(self, obj: Game) -> int | None:
        if hasattr(obj, "herodraft"):
            return obj.herodraft.id
        return None

    def get_lobby_state(self, obj: Game) -> str | None:
        """State of the game's latest dota_lobby lobby, or None. No password.

        get_bracket prefetches the lobbies into `latest_lobbies`; other
        callers serialize one game and query it.
        """
        lobbies = getattr(obj, "latest_lobbies", None)
        if lobbies is not None:
            return lobbies[0].state if lobbies else None
        return obj.lobbies.values_list("state", flat=True).first()

    class Meta:
        model = Game
        fields = (
            "pk",
            "round",
            "position",
            "bracket_type",
            "elimination_type",
            "radiant_team",
            "dire_team",
            "winning_team",
            "status",
            "next_game",
            "next_game_slot",
            "loser_next_game",
            "loser_next_game_slot",
            "swiss_record_wins",
            "swiss_record_losses",
            "gameid",
            "herodraft_id",
            "lobby_state",
        )


class BracketSaveSerializer(serializers.Serializer):
    """Serializer for saving bracket structure."""

    matches = serializers.ListField(
        child=serializers.DictField(), help_text="List of match objects to save"
    )


class BracketGenerateSerializer(serializers.Serializer):
    """Serializer for generating bracket."""

    seeding_method = serializers.ChoiceField(
        choices=["random", "mmr_total", "captain_mmr"], default="mmr_total"
    )


class JokeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Joke
        fields = ["tangoes_purchased"]
        read_only_fields = ["tangoes_purchased"]


class LeagueMatchSerializer(serializers.ModelSerializer):
    """Serializer for matches in a league context with captain info."""

    radiant_captain = TournamentUserSerializer(
        source="radiant_team.captain", read_only=True, allow_null=True
    )
    dire_captain = TournamentUserSerializer(
        source="dire_team.captain", read_only=True, allow_null=True
    )
    radiant_team_name = serializers.CharField(
        source="radiant_team.name", read_only=True, allow_null=True
    )
    dire_team_name = serializers.CharField(
        source="dire_team.name", read_only=True, allow_null=True
    )
    tournament_name = serializers.CharField(
        source="tournament.name", read_only=True, allow_null=True
    )
    tournament_pk = serializers.IntegerField(
        source="tournament.pk", read_only=True, allow_null=True
    )
    date_played = serializers.DateTimeField(
        source="tournament.date_played", read_only=True, allow_null=True
    )

    class Meta:
        model = Game
        fields = [
            "pk",
            "tournament_pk",
            "tournament_name",
            "round",
            "date_played",
            "radiant_team",
            "dire_team",
            "radiant_team_name",
            "dire_team_name",
            "radiant_captain",
            "dire_captain",
            "winning_team",
            "gameid",
        ]
