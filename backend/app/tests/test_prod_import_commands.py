from io import StringIO
from typing import Any
from unittest.mock import MagicMock, patch

from django.core.management import call_command
from django.test import TestCase

from app.management.commands import import_prod_tournament, sync_prod_users
from app.models import CustomUser, GameType, Team, Tournament
from draft.models import Draft
from league.models import League
from org.models import Organization, OrgUser, OrgUserGameMmr
from tests.populate.utils import ensure_org_user

TOURNAMENT_GET = "app.management.commands.import_prod_tournament.requests.get"
USERS_GET = "app.management.commands.sync_prod_users.requests.get"


def fake_response(payload: Any) -> MagicMock:
    response = MagicMock()
    response.json.return_value = payload
    response.raise_for_status.return_value = None
    return response


def prod_user(pk: int, discord_id: str, mmr: int | None = None) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "pk": pk,
        "username": f"prod_{pk}",
        "nickname": f"Nick {pk}",
        "avatar": None,
        "discordId": discord_id,
        "discordNickname": None,
        "steam_account_id": 1000 + pk,
        "positions": {
            "carry": 1,
            "mid": 2,
            "offlane": 3,
            "soft_support": 4,
            "hard_support": 5,
        },
    }
    if mmr is not None:
        entry.update(mmr=mmr, mmr_game_type=GameType.DOTA2)
    return entry


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


class SyncProdUsersCommandTest(TestCase):
    def run_command(self, payload: list[dict[str, Any]]) -> str:
        out = StringIO()
        with patch(USERS_GET, return_value=fake_response(payload)) as get:
            call_command("sync_prod_users", stdout=out)
        get.assert_called_once()
        self.assertEqual(get.call_args.args[0], sync_prod_users.PROD_API_URL)
        return out.getvalue()

    def test_creates_new_user_from_prod_payload(self) -> None:
        payload = [
            {
                **prod_user(11, "d11"),
                "mmr": 4000,
                "is_staff": True,
                "is_superuser": False,
            }
        ]

        output = self.run_command(payload)

        self.assertNotIn("Skipped", output)
        user = CustomUser.objects.get(discordId="d11")
        self.assertEqual(user.username, "prod_11")
        self.assertEqual(user.nickname, "Nick 11")
        self.assertEqual(user.steam_account_id, 1011)
        self.assertTrue(user.is_staff)
        self.assertEqual(user.positions.offlane, 3)


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
