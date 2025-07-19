from django.contrib.auth.models import User
from rest_framework import serializers

from .models import CustomUser, DiscordInfo, DotaInfo, Game, Team, Tournament


class DotaSerializer(serializers.ModelSerializer):
    class Meta:
        model = DotaInfo
        fields = ("mmr", "steamid", "positions")


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


class TeamSerializer(serializers.ModelSerializer):
    tournament = TeamTournamentSerializer(
        many=False,
        read_only=True,
    )
    members = TournamentUserSerializer(many=True, read_only=True)
    dropin_members = TournamentUserSerializer(many=True, read_only=True)

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
            "current_points",
            "tournament",  # Include tournament PKs
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
