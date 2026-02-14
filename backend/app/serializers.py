from ast import alias
from logging import getLogger
from typing import TypeAlias

import nh3
from django.contrib.auth.models import User
from django.db import transaction
from rest_framework import serializers

from app.cache_utils import invalidate_after_commit

log = getLogger(__name__)
from .models import (
    CustomUser,
    Draft,
    DraftEvent,
    DraftRound,
    DraftTeam,
    Game,
    HeroDraft,
    HeroDraftEvent,
    HeroDraftRound,
    Joke,
    League,
    Organization,
    PositionsModel,
    Team,
    Tournament,
)


class UserPkField(serializers.RelatedField):
    """Serialize a user relationship as just their pk integer.
    Handles nullable FKs (e.g., deputy_captain) via allow_null.
    """

    def __init__(self, **kwargs):
        kwargs.setdefault("read_only", True)
        kwargs.setdefault("allow_null", True)
        super().__init__(**kwargs)

    def to_representation(self, value):
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


def _serialize_users_with_mmr(users_qs, tournament):
    """Serialize users with org-scoped MMR if tournament has a league/org."""
    from django.db.models import Prefetch

    from league.models import LeagueUser
    from org.models import OrgUser
    from org.serializers import OrgUserSerializer

    league = tournament.league if tournament else None
    org = league.organization if league else None

    if not org:
        return TournamentUserSerializer(users_qs, many=True).data

    # Auto-create OrgUser records for tournament users missing from the org
    existing_user_pks = set(
        OrgUser.objects.filter(user__in=users_qs, organization=org).values_list(
            "user_id", flat=True
        )
    )
    missing_users = users_qs.exclude(pk__in=existing_user_pks)
    if missing_users.exists():
        OrgUser.objects.bulk_create(
            [OrgUser(user=u, organization=org) for u in missing_users],
            ignore_conflicts=True,
        )

    org_users = (
        OrgUser.objects.filter(user__in=users_qs, organization=org)
        .select_related("user", "user__positions")
        .prefetch_related(
            Prefetch(
                "league_memberships",
                queryset=LeagueUser.objects.filter(league_id=league.pk),
            )
        )
    )
    return OrgUserSerializer(
        org_users, many=True, context={"league_id": league.pk}
    ).data


def _serialize_user_with_mmr(user, tournament):
    """Serialize a single user with org-scoped MMR. Returns None if user is None."""
    if user is None:
        return None
    results = _serialize_users_with_mmr(
        type(user).objects.filter(pk=user.pk), tournament
    )
    return results[0] if results else TournamentUserSerializer(user).data


def _collect_tournament_user_pks(tournament):
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


def _build_users_dict(tournament):
    """Build a deduplicated {pk: serialized_user} dict for a tournament."""
    seen_pks = _collect_tournament_user_pks(tournament)
    user_qs = CustomUser.objects.filter(pk__in=seen_pks).select_related("positions")
    return {u["pk"]: u for u in _serialize_users_with_mmr(user_qs, tournament)}


class TournamentSerializerBase(serializers.ModelSerializer):
    users = serializers.SerializerMethodField()
    captains = UserPkField(many=True, read_only=True)
    tournament_type = serializers.CharField(read_only=False)

    def get_users(self, tournament):
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

    def get_members(self, team):
        return _serialize_users_with_mmr(team.members.all(), team.tournament)

    def get_dropin_members(self, team):
        return _serialize_users_with_mmr(team.dropin_members.all(), team.tournament)

    def get_left_members(self, team):
        return _serialize_users_with_mmr(team.left_members.all(), team.tournament)

    def get_captain(self, team):
        return _serialize_user_with_mmr(team.captain, team.tournament)

    def get_deputy_captain(self, team):
        return _serialize_user_with_mmr(team.deputy_captain, team.tournament)

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

    class Meta:
        model = League
        fields = ("pk", "name", "organization_name")

    def get_organization_name(self, obj):
        """Get the first organization name, if any."""
        # Use prefetched data if available, otherwise query
        orgs = getattr(obj, "_prefetched_objects_cache", {}).get("organizations")
        if orgs is not None:
            return orgs[0].name if orgs else None
        first_org = obj.organization
        return first_org.name if first_org else None


class TournamentListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for tournament list page.

    Only includes basic scalar fields and minimal league info.
    No nested team/user data for fast performance.
    """

    league = LeagueMinimalSerializer(read_only=True)
    user_count = serializers.IntegerField(read_only=True)

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
        )


class OrganizationSerializer(serializers.ModelSerializer):
    owner = TournamentUserSerializer(read_only=True)
    owner_id = serializers.PrimaryKeyRelatedField(
        queryset=CustomUser.objects.all(),
        write_only=True,
        source="owner",
        required=False,
        allow_null=True,
    )
    admins = TournamentUserSerializer(many=True, read_only=True)
    staff = TournamentUserSerializer(many=True, read_only=True)
    admin_ids = serializers.PrimaryKeyRelatedField(
        queryset=CustomUser.objects.all(),
        many=True,
        write_only=True,
        source="admins",
        required=False,
    )
    staff_ids = serializers.PrimaryKeyRelatedField(
        queryset=CustomUser.objects.all(),
        many=True,
        write_only=True,
        source="staff",
        required=False,
    )
    # Use annotated fields from ViewSet queryset (avoids N+1)
    league_count = serializers.IntegerField(read_only=True)
    tournament_count = serializers.IntegerField(read_only=True)
    users_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Organization
        fields = (
            "pk",
            "name",
            "description",
            "logo",
            "discord_link",
            "discord_server_id",
            "rules_template",
            "timezone",
            "owner",
            "owner_id",
            "admins",
            "staff",
            "admin_ids",
            "staff_ids",
            "default_league",
            "league_count",
            "tournament_count",
            "users_count",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "pk",
            "created_at",
            "updated_at",
            "league_count",
            "tournament_count",
            "users_count",
        )

    def validate_description(self, value):
        """Sanitize markdown to prevent XSS."""
        if value:
            return nh3.clean(value)
        return value

    def validate_rules_template(self, value):
        """Sanitize markdown to prevent XSS."""
        if value:
            return nh3.clean(value)
        return value


class OrganizationsSerializer(serializers.ModelSerializer):
    """Lightweight serializer for organization list view."""

    league_count = serializers.IntegerField(read_only=True)
    users_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Organization
        fields = ("pk", "name", "logo", "league_count", "users_count", "created_at")
        read_only_fields = ("pk", "league_count", "users_count", "created_at")


class LeagueSerializer(serializers.ModelSerializer):
    organization = OrganizationsSerializer(read_only=True)
    organization_id = serializers.PrimaryKeyRelatedField(
        queryset=Organization.objects.all(),
        write_only=True,
        source="organization",
        required=False,
    )
    admins = TournamentUserSerializer(many=True, read_only=True)
    staff = TournamentUserSerializer(many=True, read_only=True)
    admin_ids = serializers.PrimaryKeyRelatedField(
        queryset=CustomUser.objects.all(),
        many=True,
        write_only=True,
        source="admins",
        required=False,
    )
    staff_ids = serializers.PrimaryKeyRelatedField(
        queryset=CustomUser.objects.all(),
        many=True,
        write_only=True,
        source="staff",
        required=False,
    )
    tournament_count = serializers.IntegerField(read_only=True)
    users_count = serializers.IntegerField(read_only=True)
    # For backwards compatibility, return first org name
    organization_name = serializers.SerializerMethodField()

    class Meta:
        model = League
        fields = (
            "pk",
            "organization",
            "organization_id",
            "organization_name",
            "steam_league_id",
            "name",
            "description",
            "rules",
            "prize_pool",
            "timezone",
            "admins",
            "staff",
            "admin_ids",
            "staff_ids",
            "tournament_count",
            "users_count",
            "last_synced",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "pk",
            "created_at",
            "updated_at",
            "tournament_count",
            "users_count",
            "organization_name",
        )

    def get_organization_name(self, obj):
        """Return first organization name for backwards compatibility."""
        first_org = obj.organization
        return first_org.name if first_org else None

    def validate_description(self, value):
        if value:
            return nh3.clean(value)
        return value

    def validate_rules(self, value):
        if value:
            return nh3.clean(value)
        return value


class LeaguesSerializer(serializers.ModelSerializer):
    """Lightweight serializer for league list view."""

    tournament_count = serializers.IntegerField(read_only=True)
    users_count = serializers.IntegerField(read_only=True)
    organization = OrganizationsSerializer(read_only=True)
    organization_name = serializers.SerializerMethodField()

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
        )
        read_only_fields = (
            "pk",
            "tournament_count",
            "users_count",
            "organization_name",
            "organization",
        )

    def get_organization_name(self, obj):
        """Return first organization name for backwards compatibility."""
        first_org = obj.organization
        return first_org.name if first_org else None


class DraftRoundForDraftSerializer(serializers.ModelSerializer):

    captain = serializers.SerializerMethodField()
    pick_phase = serializers.IntegerField()
    pick_number = serializers.IntegerField()

    choice = serializers.SerializerMethodField()
    team = TeamSerializerForTournament(many=False, read_only=True)

    def get_captain(self, draft_round):
        return _serialize_user_with_mmr(
            draft_round.captain, draft_round.draft.tournament
        )

    def get_choice(self, draft_round):
        return _serialize_user_with_mmr(
            draft_round.choice, draft_round.draft.tournament
        )

    class Meta:
        model = DraftRound
        fields = (
            "pk",
            "captain",
            "pick_phase",
            "pick_number",
            "choice",
            "team",
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

    def get_users_remaining(self, draft):
        """Return user PKs only — full data provided via _users dict."""
        return [u.pk for u in draft.users_remaining]

    class Meta:
        model = Draft
        fields = (
            "pk",
            "draft_rounds",
            "users_remaining",
            "latest_round",
            "draft_style",
            "tournament",
        )


class DraftSerializerSlim(DraftSerializerForTournament):
    """Slim variant — user fields as PKs, uses slim nested serializers."""

    draft_rounds = DraftRoundSerializerSlim(many=True, read_only=True)
    users_remaining = serializers.SerializerMethodField()

    def get_users_remaining(self, draft):
        return [u.pk for u in draft.users_remaining]


class TournamentSerializerDraft(serializers.ModelSerializer):
    teams = TeamSerializerSlim(many=True, read_only=True)
    users = serializers.SerializerMethodField()

    tournament_type = serializers.CharField(read_only=False)
    captains = UserPkField(many=True, read_only=True)

    def get_users(self, tournament):
        """Return user PKs only — full data provided via _users dict."""
        return [u.pk for u in tournament.users.all()]

    class Meta:
        model = Tournament
        fields = (
            "pk",
            "name",
            "date_played",
            "users",
            "teams",
            "captains",
            "tournament_type",
        )


class DraftSerializer(serializers.ModelSerializer):

    tournament = TournamentSerializerDraft(
        many=False,
        read_only=True,
    )
    users_remaining = serializers.SerializerMethodField()

    draft_rounds = DraftRoundSerializerSlim(
        many=True,
        read_only=True,
    )

    def get_users_remaining(self, draft):
        """Return user PKs only — full data provided via _users dict."""
        return [u.pk for u in draft.users_remaining]

    class Meta:
        model = Draft
        fields = (
            "pk",
            "tournament",
            "draft_rounds",
            "draft_style",
            "users_remaining",
            "latest_round",
        )


class DraftSerializerMMRs(serializers.ModelSerializer):

    class Meta:
        model = Draft
        fields = (
            "pk",
            "snake_first_pick_mmr",
            "snake_last_pick_mmr",
            "normal_first_pick_mmr",
            "normal_last_pick_mmr",
        )


class GameSerializerForTournament(serializers.ModelSerializer):
    """Used inside TournamentSerializer which provides _users dict."""

    dire_team = TeamSerializerSlim(many=False, read_only=True)
    radiant_team = TeamSerializerSlim(many=False, read_only=True)
    winning_team = TeamSerializerSlim(many=False, read_only=True)
    herodraft_id = serializers.SerializerMethodField()

    def get_herodraft_id(self, obj):
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


class DraftRoundSerializer(serializers.ModelSerializer):
    draft = serializers.PrimaryKeyRelatedField(
        many=False,
        queryset=Draft.objects.all(),
        write_only=True,
        required=False,
    )
    captain = serializers.SerializerMethodField()
    captain_id = serializers.PrimaryKeyRelatedField(
        source="captain",
        many=False,
        queryset=CustomUser.objects.all(),
        write_only=True,
        required=False,
    )
    pick_phase = serializers.IntegerField()
    pick_number = serializers.IntegerField()
    team = TeamSerializerForTournament(many=False, read_only=True)

    choice = serializers.SerializerMethodField()
    choice_id = serializers.PrimaryKeyRelatedField(
        source="choice",
        many=False,
        queryset=CustomUser.objects.all(),
        write_only=True,
        required=False,
    )

    def get_captain(self, draft_round):
        return _serialize_user_with_mmr(
            draft_round.captain, draft_round.draft.tournament
        )

    def get_choice(self, draft_round):
        return _serialize_user_with_mmr(
            draft_round.choice, draft_round.draft.tournament
        )

    class Meta:
        model = DraftRound
        fields = (
            "pk",
            "draft",
            "captain",
            "captain_id",
            "pick_phase",
            "pick_number",
            "choice",
            "choice_id",
            "team",
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

    def get_members(self, team):
        return _serialize_users_with_mmr(team.members.all(), team.tournament)

    def get_dropin_members(self, team):
        return _serialize_users_with_mmr(team.dropin_members.all(), team.tournament)

    def get_captain(self, team):
        return _serialize_user_with_mmr(team.captain, team.tournament)

    def get_deputy_captain(self, team):
        return _serialize_user_with_mmr(team.deputy_captain, team.tournament)

    tournament_id = serializers.PrimaryKeyRelatedField(
        source="tournament",
        many=False,
        queryset=Tournament.objects.all(),
        write_only=True,
        read_only=False,
        required=False,
    )

    def get_total_mmr(self, obj):
        """Sum of captain MMR + all member MMRs (excluding captain from members to avoid double-counting)."""
        from org.models import OrgUser

        # Get organization from team's tournament's league
        tournament = obj.tournament
        org = None
        if tournament and tournament.league:
            org = tournament.league.organization

        # If no organization, can't determine MMR
        if not org:
            return 0

        # Use OrgUser MMR
        total = 0
        captain_pk = getattr(obj.captain, "pk", None)

        if obj.captain:
            try:
                org_user = OrgUser.objects.get(user=obj.captain, organization=org)
                total += org_user.mmr or 0
            except OrgUser.DoesNotExist:
                pass

        for member in obj.members.all():
            if member.pk != captain_pk:
                try:
                    org_user = OrgUser.objects.get(user=member, organization=org)
                    total += org_user.mmr or 0
                except OrgUser.DoesNotExist:
                    pass

        return total

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


class TournamentSerializer(serializers.ModelSerializer):
    teams = TeamSerializerSlim(many=True, read_only=True)
    users = serializers.SerializerMethodField()
    draft = DraftSerializerSlim(many=False, read_only=True)

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

    def get_organization_pk(self, tournament):
        """Return the primary organization's PK for this tournament."""
        if not tournament.league:
            return None
        org = tournament.league.organization
        return org.pk if org else None

    def get_league_pk(self, tournament):
        """Return the league's PK for this tournament."""
        return tournament.league.pk if tournament.league else None

    def get_users(self, tournament):
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
        )

    def update(self, instance, validated_data):
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
                            f"Removing {captain_teams.count()} captain team(s) from tournament {instance.name}"
                        )
                        captain_teams.delete()

                # Bulk create OrgUser and LeagueUser for added users
                if added_users and instance.league:
                    org = instance.league.organization
                    if org:
                        from league.models import LeagueUser
                        from org.models import OrgUser

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
                                    OrgUser(
                                        user=user,
                                        organization=org,
                                        mmr=0,
                                    )
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
                                            mmr=org_user.mmr,
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
    steam_account_id = serializers.IntegerField(required=False, allow_null=True)

    class Meta:
        model = CustomUser
        fields = (
            "pk",
            "username",
            "nickname",
            "is_staff",
            "is_active",
            "is_superuser",
            "avatar",
            "discordId",
            "steam_account_id",
            "avatarUrl",
            "email",
            "username",
            "date_joined",
            "teams",  # Include associated teams
            "positions",
            "default_organization",
        )

    def update(self, instance, validated_data):
        with transaction.atomic():
            try:
                positions_data = validated_data.pop("positions", None)
                if positions_data:
                    positions_instance = instance.positions
                    for key, value in positions_data.items():
                        setattr(positions_instance, key, value)
                    positions_instance.save()
                    log.debug(positions_data)
            except KeyError:
                pass
            for key, value in validated_data.items():
                setattr(instance, key, value)

            instance.save()
            log.debug("Updated User")

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

    def create(self, validated_data):
        fields = self.Meta.fields

        with transaction.atomic():

            for key in validated_data.keys():
                if key not in fields:
                    raise KeyError(f"Invalid field: {key}")

            if "positions" in validated_data:

                positions_data = validated_data.pop("positions")
                positions = PositionsModel.objects.create(**positions_data)
                user = CustomUser.objects.create(positions=positions, **validated_data)

            else:
                log.debug(validated_data)
                positions = PositionsModel.objects.create()
                user = CustomUser(positions=positions, **validated_data)

            user.save()
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

    def get_herodraft_id(self, obj):
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

    def get_herodraft_id(self, obj):
        if hasattr(obj, "herodraft"):
            return obj.herodraft.id
        return None

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


class DraftEventSerializer(serializers.ModelSerializer):
    actor = TournamentUserSerializer(read_only=True)

    class Meta:
        model = DraftEvent
        fields = (
            "pk",
            "event_type",
            "payload",
            "actor",
            "created_at",
        )


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


class HeroDraftRoundSerializerFull(serializers.ModelSerializer):
    """Full serializer for HeroDraftRound with all fields."""

    team_name = serializers.SerializerMethodField()

    class Meta:
        model = HeroDraftRound
        fields = [
            "id",
            "round_number",
            "action_type",
            "hero_id",
            "state",
            "grace_time_ms",
            "started_at",
            "completed_at",
            "draft_team",
            "team_name",
        ]

    def get_team_name(self, obj):
        """Get the team name from the draft team's tournament team."""
        if obj.draft_team and obj.draft_team.tournament_team:
            return obj.draft_team.tournament_team.name
        return None


class DraftTeamSerializerFull(serializers.ModelSerializer):
    """Full serializer for DraftTeam with captain and team members."""

    captain = TournamentUserSerializer(read_only=True)
    team_name = serializers.CharField(source="tournament_team.name", read_only=True)
    members = TournamentUserSerializer(
        source="tournament_team.members", many=True, read_only=True
    )

    class Meta:
        model = DraftTeam
        fields = [
            "id",
            "tournament_team",
            "captain",
            "team_name",
            "members",
            "is_first_pick",
            "is_radiant",
            "reserve_time_remaining",
            "is_ready",
            "is_connected",
        ]


class HeroDraftEventSerializer(serializers.ModelSerializer):
    """Serializer for HeroDraft events with full captain info for toasts."""

    draft_team = DraftTeamSerializerFull(read_only=True)

    class Meta:
        model = HeroDraftEvent
        fields = ["id", "event_type", "draft_team", "metadata", "created_at"]


class HeroDraftSerializer(serializers.ModelSerializer):
    """Full serializer for HeroDraft with nested relations."""

    pk = serializers.IntegerField(source="id", read_only=True)
    draft_teams = DraftTeamSerializerFull(many=True, read_only=True)
    rounds = HeroDraftRoundSerializerFull(many=True, read_only=True)
    roll_winner = DraftTeamSerializerFull(read_only=True)
    current_round = serializers.SerializerMethodField()
    tournament_id = serializers.SerializerMethodField()

    class Meta:
        model = HeroDraft
        fields = [
            "pk",
            "id",
            "game",
            "tournament_id",
            "state",
            "roll_winner",
            "draft_teams",
            "rounds",
            "current_round",
            "is_manual_pause",
            "created_at",
            "updated_at",
        ]

    def get_current_round(self, obj):
        active_round = obj.rounds.filter(state="active").first()
        if active_round:
            # Return index (0-based) into rounds array for frontend compatibility
            return active_round.round_number - 1
        return None

    def get_tournament_id(self, obj):
        if obj.game and obj.game.tournament:
            return obj.game.tournament.id
        return None


class HeroDraftTickSerializer(serializers.Serializer):
    """Serializer for WebSocket tick updates."""

    current_round = serializers.IntegerField()
    active_team_id = serializers.IntegerField()
    grace_time_remaining_ms = serializers.IntegerField()
    team_a_reserve_ms = serializers.IntegerField()
    team_b_reserve_ms = serializers.IntegerField()
    draft_state = serializers.CharField()
