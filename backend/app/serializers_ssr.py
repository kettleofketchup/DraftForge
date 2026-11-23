"""Lightweight serializers for SSR meta tags and above-the-fold skeletons."""

from rest_framework import serializers

from app.models import CustomUser
from events.models import Event


class EventSerializerSSR(serializers.ModelSerializer):
    org_name = serializers.CharField(source="organization.name", default=None)
    league_name = serializers.SerializerMethodField()

    class Meta:
        model = Event
        fields = ["id", "name", "description", "org_name", "league_name"]

    def get_league_name(self, obj: Event) -> str | None:
        if obj.tournament_league:
            return obj.tournament_league.name
        return None


class UserSerializerSSR(serializers.ModelSerializer):
    # nickname lives on BaseUserProfile via the OneToOne reverse
    # accessor `base_profile`. Source explicitly so DRF doesn't fall back
    # to the transitional @property and so n+1 detectors / select_related
    # callers can see the dependency.
    nickname = serializers.CharField(
        source="base_profile.nickname",
        read_only=True,
        allow_null=True,
    )
    avatar_url = serializers.SerializerMethodField()

    class Meta:
        model = CustomUser
        fields = ["pk", "username", "nickname", "avatar_url"]

    def get_avatar_url(self, obj: CustomUser) -> str | None:
        return obj.avatarUrl
