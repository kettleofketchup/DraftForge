from rest_framework import serializers

from app.models import CustomUser
from app.serializers import PositionsSerializer

from .models import BaseUserProfile, DeadlockUserProfile, DotaUserProfile


class BaseUserProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = BaseUserProfile
        fields = ["nickname", "avatar"]


class DotaUserProfileSerializer(serializers.ModelSerializer):
    positions = PositionsSerializer(required=False, allow_null=True)

    class Meta:
        model = DotaUserProfile
        fields = ["positions", "has_active_dota_mmr", "dota_mmr_last_verified"]


class DeadlockUserProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = DeadlockUserProfile
        fields = ["rank", "rank_date"]


class UserProfileLayeredSerializer(serializers.Serializer):
    """Layered profile shape consumed by userProfileEntityAdapter on the frontend.

    T1 ships only `base` populated; `gameUser` and `orgProfiles` are placeholders
    that fill in during T2 and T3.
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
        return {}  # T3 populates
