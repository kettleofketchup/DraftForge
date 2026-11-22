from django.test import SimpleTestCase, TestCase
from django.urls import resolve

from league import ssr, views


class LeagueRouteResolutionTests(SimpleTestCase):
    def test_league_viewset_lives_in_league(self) -> None:
        cases = {
            "/api/leagues/": "league-list",
            "/api/leagues/1/": "league-detail",
            "/api/leagues/1/matches/": "league-matches",
            "/api/leagues/1/users/": "league-users",
        }
        for path, url_name in cases.items():
            with self.subTest(path=path):
                match = resolve(path)
                self.assertIs(match.func.cls, views.LeagueView)
                self.assertEqual(match.url_name, url_name)

    def test_league_admin_team_routes_live_in_league(self) -> None:
        cases = {
            "/api/leagues/1/admins/": "add_league_admin",
            "/api/leagues/1/admins/2/": "remove_league_admin",
            "/api/leagues/1/staff/": "add_league_staff",
            "/api/leagues/1/staff/2/": "remove_league_staff",
            "/api/leagues/1/members/": "add_league_member",
        }
        for path, url_name in cases.items():
            with self.subTest(path=path):
                match = resolve(path)
                self.assertEqual(match.func.cls.__module__, "league.views_admin_team")
                self.assertEqual(match.func.cls.__name__, url_name)
                self.assertEqual(match.url_name, url_name)

    def test_league_ssr_view_lives_in_league(self) -> None:
        match = resolve("/api/leagues/1/ssr/")
        self.assertIs(match.func.view_class, ssr.LeagueSSRView)
        self.assertEqual(match.url_name, "league_ssr")


class ApiRootTests(TestCase):
    def test_api_root_lists_leagues(self) -> None:
        response = self.client.get("/api/", HTTP_HOST="localhost")
        self.assertEqual(response.status_code, 200)
        self.assertIn("leagues", response.json())
