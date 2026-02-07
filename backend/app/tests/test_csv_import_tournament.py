"""Tests for tournament CSV import endpoint."""

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from app.models import (
    CustomUser,
    League,
    Organization,
    PositionsModel,
    Team,
    Tournament,
)
from org.models import OrgUser


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
            {"rows": [{"steam_friend_id": "76561198012345678", "base_mmr": 5000}]},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["summary"]["added"], 1)
        self.assertTrue(self.tournament.users.filter(pk=user.pk).exists())
        # Also creates OrgUser with MMR
        org_user = OrgUser.objects.get(user=user, organization=self.org)
        self.assertEqual(org_user.mmr, 5000)

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
                        "base_mmr": 5000,
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
        u1 = CustomUser.objects.create_user(
            username="p1",
            password="pass",
            positions=pos1,
            steamid=76561198011111111,
        )
        u2 = CustomUser.objects.create_user(
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
