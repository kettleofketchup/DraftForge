"""Lightweight serializers for SSR meta tags and above-the-fold skeletons."""

from rest_framework import serializers

from app.models import CustomUser, HeroDraft, League, Organization, Tournament
from events.models import Event


class TournamentSerializerSSR(serializers.ModelSerializer):
    org_name = serializers.SerializerMethodField()
    org_logo = serializers.SerializerMethodField()
    league_name = serializers.CharField(source="league.name", default=None)

    class Meta:
        model = Tournament
        fields = ["pk", "name", "org_name", "org_logo", "league_name"]

    def get_org_name(self, obj):
        if obj.league and obj.league.organization:
            return obj.league.organization.name
        return None

    def get_org_logo(self, obj):
        if obj.league and obj.league.organization and obj.league.organization.logo:
            return obj.league.organization.logo
        return None


class OrganizationSerializerSSR(serializers.ModelSerializer):
    class Meta:
        model = Organization
        fields = ["pk", "name", "description", "logo"]


class LeagueSerializerSSR(serializers.ModelSerializer):
    org_name = serializers.CharField(source="organization.name", default=None)
    org_logo = serializers.SerializerMethodField()

    class Meta:
        model = League
        fields = ["pk", "name", "description", "org_name", "org_logo"]

    def get_org_logo(self, obj):
        if obj.organization and obj.organization.logo:
            return obj.organization.logo
        return None


class EventSerializerSSR(serializers.ModelSerializer):
    org_name = serializers.CharField(source="organization.name", default=None)
    league_name = serializers.SerializerMethodField()

    class Meta:
        model = Event
        fields = ["id", "name", "description", "org_name", "league_name"]

    def get_league_name(self, obj):
        if obj.tournament_league:
            return obj.tournament_league.name
        return None


class HeroDraftSerializerSSR(serializers.ModelSerializer):
    tournament_name = serializers.SerializerMethodField()
    org_name = serializers.SerializerMethodField()
    team_names = serializers.SerializerMethodField()

    class Meta:
        model = HeroDraft
        fields = ["pk", "tournament_name", "org_name", "team_names"]

    def get_tournament_name(self, obj):
        if obj.game and obj.game.tournament:
            return obj.game.tournament.name
        return None

    def get_org_name(self, obj):
        if obj.game and obj.game.tournament and obj.game.tournament.league:
            org = obj.game.tournament.league.organization
            return org.name if org else None
        return None

    def get_team_names(self, obj):
        # Uses prefetched draft_teams + tournament_team from the view's queryset.
        # Don't call .select_related() or [:2] here — both bypass the prefetch cache.
        return [dt.tournament_team.name for dt in obj.draft_teams.all()]


class UserSerializerSSR(serializers.ModelSerializer):
    avatar_url = serializers.SerializerMethodField()

    class Meta:
        model = CustomUser
        fields = ["pk", "username", "nickname", "avatar_url"]

    def get_avatar_url(self, obj):
        return obj.avatarUrl
