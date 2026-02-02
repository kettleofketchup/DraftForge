from rest_framework import serializers

from app.models import ProfileClaimRequest
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
        """Get MMR from LeagueUser if league_id is in context.

        Uses prefetched league_users if available to avoid N+1 queries.
        Prefetch with: OrgUser.objects.prefetch_related(
            Prefetch('league_users', queryset=LeagueUser.objects.filter(league_id=X))
        )
        """
        league_id = self.context.get("league_id")
        if not league_id:
            return None

        # Try to use prefetched data first (avoids N+1)
        if (
            hasattr(org_user, "_prefetched_objects_cache")
            and "league_users" in org_user._prefetched_objects_cache
        ):
            league_users = org_user._prefetched_objects_cache["league_users"]
            for lu in league_users:
                if lu.league_id == league_id:
                    return lu.mmr
            return None

        # Fallback to query (will cause N+1 if not prefetched)
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


class ProfileClaimRequestSerializer(serializers.ModelSerializer):
    """Serializer for profile claim requests."""

    claimer_username = serializers.CharField(source="claimer.username", read_only=True)
    claimer_discord_id = serializers.CharField(
        source="claimer.discordId", read_only=True
    )
    claimer_avatar = serializers.CharField(source="claimer.avatarUrl", read_only=True)

    target_nickname = serializers.CharField(
        source="target_user.nickname", read_only=True
    )
    target_steamid = serializers.IntegerField(
        source="target_user.steamid", read_only=True
    )
    target_mmr = serializers.IntegerField(source="target_user.mmr", read_only=True)

    organization_name = serializers.CharField(
        source="organization.name", read_only=True
    )

    reviewed_by_username = serializers.CharField(
        source="reviewed_by.username", read_only=True, allow_null=True
    )

    class Meta:
        model = ProfileClaimRequest
        fields = (
            "id",
            "claimer",
            "claimer_username",
            "claimer_discord_id",
            "claimer_avatar",
            "target_user",
            "target_nickname",
            "target_steamid",
            "target_mmr",
            "organization",
            "organization_name",
            "status",
            "reviewed_by",
            "reviewed_by_username",
            "rejection_reason",
            "created_at",
            "reviewed_at",
        )
        read_only_fields = (
            "id",
            "claimer",
            "target_user",
            "organization",
            "status",
            "reviewed_by",
            "rejection_reason",
            "created_at",
            "reviewed_at",
        )
