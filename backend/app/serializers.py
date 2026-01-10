from ast import alias
from logging import getLogger
from typing import TypeAlias

from django.contrib.auth.models import User
from django.db import transaction
from rest_framework import serializers

log = getLogger(__name__)
from .models import (
    CustomUser,
    Draft,
    DraftRound,
    Game,
    PositionsModel,
    Team,
    Tournament,
)


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

    class Meta:
        model = CustomUser
        fields = (
            "pk",
            "username",
            "nickname",
            "avatar",
            "discordId",
            "positions",
            "steamid",
            "avatarUrl",
            "mmr",
            "positions",
        )


class TournamentSerializerBase(serializers.ModelSerializer):
    users = TournamentUserSerializer(many=True, read_only=True)
    captains = TournamentUserSerializer(many=True, read_only=True)
    tournament_type = serializers.CharField(read_only=False)

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
    members = TournamentUserSerializer(many=True, read_only=True)
    dropin_members = TournamentUserSerializer(many=True, read_only=True)
    left_members = TournamentUserSerializer(many=True, read_only=True)
    captain = TournamentUserSerializer(many=False, read_only=True)
    draft_order = serializers.IntegerField()

    class Meta:
        model = Team
        fields = (
            "pk",
            "name",
            "members",
            "dropin_members",
            "left_members",
            "captain",
            "draft_order",
            "placement",
        )


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
            "tournament_type",
            "state",
            "captains",
            "winner",
        )


class DraftRoundForDraftSerializer(serializers.ModelSerializer):

    captain = TournamentUserSerializer(many=False, read_only=True)
    pick_phase = serializers.IntegerField()
    pick_number = serializers.IntegerField()

    choice = TournamentUserSerializer(many=False, read_only=True)
    team = TeamSerializerForTournament(many=False, read_only=True)

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


class DraftSerializerForTournament(serializers.ModelSerializer):

    draft_rounds = DraftRoundForDraftSerializer(
        many=True,
        read_only=True,
    )
    users_remaining = TournamentUserSerializer(many=True, read_only=True)

    class Meta:
        model = Draft
        fields = (
            "pk",
            "draft_rounds",
            "users_remaining",
            "latest_round",
            "draft_style",
        )


class TournamentSerializerDraft(serializers.ModelSerializer):
    teams = TeamSerializerForTournament(
        many=True, read_only=True
    )  # Return full team objects
    users = TournamentUserSerializer(many=True, read_only=True)

    tournament_type = serializers.CharField(read_only=False)
    captains = TournamentUserSerializer(many=True, read_only=True)

    class Meta:
        model = Tournament
        fields = (
            "pk",
            "name",
            "date_played",
            "users",
            "teams",  # Include full team objects
            "captains",
            "tournament_type",
        )


class DraftSerializer(serializers.ModelSerializer):

    tournament = TournamentSerializerDraft(
        many=False,
        read_only=True,
    )
    users_remaining = TournamentUserSerializer(many=True, read_only=True)

    draft_rounds = DraftRoundForDraftSerializer(
        many=True,
        read_only=True,
    )

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

    dire_team = TeamSerializerForTournament(many=False, read_only=True)
    radiant_team = TeamSerializerForTournament(many=False, read_only=True)
    winning_team = TeamSerializerForTournament(many=False, read_only=True)

    class Meta:
        model = Game

        fields = (
            "pk",
            "radiant_team",
            "dire_team",
            "gameid",
            "round",
            "winning_team",
        )


class DraftRoundSerializer(serializers.ModelSerializer):
    draft = serializers.PrimaryKeyRelatedField(
        many=False,
        queryset=Draft.objects.all(),
        write_only=True,
        required=False,
    )
    captain = TournamentUserSerializer(many=False, read_only=True)
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

    choice = TournamentUserSerializer(many=False, read_only=True)
    choice_id = serializers.PrimaryKeyRelatedField(
        source="choice",
        many=False,
        queryset=CustomUser.objects.all(),
        write_only=True,
        required=False,
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
    members = TournamentUserSerializer(many=True, read_only=True)
    dropin_members = TournamentUserSerializer(many=True, read_only=True)
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
    captain = TournamentUserSerializer(many=False, read_only=True)

    captain_id = serializers.PrimaryKeyRelatedField(
        source="captain",
        many=False,
        queryset=CustomUser.objects.all(),
        write_only=True,
        required=False,
    )
    total_mmr = serializers.SerializerMethodField()

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
        total = 0
        if obj.captain and obj.captain.mmr:
            total += obj.captain.mmr
        for member in obj.members.all():
            if member.mmr and member.pk != getattr(obj.captain, "pk", None):
                total += member.mmr
        return total

    class Meta:
        model = Team
        fields = (
            "pk",
            "name",
            "left_members",
            "left_member_ids",
            "captain",
            "captain_id",  # Allow setting captain by ID
            "member_ids",  # Allow setting member IDs
            "dropin_member_ids",  # Allow setting drop-in member IDs
            "tournament_id",  # Allow setting tournament by ID
            "members",
            "dropin_members",
            "draft_order",
            "current_points",
            "tournament",
            "total_mmr",
            "placement",
        )


class TournamentSerializer(serializers.ModelSerializer):
    teams = TeamSerializerForTournament(
        many=True, read_only=True
    )  # Return full team objects
    users = TournamentUserSerializer(many=True, read_only=True)
    draft = DraftSerializerForTournament(many=False, read_only=True)

    user_ids = serializers.PrimaryKeyRelatedField(
        source="users",
        many=True,
        queryset=CustomUser.objects.all(),
        write_only=True,
        required=False,
    )
    tournament_type = serializers.CharField(read_only=False)
    captains = TournamentUserSerializer(many=True, read_only=True)
    games = GameSerializerForTournament(many=True, read_only=True)

    class Meta:
        model = Tournament
        fields = (
            "pk",
            "name",
            "draft",
            "date_played",
            "users",
            "teams",  # Include full team objects
            "winning_team",
            "state",
            "games",
            "user_ids",  # Allow setting user IDs for the tournament
            "captains",
            "tournament_type",
        )


class UserSerializer(serializers.ModelSerializer):
    teams = TeamSerializer(many=True, read_only=True)  # Associated teams
    positions = PositionsSerializer(many=False, read_only=False, required=False)

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
            "steamid",
            "mmr",
            "avatarUrl",
            "email",
            "username",
            "date_joined",
            "teams",  # Include associated teams
            "positions",
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
        )


class BracketGameSerializer(serializers.ModelSerializer):
    """Serializer for bracket view with full team details."""

    radiant_team = TeamSerializerForTournament(read_only=True)
    dire_team = TeamSerializerForTournament(read_only=True)
    winning_team = TeamSerializerForTournament(read_only=True)

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
