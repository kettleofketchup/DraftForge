from rest_framework import serializers

from app.models import CustomUser

from .models import BaseUserProfile


class BaseUserProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = BaseUserProfile
        fields = ["nickname", "avatar"]


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
        return {}  # T2 populates

    def get_orgProfiles(self, user: CustomUser) -> dict:
        return {}  # T3 populates
