"""Lightweight tournament serializer and view for SSR meta tags."""

from rest_framework import serializers
from rest_framework.generics import RetrieveAPIView
from rest_framework.permissions import AllowAny

from app.models import Tournament


class TournamentSerializerSSR(serializers.ModelSerializer):
    org_name = serializers.SerializerMethodField()
    org_logo = serializers.SerializerMethodField()
    league_name = serializers.CharField(source="league.name", default=None)

    class Meta:
        model = Tournament
        fields = ["pk", "name", "org_name", "org_logo", "league_name"]

    def get_org_name(self, obj: Tournament) -> str | None:
        if obj.league and obj.league.organization:
            return obj.league.organization.name
        return None

    def get_org_logo(self, obj: Tournament) -> str | None:
        if obj.league and obj.league.organization and obj.league.organization.logo:
            return obj.league.organization.logo
        return None


class TournamentSSRView(RetrieveAPIView):
    serializer_class = TournamentSerializerSSR
    permission_classes = [AllowAny]
    queryset = Tournament.objects.select_related("league__organization")
