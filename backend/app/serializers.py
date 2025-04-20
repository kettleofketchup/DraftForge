from rest_framework import serializers
from django.contrib.auth.models import User
from .models import DotaInfo, CustomUser, DiscordInfo


class DotaSerializer(serializers.ModelSerializer):
    class Meta:
        model = DotaInfo
        fields = ("mmr", "steamid", "position")


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomUser
        fields = (
            "username",
            "is_staff",
            "is_active",
            "steamid",
            "mmr",
            "avatarUrl",
            "email",
            "username",
            "date_joined",
        )
