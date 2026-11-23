from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.response import Response
from rest_framework.test import APIClient

from app.models import CustomUser, GameType
from events.constants import EventState
from events.models import Event
from league.models import League
from org.models import Organization
from tournament.choices import GameMode
from tournament.models import Tournament


class TournamentEditConfigBase(TestCase):
    def setUp(self) -> None:
        self.owner = CustomUser.objects.create_user(username="owner", password="x")
        self.league_admin = CustomUser.objects.create_user(
            username="league_admin", password="x"
        )
        self.outsider = CustomUser.objects.create_user(
            username="outsider", password="x"
        )
        self.site_staff = CustomUser.objects.create_user(
            username="site_staff", password="x", is_staff=True
        )
        self.org = Organization.objects.create(name="Config Org", owner=self.owner)
        self.league = League.objects.create(
            name="Config League", organization=self.org, steam_league_id=4242
        )
        self.league.admins.add(self.league_admin)
        self.league_staff = CustomUser.objects.create_user(
            username="league_staff", password="x"
        )
        self.league.staff.add(self.league_staff)
        other_owner = CustomUser.objects.create_user(
            username="other_owner", password="x"
        )
        other_org = Organization.objects.create(name="Other Org", owner=other_owner)
        self.other_league = League.objects.create(
            name="Other League", organization=other_org, steam_league_id=7777
        )
        self.tournament = Tournament.objects.create(
            name="Config Tourney",
            league=self.league,
            tournament_type="double_elimination",
            date_played=timezone.now(),
            state="in_progress",
        )
        self.event = Event.objects.create(
            organization=self.org,
            name="Config Night",
            scheduled_at=timezone.now() + timedelta(days=1),
            state=EventState.SIGNUPS_OPEN,
            tournament_league=self.league,
            tournament=self.tournament,
        )
        self.url = f"/api/tournaments/{self.tournament.pk}/"
        self.client = APIClient()
        self.client.force_authenticate(self.league_admin)

    def patch(self, data: dict[str, object]) -> Response:
        return self.client.patch(self.url, data, format="json")

    def full_config(self) -> dict:
        return {
            "game_mode": "turbo",
            "captains_draft_time": 30,
            "custom_game_name": "n",
            "lobby_steam_league_id": 123,
            "dota_lobby_mode": "auto",
            "dota_lobby_launch": "auto",
            "dota_lobby_region": "europe",
            "discord_send_lobby_info": True,
        }


class TournamentEditConfigTests(TournamentEditConfigBase):
    def test_league_admin_sets_game_config_on_in_progress_event_tournament(
        self,
    ) -> None:
        payload = self.full_config()
        resp = self.patch(payload)
        self.assertEqual(resp.status_code, 200, resp.data)
        self.tournament.refresh_from_db()
        for name, value in payload.items():
            with self.subTest(field=name):
                self.assertEqual(getattr(self.tournament, name), value)

    def test_event_row_unchanged_after_tournament_edit(self) -> None:
        before_mode = self.event.game_mode
        before_lobby = self.event.dota_lobby_mode
        resp = self.patch(self.full_config())
        self.assertEqual(resp.status_code, 200, resp.data)
        self.event.refresh_from_db()
        self.assertEqual(self.event.game_mode, before_mode)
        self.assertEqual(self.event.dota_lobby_mode, before_lobby)

    def test_cm_and_turbo_rejected_for_non_dota(self) -> None:
        Tournament.objects.filter(pk=self.tournament.pk).update(
            game_type=GameType.DEADLOCK
        )
        for mode in (GameMode.CAPTAINS_MODE, GameMode.TURBO):
            with self.subTest(mode=mode):
                resp = self.patch({"game_mode": mode})
                self.assertEqual(resp.status_code, 400)
                self.assertIn("game_mode", resp.data)
                self.assertEqual(
                    str(resp.data["game_mode"][0]),
                    f"{mode} is only available for Dota 2.",
                )

    def test_unchanged_cm_on_non_dota_saves(self) -> None:
        Tournament.objects.filter(pk=self.tournament.pk).update(
            game_type=GameType.DEADLOCK, game_mode=GameMode.CAPTAINS_MODE
        )
        resp = self.patch({"name": "Renamed", "game_mode": "captains_mode"})
        self.assertEqual(resp.status_code, 200, resp.data)

    def test_game_type_is_read_only(self) -> None:
        resp = self.patch({"game_type": GameType.DEADLOCK})
        self.assertEqual(resp.status_code, 200, resp.data)
        self.tournament.refresh_from_db()
        self.assertEqual(self.tournament.game_type, GameType.DOTA2)

    def test_draft_time_below_one_rejected(self) -> None:
        resp = self.patch({"captains_draft_time": 0})
        self.assertEqual(resp.status_code, 400)
        self.assertIn("captains_draft_time", resp.data)

    def test_invalid_game_mode_rejected(self) -> None:
        resp = self.patch({"game_mode": "allpick"})
        self.assertEqual(resp.status_code, 400)
        self.assertIn("game_mode", resp.data)

    def test_outsider_gets_403(self) -> None:
        self.client.force_authenticate(self.outsider)
        resp = self.patch({"game_mode": "turbo"})
        self.assertEqual(resp.status_code, 403)

    def test_register_with_turbo_as_site_staff(self) -> None:
        self.client.force_authenticate(self.site_staff)
        resp = self.client.post(
            "/api/tournament/register",
            {
                "name": "Turbo Cup",
                "date_played": timezone.now().isoformat(),
                "tournament_type": "double_elimination",
                "game_mode": "turbo",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 201, resp.data)
        self.assertEqual(resp.data["game_mode"], "turbo")
        self.assertEqual(resp.data["game_type"], GameType.DOTA2)

    def test_detail_reflects_game_mode_after_patch(self) -> None:
        self.assertEqual(self.client.get(self.url).data["game_mode"], "normal")
        resp = self.patch({"game_mode": "turbo"})
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertEqual(self.client.get(self.url).data["game_mode"], "turbo")


class TournamentLobbySteamLeagueIdTests(TournamentEditConfigBase):
    def setUp(self) -> None:
        super().setUp()
        self.client.force_authenticate(self.league_staff)

    def steam_id(self) -> int | None:
        return Tournament.objects.get(pk=self.tournament.pk).lobby_steam_league_id

    def test_league_staff_refused_another_leagues_steam_id(self) -> None:
        resp = self.patch({"lobby_steam_league_id": 7777})
        self.assertEqual(resp.status_code, 400, resp.data)
        self.assertEqual(
            str(resp.data["lobby_steam_league_id"][0]),
            "Steam league ID 7777 belongs to 'Other League'. "
            "Only an admin of that league can use it.",
        )
        self.assertIsNone(self.steam_id())

    def test_own_league_steam_id_allowed(self) -> None:
        resp = self.patch({"lobby_steam_league_id": 4242})
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertEqual(self.steam_id(), 4242)

    def test_non_positive_steam_id_rejected(self) -> None:
        for value in (0, -5):
            with self.subTest(value=value):
                resp = self.patch({"lobby_steam_league_id": value})
                self.assertEqual(resp.status_code, 400, resp.data)
                self.assertEqual(
                    str(resp.data["lobby_steam_league_id"][0]),
                    "Steam league ID must be a positive integer.",
                )

    def test_clearing_steam_id_allowed(self) -> None:
        Tournament.objects.filter(pk=self.tournament.pk).update(
            lobby_steam_league_id=4242
        )
        resp = self.patch({"lobby_steam_league_id": None})
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertIsNone(self.steam_id())

    def test_admin_of_owning_league_may_use_its_id(self) -> None:
        self.other_league.admins.add(self.league_staff)
        resp = self.patch({"lobby_steam_league_id": 7777})
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertEqual(self.steam_id(), 7777)

    def test_unchanged_foreign_id_does_not_block_other_edits(self) -> None:
        Tournament.objects.filter(pk=self.tournament.pk).update(
            lobby_steam_league_id=7777
        )
        resp = self.patch({"name": "Renamed", "lobby_steam_league_id": 7777})
        self.assertEqual(resp.status_code, 200, resp.data)


class TournamentDiscordLogsAccessTests(TournamentEditConfigBase):
    def logs_url(self) -> str:
        return f"{self.url}discord-logs/"

    def test_anonymous_refused(self) -> None:
        self.client.force_authenticate(None)
        resp = self.client.get(self.logs_url())
        self.assertIn(resp.status_code, (401, 403))

    def test_outsider_refused(self) -> None:
        self.client.force_authenticate(self.outsider)
        self.assertEqual(self.client.get(self.logs_url()).status_code, 403)

    def test_league_staff_allowed(self) -> None:
        self.client.force_authenticate(self.league_staff)
        self.assertEqual(self.client.get(self.logs_url()).status_code, 200)
