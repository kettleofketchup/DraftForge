from django.test import TestCase

from app.models import CustomUser, League
from league.models import LeagueUser
from org.models import Organization, OrgUser


class AdminSearchFieldsTest(TestCase):
    def setUp(self) -> None:
        self.superuser = CustomUser.objects.create_superuser(
            username="search_admin", password="x", email="sa@example.com"
        )
        self.client.force_login(self.superuser)
        org = Organization.objects.create(name="Admin Search Org")
        league = League.objects.create(
            name="Admin Search League", organization=org, steam_league_id=88301
        )
        user = CustomUser.objects.create_user(
            username="admin_search_target",
            password="x",
            nickname="SiteNick",
            discordNickname="GlobalNick",
        )
        org_user = OrgUser.objects.create(
            user=user, organization=org, guild_nickname="ServerNick"
        )
        LeagueUser.objects.create(user=user, org_user=org_user, league=league)

    def _assert_finds(self, url: str, term: str) -> None:
        resp = self.client.get(url, {"q": term})
        self.assertEqual(resp.status_code, 200)
        self.assertIn("admin_search_target", resp.content.decode())

    def test_org_user_admin_search(self) -> None:
        for term in ("x", "SiteNick", "GlobalNick", "ServerNick"):
            with self.subTest(term=term):
                resp = self.client.get("/admin/org/orguser/", {"q": term})
                self.assertEqual(resp.status_code, 200)
        for term in ("SiteNick", "GlobalNick", "ServerNick"):
            with self.subTest(term=term):
                self._assert_finds("/admin/org/orguser/", term)

    def test_league_user_admin_search(self) -> None:
        resp = self.client.get("/admin/league/leagueuser/", {"q": "x"})
        self.assertEqual(resp.status_code, 200)
        for term in ("SiteNick", "GlobalNick", "ServerNick"):
            with self.subTest(term=term):
                self._assert_finds("/admin/league/leagueuser/", term)
