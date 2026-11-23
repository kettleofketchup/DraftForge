"""Tests for tournament CSV import endpoint."""

from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from app.models import CustomUser, GameType, PositionsModel
from league.models import League, LeagueUser
from org import mmr as org_mmr
from org.mmr import org_mmr_for
from org.models import Organization, OrgUser, OrgUserGameMmr
from tests.populate.utils import ensure_org_user
from tournament.models import Team, Tournament
from tournament.services.team_leadership import teams_with_leadership_problems


class TournamentCSVImportTest(TestCase):
    """Test POST /api/tournaments/{id}/import-csv/"""

    def setUp(self):
        pos = PositionsModel.objects.create()
        self.admin = CustomUser.objects.create_user(
            username="admin", password="pass", positions=pos
        )
        self.org = Organization.objects.create(name="Test Org", owner=self.admin)
        self.org.admins.add(self.admin)
        self.league = League.objects.create(
            name="Test League",
            organization=self.org,
            steam_league_id=99999,
        )
        self.tournament = Tournament.objects.create(
            name="Test Tournament",
            league=self.league,
            date_played=timezone.now(),
        )
        self.client = APIClient()
        self.client.force_authenticate(self.admin)
        self.url = f"/api/tournaments/{self.tournament.pk}/import-csv/"

    def test_import_adds_user_to_tournament(self):
        """Row with steam_friend_id adds user to tournament.users M2M."""
        pos = PositionsModel.objects.create()
        user = CustomUser.objects.create_user(
            username="player",
            password="pass",
            positions=pos,
            steamid=76561198012345678,
        )
        resp = self.client.post(
            self.url,
            {"rows": [{"steam_friend_id": "76561198012345678", "mmr": 5000}]},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["summary"]["added"], 1)
        self.assertTrue(self.tournament.users.filter(pk=user.pk).exists())
        # Also creates OrgUser with MMR
        OrgUser.objects.get(user=user, organization=self.org)
        self.assertEqual(org_mmr_for(self.org.pk, user.pk, GameType.DOTA2), 5000)

    def test_import_with_team_name_creates_team(self):
        """Row with team_name creates/assigns team."""
        pos = PositionsModel.objects.create()
        user = CustomUser.objects.create_user(
            username="player",
            password="pass",
            positions=pos,
            steamid=76561198012345678,
        )
        resp = self.client.post(
            self.url,
            {
                "rows": [
                    {
                        "steam_friend_id": "76561198012345678",
                        "mmr": 5000,
                        "team_name": "Team Alpha",
                    }
                ]
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["summary"]["added"], 1)
        team = Team.objects.get(name="Team Alpha", tournament=self.tournament)
        self.assertTrue(team.members.filter(pk=user.pk).exists())

    def test_import_same_team_name_groups_users(self):
        """Multiple rows with same team_name go to the same team."""
        pos1 = PositionsModel.objects.create()
        pos2 = PositionsModel.objects.create()
        CustomUser.objects.create_user(
            username="p1",
            password="pass",
            positions=pos1,
            steamid=76561198011111111,
        )
        CustomUser.objects.create_user(
            username="p2",
            password="pass",
            positions=pos2,
            steamid=76561198022222222,
        )
        resp = self.client.post(
            self.url,
            {
                "rows": [
                    {"steam_friend_id": "76561198011111111", "team_name": "Team Beta"},
                    {"steam_friend_id": "76561198022222222", "team_name": "Team Beta"},
                ]
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        team = Team.objects.get(name="Team Beta", tournament=self.tournament)
        self.assertEqual(team.members.count(), 2)

    def test_import_update_mmr_org_level(self):
        """update_mmr=True with mmr_target=organization updates the Dota org MMR."""
        pos = PositionsModel.objects.create()
        user = CustomUser.objects.create_user(
            username="player",
            password="pass",
            positions=pos,
            steamid=76561198012345678,
        )
        ensure_org_user(user, self.org, mmr=1000)
        self.tournament.users.add(user)

        resp = self.client.post(
            self.url,
            {
                "rows": [{"steam_friend_id": "76561198012345678", "mmr": 6000}],
                "update_mmr": True,
                "mmr_target": "organization",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["summary"]["updated"], 1)
        OrgUser.objects.get(user=user, organization=self.org)
        self.assertEqual(org_mmr_for(self.org.pk, user.pk, GameType.DOTA2), 6000)

    def test_import_update_mmr_league_level(self):
        """update_mmr=True with mmr_target=league updates LeagueUser.mmr."""
        pos = PositionsModel.objects.create()
        user = CustomUser.objects.create_user(
            username="player",
            password="pass",
            positions=pos,
            steamid=76561198012345678,
        )
        ensure_org_user(user, self.org, mmr=1000)
        self.tournament.users.add(user)

        resp = self.client.post(
            self.url,
            {
                "rows": [{"steam_friend_id": "76561198012345678", "mmr": 7000}],
                "update_mmr": True,
                "mmr_target": "league",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["summary"]["updated"], 1)
        league_user = LeagueUser.objects.get(user=user, league=self.league)
        self.assertEqual(league_user.mmr, 7000)

    def test_import_skips_existing_without_update_mmr(self):
        """Without update_mmr, existing tournament users are skipped."""
        pos = PositionsModel.objects.create()
        user = CustomUser.objects.create_user(
            username="player",
            password="pass",
            positions=pos,
            steamid=76561198012345678,
        )
        ensure_org_user(user, self.org, mmr=1000)
        self.tournament.users.add(user)

        resp = self.client.post(
            self.url,
            {
                "rows": [{"steam_friend_id": "76561198012345678", "mmr": 9000}],
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["summary"]["skipped"], 1)
        self.assertEqual(resp.data["summary"]["updated"], 0)
        OrgUser.objects.get(user=user, organization=self.org)
        self.assertEqual(
            org_mmr_for(self.org.pk, user.pk, GameType.DOTA2), 1000
        )  # Unchanged

    def test_import_requires_permission(self):
        """Non-admin user gets 403."""
        pos = PositionsModel.objects.create()
        nonadmin = CustomUser.objects.create_user(
            username="nonadmin", password="pass", positions=pos
        )
        client = APIClient()
        client.force_authenticate(nonadmin)
        resp = client.post(
            self.url,
            {"rows": [{"steam_friend_id": "76561198099999999"}]},
            format="json",
        )
        self.assertEqual(resp.status_code, 403)

    def test_import_with_captains_leaves_leadership_audit_clean(self):
        """Captains imported by CSV are members of their team (#571)."""
        for i in range(4):
            CustomUser.objects.create_user(
                username=f"audit_p{i}",
                password="pass",
                positions=PositionsModel.objects.create(),
                steamid=76561198030000000 + i,
            )
        rows = [
            {
                "steam_friend_id": str(76561198030000000 + i),
                "team_name": "Audit A" if i < 2 else "Audit B",
                "team_captain": i in (1, 2),
            }
            for i in range(4)
        ]
        resp = self.client.post(self.url, {"rows": rows}, format="json")

        self.assertEqual(resp.status_code, 200, resp.data)
        teams = Team.objects.filter(tournament=self.tournament)
        self.assertEqual(teams.exclude(captain=None).count(), 2)
        self.assertEqual(teams_with_leadership_problems(teams), [])


class TournamentCSVImportDotaRowTest(TestCase):
    def setUp(self) -> None:
        self.admin = CustomUser.objects.create_user(
            username="trow_admin", password="pass"
        )
        self.org = Organization.objects.create(name="TRow Org", owner=self.admin)
        self.org.admins.add(self.admin)
        self.league = League.objects.create(
            name="TRow League", organization=self.org, steam_league_id=99998
        )
        self.tournament = Tournament.objects.create(
            name="TRow Tournament", league=self.league, date_played=timezone.now()
        )
        self.client = APIClient()
        self.client.force_authenticate(self.admin)
        self.url = f"/api/tournaments/{self.tournament.pk}/import-csv/"
        self.user = CustomUser.objects.create_user(
            username="trow_member", password="pass", steamid=76561198012345679
        )
        self.org_user = ensure_org_user(self.user, self.org, mmr=1000)

    def dota_row(self) -> int:
        return OrgUserGameMmr.objects.get(
            org_user=self.org_user, game_type=GameType.DOTA2
        ).mmr

    def post(self, mmr: int, **extra: object) -> dict:
        resp = self.client.post(
            self.url,
            {"rows": [{"steam_friend_id": "76561198012345679", "mmr": mmr}], **extra},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        return resp.data

    def test_update_mmr_org_target_writes_dota_row(self) -> None:
        self.tournament.users.add(self.user)
        data = self.post(6000, update_mmr=True, mmr_target="organization")
        self.assertEqual(data["summary"]["updated"], 1)
        self.assertEqual(self.dota_row(), 6000)

    def test_existing_org_member_added_with_update_mmr_writes_dota_row(
        self,
    ) -> None:
        data = self.post(6500, update_mmr=True)
        self.assertEqual(data["summary"]["added"], 1)
        self.assertEqual(self.dota_row(), 6500)

    def test_existing_org_member_added_without_update_mmr_keeps_dota_row(
        self,
    ) -> None:
        data = self.post(6500)
        self.assertEqual(data["summary"]["added"], 1)
        self.assertTrue(self.tournament.users.filter(pk=self.user.pk).exists())
        self.assertEqual(self.dota_row(), 1000)

    def test_new_member_seeded_without_update_mmr(self) -> None:
        resp = self.client.post(
            self.url,
            {"rows": [{"steam_friend_id": "76561198012345690", "mmr": 4200}]},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["summary"]["added"], 1)
        new_user = CustomUser.objects.get(steamid=76561198012345690)
        self.assertEqual(org_mmr_for(self.org.pk, new_user.pk, GameType.DOTA2), 4200)

    def snapshot(self, user: CustomUser) -> int:
        return LeagueUser.objects.nocache().get(user=user, league=self.league).mmr

    def post_new(self, mmr: int | str, **extra: object) -> CustomUser:
        resp = self.client.post(
            self.url,
            {"rows": [{"steam_friend_id": "76561198012345690", "mmr": mmr}], **extra},
            format="json",
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.data["summary"]["added"], 1)
        return CustomUser.objects.get(steamid=76561198012345690)

    def test_new_member_org_target_snapshot_is_csv_mmr(self) -> None:
        new_user = self.post_new(4200, mmr_target="organization")
        self.assertEqual(org_mmr_for(self.org.pk, new_user.pk, GameType.DOTA2), 4200)
        self.assertEqual(self.snapshot(new_user), 4200)

    def test_existing_member_update_mmr_org_target_snapshot_is_new_value(
        self,
    ) -> None:
        self.post(6500, update_mmr=True, mmr_target="organization")
        self.assertEqual(self.dota_row(), 6500)
        self.assertEqual(self.snapshot(self.user), 6500)

    def test_org_target_keeps_existing_snapshot(self) -> None:
        LeagueUser.objects.create(
            user=self.user, league=self.league, org_user=self.org_user, mmr=1100
        )
        self.post(6500, update_mmr=True, mmr_target="organization")
        self.assertEqual(self.dota_row(), 6500)
        self.assertEqual(self.snapshot(self.user), 1100)

    def test_new_member_zero_mmr_org_and_snapshot_agree(self) -> None:
        for target in ("organization", "league"):
            with self.subTest(target=target):
                new_user = self.post_new(0, mmr_target=target)
                self.assertEqual(
                    org_mmr_for(self.org.pk, new_user.pk, GameType.DOTA2), 0
                )
                self.assertFalse(
                    OrgUserGameMmr.objects.filter(
                        org_user__user=new_user, game_type=GameType.DOTA2
                    ).exists()
                )
                self.assertEqual(self.snapshot(new_user), 0)
                new_user.delete()

    def test_existing_league_snapshot_kept_without_update_mmr(self) -> None:
        LeagueUser.objects.create(
            user=self.user, league=self.league, org_user=self.org_user, mmr=1100
        )
        data = self.post(6500, mmr_target="league")
        self.assertEqual(data["summary"]["added"], 1)
        self.assertEqual(
            LeagueUser.objects.get(user=self.user, league=self.league).mmr, 1100
        )
        self.assertEqual(self.dota_row(), 1000)

    def test_missing_league_snapshot_taken_from_org_without_update_mmr(
        self,
    ) -> None:
        self.post(6500, mmr_target="league")
        self.assertEqual(
            LeagueUser.objects.get(user=self.user, league=self.league).mmr, 1000
        )

    def test_existing_league_snapshot_updated_with_update_mmr(self) -> None:
        LeagueUser.objects.create(
            user=self.user, league=self.league, org_user=self.org_user, mmr=1100
        )
        data = self.post(6500, update_mmr=True, mmr_target="league")
        self.assertEqual(data["summary"]["added"], 1)
        self.assertEqual(
            LeagueUser.objects.get(user=self.user, league=self.league).mmr, 6500
        )

    def test_new_member_league_snapshot_seeded_without_update_mmr(self) -> None:
        resp = self.client.post(
            self.url,
            {
                "rows": [{"steam_friend_id": "76561198012345690", "mmr": 4200}],
                "mmr_target": "league",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        new_user = CustomUser.objects.get(steamid=76561198012345690)
        self.assertEqual(
            LeagueUser.objects.get(user=new_user, league=self.league).mmr, 4200
        )

    def test_out_of_range_for_existing_org_member_is_row_error(self) -> None:
        data = self.post(25000)
        self.assertEqual(data["summary"]["errors"], 1)
        self.assertFalse(self.tournament.users.filter(pk=self.user.pk).exists())
        self.assertEqual(self.dota_row(), 1000)


class TournamentCSVImportGameTest(TestCase):
    STEAM_ID = 76561198012345680
    NEW_STEAM_ID = 76561198012345681

    def setUp(self) -> None:
        self.admin = CustomUser.objects.create_user(
            username="tgame_admin", password="pass"
        )
        self.org = Organization.objects.create(name="TGame Org", owner=self.admin)
        self.org.admins.add(self.admin)
        self.league = League.objects.create(
            name="TGame League", organization=self.org, steam_league_id=99997
        )
        self.dl_tournament = Tournament.objects.create(
            name="TGame DL",
            league=self.league,
            date_played=timezone.now(),
            game_type=GameType.DEADLOCK,
        )
        self.dota_tournament = Tournament.objects.create(
            name="TGame Dota", league=self.league, date_played=timezone.now()
        )
        self.client = APIClient()
        self.client.force_authenticate(self.admin)
        self.user = CustomUser.objects.create_user(
            username="tgame_member", password="pass", steamid=self.STEAM_ID
        )
        self.org_user = ensure_org_user(
            self.user, self.org, mmr=1000, game_mmrs={GameType.DEADLOCK: 700}
        )

    def post(self, tournament: Tournament, rows: list[dict], **extra: object):
        return self.client.post(
            f"/api/tournaments/{tournament.pk}/import-csv/",
            {"rows": rows, **extra},
            format="json",
        )

    def rows_for(self, org_user: OrgUser) -> dict[int, int]:
        return dict(
            OrgUserGameMmr.objects.nocache()
            .filter(org_user=org_user)
            .values_list("game_type", "mmr")
        )

    def test_tournament_import_uses_tournament_game(self) -> None:
        self.dl_tournament.users.add(self.user)
        resp = self.post(
            self.dl_tournament,
            [
                {"steam_friend_id": str(self.STEAM_ID), "mmr": 2600},
                {"steam_friend_id": str(self.NEW_STEAM_ID), "mmr": 1900},
            ],
            update_mmr=True,
            game_type=GameType.DOTA2,
        )

        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.data["summary"]["updated"], 1)
        self.assertEqual(resp.data["summary"]["added"], 1)
        self.assertEqual(
            self.rows_for(self.org_user),
            {GameType.DOTA2: 1000, GameType.DEADLOCK: 2600},
        )
        new_ou = OrgUser.objects.get(
            user__steamid=self.NEW_STEAM_ID, organization=self.org
        )
        self.assertEqual(self.rows_for(new_ou), {GameType.DEADLOCK: 1900})

    def test_tournament_import_writes_org_mmrs_in_one_batch(self) -> None:
        self.dl_tournament.users.add(self.user)
        with patch(
            "tournament.views.csv_import.bulk_set_org_mmrs",
            wraps=org_mmr.bulk_set_org_mmrs,
        ) as bulk:
            resp = self.post(
                self.dl_tournament,
                [
                    {"steam_friend_id": str(self.STEAM_ID), "mmr": 2600},
                    {"steam_friend_id": str(self.NEW_STEAM_ID), "mmr": 1900},
                ],
                update_mmr=True,
            )

        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.data["summary"]["errors"], 0)
        bulk.assert_called_once()
        org_id, game, values = bulk.call_args.args
        new_user = CustomUser.objects.get(steamid=self.NEW_STEAM_ID)
        self.assertEqual(org_id, self.org.pk)
        self.assertEqual(game, GameType.DEADLOCK)
        self.assertEqual(values, {self.user.pk: 2600, new_user.pk: 1900})

    def test_tournament_import_existing_org_member_writes_tournament_game(
        self,
    ) -> None:
        resp = self.post(
            self.dl_tournament,
            [{"steam_friend_id": str(self.STEAM_ID), "mmr": 2700}],
            update_mmr=True,
        )

        self.assertEqual(resp.data["summary"]["added"], 1)
        self.assertEqual(
            self.rows_for(self.org_user),
            {GameType.DOTA2: 1000, GameType.DEADLOCK: 2700},
        )

    def test_tournament_import_without_update_mmr_keeps_tournament_game(
        self,
    ) -> None:
        resp = self.post(
            self.dl_tournament,
            [
                {"steam_friend_id": str(self.STEAM_ID), "mmr": 2700},
                {"steam_friend_id": str(self.NEW_STEAM_ID), "mmr": 1900},
            ],
        )

        self.assertEqual(resp.data["summary"]["added"], 2)
        self.assertEqual(
            self.rows_for(self.org_user),
            {GameType.DOTA2: 1000, GameType.DEADLOCK: 700},
        )
        new_ou = OrgUser.objects.get(
            user__steamid=self.NEW_STEAM_ID, organization=self.org
        )
        self.assertEqual(self.rows_for(new_ou), {GameType.DEADLOCK: 1900})

    def test_deadlock_import_does_not_seed_league_snapshot(self) -> None:
        resp = self.post(
            self.dl_tournament,
            [{"steam_friend_id": str(self.NEW_STEAM_ID), "mmr": 1900}],
        )

        self.assertEqual(resp.data["summary"]["added"], 1)
        new_user = CustomUser.objects.get(steamid=self.NEW_STEAM_ID)
        self.assertEqual(
            LeagueUser.objects.nocache().get(user=new_user, league=self.league).mmr,
            0,
        )

    def test_tournament_import_new_member_out_of_range_row_error(self) -> None:
        resp = self.post(
            self.dl_tournament,
            [{"steam_friend_id": str(self.NEW_STEAM_ID), "mmr": -1}],
        )

        self.assertEqual(resp.data["summary"]["errors"], 1)
        self.assertFalse(
            OrgUser.objects.filter(user__steamid=self.NEW_STEAM_ID).exists()
        )

    def test_tournament_import_league_target_rejected_for_deadlock(self) -> None:
        self.dl_tournament.users.add(self.user)
        LeagueUser.objects.update_or_create(
            user=self.user,
            league=self.league,
            defaults={"org_user": self.org_user, "mmr": 1000},
        )
        resp = self.post(
            self.dl_tournament,
            [{"steam_friend_id": str(self.STEAM_ID), "mmr": 7000}],
            update_mmr=True,
            mmr_target="league",
        )

        self.assertEqual(resp.status_code, 400, resp.content)
        self.assertEqual(
            LeagueUser.objects.get(user=self.user, league=self.league).mmr, 1000
        )

    def test_tournament_import_league_target_allowed_for_dota(self) -> None:
        self.dota_tournament.users.add(self.user)
        resp = self.post(
            self.dota_tournament,
            [{"steam_friend_id": str(self.STEAM_ID), "mmr": 7000}],
            update_mmr=True,
            mmr_target="league",
        )

        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(
            LeagueUser.objects.get(user=self.user, league=self.league).mmr, 7000
        )
        self.assertEqual(self.rows_for(self.org_user)[GameType.DOTA2], 1000)
