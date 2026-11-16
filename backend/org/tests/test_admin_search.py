from django.contrib import admin
from django.test import TestCase

from app.models import CustomUser, League, Organization
from app.tests.raw_site_nickname import set_raw_site_nickname
from league.models import LeagueUser
from org.models import OrgUser
from user.models import BaseUserProfile


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
            discordNickname="GlobalNick",
        )
        set_raw_site_nickname(user.pk, "SiteNick")
        org_user = OrgUser.objects.create(
            user=user, organization=org, guild_nickname="ServerNick"
        )
        LeagueUser.objects.create(user=user, org_user=org_user, league=league)

    def _assert_finds(self, url: str, term: str) -> None:
        resp = self.client.get(url, {"q": term})
        self.assertEqual(resp.status_code, 200)
        self.assertIn("admin_search_target", resp.content.decode())

    def _assert_not_finds(self, url: str, term: str) -> None:
        resp = self.client.get(url, {"q": term})
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn("admin_search_target", resp.content.decode())

    def test_org_user_admin_search(self) -> None:
        for term in ("x", "SiteNick", "GlobalNick", "ServerNick"):
            with self.subTest(term=term):
                resp = self.client.get("/admin/org/orguser/", {"q": term})
                self.assertEqual(resp.status_code, 200)
        for term in ("GlobalNick", "ServerNick"):
            with self.subTest(term=term):
                self._assert_finds("/admin/org/orguser/", term)
        self._assert_not_finds("/admin/org/orguser/", "SiteNick")

    def test_league_user_admin_search(self) -> None:
        resp = self.client.get("/admin/league/leagueuser/", {"q": "x"})
        self.assertEqual(resp.status_code, 200)
        for term in ("GlobalNick", "ServerNick"):
            with self.subTest(term=term):
                self._assert_finds("/admin/league/leagueuser/", term)
        self._assert_not_finds("/admin/league/leagueuser/", "SiteNick")

    def test_no_admin_lists_or_searches_site_nickname(self) -> None:
        for model in (OrgUser, LeagueUser, BaseUserProfile):
            model_admin = admin.site._registry[model]
            for attr in ("search_fields", "list_display"):
                with self.subTest(model=model.__name__, attr=attr):
                    fields = [str(f) for f in getattr(model_admin, attr)]
                    self.assertFalse(
                        [f for f in fields if f.split("__")[-1] == "nickname"]
                    )
