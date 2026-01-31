"""Tests for URL-based label extraction."""

from unittest import TestCase

from telemetry.labels import extract_labels


class ExtractLabelsTest(TestCase):
    """Tests for extract_labels function."""

    def test_tournament_root(self):
        """Extract labels from /api/tournaments/{id}/"""
        result = extract_labels("/api/tournaments/5/")
        self.assertEqual(result["labels"], ["tournament"])
        self.assertEqual(result["tournament.id"], 5)

    def test_tournament_draft(self):
        """Extract labels from /api/tournaments/{id}/draft/{id}/"""
        result = extract_labels("/api/tournaments/5/draft/12/")
        self.assertEqual(result["labels"], ["tournament", "draft"])
        self.assertEqual(result["tournament.id"], 5)
        self.assertEqual(result["draft.id"], 12)

    def test_draft_root(self):
        """Extract labels from /api/drafts/{id}/"""
        result = extract_labels("/api/drafts/42/")
        self.assertEqual(result["labels"], ["draft"])
        self.assertEqual(result["draft.id"], 42)

    def test_league_standings(self):
        """Extract labels from /api/leagues/{id}/standings/"""
        result = extract_labels("/api/leagues/3/standings/")
        self.assertEqual(result["labels"], ["league", "standings"])
        self.assertEqual(result["league.id"], 3)

    def test_organization(self):
        """Extract labels from /api/organizations/{id}/"""
        result = extract_labels("/api/organizations/7/")
        self.assertEqual(result["labels"], ["organization"])
        self.assertEqual(result["organization.id"], 7)

    def test_match(self):
        """Extract labels from /api/matches/{id}/"""
        result = extract_labels("/api/matches/99/")
        self.assertEqual(result["labels"], ["match"])
        self.assertEqual(result["match.id"], 99)

    def test_users(self):
        """Extract labels from /api/users/"""
        result = extract_labels("/api/users/")
        self.assertEqual(result["labels"], ["user"])
        self.assertNotIn("user.id", result)

    def test_users_me(self):
        """Extract labels from /api/users/me/"""
        result = extract_labels("/api/users/me/")
        self.assertEqual(result["labels"], ["user"])

    def test_unknown_path(self):
        """Unknown paths return empty dict."""
        result = extract_labels("/api/unknown/path/")
        self.assertEqual(result, {})

    def test_nested_resources(self):
        """Deeply nested paths extract all labels."""
        result = extract_labels("/api/leagues/1/tournaments/2/games/3/")
        self.assertEqual(result["labels"], ["league", "tournament", "game"])
        self.assertEqual(result["league.id"], 1)
        self.assertEqual(result["tournament.id"], 2)
        self.assertEqual(result["game.id"], 3)

    def test_games(self):
        """Extract labels from /api/games/{id}/"""
        result = extract_labels("/api/games/15/")
        self.assertEqual(result["labels"], ["game"])
        self.assertEqual(result["game.id"], 15)

    def test_teams(self):
        """Extract labels from /api/teams/{id}/"""
        result = extract_labels("/api/teams/8/")
        self.assertEqual(result["labels"], ["team"])
        self.assertEqual(result["team.id"], 8)

    def test_non_api_path(self):
        """Non-API paths return empty dict."""
        result = extract_labels("/static/css/style.css")
        self.assertEqual(result, {})

    # WebSocket path tests (CRITICAL FIX #7)
    def test_websocket_draft_singular(self):
        """Extract labels from WebSocket /draft/{id}/ path."""
        result = extract_labels("/draft/5/")
        self.assertEqual(result["labels"], ["draft"])
        self.assertEqual(result["draft.id"], 5)

    def test_websocket_tournament_singular(self):
        """Extract labels from WebSocket /tournament/{id}/ path."""
        result = extract_labels("/tournament/10/")
        self.assertEqual(result["labels"], ["tournament"])
        self.assertEqual(result["tournament.id"], 10)
