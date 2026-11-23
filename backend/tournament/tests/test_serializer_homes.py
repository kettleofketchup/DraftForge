from typing import Any

from django.test import TestCase
from django.utils import timezone

from app.models import CustomUser, Game, Team, Tournament
from draft.models import Draft, DraftRound
from league.models import League
from league.serializers import LeagueMinimalSerializer, LeaguesSerializer
from org.models import Organization
from org.serializers import OrganizationsSerializer
from tournament.serializers.tournament import TournamentSerializer

TEAM_SLIM_KEYS = [
    "captain",
    "deputy_captain",
    "draft_is_connected",
    "draft_is_ready",
    "draft_order",
    "draft_reserve_ms",
    "dropin_members",
    "left_members",
    "members",
    "name",
    "pk",
    "placement",
]
DRAFT_OPTIONS_KEYS = [
    "grace_time_ms",
    "hero_grace_time_ms",
    "hero_reserve_time_ms",
    "hero_timer_enabled",
    "reserve_time_ms",
    "timeout_action",
    "timer_enabled",
]
EXPECTED_SHAPE: dict[str, list[str]] = {
    "tournament": [
        "auto_create_hero_drafts",
        "captains",
        "captains_draft_time",
        "custom_game_name",
        "date_played",
        "discord_send_draft_link",
        "discord_send_herodraft_link",
        "discord_send_lobby_info",
        "dota_lobby_launch",
        "dota_lobby_mode",
        "dota_lobby_region",
        "draft",
        "draft_options",
        "game_mode",
        "game_type",
        "games",
        "league",
        "league_pk",
        "lobby_steam_league_id",
        "name",
        "organization_pk",
        "pk",
        "source_event",
        "state",
        "teams",
        "timezone",
        "tournament_type",
        "users",
        "winning_team",
    ],
    "team": sorted([*TEAM_SLIM_KEYS, "leadership_problems"]),
    "game": [
        "dire_team",
        "gameid",
        "herodraft_id",
        "pk",
        "radiant_team",
        "round",
        "winning_team",
    ],
    "game.radiant_team": TEAM_SLIM_KEYS,
    "league": [
        "admin_ids",
        "name",
        "organization",
        "organization_name",
        "pk",
        "staff_ids",
        "steam_league_id",
    ],
    "league.organization": ["created_at", "logo", "name", "pk"],
    "draft": [
        "clock_armed",
        "draft_options",
        "draft_rounds",
        "draft_style",
        "is_manual_pause",
        "latest_round",
        "paused_at",
        "pk",
        "resuming_until",
        "state",
        "tournament",
        "users_remaining",
    ],
    "draft.draft_rounds": [
        "captain",
        "choice",
        "completed_at",
        "grace_time_ms",
        "pick_duration_ms",
        "pick_number",
        "pick_phase",
        "pk",
        "reserve_used_ms",
        "skip_count",
        "started_at",
        "team",
        "timed_out_at",
    ],
    "draft.draft_rounds.team": TEAM_SLIM_KEYS,
    "draft.tournament": ["pk", "teams"],
    "draft.tournament.teams": TEAM_SLIM_KEYS,
    "draft.draft_options": DRAFT_OPTIONS_KEYS,
    "draft_options": DRAFT_OPTIONS_KEYS,
}


def _shape(data: dict[str, Any]) -> dict[str, list[str]]:
    draft = data["draft"]
    return {
        "tournament": sorted(data),
        "team": sorted(data["teams"][0]),
        "game": sorted(data["games"][0]),
        "game.radiant_team": sorted(data["games"][0]["radiant_team"]),
        "league": sorted(data["league"]),
        "league.organization": sorted(data["league"]["organization"]),
        "draft": sorted(draft),
        "draft.draft_rounds": sorted(draft["draft_rounds"][0]),
        "draft.draft_rounds.team": sorted(draft["draft_rounds"][0]["team"]),
        "draft.tournament": sorted(draft["tournament"]),
        "draft.tournament.teams": sorted(draft["tournament"]["teams"][0]),
        "draft.draft_options": sorted(draft["draft_options"]),
        "draft_options": sorted(data["draft_options"]),
    }


class TournamentSerializerPayloadTest(TestCase):
    def test_tournament_serializer_payload_keys_unchanged(self) -> None:
        owner = CustomUser.objects.create_user(username="payload_owner")
        captain = CustomUser.objects.create_user(username="payload_captain")
        other = CustomUser.objects.create_user(username="payload_other")
        org = Organization.objects.create(name="Payload Org", owner=owner)
        league = League.objects.create(
            name="Payload League", organization=org, steam_league_id=4242
        )
        tournament = Tournament.objects.create(
            name="Payload Cup", league=league, date_played=timezone.now()
        )
        tournament.users.add(captain, other)
        team = Team.objects.create(
            tournament=tournament, name="Payload Team", captain=captain, draft_order=1
        )
        team.members.add(captain)
        other_team = Team.objects.create(
            tournament=tournament, name="Payload Team 2", captain=other, draft_order=2
        )
        other_team.members.add(other)
        Game.objects.create(
            tournament=tournament, radiant_team=team, dire_team=other_team, round=1
        )
        draft = Draft.objects.create(tournament=tournament, draft_style="snake")
        DraftRound.objects.create(draft=draft, captain=captain, pick_number=1)

        tournament = Tournament.objects.nocache().get(pk=tournament.pk)
        self.assertEqual(_shape(TournamentSerializer(tournament).data), EXPECTED_SHAPE)


class LeftoverSerializerHomesTest(TestCase):
    def test_leftovers_live_in_their_apps(self) -> None:
        self.assertEqual(OrganizationsSerializer.__module__, "org.serializers")
        self.assertEqual(LeaguesSerializer.__module__, "league.serializers")
        self.assertEqual(LeagueMinimalSerializer.__module__, "league.serializers")

    def test_tournament_serializer_home(self) -> None:
        self.assertEqual(
            TournamentSerializer.__module__, "tournament.serializers.tournament"
        )
