from django.contrib.auth.models import User
from django.db import transaction
from rest_framework import serializers

from .models import (
    CustomUser,
    Game,
    Team,
    Tournament,
    Draft,
    DraftRound,
)


class DraftTournamentSerializer(serializers.ModelSerializer):

    class Meta:
        model = Tournament
        fields = (
            "pk",
            "name",
            "date_played",
            "teams",
            "users",
            "captains" "winning_team",
        )


class TeamTournamentSerializer(serializers.ModelSerializer):

    class Meta:
        model = Tournament
        fields = (
            "pk",
            "name",
            "date_played",
            "winning_team",
        )


class TournamentUserSerializer(serializers.ModelSerializer):

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
            "steamid",
        )


class DraftRoundForDraftSerializer(serializers.ModelSerializer):
    captain = TournamentUserSerializer(many=False, read_only=True)
    pick_phase = serializers.IntegerField(source="pick_phase")
    pick_number = serializers.IntegerField(source="pick_number")
    users_remaining = TournamentUserSerializer(many=True, read_only=True)
    choice = TournamentUserSerializer(many=False, read_only=True)

    class Meta:
        model = DraftRound
        fields = (
            "captain",
            "pick_phase",
            "pick_number",
            "choice",
            "users_remaining",
        )


class DraftSerializer(serializers.ModelSerializer):

    tournament = TeamTournamentSerializer(
        many=False,
        read_only=True,
    )

    tournament_id = serializers.PrimaryKeyRelatedField(
        source="tournament",
        many=False,
        queryset=Tournament.objects.all(),
        write_only=True,
    )
    draft_rounds = DraftRoundForDraftSerializer(
        many=True,
        read_only=True,
    )
    draft_round_ids = serializers.PrimaryKeyRelatedField(
        source="draft_rounds",
        many=True,
        queryset=DraftRound.objects.all(),
        write_only=True,
        required=False,
    )

    members = TournamentUserSerializer(many=True, read_only=True)
    dropin_members = TournamentUserSerializer(many=True, read_only=True)

    user_ids = serializers.PrimaryKeyRelatedField(
        source="users",
        many=True,
        queryset=CustomUser.objects.all(),
        write_only=True,
        required=False,
    )

    class Meta:
        model = Draft
        fields = (
            "pk",
            "team1",
            "team2",
            "winning_team",
        )


class DraftRoundSerializer(serializers.ModelSerializer):
    draft = DraftSerializer(many=False, read_only=True)
    draft_id = serializers.PrimaryKeyRelatedField(
        source="draft",
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
    pick_phase = serializers.IntegerField(source="pick_phase")
    pick_number = serializers.IntegerField(source="pick_number")
    users_remaining = TournamentUserSerializer(many=True, read_only=True)
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
            "draft",
            "draft_id",
            "captain",
            "captain_id",
            "pick_phase",
            "pick_number",
            "choice",
            "choice_id",
            "users_remaining",
        )


class TeamSerializer(serializers.ModelSerializer):
    tournament = TeamTournamentSerializer(
        many=False,
        read_only=True,
    )
    members = TournamentUserSerializer(many=True, read_only=True)
    dropin_members = TournamentUserSerializer(many=True, read_only=True)
    draft_order = serializers.IntegerField(
        source="draft_order",
        default=0,
        help_text="Order in which a team picks their players in the draft",
    )
    current_points = serializers.IntegerField(
        source="current_points", read_only=False, write_only=False, default=0
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
    tournament_id = serializers.PrimaryKeyRelatedField(
        source="tournament",
        many=False,
        queryset=Tournament.objects.all(),
        write_only=True,
        read_only=False,
        required=False,
    )

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
        )


class TournamentSerializer(serializers.ModelSerializer):
    teams = TeamSerializer(many=True, read_only=True)  # Return full team objects
    users = TournamentUserSerializer(many=True, read_only=True)

    user_ids = serializers.PrimaryKeyRelatedField(
        source="users",
        many=True,
        queryset=CustomUser.objects.all(),
        write_only=True,
        required=False,
    )
    captains = TournamentUserSerializer(many=True, read_only=True)

    class Meta:
        model = Tournament
        fields = (
            "pk",
            "name",
            "date_played",
            "users",
            "teams",  # Include full team objects
            "winning_team",
            "state",
            "user_ids",  # Allow setting user IDs for the tournament
            "captains",
        )


class UserSerializer(serializers.ModelSerializer):
    teams = TeamSerializer(many=True, read_only=True)  # Associated teams

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
            "positions",
            "discordId",
            "steamid",
            "mmr",
            "avatarUrl",
            "email",
            "username",
            "date_joined",
            "teams",  # Include associated teams
        )

    def create(self, validated_data):
        fields = self.Meta.fields
        for key in validated_data.keys():
            if key not in fields:
                raise KeyError(f"Invalid field: {key}")

        user = CustomUser(**validated_data)  # Create user with all the other fields
        user.save()
        return user


class GameSerializer(serializers.ModelSerializer):
    class Meta:
        model = Game
        fields = (
            "pk",
            "tournament",
            "team1",
            "team2",
            "winning_team",
        )
