"""Lightweight league serializer and view for SSR meta tags."""

from rest_framework import serializers
from rest_framework.generics import RetrieveAPIView
from rest_framework.permissions import AllowAny

from app.models import League


class LeagueSerializerSSR(serializers.ModelSerializer):
    org_name = serializers.CharField(source="organization.name", default=None)
    org_logo = serializers.SerializerMethodField()

    class Meta:
        model = League
        fields = ["pk", "name", "description", "org_name", "org_logo"]

    def get_org_logo(self, obj: League) -> str | None:
        if obj.organization and obj.organization.logo:
            return obj.organization.logo
        return None


class LeagueSSRView(RetrieveAPIView):
    serializer_class = LeagueSerializerSSR
    permission_classes = [AllowAny]
    queryset = League.objects.select_related("organization")
