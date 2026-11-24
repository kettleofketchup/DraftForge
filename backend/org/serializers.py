from functools import cache
from typing import Any
from zoneinfo import available_timezones

import nh3
from rest_framework import serializers

from app.models import ProfileClaimRequest
from common.game import GameType
from league.models import LeagueUser
from org import settings_constants
from org.mmr import get_org_mmrs, resolve_game_type
from org.models import Organization, OrgSettings, OrgUser, OrgUserGameMmr
from org.settings_constants import StaffOverridePolicy
from org.settings_service import normalize_warning_codes
from user.serializers import PositionsSerializer, TournamentUserSerializer


@cache
def _known_timezones() -> frozenset[str]:
    return frozenset(available_timezones())


class OrganizationsSerializer(serializers.ModelSerializer):
    """Lightweight serializer for organization list view."""

    league_count = serializers.IntegerField(read_only=True)
    users_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Organization
        fields = ("pk", "name", "logo", "league_count", "users_count", "created_at")
        read_only_fields = ("pk", "league_count", "users_count", "created_at")


class OrganizationSerializer(serializers.ModelSerializer):
    # Roles change only through the admin_team endpoints.
    owner = TournamentUserSerializer(read_only=True)
    admins = TournamentUserSerializer(many=True, read_only=True)
    staff = TournamentUserSerializer(many=True, read_only=True)
    # Use annotated fields from ViewSet queryset (avoids N+1)
    league_count = serializers.IntegerField(read_only=True)
    tournament_count = serializers.IntegerField(read_only=True)
    users_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Organization
        fields = (
            "pk",
            "name",
            "description",
            "logo",
            "discord_link",
            "discord_server_id",
            "rules_template",
            "timezone",
            "members_private",
            "owner",
            "admins",
            "staff",
            "default_league",
            "league_count",
            "tournament_count",
            "users_count",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "pk",
            "created_at",
            "updated_at",
            "league_count",
            "tournament_count",
            "users_count",
        )

    def validate_description(self, value: str | None) -> str | None:
        """Sanitize markdown to prevent XSS."""
        if value:
            return nh3.clean(value)
        return value

    def validate_rules_template(self, value: str | None) -> str | None:
        """Sanitize markdown to prevent XSS."""
        if value:
            return nh3.clean(value)
        return value

    def validate_timezone(self, value: str) -> str:
        if self.instance is not None and value == getattr(
            self.instance, "timezone", None
        ):
            return value
        if value not in _known_timezones():
            raise serializers.ValidationError(f"Unknown timezone {value!r}.")
        return value


class OrgUserSerializer(serializers.ModelSerializer):
    """
    Serializer for OrgUser that returns user data with org-scoped MMR.

    Context:
        league_id: Optional league ID to include league_mmr from LeagueUser
        game_type: GameType `mmr` is resolved for (default Dota 2)
        include_game_mmrs: emit `game_mmrs`; only gated endpoints set it

    Instances must carry the `game_mmrs` prefetch (org.mmr.game_mmrs_prefetch).
    """

    orgUserPk = serializers.IntegerField(
        source="id", read_only=True
    )  # OrgUser's pk (for PATCH)
    pk = serializers.IntegerField(source="user.pk", read_only=True)  # User's pk
    username = serializers.CharField(source="user.username", read_only=True)
    nickname = serializers.CharField(source="user.nickname", read_only=True)
    guildNickname = serializers.CharField(
        source="guild_nickname", read_only=True, allow_null=True
    )
    discordNickname = serializers.CharField(
        source="user.discordNickname", read_only=True, allow_null=True
    )
    avatar = serializers.CharField(source="user.avatar", read_only=True)
    discordId = serializers.CharField(source="user.discordId", read_only=True)
    positions = PositionsSerializer(source="user.positions", read_only=True)
    steam_account_id = serializers.IntegerField(
        source="user.steam_account_id", read_only=True
    )
    avatarUrl = serializers.CharField(source="user.avatarUrl", read_only=True)
    mmr = serializers.SerializerMethodField()
    mmr_game_type = serializers.SerializerMethodField()
    game_mmrs = serializers.SerializerMethodField()
    league_mmr = serializers.SerializerMethodField()

    def get_fields(self) -> dict[str, serializers.Field]:
        fields = super().get_fields()
        if not self.context.get("include_game_mmrs"):
            fields.pop("game_mmrs")
        return fields

    def _game_type(self) -> int:
        return int(resolve_game_type(self.context.get("game_type")))

    def get_mmr(self, org_user: OrgUser) -> int:
        return get_org_mmrs(org_user)[self._game_type()]

    def get_mmr_game_type(self, org_user: OrgUser) -> int:
        return self._game_type()

    def get_game_mmrs(self, org_user: OrgUser) -> dict[str, int]:
        return {str(game): mmr for game, mmr in get_org_mmrs(org_user).items()}

    def get_league_mmr(self, org_user: OrgUser) -> int | None:
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
            and "league_memberships" in org_user._prefetched_objects_cache
        ):
            league_users = org_user._prefetched_objects_cache["league_memberships"]
            for lu in league_users:
                if lu.league_id == league_id:
                    return lu.mmr
            return None

        # Fallback to query (will cause N+1 if not prefetched)
        try:
            league_user = LeagueUser.objects.get(org_user=org_user, league_id=league_id)
            return league_user.mmr
        except LeagueUser.DoesNotExist:
            return None

    class Meta:
        model = OrgUser
        fields = (
            "orgUserPk",
            "pk",
            "username",
            "nickname",
            "guildNickname",
            "discordNickname",
            "avatar",
            "discordId",
            "positions",
            "steam_account_id",
            "avatarUrl",
            "mmr",
            "mmr_game_type",
            "game_mmrs",
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
        source="target_user.nickname", read_only=True, allow_null=True
    )
    target_username = serializers.CharField(
        source="target_user.username", read_only=True, allow_null=True
    )
    target_discordNickname = serializers.CharField(
        source="target_user.discordNickname", read_only=True, allow_null=True
    )
    target_steamid = serializers.IntegerField(
        source="target_user.steamid", read_only=True, allow_null=True
    )
    target_mmr = serializers.SerializerMethodField()
    target_game_mmrs = serializers.SerializerMethodField()

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
            "target_username",
            "target_discordNickname",
            "target_steamid",
            "target_mmr",
            "target_game_mmrs",
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

    def _target_mmrs(self, obj: ProfileClaimRequest) -> dict[int, int]:
        memo: dict[int, dict[int, int]] = self.__dict__.setdefault(
            "_target_mmrs_memo", {}
        )
        if obj.pk not in memo:
            mmrs = {game: 0 for game in GameType.values}
            mmrs.update(
                OrgUserGameMmr.objects.filter(
                    org_user__user_id=obj.target_user_id,
                    org_user__organization_id=obj.organization_id,
                ).values_list("game_type", "mmr")
            )
            memo[obj.pk] = mmrs
        return memo[obj.pk]

    def get_target_mmr(self, obj: ProfileClaimRequest) -> int | None:
        if obj.target_user_id is None:
            return None
        return self._target_mmrs(obj)[GameType.DOTA2]

    def get_target_game_mmrs(self, obj: ProfileClaimRequest) -> dict[str, int] | None:
        if obj.target_user_id is None:
            return None
        return {str(game): mmr for game, mmr in self._target_mmrs(obj).items()}


class OrgSettingsSerializer(serializers.ModelSerializer):
    staff_override_policy = serializers.ChoiceField(choices=StaffOverridePolicy.choices)
    staff_override_warning_codes = serializers.ListField(
        child=serializers.CharField(), allow_empty=True
    )
    available_warning_codes = serializers.SerializerMethodField()

    class Meta:
        model = OrgSettings
        fields = [
            "organization",
            "staff_override_policy",
            "staff_override_warning_codes",
            "available_warning_codes",
            "updated_at",
        ]
        read_only_fields = ["organization", "available_warning_codes", "updated_at"]

    def to_representation(self, instance: OrgSettings) -> dict[str, Any]:
        data = super().to_representation(instance)
        all_codes = settings_constants.ALL_CODES
        data["staff_override_warning_codes"] = [
            code for code in data["staff_override_warning_codes"] if code in all_codes
        ]
        return data

    def validate_staff_override_warning_codes(self, value: list[str]) -> list[str]:
        try:
            return normalize_warning_codes(value)
        except ValueError as exc:
            raise serializers.ValidationError(str(exc)) from exc

    def get_available_warning_codes(self, obj: OrgSettings) -> list[dict[str, str]]:
        labels = settings_constants.WARNING_CODE_LABELS
        return [
            {"code": code, "label": labels.get(code, code)}
            for code in settings_constants.ALL_CODES
        ]
