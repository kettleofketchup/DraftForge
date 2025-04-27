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
            "pk",
            "username",
            "nickname",
            "is_staff",
            "is_active",
            "is_superuser",
            "avatar",
            "position",
            "discordId",
            "steamid",
            "mmr",
            "avatarUrl",
            "email",
            "username",
            "date_joined",
        )

    def create(self, validated_data):
        fields = self.Meta.fields
        for key in validated_data.keys():
            if key not in fields:
                raise KeyError(f"Invalid field: {key}")

        user = CustomUser(**validated_data)  # create user with all the other fields
        user.save()
        return user
