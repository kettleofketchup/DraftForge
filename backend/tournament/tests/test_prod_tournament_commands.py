from io import StringIO
from typing import Any
from unittest.mock import MagicMock, patch

from django.core.management import call_command
from django.test import TestCase

from app.models import CustomUser, GameType, Team, Tournament
from app.tests.test_prod_import_commands import fake_response, prod_user
from draft.models import Draft
from league.models import League
from org.models import Organization, OrgUser, OrgUserGameMmr
from tests.populate.utils import ensure_org_user
from tournament.management.commands import import_prod_tournament, sync_prod_tournaments

TOURNAMENT_GET = "tournament.management.commands.import_prod_tournament.requests.get"
TOURNAMENTS_GET = "tournament.management.commands.sync_prod_tournaments.requests.get"


def tournament_payload(game_type: int = GameType.DOTA2) -> dict[str, Any]:
    """Shape of GET /api/tournaments/<pk>/: user refs are pks into ``_users``."""
    return {
        "pk": 77,
        "name": "Spring Cup",
        "date_played": "2026-03-14T18:00:00Z",
        "timezone": "America/Chicago",
        "state": "past",
        "tournament_type": "double_elimination",
        "game_type": game_type,
        "users": [501, 502, 503],
        "teams": [
            {
                "pk": 901,
                "name": "Team One",
                "captain": 501,
                "deputy_captain": None,
                "members": [501, 502],
                "dropin_members": [],
                "left_members": [],
                "draft_order": 1,
            },
            {
                "pk": 902,
                "name": "Team Two",
                "captain": 503,
                "deputy_captain": None,
                "members": [503],
                "dropin_members": [],
                "left_members": [],
                "draft_order": 2,
            },
        ],
        "winning_team": 901,
        "draft": {
            "pk": 41,
            "draft_style": "snake",
            "draft_rounds": [
                {"pk": 1, "captain": 501, "choice": 502, "pick_number": 1},
                {"pk": 2, "captain": 503, "choice": None, "pick_number": 2},
            ],
        },
        "games": [
            {
                "pk": 61,
                "round": 1,
                "gameid": 123456,
                "radiant_team": {"pk": 901, "name": "Team One"},
                "dire_team": {"pk": 902, "name": "Team Two"},
                "winning_team": {"pk": 901, "name": "Team One"},
            }
        ],
        "_users": {
            "501": prod_user(501, "d501", mmr=4200),
            "502": prod_user(502, "d502", mmr=3100),
            "503": prod_user(503, "d503"),
        },
    }


def mmr_rows(org: Organization) -> dict[str | None, tuple[int, int]]:
    return {
        row["org_user__user__discordId"]: (row["game_type"], row["mmr"])
        for row in OrgUserGameMmr.objects.filter(org_user__organization=org).values(
            "org_user__user__discordId", "game_type", "mmr"
        )
    }


class ImportProdTournamentCommandTest(TestCase):
    def setUp(self) -> None:
        self.org = Organization.objects.create(name="Import Org")
        self.league = League.objects.create(organization=self.org, name="Import L")

    def run_command(self, payload: dict[str, Any], *args: str) -> str:
        out = StringIO()
        with patch(TOURNAMENT_GET, return_value=fake_response(payload)) as get:
            call_command("import_prod_tournament", "77", *args, stdout=out)
        get.assert_called_once()
        self.assertTrue(
            get.call_args.args[0].startswith(import_prod_tournament.PROD_BASE_URL)
        )
        return out.getvalue()

    def test_imports_new_users_and_writes_league_org_mmr(self) -> None:
        self.run_command(
            tournament_payload(), "--include-draft", "--league", str(self.league.pk)
        )

        tournament = Tournament.objects.get(name="Real-Spring Cup")
        self.assertEqual(tournament.league, self.league)
        self.assertEqual(tournament.users.count(), 3)
        self.assertEqual(tournament.date_played.year, 2026)
        team_one = Team.objects.get(tournament=tournament, name="Team One")
        self.assertEqual(team_one.captain.discordId, "d501")
        self.assertEqual(
            set(team_one.members.values_list("discordId", flat=True)),
            {"d501", "d502"},
        )
        self.assertEqual(tournament.winning_team, team_one)
        game = tournament.games.get()
        self.assertEqual(game.winning_team, team_one)
        draft = Draft.objects.get(tournament=tournament)
        self.assertEqual(draft.draft_rounds.count(), 2)
        self.assertEqual(
            mmr_rows(self.org),
            {"d501": (GameType.DOTA2, 4200), "d502": (GameType.DOTA2, 3100)},
        )

    def test_existing_user_keeps_their_org_mmr(self) -> None:
        existing = CustomUser.objects.create(username="local_501", discordId="d501")
        ensure_org_user(existing, self.org, mmr=2500)

        self.run_command(tournament_payload(), "--league", str(self.league.pk))

        self.assertEqual(CustomUser.objects.filter(discordId="d501").count(), 1)
        existing.refresh_from_db()
        self.assertEqual(existing.username, "local_501")
        rows = mmr_rows(self.org)
        self.assertEqual(rows["d501"], (GameType.DOTA2, 2500))
        self.assertEqual(rows["d502"], (GameType.DOTA2, 3100))

    def test_organization_option_uses_tournament_game(self) -> None:
        self.run_command(
            tournament_payload(game_type=GameType.DEADLOCK),
            "--organization",
            str(self.org.pk),
        )

        tournament = Tournament.objects.get(name="Real-Spring Cup")
        self.assertIsNone(tournament.league)
        self.assertEqual(tournament.game_type, GameType.DEADLOCK)
        self.assertEqual(
            mmr_rows(self.org),
            {"d501": (GameType.DEADLOCK, 4200), "d502": (GameType.DEADLOCK, 3100)},
        )

    def test_without_organization_creates_users_and_no_mmr(self) -> None:
        self.run_command(tournament_payload())

        self.assertEqual(
            CustomUser.objects.filter(discordId__in=["d501", "d502", "d503"]).count(),
            3,
        )
        self.assertFalse(OrgUser.objects.exists())
        self.assertFalse(OrgUserGameMmr.objects.exists())


class SyncProdTournamentsCommandTest(TestCase):
    def setUp(self) -> None:
        self.u501 = CustomUser.objects.create(username="local_501", discordId="d501")
        self.u502 = CustomUser.objects.create(username="local_502", discordId="d502")
        # matched by Steam Friend ID alone
        self.u503 = CustomUser.objects.create(
            username="local_503", steam_account_id=1503
        )

    def run_command(self, responses: dict[str, Any]) -> tuple[str, list[str]]:
        urls: list[str] = []

        def get(url: str, **kwargs: Any) -> MagicMock:
            urls.append(url)
            return fake_response(responses[url])

        out = StringIO()
        with patch(TOURNAMENTS_GET, side_effect=get):
            call_command("sync_prod_tournaments", stdout=out)
        return out.getvalue(), urls

    def test_syncs_current_payload_via_detail_users(self) -> None:
        detail = tournament_payload()
        detail["_users"]["503"] = {
            **prod_user(503, "d-other"),
            "discordId": None,
            "steam_account_id": 1503,
        }
        listed = {k: v for k, v in detail.items() if k != "_users"}
        base = sync_prod_tournaments.PROD_API_URL

        output, urls = self.run_command({base: [listed], f"{base}77/": detail})

        self.assertEqual(urls, [base, f"{base}77/"])
        self.assertNotIn("Skipped", output)
        tournament = Tournament.objects.get(name="Spring Cup")
        self.assertEqual(
            tournament.date_played.isoformat(), "2026-03-14T18:00:00+00:00"
        )
        self.assertEqual(tournament.timezone, "America/Chicago")
        self.assertEqual(set(tournament.users.all()), {self.u501, self.u502, self.u503})
        team_one = Team.objects.get(tournament=tournament, name="Team One")
        team_two = Team.objects.get(tournament=tournament, name="Team Two")
        self.assertEqual(team_one.captain, self.u501)
        self.assertEqual(set(team_one.members.all()), {self.u501, self.u502})
        self.assertEqual(team_two.captain, self.u503)
        self.assertEqual(tournament.winning_team, team_one)
        game = tournament.games.get()
        self.assertEqual(
            (game.radiant_team, game.dire_team, game.winning_team),
            (team_one, team_two, team_one),
        )
        rounds = Draft.objects.get(tournament=tournament).draft_rounds.order_by(
            "pick_number"
        )
        self.assertEqual(
            [(r.captain, r.choice) for r in rounds],
            [(self.u501, self.u502), (self.u503, None)],
        )

    def test_syncs_legacy_nested_payload_with_date_only(self) -> None:
        legacy = {
            "name": "Old Cup",
            "date_played": "2024-05-06",
            "state": "past",
            "tournament_type": "double_elimination",
            "users": [{"discordId": "d501"}, {"username": "local_502"}],
            "teams": [
                {
                    "name": "Old Team",
                    "captain": {"discordId": "d501"},
                    "members": [{"discordId": "d501"}, {"username": "local_502"}],
                }
            ],
            "games": [
                {
                    "round": 1,
                    "radiant_team": {"name": "Old Team"},
                    "winning_team": {"name": "Old Team"},
                }
            ],
        }

        output, urls = self.run_command({sync_prod_tournaments.PROD_API_URL: [legacy]})

        self.assertEqual(len(urls), 1)
        self.assertNotIn("Skipped", output)
        tournament = Tournament.objects.get(name="Old Cup")
        self.assertEqual(
            tournament.date_played.isoformat(), "2024-05-06T00:00:00+00:00"
        )
        self.assertEqual(set(tournament.users.all()), {self.u501, self.u502})
        team = Team.objects.get(tournament=tournament)
        self.assertEqual(team.captain, self.u501)
        self.assertEqual(tournament.games.get().winning_team, team)
