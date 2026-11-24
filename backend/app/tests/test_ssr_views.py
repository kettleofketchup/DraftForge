"""Tests for SSR meta tag endpoints."""

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from draft.models import DraftTeam, HeroDraft
from events.models import Event
from league.models import League
from org.models import Organization
from tournament.models import Game, Team, Tournament


class NonUserSSREndpointTests(TestCase):
    """Test that SSR endpoints return lightweight data without auth."""

    def setUp(self):
        self.client = APIClient()

    def test_league_ssr_returns_200(self):
        org = Organization.objects.create(name="Test Org")
        league = League.objects.create(
            name="Test League", organization=org, steam_league_id=12345
        )
        resp = self.client.get(f"/api/leagues/{league.pk}/ssr/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["name"], "Test League")
        self.assertEqual(resp.data["org_name"], "Test Org")

    def test_event_ssr_returns_200(self):
        org = Organization.objects.create(name="Test Org")
        event = Event.objects.create(
            name="Test Event",
            organization=org,
            scheduled_at=timezone.now(),
        )
        resp = self.client.get(f"/api/events/{event.pk}/ssr/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["name"], "Test Event")
        self.assertEqual(resp.data["org_name"], "Test Org")

    def test_herodraft_ssr_returns_200(self):
        t = Tournament.objects.create(name="Draft Tourney", date_played=timezone.now())
        game = Game.objects.create(tournament=t, round=1)
        draft = HeroDraft.objects.create(game=game)
        team1 = Team.objects.create(name="Team Alpha", tournament=t)
        team2 = Team.objects.create(name="Team Beta", tournament=t)
        DraftTeam.objects.create(draft=draft, tournament_team=team1)
        DraftTeam.objects.create(draft=draft, tournament_team=team2)
        resp = self.client.get(f"/api/herodraft/{draft.pk}/ssr/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["tournament_name"], "Draft Tourney")
        self.assertEqual(resp.data["team_names"], ["Team Alpha", "Team Beta"])

    def test_ssr_endpoints_are_public(self) -> None:
        client = APIClient()
        org = Organization.objects.create(name="Pub Org")
        t = Tournament.objects.create(name="Pub T", date_played=timezone.now())

        for url in [
            f"/api/tournaments/{t.pk}/ssr/",
            f"/api/organizations/{org.pk}/ssr/",
        ]:
            resp = client.get(url)
            self.assertEqual(resp.status_code, 200, f"Failed for {url}")
