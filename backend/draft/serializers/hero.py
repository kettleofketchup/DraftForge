from typing import Any

from rest_framework import serializers

from app.models import CustomUser
from app.serializers import TournamentUserSerializer, tournament_organization
from draft.models import DraftTeam, HeroDraft, HeroDraftEvent, HeroDraftRound
from org.models import OrgUser


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

    def get_team_name(self, obj: HeroDraftRound) -> str | None:
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


HERODRAFT_GUILD_NICKNAMES = "herodraft_guild_nicknames"


class HeroDraftUserSerializer(TournamentUserSerializer):
    """Captain/member with the draft tournament org's server nickname."""

    guildNickname = serializers.SerializerMethodField()

    class Meta(TournamentUserSerializer.Meta):
        fields = (*TournamentUserSerializer.Meta.fields, "guildNickname")

    def get_guildNickname(self, user: CustomUser) -> str | None:
        return self.context.get(HERODRAFT_GUILD_NICKNAMES, {}).get(user.pk)


class HeroDraftTeamSerializer(DraftTeamSerializerFull):
    captain = HeroDraftUserSerializer(read_only=True)
    members = HeroDraftUserSerializer(
        source="tournament_team.members", many=True, read_only=True
    )

    class Meta(DraftTeamSerializerFull.Meta):
        pass


class HeroDraftEventSerializer(serializers.ModelSerializer):
    """Serializer for HeroDraft events with full captain info for toasts."""

    draft_team = DraftTeamSerializerFull(read_only=True)

    class Meta:
        model = HeroDraftEvent
        fields = ["id", "event_type", "draft_team", "metadata", "created_at"]


class HeroDraftSerializer(serializers.ModelSerializer):
    """Full serializer for HeroDraft with nested relations."""

    pk = serializers.IntegerField(source="id", read_only=True)
    draft_teams = HeroDraftTeamSerializer(many=True, read_only=True)
    rounds = HeroDraftRoundSerializerFull(many=True, read_only=True)
    roll_winner = serializers.SerializerMethodField()
    current_round = serializers.SerializerMethodField()
    tournament_id = serializers.SerializerMethodField()
    organization_pk = serializers.SerializerMethodField()
    league_pk = serializers.SerializerMethodField()

    class Meta:
        model = HeroDraft
        fields = [
            "pk",
            "id",
            "game",
            "tournament_id",
            "organization_pk",
            "league_pk",
            "state",
            "roll_winner",
            "draft_teams",
            "rounds",
            "current_round",
            "is_manual_pause",
            "timer_enabled",
            "created_at",
            "updated_at",
        ]

    def get_current_round(self, obj: HeroDraft) -> int | None:
        active_round = obj.rounds.filter(state="active").first()
        if active_round:
            # Return index (0-based) into rounds array for frontend compatibility
            return active_round.round_number - 1
        return None

    def get_tournament_id(self, obj: HeroDraft) -> int | None:
        if obj.game and obj.game.tournament:
            return obj.game.tournament.id
        return None

    def to_representation(self, instance: HeroDraft) -> dict[str, Any]:
        org = tournament_organization(
            instance.game.tournament if instance.game else None
        )
        nicknames: dict[int, str | None] = {}
        if org is not None:
            user_ids: set[int] = set()
            for draft_team in instance.draft_teams.all():
                team = draft_team.tournament_team
                if team.captain_id:
                    user_ids.add(team.captain_id)
                user_ids.update(member.pk for member in team.members.all())
            nicknames = dict(
                OrgUser.objects.nocache()
                .filter(organization=org, user_id__in=user_ids)
                .values_list("user_id", "guild_nickname")
            )
        self._organization_pk = org.pk if org else None
        self.context[HERODRAFT_GUILD_NICKNAMES] = nicknames
        return super().to_representation(instance)

    def get_organization_pk(self, obj: HeroDraft) -> int | None:
        return self._organization_pk

    def get_league_pk(self, obj: HeroDraft) -> int | None:
        if obj.game and obj.game.tournament:
            return obj.game.tournament.league_id
        return None

    def get_roll_winner(self, obj: HeroDraft) -> dict[str, Any] | None:
        if obj.roll_winner_id is None:
            return None
        winner = next(
            (t for t in obj.draft_teams.all() if t.pk == obj.roll_winner_id),
            obj.roll_winner,
        )
        return HeroDraftTeamSerializer(winner, context=self.context).data
