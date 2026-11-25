from collections.abc import Collection
from typing import Any, ClassVar

from rest_framework import serializers
from rest_framework.utils.serializer_helpers import ReturnList

from app.models import CustomUser
from events.overrides import (
    REASON_MAX_LENGTH,
    OverrideReasonRequired,
    OverrideRequestSerializer,
)
from org.mmr import game_for_tournament, org_mmr_map
from tournament.models import Team, TeamLog, Tournament
from tournament.serializers.users import (
    TEAM_MMR_MAPS,
    TEAM_USER_INDEX,
    TeamUserIndex,
    _serialize_users_with_mmr,
    serialize_user_with_mmr,
)
from tournament.services.team_references import team_references
from user.serializers import TournamentUserSerializer, UserPkField


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

    # Members last: emptying them may delete the team (see tournament.signals).
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


class TeamReplaceCaptainRequestSerializer(TeamActionRequestSerializer):
    user_id = serializers.PrimaryKeyRelatedField(queryset=CustomUser.objects.all())
    mark_outgoing_dropout = serializers.BooleanField(required=False, default=True)


class TeamRenameRequestSerializer(TeamActionRequestSerializer):
    # Blank/length/unchanged checks belong to the service so codes have one source.
    name = serializers.CharField(allow_blank=True, trim_whitespace=False)
