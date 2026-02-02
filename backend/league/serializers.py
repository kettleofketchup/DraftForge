from rest_framework import serializers

from app.serializers import PositionsSerializer

from .models import LeagueUser


class LeagueUserSerializer(serializers.ModelSerializer):
    """
    Serializer for LeagueUser that returns user data with league-specific MMR.
    """

    id = serializers.IntegerField(read_only=True)  # LeagueUser's pk
    pk = serializers.IntegerField(source="user.pk", read_only=True)  # User's pk
    username = serializers.CharField(source="user.username", read_only=True)
    nickname = serializers.CharField(source="user.nickname", read_only=True)
    avatar = serializers.CharField(source="user.avatar", read_only=True)
    discordId = serializers.CharField(source="user.discordId", read_only=True)
    positions = PositionsSerializer(source="user.positions", read_only=True)
    steamid = serializers.IntegerField(source="user.steamid", read_only=True)
    steam_account_id = serializers.IntegerField(
        source="user.steam_account_id", read_only=True
    )
    avatarUrl = serializers.CharField(source="user.avatarUrl", read_only=True)
    mmr = serializers.IntegerField(read_only=True)  # LeagueUser's snapshot MMR

    class Meta:
        model = LeagueUser
        fields = (
            "id",
            "pk",
            "username",
            "nickname",
            "avatar",
            "discordId",
            "positions",
            "steamid",
            "steam_account_id",
            "avatarUrl",
            "mmr",
        )
