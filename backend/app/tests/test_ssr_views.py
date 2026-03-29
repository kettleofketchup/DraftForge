"""Tests for SSR meta tag endpoints."""

from django.test import TestCase
from rest_framework.test import APIClient


class SSREndpointTests(TestCase):
    """Test that SSR endpoints return lightweight data without auth."""

    def setUp(self):
        self.client = APIClient()

    def test_tournament_ssr_returns_200(self):
        from django.utils import timezone

        from app.models import Tournament

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

    def test_organization_ssr_returns_200(self):
        from app.models import Organization

        org = Organization.objects.create(name="Test Org", description="A test org")
        resp = self.client.get(f"/api/organizations/{org.pk}/ssr/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["name"], "Test Org")
        self.assertEqual(resp.data["description"], "A test org")
        self.assertNotIn("admins", resp.data)
        self.assertNotIn("staff", resp.data)

    def test_league_ssr_returns_200(self):
        from app.models import League, Organization

        org = Organization.objects.create(name="Test Org")
        league = League.objects.create(
            name="Test League", organization=org, steam_league_id=12345
        )
        resp = self.client.get(f"/api/leagues/{league.pk}/ssr/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["name"], "Test League")
        self.assertEqual(resp.data["org_name"], "Test Org")

    def test_event_ssr_returns_200(self):
        from django.utils import timezone

        from app.models import Organization
        from events.models import Event

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

    def test_user_ssr_returns_200(self):
        from app.models import CustomUser

        user = CustomUser.objects.create_user(
            username="testplayer", password="testpass123"
        )
        resp = self.client.get(f"/api/users/{user.pk}/ssr/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["username"], "testplayer")
        self.assertNotIn("email", resp.data)

    def test_tournament_ssr_with_org(self):
        from django.utils import timezone

        from app.models import League, Organization, Tournament

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

    def test_herodraft_ssr_returns_200(self):
        from django.utils import timezone

        from app.models import DraftTeam, Game, HeroDraft, Team, Tournament

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

    def test_ssr_endpoints_are_public(self):
        from django.utils import timezone

        from app.models import CustomUser, Organization, Tournament

        client = APIClient()
        org = Organization.objects.create(name="Pub Org")
        t = Tournament.objects.create(name="Pub T", date_played=timezone.now())
        user = CustomUser.objects.create_user(username="pub", password="test123")

        for url in [
            f"/api/tournaments/{t.pk}/ssr/",
            f"/api/organizations/{org.pk}/ssr/",
            f"/api/users/{user.pk}/ssr/",
        ]:
            resp = client.get(url)
            self.assertEqual(resp.status_code, 200, f"Failed for {url}")
