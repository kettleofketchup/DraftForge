from django.db import transaction
from rest_framework import serializers

from app.models import CustomUser, GameType
from app.permissions import request_user
from app.serializers import TournamentUserSerializer, UserPkField
from draft.models import DraftOptions
from league.models import League, LeagueUser
from league.permissions import check_lobby_steam_league_id
from league.serializers import LeagueMinimalSerializer, LeaguesSerializer
from org.mmr import LEAGUE_GAME, org_mmr_map
from org.models import OrgUser
from telemetry.logging import get_logger
from tournament.choices import GameMode
from tournament.models import Team, Tournament
from tournament.serializers.draft import (
    DraftOptionsSerializer,
    DraftSerializerSlim,
    _shared_draft_options,
)
from tournament.serializers.game import GameSerializerForTournament
from tournament.serializers.team import (
    TeamSerializerForTournament,
    TournamentTeamSerializer,
)
from tournament.serializers.users import tournament_organization

log = get_logger(__name__)


# For tournaments page
class TournamentsSerializer(serializers.ModelSerializer):
    captains = TournamentUserSerializer(many=True, read_only=True)
    winner = TeamSerializerForTournament(many=False, read_only=True)

    class Meta:
        model = Tournament
        fields = (
            "pk",
            "name",
            "date_played",
            "timezone",
            "tournament_type",
            "state",
            "captains",
            "winner",
        )


class TournamentListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for tournament list page.

    Only includes basic scalar fields and minimal league info.
    No nested team/user data for fast performance.
    """

    league = LeagueMinimalSerializer(read_only=True)
    user_count = serializers.IntegerField(read_only=True)
    signups_open = serializers.BooleanField(read_only=True)

    class Meta:
        model = Tournament
        fields = (
            "pk",
            "name",
            "date_played",
            "timezone",
            "tournament_type",
            "state",
            "league",
            "user_count",
            "signups_open",
        )


class TournamentSerializer(serializers.ModelSerializer):
    teams = TournamentTeamSerializer(many=True, read_only=True)
    users = serializers.SerializerMethodField()
    draft = DraftSerializerSlim(many=False, read_only=True)
    draft_options = DraftOptionsSerializer(required=False)

    user_ids = serializers.PrimaryKeyRelatedField(
        source="users",
        many=True,
        queryset=CustomUser.objects.all(),
        write_only=True,
        required=False,
    )
    tournament_type = serializers.CharField(read_only=False)
    captains = UserPkField(many=True, read_only=True)
    games = GameSerializerForTournament(many=True, read_only=True)
    league = LeaguesSerializer(read_only=True)
    league_id_write = serializers.PrimaryKeyRelatedField(
        queryset=League.objects.all(),
        write_only=True,
        source="league",
        required=False,
        allow_null=True,
    )
    organization_pk = serializers.SerializerMethodField()
    league_pk = serializers.SerializerMethodField()
    source_event = serializers.SerializerMethodField()

    def get_organization_pk(self, tournament: Tournament) -> int | None:
        """Return the primary organization's PK for this tournament."""
        org = tournament_organization(
            tournament, fresh=self.context.get("fresh", False)
        )
        return org.pk if org else None

    def get_league_pk(self, tournament: Tournament) -> int | None:
        """Return the league's PK for this tournament."""
        return tournament.league.pk if tournament.league else None

    def get_source_event(self, tournament: Tournament) -> dict | None:
        """Return lightweight source event data (event that spawned this tournament)."""
        events = tournament.source_event.all()
        if self.context.get("fresh", False):
            events = events.nocache().select_related("event_repeater")
        event = events.first()
        if not event:
            return None
        result = {
            "id": event.id,
            "name": event.name,
            "organization_id": event.organization_id,
            "event_repeater": None,
        }
        if event.event_repeater:
            result["event_repeater"] = {
                "id": event.event_repeater.id,
                "name": event.event_repeater.name,
            }
        return result

    def get_users(self, tournament: Tournament) -> list[int]:
        """Return user PKs only — full data provided via _users dict."""
        return [u.pk for u in tournament.users.all()]

    class Meta:
        model = Tournament
        fields = (
            "pk",
            "name",
            "draft",
            "date_played",
            "timezone",
            "users",
            "teams",
            "winning_team",
            "state",
            "games",
            "user_ids",
            "captains",
            "tournament_type",
            "league",
            "league_id_write",
            "organization_pk",
            "league_pk",
            "source_event",
            "auto_create_hero_drafts",
            "discord_send_draft_link",
            "discord_send_herodraft_link",
            "draft_options",
            "dota_lobby_mode",
            "dota_lobby_launch",
            "dota_lobby_region",
            "discord_send_lobby_info",
            "game_type",
            "game_mode",
            "lobby_steam_league_id",
            "captains_draft_time",
            "custom_game_name",
        )
        # The game is fixed at creation; everything else is editable.
        read_only_fields = ("game_type",)
        extra_kwargs = {"captains_draft_time": {"min_value": 1}}

    def validate(self, data: dict) -> dict:
        self._validate_game_mode(data)
        if "lobby_steam_league_id" in data and (
            self.instance is None
            or data["lobby_steam_league_id"] != self.instance.lobby_steam_league_id
        ):
            check_lobby_steam_league_id(
                request_user(self.context),
                data["lobby_steam_league_id"],
                data.get("league", self.instance.league if self.instance else None),
            )
        return data

    def _validate_game_mode(self, data: dict) -> None:
        mode = data.get("game_mode")
        if mode is None or (self.instance and mode == self.instance.game_mode):
            return
        game_type = (
            self.instance.game_type
            if self.instance
            else Tournament._meta.get_field("game_type").default
        )
        if game_type != GameType.DOTA2 and mode in (
            GameMode.CAPTAINS_MODE,
            GameMode.TURBO,
        ):
            raise serializers.ValidationError(
                {"game_mode": f"{mode} is only available for Dota 2."}
            )

    def to_representation(self, instance: Tournament) -> dict:
        data = super().to_representation(instance)
        data["draft_options"] = DraftOptionsSerializer(self._options_for(instance)).data
        return data

    def _options_for(self, instance: Tournament) -> DraftOptions:
        if isinstance(self.parent, serializers.ListSerializer):
            try:
                return instance.draft_options
            except DraftOptions.DoesNotExist:
                return DraftOptions(tournament=instance)
        return _shared_draft_options(self, instance)

    def update(self, instance: Tournament, validated_data: dict) -> Tournament:
        """
        Override update to handle:
        1. Captain removal when users are removed (delete their team)
        2. OrgUser/LeagueUser creation when users are added
        """
        with transaction.atomic():
            # Check if users are being updated
            if "users" in validated_data:
                new_users = set(validated_data["users"])
                current_users = set(instance.users.all())
                removed_users = current_users - new_users
                added_users = new_users - current_users

                # Bulk delete teams where removed users are captains
                if removed_users:
                    removed_user_ids = [u.pk for u in removed_users]
                    captain_teams = Team.objects.filter(
                        tournament=instance, captain_id__in=removed_user_ids
                    )
                    if captain_teams.exists():
                        log.info(
                            "captain_teams_removed",
                            system="api",
                            subsystem="serializer",
                            count=captain_teams.count(),
                            tournament_id=instance.pk,
                        )
                        captain_teams.delete()

                # Bulk create OrgUser and LeagueUser for added users
                if added_users and instance.league:
                    org = instance.league.organization
                    if org:
                        # Get existing OrgUsers for these users in this org
                        existing_org_users = {
                            ou.user_id: ou
                            for ou in OrgUser.objects.filter(
                                user__in=added_users, organization=org
                            )
                        }

                        # Create missing OrgUsers in bulk
                        new_org_users = []
                        for user in added_users:
                            if user.pk not in existing_org_users:
                                new_org_users.append(
                                    OrgUser(user=user, organization=org)
                                )
                        if new_org_users:
                            OrgUser.objects.bulk_create(new_org_users)
                            # Refresh existing_org_users with newly created ones
                            existing_org_users = {
                                ou.user_id: ou
                                for ou in OrgUser.objects.filter(
                                    user__in=added_users, organization=org
                                )
                            }

                        # Get existing LeagueUsers for these users in this league
                        existing_league_users = set(
                            LeagueUser.objects.filter(
                                user__in=added_users, league=instance.league
                            ).values_list("user_id", flat=True)
                        )

                        # Create missing LeagueUsers in bulk
                        league_mmrs = org_mmr_map(
                            org.pk,
                            [
                                u.pk
                                for u in added_users
                                if u.pk not in existing_league_users
                            ],
                            LEAGUE_GAME,
                        )
                        new_league_users = []
                        for user in added_users:
                            if user.pk not in existing_league_users:
                                org_user = existing_org_users.get(user.pk)
                                if org_user:
                                    new_league_users.append(
                                        LeagueUser(
                                            user=user,
                                            org_user=org_user,
                                            league=instance.league,
                                            mmr=league_mmrs.get(user.pk, 0),
                                        )
                                    )
                        if new_league_users:
                            LeagueUser.objects.bulk_create(new_league_users)

            return super().update(instance, validated_data)
