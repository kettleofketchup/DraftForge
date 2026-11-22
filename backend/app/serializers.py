from django.db import transaction
from rest_framework import serializers
from rest_framework.validators import UniqueValidator

from app.cache_utils import invalidate_after_commit
from org.models import Organization
from telemetry.logging import get_logger

from .models import (
    CustomUser,
    Joke,
    PositionsModel,
)

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


class TournamentUserSerializer(serializers.ModelSerializer):
    positions = PositionsSerializer(many=False, read_only=True)
    # Auto-computed 32-bit Steam Account ID from 64-bit Friend ID
    steam_account_id = serializers.IntegerField(read_only=True)
    # nickname/avatar live on BaseUserProfile. Use `source="nickname"`
    # so DRF goes through the CustomUser transitional @property — the getter
    # reads from base_profile, the setter writes to base_profile + invalidates
    # cacheops. Critically, this keeps PATCH /users/<pk>/ working for admin
    # user-edit flows (org / tournament pages), which would otherwise be a
    # silent no-op if the fields were read_only=True.
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
    admin_organization_ids = serializers.SerializerMethodField()
    staff_organization_ids = serializers.SerializerMethodField()
    admin_league_ids = serializers.SerializerMethodField()
    staff_league_ids = serializers.SerializerMethodField()
    # nickname/avatar live on BaseUserProfile. Use `source="nickname"`
    # so DRF goes through the CustomUser transitional @property — the getter
    # reads from base_profile, the setter writes to base_profile + invalidates
    # cacheops. Keeps PATCH /users/<pk>/ working for admin user-edit flows
    # (org/tournament pages) which would otherwise be a silent no-op.
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

    def update(self, instance: CustomUser, validated_data: dict) -> CustomUser:
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
            for key, value in validated_data.items():
                setattr(instance, key, value)

            instance.save()
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
        fields = self.Meta.fields

        with transaction.atomic():
            for key in validated_data.keys():
                if key not in fields:
                    raise KeyError(f"Invalid field: {key}")

            if "positions" in validated_data:
                positions_data = validated_data.pop("positions")
                positions = PositionsModel.objects.create(**positions_data)
                user = CustomUser.objects.create(positions=positions, **validated_data)

            else:
                log.debug(
                    "user_create_no_positions", system="api", subsystem="serializer"
                )
                positions = PositionsModel.objects.create()
                user = CustomUser(positions=positions, **validated_data)

            user.save()
            return user


class JokeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Joke
        fields = ["tangoes_purchased"]
        read_only_fields = ["tangoes_purchased"]
