from rest_framework import serializers

from draft.models import HeroDraft


class HeroDraftSerializerSSR(serializers.ModelSerializer):
    tournament_name = serializers.SerializerMethodField()
    org_name = serializers.SerializerMethodField()
    team_names = serializers.SerializerMethodField()

    class Meta:
        model = HeroDraft
        fields = ["pk", "tournament_name", "org_name", "team_names"]

    def get_tournament_name(self, obj: HeroDraft) -> str | None:
        if obj.game and obj.game.tournament:
            return obj.game.tournament.name
        return None

    def get_org_name(self, obj: HeroDraft) -> str | None:
        if obj.game and obj.game.tournament and obj.game.tournament.league:
            org = obj.game.tournament.league.organization
            return org.name if org else None
        return None

    def get_team_names(self, obj: HeroDraft) -> list[str]:
        # Uses prefetched draft_teams + tournament_team from the view's queryset.
        # Don't call .select_related() or [:2] here — both bypass the prefetch cache.
        return [dt.tournament_team.name for dt in obj.draft_teams.all()]
