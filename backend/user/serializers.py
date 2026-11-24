from typing import Any, Final

from django.db import transaction
from rest_framework import serializers
from rest_framework.validators import UniqueValidator

from app.cache_utils import invalidate_after_commit
from app.models import CustomUser
from events.eligibility.steam import (
    STEAM_ACCOUNT_ID_RANGE,
    apply_admin_steam_account_id,
)
from org.models import Organization
from telemetry.logging import get_logger
from user.models import (
    BaseUserProfile,
    DeadlockUserProfile,
    DotaUserProfile,
    PositionsModel,
)
from user.steam_accounts import log_steam_verification_change

log = get_logger(__name__)


class UserPkField(serializers.RelatedField):
    """Serialize a user relationship as just their pk integer.
    Handles nullable FKs (e.g., deputy_captain) via allow_null.
    """

    def __init__(self, **kwargs: object) -> None:
        kwargs.setdefault("read_only", True)
        kwargs.setdefault("allow_null", True)
        super().__init__(**kwargs)

    def to_representation(self, value: CustomUser | None) -> int | None:
        if value is None:
            return None
        return value.pk


class PositionsSerializer(serializers.ModelSerializer):
    pk = serializers.IntegerField(required=False)
    carry = serializers.IntegerField()
    mid = serializers.IntegerField()
    offlane = serializers.IntegerField()
    soft_support = serializers.IntegerField()
    hard_support = serializers.IntegerField()

    class Meta:
        model = PositionsModel
        fields = ["pk", "carry", "mid", "offlane", "soft_support", "hard_support"]


STEAM_VERIFICATION_READ_FIELDS: Final[tuple[str, ...]] = (
    "steam_account_verified",
    "steam_account_verified_at",
    "steam_account_exists_checked",
)


class TournamentUserSerializer(serializers.ModelSerializer):
    positions = PositionsSerializer(many=False, read_only=True)
    # Auto-computed 32-bit Steam Account ID from 64-bit Friend ID
    steam_account_id = serializers.IntegerField(read_only=True)
    steam_account_verified = serializers.BooleanField(read_only=True)
    steam_account_verified_at = serializers.DateTimeField(read_only=True)
    steam_account_exists_checked = serializers.BooleanField(read_only=True)
    # Writable fields use CustomUser's profile-backed properties.
    nickname = serializers.CharField(
        allow_null=True,
        allow_blank=True,
        required=False,
    )
    avatar = serializers.CharField(
        allow_null=True,
        allow_blank=True,
        required=False,
    )

    class Meta:
        model = CustomUser
        fields = (
            "pk",
            "username",
            "nickname",
            "avatar",
            "discordId",
            "discordNickname",
            "positions",
            "steam_account_id",
            *STEAM_VERIFICATION_READ_FIELDS,
            "avatarUrl",
            "positions",
        )


class UserSerializer(serializers.ModelSerializer):
    positions = PositionsSerializer(many=False, read_only=False, required=False)
    default_organization = serializers.PrimaryKeyRelatedField(
        queryset=Organization.objects.all(),
        required=False,
        allow_null=True,
    )
    # Declaring the field explicitly drops the UniqueValidator ModelSerializer
    # would have built from unique=True, so re-attach it — without this a
    # collision reaches the DB and surfaces as a 500.
    steam_account_id = serializers.IntegerField(
        required=False,
        allow_null=True,
        min_value=STEAM_ACCOUNT_ID_RANGE.start,
        max_value=STEAM_ACCOUNT_ID_RANGE.stop - 1,
        validators=[
            UniqueValidator(
                queryset=CustomUser.objects.all(),
                message="This Friend ID is already assigned to another account.",
            )
        ],
    )
    # Role memberships used by frontend permission hooks to gate create
    # actions without needing a follow-up fetch (e.g. Create Tournament
    # button on the global /tournaments/ page). Empty lists for users with
    # no affiliations — never null.
    steam_account_verified = serializers.BooleanField(read_only=True)
    steam_account_verified_at = serializers.DateTimeField(read_only=True)
    steam_account_exists_checked = serializers.BooleanField(read_only=True)
    admin_organization_ids = serializers.SerializerMethodField()
    staff_organization_ids = serializers.SerializerMethodField()
    admin_league_ids = serializers.SerializerMethodField()
    staff_league_ids = serializers.SerializerMethodField()
    # Writable fields use CustomUser's profile-backed properties.
    nickname = serializers.CharField(
        allow_null=True,
        allow_blank=True,
        required=False,
    )
    avatar = serializers.CharField(
        allow_null=True,
        allow_blank=True,
        required=False,
    )

    class Meta:
        model = CustomUser
        fields = (
            "pk",
            "username",
            "nickname",
            "discordNickname",
            "is_staff",
            "is_active",
            "is_superuser",
            "avatar",
            "discordId",
            "steam_account_id",
            *STEAM_VERIFICATION_READ_FIELDS,
            "avatarUrl",
            "email",
            "date_joined",
            "positions",
            "default_organization",
            "admin_organization_ids",
            "staff_organization_ids",
            "admin_league_ids",
            "staff_league_ids",
        )

    def get_admin_organization_ids(self, obj: CustomUser) -> list[int]:
        # Owner counts as admin in the hierarchy; merge both reverse
        # relations so the frontend gets one canonical "I can admin this
        # org" list. Dedupe via set in case an owner is also in admins.
        owned = obj.owned_organizations.values_list("pk", flat=True)
        admin = obj.admin_organizations.values_list("pk", flat=True)
        return sorted({*owned, *admin})

    def get_staff_organization_ids(self, obj: CustomUser) -> list[int]:
        return list(obj.staff_organizations.values_list("pk", flat=True))

    def get_admin_league_ids(self, obj: CustomUser) -> list[int]:
        return list(obj.admin_leagues.values_list("pk", flat=True))

    def get_staff_league_ids(self, obj: CustomUser) -> list[int]:
        return list(obj.staff_leagues.values_list("pk", flat=True))

    PRIVILEGE_FIELDS: Final[frozenset[str]] = frozenset(
        {"is_staff", "is_superuser", "is_active"}
    )

    def _strip_privilege_fields(
        self, validated_data: dict[str, Any], target_id: int | None
    ) -> None:
        request = self.context.get("request")
        actor = getattr(request, "user", None)
        if actor is not None and actor.is_superuser:
            return
        dropped = sorted(f for f in self.PRIVILEGE_FIELDS if f in validated_data)
        if not dropped:
            return
        for field in dropped:
            validated_data.pop(field)
        log.warning(
            "user_privilege_fields_ignored",
            system="user",
            subsystem="serializer",
            actor_id=getattr(actor, "pk", None),
            target_id=target_id,
            fields=dropped,
        )

    def _actor(self) -> CustomUser | None:
        actor = getattr(self.context.get("request"), "user", None)
        return actor if isinstance(actor, CustomUser) else None

    def update(self, instance: CustomUser, validated_data: dict) -> CustomUser:
        self._strip_privilege_fields(validated_data, instance.pk)
        validated_data.pop("discordNickname", None)
        with transaction.atomic():
            try:
                positions_data = validated_data.pop("positions", None)
                if positions_data:
                    if instance.positions is None:
                        # SET_NULL on DotaUserProfile.positions means the shim
                        # getter can return None — create on demand (the shim
                        # setter persists it onto the dota profile).
                        instance.positions = PositionsModel.objects.create()
                    positions_instance = instance.positions
                    for key, value in positions_data.items():
                        setattr(positions_instance, key, value)
                    positions_instance.save()
                    log.debug(
                        "positions_updated",
                        system="api",
                        subsystem="serializer",
                    )
            except KeyError:
                pass
            has_steam_id = "steam_account_id" in validated_data
            new_steam_id = validated_data.pop("steam_account_id", None)
            for key, value in validated_data.items():
                setattr(instance, key, value)
            grant = (
                apply_admin_steam_account_id(
                    instance, new_steam_id, actor=self._actor()
                )
                if has_steam_id
                else None
            )

            instance.save()
            if grant is not None:
                log_steam_verification_change(
                    instance, self._actor(), grant.org_id, True
                )
            log.debug(
                "user_updated",
                system="api",
                subsystem="serializer",
                user_id=instance.pk,
            )

            # Invalidate all cached views that include this user.
            # Deferred until after commit so cacheops sees committed state.
            invalidate_after_commit(
                *instance.tournaments.all(),
                *instance.org_memberships.select_related("organization").all(),
                *(
                    mu.organization
                    for mu in instance.org_memberships.select_related(
                        "organization"
                    ).all()
                ),
                *instance.league_memberships.select_related("league").all(),
                *(
                    mu.league
                    for mu in instance.league_memberships.select_related("league").all()
                ),
            )

        return instance

    def create(self, validated_data: dict) -> CustomUser:
        self._strip_privilege_fields(validated_data, None)
        fields = self.Meta.fields

        with transaction.atomic():
            for key in validated_data.keys():
                if key not in fields:
                    raise KeyError(f"Invalid field: {key}")

            has_steam_id = "steam_account_id" in validated_data
            new_steam_id = validated_data.pop("steam_account_id", None)
            if "positions" in validated_data:
                positions_data = validated_data.pop("positions")
                positions = PositionsModel.objects.create(**positions_data)
            else:
                log.debug(
                    "user_create_no_positions", system="api", subsystem="serializer"
                )
                positions = PositionsModel.objects.create()
            user = CustomUser(positions=positions, **validated_data)
            grant = (
                apply_admin_steam_account_id(user, new_steam_id, actor=self._actor())
                if has_steam_id
                else None
            )

            user.save()
            if grant is not None:
                log_steam_verification_change(user, self._actor(), grant.org_id, True)
            return user


class BaseUserProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = BaseUserProfile
        fields = ["nickname", "avatar"]


class DotaUserProfileSerializer(serializers.ModelSerializer):
    positions = PositionsSerializer(required=False, allow_null=True)

    class Meta:
        model = DotaUserProfile
        fields = ["positions", "has_active_dota_mmr", "dota_mmr_last_verified"]

    def update(
        self, instance: DotaUserProfile, validated_data: dict[str, Any]
    ) -> DotaUserProfile:
        positions_data = validated_data.pop("positions", None)
        if positions_data:
            if instance.positions is None:
                instance.positions = PositionsModel.objects.create()
            for key, value in positions_data.items():
                setattr(instance.positions, key, value)
            instance.positions.save()
        for key, value in validated_data.items():
            setattr(instance, key, value)
        instance.save()
        return instance


class DeadlockUserProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = DeadlockUserProfile
        fields = ["rank", "rank_date"]


class UserProfileLayeredSerializer(serializers.Serializer):
    """Layered profile shape consumed by userProfileEntityAdapter on the frontend.

    `orgProfiles` is a placeholder and always empty for now.
    """

    pk = serializers.IntegerField(read_only=True)
    base = BaseUserProfileSerializer(source="base_profile", read_only=True)
    gameUser = serializers.SerializerMethodField()
    orgProfiles = serializers.SerializerMethodField()

    def get_gameUser(self, user: CustomUser) -> dict:
        bp = user.base_profile
        return {
            "dota": DotaUserProfileSerializer(bp.dota_user_profile).data,
            "deadlock": DeadlockUserProfileSerializer(bp.deadlock_user_profile).data,
        }

    def get_orgProfiles(self, user: CustomUser) -> dict:
        return {}  # org-scoped profiles are not built yet
