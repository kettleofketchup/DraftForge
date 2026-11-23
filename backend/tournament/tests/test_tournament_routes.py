from django.test import SimpleTestCase
from django.urls import resolve


class TournamentRouteResolutionTests(SimpleTestCase):
    def test_create_team_from_captain_route(self) -> None:
        match = resolve("/api/tournaments/create-team-from-captain")
        self.assertEqual(match.func.__module__, "tournament.functions")
        self.assertEqual(match.func.cls.__module__, "tournament.functions")
        self.assertEqual(match.url_name, "create-team-from-captain")
