from rest_framework import serializers

from app.serializers import PositionsSerializer

from .models import OrgUser


class OrgUserSerializer(serializers.ModelSerializer):
    """
    Serializer for OrgUser that returns user data with org-scoped MMR.

    Context:
        league_id: Optional league ID to include league_mmr from LeagueUser
    """

    id = serializers.IntegerField(read_only=True)  # OrgUser's pk (for PATCH)
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
    mmr = serializers.IntegerField(read_only=True)  # From OrgUser.mmr
    league_mmr = serializers.SerializerMethodField()

    def get_league_mmr(self, org_user):
        """Get MMR from LeagueUser if league_id is in context."""
        league_id = self.context.get("league_id")
        if not league_id:
            return None

        from league.models import LeagueUser

        try:
            league_user = LeagueUser.objects.get(org_user=org_user, league_id=league_id)
            return league_user.mmr
        except LeagueUser.DoesNotExist:
            return None

    class Meta:
        model = OrgUser
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
            "league_mmr",
        )
