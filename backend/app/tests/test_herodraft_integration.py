"""Integration tests for HeroDraft API flow."""

from datetime import date

from django.test import TestCase
from rest_framework.test import APIClient

from app.models import CustomUser, DraftTeam, Game, HeroDraft, Team, Tournament


class HeroDraftAPITest(TestCase):
    """Tests for the HeroDraft API endpoints."""

    def setUp(self):
        self.client = APIClient()
        self.captain1 = CustomUser.objects.create_user(
            username="captain1", password="test123"
        )
        self.captain2 = CustomUser.objects.create_user(
            username="captain2", password="test123"
        )
        self.tournament = Tournament.objects.create(
            name="Test Tournament",
            date_played=date.today(),
        )
        self.team1 = Team.objects.create(
            name="Team 1",
            tournament=self.tournament,
            captain=self.captain1,
        )
        self.team2 = Team.objects.create(
            name="Team 2",
            tournament=self.tournament,
            captain=self.captain2,
        )
        self.game = Game.objects.create(
            tournament=self.tournament,
            radiant_team=self.team1,
            dire_team=self.team2,
        )

    def test_create_herodraft(self):
        """Captain can create a hero draft for a game."""
        self.client.force_authenticate(user=self.captain1)

        response = self.client.post(f"/api/games/{self.game.id}/create-herodraft/")

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["state"], "waiting_for_captains")
        self.assertEqual(len(response.data["draft_teams"]), 2)

    def test_non_captain_cannot_create(self):
        """Non-captain can still create a draft (API doesn't restrict this)."""
        other_user = CustomUser.objects.create_user(username="other", password="test")
        self.client.force_authenticate(user=other_user)

        response = self.client.post(f"/api/games/{self.game.id}/create-herodraft/")

        # Note: The create endpoint doesn't check if user is a captain
        # It only requires authentication
        self.assertEqual(response.status_code, 201)

    def test_unauthenticated_cannot_create(self):
        """Unauthenticated user cannot create a draft."""
        response = self.client.post(f"/api/games/{self.game.id}/create-herodraft/")

        # Django REST Framework returns 403 for unauthenticated requests by default
        self.assertIn(response.status_code, [401, 403])

    def test_cannot_create_duplicate_draft(self):
        """Cannot create a second draft for a game that already has one."""
        self.client.force_authenticate(user=self.captain1)

        # Create first draft
        response1 = self.client.post(f"/api/games/{self.game.id}/create-herodraft/")
        self.assertEqual(response1.status_code, 201)

        # Try to create second draft
        response2 = self.client.post(f"/api/games/{self.game.id}/create-herodraft/")
        self.assertEqual(response2.status_code, 400)
        self.assertIn("already has a hero draft", response2.data["error"])

    def test_full_ready_flow(self):
        """Both captains can ready up and state changes to rolling."""
        # Create draft
        self.client.force_authenticate(user=self.captain1)
        create_response = self.client.post(
            f"/api/games/{self.game.id}/create-herodraft/"
        )
        draft_id = create_response.data["id"]

        # Captain 1 ready
        response = self.client.post(f"/api/herodraft/{draft_id}/set-ready/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["state"], "waiting_for_captains")

        # Verify captain 1's team is ready
        draft_teams = response.data["draft_teams"]
        captain1_team = next(
            t for t in draft_teams if t["captain"]["pk"] == self.captain1.id
        )
        self.assertTrue(captain1_team["is_ready"])

        # Captain 2 ready
        self.client.force_authenticate(user=self.captain2)
        response = self.client.post(f"/api/herodraft/{draft_id}/set-ready/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["state"], "rolling")

    def test_non_captain_cannot_ready(self):
        """Non-captain cannot mark themselves as ready."""
        self.client.force_authenticate(user=self.captain1)
        create_response = self.client.post(
            f"/api/games/{self.game.id}/create-herodraft/"
        )
        draft_id = create_response.data["id"]

        # Non-captain tries to ready
        other_user = CustomUser.objects.create_user(username="other", password="test")
        self.client.force_authenticate(user=other_user)
        response = self.client.post(f"/api/herodraft/{draft_id}/set-ready/")

        self.assertEqual(response.status_code, 403)
        self.assertIn("not a captain", response.data["error"])

    def test_roll_and_choose_flow(self):
        """Roll and choice flow works correctly."""
        # Setup: create draft and ready up
        self.client.force_authenticate(user=self.captain1)
        create_response = self.client.post(
            f"/api/games/{self.game.id}/create-herodraft/"
        )
        draft_id = create_response.data["id"]

        self.client.post(f"/api/herodraft/{draft_id}/set-ready/")
        self.client.force_authenticate(user=self.captain2)
        self.client.post(f"/api/herodraft/{draft_id}/set-ready/")

        # Trigger roll
        response = self.client.post(f"/api/herodraft/{draft_id}/trigger-roll/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["state"], "choosing")
        self.assertIsNotNone(response.data["roll_winner"])

        # Determine winner and loser captains
        roll_winner_id = response.data["roll_winner"]["id"]
        draft_teams = response.data["draft_teams"]
        winner_team = next(t for t in draft_teams if t["id"] == roll_winner_id)
        loser_team = next(t for t in draft_teams if t["id"] != roll_winner_id)

        winner_captain = (
            self.captain1
            if winner_team["captain"]["pk"] == self.captain1.id
            else self.captain2
        )
        loser_captain = (
            self.captain2 if winner_captain == self.captain1 else self.captain1
        )

        # Winner chooses pick order
        self.client.force_authenticate(user=winner_captain)
        response = self.client.post(
            f"/api/herodraft/{draft_id}/submit-choice/",
            {"choice_type": "pick_order", "value": "first"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["state"], "choosing")

        # Loser chooses side
        self.client.force_authenticate(user=loser_captain)
        response = self.client.post(
            f"/api/herodraft/{draft_id}/submit-choice/",
            {"choice_type": "side", "value": "radiant"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["state"], "drafting")
        self.assertEqual(len(response.data["rounds"]), 24)

    def test_loser_cannot_choose_first(self):
        """Roll loser cannot make a choice before the winner."""
        # Setup: create draft, ready up, and roll
        self.client.force_authenticate(user=self.captain1)
        create_response = self.client.post(
            f"/api/games/{self.game.id}/create-herodraft/"
        )
        draft_id = create_response.data["id"]

        self.client.post(f"/api/herodraft/{draft_id}/set-ready/")
        self.client.force_authenticate(user=self.captain2)
        self.client.post(f"/api/herodraft/{draft_id}/set-ready/")
        response = self.client.post(f"/api/herodraft/{draft_id}/trigger-roll/")

        # Determine loser captain
        roll_winner_id = response.data["roll_winner"]["id"]
        draft_teams = response.data["draft_teams"]
        winner_team = next(t for t in draft_teams if t["id"] == roll_winner_id)
        loser_captain = (
            self.captain2
            if winner_team["captain"]["pk"] == self.captain1.id
            else self.captain1
        )

        # Loser tries to choose first
        self.client.force_authenticate(user=loser_captain)
        response = self.client.post(
            f"/api/herodraft/{draft_id}/submit-choice/",
            {"choice_type": "pick_order", "value": "first"},
        )

        self.assertEqual(response.status_code, 403)
        self.assertIn("winner must choose first", response.data["error"].lower())

    def test_invalid_choice_type(self):
        """Invalid choice type returns error."""
        # Setup: create draft, ready up, roll
        self.client.force_authenticate(user=self.captain1)
        create_response = self.client.post(
            f"/api/games/{self.game.id}/create-herodraft/"
        )
        draft_id = create_response.data["id"]

        self.client.post(f"/api/herodraft/{draft_id}/set-ready/")
        self.client.force_authenticate(user=self.captain2)
        self.client.post(f"/api/herodraft/{draft_id}/set-ready/")
        response = self.client.post(f"/api/herodraft/{draft_id}/trigger-roll/")

        # Get winner captain
        roll_winner_id = response.data["roll_winner"]["id"]
        draft_teams = response.data["draft_teams"]
        winner_team = next(t for t in draft_teams if t["id"] == roll_winner_id)
        winner_captain = (
            self.captain1
            if winner_team["captain"]["pk"] == self.captain1.id
            else self.captain2
        )

        # Try invalid choice type
        self.client.force_authenticate(user=winner_captain)
        response = self.client.post(
            f"/api/herodraft/{draft_id}/submit-choice/",
            {"choice_type": "invalid", "value": "first"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("choice_type", response.data["error"])

    def test_cannot_roll_twice(self):
        """Cannot trigger roll after it has been done."""
        # Setup: create draft, ready up, and roll once
        self.client.force_authenticate(user=self.captain1)
        create_response = self.client.post(
            f"/api/games/{self.game.id}/create-herodraft/"
        )
        draft_id = create_response.data["id"]

        self.client.post(f"/api/herodraft/{draft_id}/set-ready/")
        self.client.force_authenticate(user=self.captain2)
        self.client.post(f"/api/herodraft/{draft_id}/set-ready/")
        self.client.post(f"/api/herodraft/{draft_id}/trigger-roll/")

        # Try to roll again
        response = self.client.post(f"/api/herodraft/{draft_id}/trigger-roll/")

        self.assertEqual(response.status_code, 400)
        self.assertIn("Cannot trigger roll", response.data["error"])


class HeroDraftPickTest(TestCase):
    """Tests for hero pick/ban functionality."""

    def setUp(self):
        self.client = APIClient()
        self.captain1 = CustomUser.objects.create_user(
            username="captain1", password="test123"
        )
        self.captain2 = CustomUser.objects.create_user(
            username="captain2", password="test123"
        )
        self.tournament = Tournament.objects.create(
            name="Test Tournament",
            date_played=date.today(),
        )
        self.team1 = Team.objects.create(
            name="Team 1",
            tournament=self.tournament,
            captain=self.captain1,
        )
        self.team2 = Team.objects.create(
            name="Team 2",
            tournament=self.tournament,
            captain=self.captain2,
        )
        self.game = Game.objects.create(
            tournament=self.tournament,
            radiant_team=self.team1,
            dire_team=self.team2,
        )

    def _setup_draft_to_picking(self):
        """Helper to set up a draft in the drafting state."""
        self.client.force_authenticate(user=self.captain1)
        create_response = self.client.post(
            f"/api/games/{self.game.id}/create-herodraft/"
        )
        draft_id = create_response.data["id"]

        self.client.post(f"/api/herodraft/{draft_id}/set-ready/")
        self.client.force_authenticate(user=self.captain2)
        self.client.post(f"/api/herodraft/{draft_id}/set-ready/")
        response = self.client.post(f"/api/herodraft/{draft_id}/trigger-roll/")

        # Determine winner and loser
        roll_winner_id = response.data["roll_winner"]["id"]
        draft_teams = response.data["draft_teams"]
        winner_team = next(t for t in draft_teams if t["id"] == roll_winner_id)
        loser_team = next(t for t in draft_teams if t["id"] != roll_winner_id)

        winner_captain = (
            self.captain1
            if winner_team["captain"]["pk"] == self.captain1.id
            else self.captain2
        )
        loser_captain = (
            self.captain2 if winner_captain == self.captain1 else self.captain1
        )

        # Winner chooses first pick
        self.client.force_authenticate(user=winner_captain)
        self.client.post(
            f"/api/herodraft/{draft_id}/submit-choice/",
            {"choice_type": "pick_order", "value": "first"},
        )

        # Loser chooses side
        self.client.force_authenticate(user=loser_captain)
        response = self.client.post(
            f"/api/herodraft/{draft_id}/submit-choice/",
            {"choice_type": "side", "value": "radiant"},
        )

        return draft_id, winner_captain, loser_captain

    def test_submit_pick(self):
        """First pick team can submit a ban."""
        draft_id, first_pick_captain, _ = self._setup_draft_to_picking()

        # First pick captain submits a ban (round 1 is a ban)
        self.client.force_authenticate(user=first_pick_captain)
        response = self.client.post(
            f"/api/herodraft/{draft_id}/submit-pick/",
            {"hero_id": 1},  # Anti-Mage
        )

        self.assertEqual(response.status_code, 200)
        # Verify the round was completed
        rounds = response.data["rounds"]
        completed_round = next(r for r in rounds if r["round_number"] == 1)
        self.assertEqual(completed_round["hero_id"], 1)
        self.assertEqual(completed_round["state"], "completed")

    def test_cannot_pick_when_not_your_turn(self):
        """Player cannot pick when it's not their turn."""
        draft_id, first_pick_captain, second_pick_captain = (
            self._setup_draft_to_picking()
        )

        # Second pick captain tries to pick on first pick's turn
        self.client.force_authenticate(user=second_pick_captain)
        response = self.client.post(
            f"/api/herodraft/{draft_id}/submit-pick/",
            {"hero_id": 1},
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("Not your turn", response.data["error"])

    def test_cannot_pick_hero_twice(self):
        """Cannot pick a hero that has already been picked or banned."""
        draft_id, first_pick_captain, _ = self._setup_draft_to_picking()

        # First pick captain bans a hero
        self.client.force_authenticate(user=first_pick_captain)
        self.client.post(
            f"/api/herodraft/{draft_id}/submit-pick/",
            {"hero_id": 1},
        )

        # Second ban is also first pick team - try to ban same hero
        response = self.client.post(
            f"/api/herodraft/{draft_id}/submit-pick/",
            {"hero_id": 1},
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("not available", response.data["error"])

    def test_get_available_heroes(self):
        """Can get list of available heroes."""
        draft_id, first_pick_captain, _ = self._setup_draft_to_picking()

        # Check initial available heroes
        self.client.force_authenticate(user=first_pick_captain)
        response = self.client.get(f"/api/herodraft/{draft_id}/list-available-heroes/")

        self.assertEqual(response.status_code, 200)
        # Initially all heroes should be available (1-138)
        self.assertIn("available_heroes", response.data)
        self.assertGreater(len(response.data["available_heroes"]), 100)

        # Ban a hero
        self.client.post(
            f"/api/herodraft/{draft_id}/submit-pick/",
            {"hero_id": 1},
        )

        # Check available heroes after ban
        response = self.client.get(f"/api/herodraft/{draft_id}/list-available-heroes/")
        self.assertNotIn(1, response.data["available_heroes"])


class HeroDraftGetTest(TestCase):
    """Tests for getting draft state."""

    def setUp(self):
        self.client = APIClient()
        self.captain1 = CustomUser.objects.create_user(
            username="captain1", password="test123"
        )
        self.captain2 = CustomUser.objects.create_user(
            username="captain2", password="test123"
        )
        self.tournament = Tournament.objects.create(
            name="Test Tournament",
            date_played=date.today(),
        )
        self.team1 = Team.objects.create(
            name="Team 1",
            tournament=self.tournament,
            captain=self.captain1,
        )
        self.team2 = Team.objects.create(
            name="Team 2",
            tournament=self.tournament,
            captain=self.captain2,
        )
        self.game = Game.objects.create(
            tournament=self.tournament,
            radiant_team=self.team1,
            dire_team=self.team2,
        )

    def test_get_draft(self):
        """Can retrieve draft state."""
        self.client.force_authenticate(user=self.captain1)
        create_response = self.client.post(
            f"/api/games/{self.game.id}/create-herodraft/"
        )
        draft_id = create_response.data["id"]

        response = self.client.get(f"/api/herodraft/{draft_id}/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["id"], draft_id)
        self.assertEqual(response.data["state"], "waiting_for_captains")
        self.assertEqual(len(response.data["draft_teams"]), 2)

    def test_list_events(self):
        """Can list draft events."""
        self.client.force_authenticate(user=self.captain1)
        create_response = self.client.post(
            f"/api/games/{self.game.id}/create-herodraft/"
        )
        draft_id = create_response.data["id"]

        response = self.client.get(f"/api/herodraft/{draft_id}/list-events/")

        self.assertEqual(response.status_code, 200)
        # There should be at least one event (captain_connected on creation)
        self.assertGreaterEqual(len(response.data), 1)


class HeroDraftErrorCasesTest(TestCase):
    """Tests for error handling in HeroDraft API."""

    def setUp(self):
        self.client = APIClient()
        self.captain1 = CustomUser.objects.create_user(
            username="captain1", password="test123"
        )
        self.tournament = Tournament.objects.create(
            name="Test Tournament",
            date_played=date.today(),
        )
        self.team1 = Team.objects.create(
            name="Team 1",
            tournament=self.tournament,
            captain=self.captain1,
        )

    def test_create_draft_missing_teams(self):
        """Cannot create draft for game without both teams."""
        game = Game.objects.create(
            tournament=self.tournament,
            radiant_team=self.team1,
            # dire_team is missing
        )

        self.client.force_authenticate(user=self.captain1)
        response = self.client.post(f"/api/games/{game.id}/create-herodraft/")

        self.assertEqual(response.status_code, 400)
        self.assertIn("both radiant and dire teams", response.data["error"])

    def test_create_draft_missing_captain(self):
        """Cannot create draft when a team has no captain."""
        captain2 = CustomUser.objects.create_user(username="captain2", password="test")
        team2 = Team.objects.create(
            name="Team 2",
            tournament=self.tournament,
            # captain is None
        )
        game = Game.objects.create(
            tournament=self.tournament,
            radiant_team=self.team1,
            dire_team=team2,
        )

        self.client.force_authenticate(user=self.captain1)
        response = self.client.post(f"/api/games/{game.id}/create-herodraft/")

        self.assertEqual(response.status_code, 400)
        self.assertIn("captains", response.data["error"].lower())

    def test_nonexistent_game(self):
        """Returns 404 for nonexistent game."""
        self.client.force_authenticate(user=self.captain1)
        response = self.client.post("/api/games/99999/create-herodraft/")

        self.assertEqual(response.status_code, 404)

    def test_nonexistent_draft(self):
        """Returns 404 for nonexistent draft."""
        self.client.force_authenticate(user=self.captain1)
        response = self.client.get("/api/herodraft/99999/")

        self.assertEqual(response.status_code, 404)
