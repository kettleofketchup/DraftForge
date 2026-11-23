"""Tests for the tournament SSR meta tag endpoint."""

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from league.models import League
from org.models import Organization
from tournament.models import Tournament


class TournamentSSREndpointTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_tournament_ssr_returns_200(self):
        t = Tournament.objects.create(name="Test Tourney", date_played=timezone.now())
        resp = self.client.get(f"/api/tournaments/{t.pk}/ssr/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["name"], "Test Tourney")
        self.assertIn("pk", resp.data)
        self.assertNotIn("teams", resp.data)
        self.assertNotIn("users", resp.data)

    def test_tournament_ssr_returns_404(self):
        resp = self.client.get("/api/tournaments/99999/ssr/")
        self.assertEqual(resp.status_code, 404)

    def test_tournament_ssr_with_org(self):
        org = Organization.objects.create(
            name="Big Org", logo="https://example.com/logo.png"
        )
        league = League.objects.create(
            name="Big League", organization=org, steam_league_id=99999
        )
        t = Tournament.objects.create(
            name="Big Tourney", date_played=timezone.now(), league=league
        )
        resp = self.client.get(f"/api/tournaments/{t.pk}/ssr/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["org_name"], "Big Org")
        self.assertEqual(resp.data["org_logo"], "https://example.com/logo.png")
        self.assertEqual(resp.data["league_name"], "Big League")
