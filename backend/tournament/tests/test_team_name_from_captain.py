from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from app.models import CustomUser, Team, Tournament
from league.models import League
from org.models import Organization, OrgUser

URL = "/api/tournaments/create-team-from-captain"


class TeamNameFromCaptainTest(TestCase):
    def setUp(self) -> None:
        self.staff = CustomUser.objects.create_user(
            username="tnc_staff", password="x", is_staff=True
        )
        self.captain = CustomUser.objects.create_user(
            username="tnc_dragon", password="x", discordNickname="Gwaihir"
        )
        self.captain.nickname = "SiteDragon"
        self.client = APIClient()
        self.client.force_authenticate(self.staff)

    def _tournament(self, org: Organization | None, seq: int) -> Tournament:
        league = None
        if org is not None:
            league = League.objects.create(
                name=f"TNC League {seq}", organization=org, steam_league_id=77100 + seq
            )
        return Tournament.objects.create(
            name=f"TNC Cup {seq}", date_played=timezone.now(), league=league
        )

    def _team_name(self, tournament: Tournament, user: CustomUser) -> str:
        resp = self.client.post(
            URL, {"tournament_pk": tournament.pk, "user_pk": user.pk}, format="json"
        )
        self.assertEqual(resp.status_code, 201)
        return Team.objects.get(tournament=tournament, captain=user).name

    def _org(self, *, private: bool) -> Organization:
        org = Organization.objects.create(
            name=f"TNC Org {private}", members_private=private
        )
        OrgUser.objects.create(
            user=self.captain, organization=org, guild_nickname="DragonClaw"
        )
        return org

    def test_public_org_uses_server_nickname(self) -> None:
        tournament = self._tournament(self._org(private=False), 1)
        self.assertEqual(self._team_name(tournament, self.captain), "DragonClaw's Team")

    def test_private_org_uses_global_name(self) -> None:
        tournament = self._tournament(self._org(private=True), 2)
        self.assertEqual(self._team_name(tournament, self.captain), "Gwaihir's Team")

    def test_no_org_uses_global_name(self) -> None:
        tournament = self._tournament(None, 3)
        self.assertEqual(self._team_name(tournament, self.captain), "Gwaihir's Team")

    def test_site_nickname_without_global_name(self) -> None:
        self.captain.discordNickname = None
        self.captain.save()
        tournament = self._tournament(None, 5)
        self.assertEqual(self._team_name(tournament, self.captain), "SiteDragon's Team")

    def test_steam_only_captain(self) -> None:
        steam = CustomUser.objects.create(username=None, steamid=76561198000077001)
        tournament = self._tournament(None, 4)
        self.assertEqual(self._team_name(tournament, steam), f"User {steam.pk}'s Team")
