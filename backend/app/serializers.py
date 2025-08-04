from ast import alias
from typing import TypeAlias

from django.contrib.auth.models import User
from django.db import transaction
from rest_framework import serializers

from .models import CustomUser, Draft, DraftRound, Game, Team, Tournament


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
        )


class DraftRoundForDraftSerializer(serializers.ModelSerializer):

    captain = TournamentUserSerializer(many=False, read_only=True)
    pick_phase = serializers.IntegerField()
    pick_number = serializers.IntegerField()

    choice = TournamentUserSerializer(many=False, read_only=True)

    class Meta:
        model = DraftRound
        fields = (
            "captain",
            "pick_phase",
            "pick_number",
            "choice",
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
            "users_remaining",
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
            "captain",
            "captain_id",
            "pick_phase",
            "pick_number",
            "choice",
            "choice_id",
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
    teams = TeamSerializerForTournament(
        many=True, read_only=True
    )  # Return full team objects
    users = TournamentUserSerializer(many=True, read_only=True)
    draft = serializers.SerializerMethodField()

    user_ids = serializers.PrimaryKeyRelatedField(
        source="users",
        many=True,
        queryset=CustomUser.objects.all(),
        write_only=True,
        required=False,
    )
    tournament_type = serializers.CharField(read_only=False)
    captains = TournamentUserSerializer(many=True, read_only=True)

    def get_draft(self, obj):
        """
        Get the draft for this tournament if it exists
        """
        try:
            # Check if draft exists and get the first (and hopefully only) one
            if hasattr(obj, "draft") and obj.draft.exists():
                draft = obj.draft.first()
                return DraftSerializerForTournament(draft).data
            return None
        except Exception as e:
            # If there's no draft or any error, return None
            return None

    class Meta:
        model = Tournament
        fields = (
            "pk",
            "name",
            "date_played",
            "draft",
            "users",
            "teams",  # Include full team objects
            "winning_team",
            "state",
            "user_ids",  # Allow setting user IDs for the tournament
            "captains",
            "tournament_type",
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
