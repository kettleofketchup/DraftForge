"""Lightweight serializers for SSR meta tags and above-the-fold skeletons."""

from rest_framework import serializers

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
