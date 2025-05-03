from django.contrib.auth.models import User
from rest_framework import serializers

from .models import CustomUser, DiscordInfo, DotaInfo


class DotaSerializer(serializers.ModelSerializer):
    class Meta:
        model = DotaInfo
        fields = ("mmr", "steamid", "position")


class UserSerializer(serializers.ModelSerializer):
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
        )

    def create(self, validated_data):
        fields = self.Meta.fields
        for key in validated_data.keys():
            if key not in fields:
                raise KeyError(f"Invalid field: {key}")

        user = CustomUser(**validated_data)  # create user with all the other fields
        user.save()
        return user


from .models import Game, Team, Tournament


class TeamSerializer(serializers.ModelSerializer):
    class Meta:
        model = Team
        fields = (
            "pk",
            "name",
            "captain",
            "members",
            "dropin_members",
            "current_points",
        )


class TournamentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tournament
        fields = (
            "pk",
            "name",
            "date_played",
            "users",
            "teams",
            "winning_team",
            "state",
        )


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
