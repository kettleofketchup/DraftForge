from typing import Any

import nh3
from rest_framework import serializers

from league.models import League
from org.mmr import get_org_mmrs
from org.models import Organization
from org.serializers import OrganizationsSerializer
from user.serializers import PositionsSerializer, TournamentUserSerializer

from .models import LeagueUser


class LeagueMinimalSerializer(serializers.ModelSerializer):
    """Minimal league info for tournament list cards."""

    organization_name = serializers.SerializerMethodField()
    organization_id = serializers.SerializerMethodField()
    organization_logo = serializers.SerializerMethodField()

    class Meta:
        model = League
        fields = (
            "pk",
            "name",
            "organization_name",
            "organization_id",
            "organization_logo",
        )

    def get_organization_name(self, obj: League) -> str | None:
        org = obj.organization
        return org.name if org else None

    def get_organization_id(self, obj: League) -> int | None:
        return obj.organization_id

    def get_organization_logo(self, obj: League) -> str | None:
        org = obj.organization
        return (org.logo or None) if org else None


class LeaguesSerializer(serializers.ModelSerializer):
    """Lightweight serializer for league list view."""

    tournament_count = serializers.IntegerField(read_only=True)
    users_count = serializers.IntegerField(read_only=True)
    organization = OrganizationsSerializer(read_only=True)
    organization_name = serializers.SerializerMethodField()
    # Expose admin/staff membership IDs so the frontend permission hook
    # (useIsLeagueStaff / useCanEditTournament) can recognize league-level
    # admins and staff when this serializer is embedded inside a tournament
    # payload (TournamentSerializer.league). Without these the hook can only
    # see org-level membership and would deny league-staff users edit access
    # to bracket controls. PrimaryKeyRelatedField with many=True is read-only
    # by default for the GET path here.
    admin_ids = serializers.PrimaryKeyRelatedField(
        source="admins", many=True, read_only=True
    )
    staff_ids = serializers.PrimaryKeyRelatedField(
        source="staff", many=True, read_only=True
    )

    class Meta:
        model = League
        fields = (
            "pk",
            "organization",
            "organization_name",
            "steam_league_id",
            "name",
            "tournament_count",
            "users_count",
            "admin_ids",
            "staff_ids",
        )
        read_only_fields = (
            "pk",
            "tournament_count",
            "users_count",
            "organization_name",
            "organization",
            "admin_ids",
            "staff_ids",
        )

    def get_organization_name(self, obj: League) -> str | None:
        """Return first organization name for backwards compatibility."""
        first_org = obj.organization
        return first_org.name if first_org else None


class LeagueUserSerializer(serializers.ModelSerializer):
    """
    Serializer for LeagueUser that returns user data with league-specific MMR.
    """

    id = serializers.IntegerField(read_only=True)  # LeagueUser's pk
    pk = serializers.IntegerField(source="user.pk", read_only=True)  # User's pk
    username = serializers.CharField(source="user.username", read_only=True)
    nickname = serializers.CharField(source="user.nickname", read_only=True)
    guildNickname = serializers.CharField(
        source="org_user.guild_nickname", read_only=True, allow_null=True
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
    mmr = serializers.IntegerField(read_only=True)  # LeagueUser's snapshot MMR
    orgUserPk = serializers.IntegerField(source="org_user_id", read_only=True)
    game_mmrs = serializers.SerializerMethodField()
    league_mmr = serializers.IntegerField(source="mmr", read_only=True)

    def get_game_mmrs(self, league_user: LeagueUser) -> dict[str, int]:
        return {
            str(game): mmr for game, mmr in get_org_mmrs(league_user.org_user).items()
        }

    class Meta:
        model = LeagueUser
        fields = (
            "id",
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
            "orgUserPk",
            "game_mmrs",
            "league_mmr",
        )


class LeagueSerializer(serializers.ModelSerializer):
    organization = OrganizationsSerializer(read_only=True)
    # Create-only: update() drops it so a league can't be moved between orgs.
    organization_id = serializers.PrimaryKeyRelatedField(
        queryset=Organization.objects.all(),
        write_only=True,
        source="organization",
        required=False,
    )
    # Roles change only through the admin_team league endpoints.
    admins = TournamentUserSerializer(many=True, read_only=True)
    staff = TournamentUserSerializer(many=True, read_only=True)
    tournament_count = serializers.IntegerField(read_only=True)
    users_count = serializers.IntegerField(read_only=True)
    # Flat org name, kept for backwards compatibility.
    organization_name = serializers.SerializerMethodField()
    # Explicit so DRF doesn't attach a UniqueValidator whose generic "already
    # exists" shadows validate_steam_league_id's "already in use by '<name>'".
    # allow_null=True permits leagues without a Steam League ID; the column's
    # unique constraint ignores NULL (SQL treats NULLs as distinct).
    steam_league_id = serializers.IntegerField(allow_null=True, required=False)

    class Meta:
        model = League
        fields = (
            "pk",
            "organization",
            "organization_id",
            "organization_name",
            "steam_league_id",
            "name",
            "description",
            "rules",
            "prize_pool",
            "timezone",
            "admins",
            "staff",
            "tournament_count",
            "users_count",
            "last_synced",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "pk",
            "created_at",
            "updated_at",
            "tournament_count",
            "users_count",
            "organization_name",
        )

    def get_organization_name(self, obj: League) -> str | None:
        """Return the organization's name, kept for backwards compatibility."""
        first_org = obj.organization
        return first_org.name if first_org else None

    def update(self, instance: League, validated_data: dict[str, Any]) -> League:
        validated_data.pop("organization", None)
        return super().update(instance, validated_data)

    def validate_steam_league_id(self, value: int | None) -> int | None:
        if value is None:
            return value
        if value <= 0:
            raise serializers.ValidationError(
                "Steam league ID must be a positive integer."
            )
        # .nocache() ensures the collision check sees the live row (not a stale
        # cacheops snapshot) — important after a recent PATCH renames an ID.
        qs = League.objects.filter(steam_league_id=value).nocache()
        if self.instance is not None:
            qs = qs.exclude(pk=self.instance.pk)
        other = qs.first()
        if other is not None:
            raise serializers.ValidationError(
                f"Steam league ID {value} is already in use by '{other.name}'."
            )
        return value

    def validate_description(self, value: str | None) -> str | None:
        if value:
            return nh3.clean(value)
        return value

    def validate_rules(self, value: str | None) -> str | None:
        if value:
            return nh3.clean(value)
        return value
