from django.contrib.auth.models import User
from rest_framework import serializers

from .models import CustomUser, DiscordInfo, DotaInfo, Game, Team, Tournament


class DotaSerializer(serializers.ModelSerializer):
    class Meta:
        model = DotaInfo
        fields = ("mmr", "steamid", "position")


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
            "position",
            "steamid",
            "avatarUrl",
            "username",
        )


class TeamSerializer(serializers.ModelSerializer):
    tournament = TeamTournamentSerializer(
        many=False,
        read_only=False,
    )

    class Meta:
        model = Team
        fields = (
            "pk",
            "name",
            "captain",
            "members",
            "dropin_members",
            "current_points",
            "tournament",  # Include tournament PKs
        )


class TournamentSerializer(serializers.ModelSerializer):
    teams = TeamSerializer(many=True, read_only=True)  # Return full team objects
    users = TournamentUserSerializer(
        many=True, read_only=True
    )  # Return full user objects

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
            "position",
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
