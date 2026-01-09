# Bracket Save + Team Placement Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement bracket persistence and automatic team placement tracking for double elimination tournaments.

**Architecture:** Frontend generates bracket structure, sends to `save_bracket` endpoint which persists as `Game` records. When `advance_winner` is called and a team is eliminated (no loser path), their placement is auto-calculated based on bracket position.

**Tech Stack:** Django REST Framework, SQLite, Zustand (frontend state)

**Worktree:** `/home/kettle/git_repos/website/.worktrees/bracket-save-placement`

**Test Command:** `docker exec backend python /app/backend/manage.py test app.tests.test_bracket -v 2`

---

## Task 1: Add Placement Field to Team Model

**Files:**
- Modify: `backend/app/models.py:297` (after `current_points` field)
- Create: `backend/app/migrations/0047_team_placement.py` (auto-generated)

**Step 1: Add the placement field**

In `backend/app/models.py`, after line 297 (`current_points = models.IntegerField(...)`), add:

```python
    placement = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        help_text="Final tournament placement (1=winner, 2=runner-up, etc.)",
    )
```

**Step 2: Generate migration**

```bash
docker exec backend python /app/backend/manage.py makemigrations app --name team_placement
```

Expected: Creates migration file `0047_team_placement.py`

**Step 3: Apply migration**

```bash
docker exec backend python /app/backend/manage.py migrate
```

Expected: `Applying app.0047_team_placement... OK`

**Step 4: Commit**

```bash
cd /home/kettle/git_repos/website/.worktrees/bracket-save-placement
git add backend/app/models.py backend/app/migrations/
git commit -m "feat: add placement field to Team model"
```

---

## Task 2: Create Bracket Test File with Save Tests

**Files:**
- Create: `backend/app/tests/test_bracket.py`

**Step 1: Create test file with save_bracket tests**

Create `backend/app/tests/test_bracket.py`:

```python
"""Tests for bracket save and team placement functionality."""

from datetime import date

from django.test import TestCase
from rest_framework.test import APIClient

from app.models import CustomUser, Game, Team, Tournament


class SaveBracketTest(TestCase):
    """Test save_bracket endpoint."""

    def setUp(self):
        """Create test data."""
        self.admin = CustomUser.objects.create_superuser(
            username="admin",
            password="admin123",
            email="admin@test.com",
        )
        self.tournament = Tournament.objects.create(
            name="Test Tournament",
            date_played=date.today(),
        )
        # Create 4 teams
        self.teams = []
        for i in range(4):
            captain = CustomUser.objects.create_user(
                username=f"captain{i}",
                password="test123",
                mmr=5000 - (i * 100),
            )
            team = Team.objects.create(
                name=f"Team {i+1}",
                captain=captain,
                tournament=self.tournament,
            )
            self.teams.append(team)

        self.client = APIClient()
        self.client.force_authenticate(user=self.admin)

    def test_save_bracket_creates_games(self):
        """Save bracket creates Game records for each match."""
        matches = [
            {
                "id": "w-1-0",
                "round": 1,
                "position": 0,
                "bracketType": "winners",
                "eliminationType": "double",
                "radiantTeam": {"pk": self.teams[0].pk},
                "direTeam": {"pk": self.teams[3].pk},
                "status": "pending",
                "nextMatchId": "w-2-0",
                "nextMatchSlot": "radiant",
                "loserNextMatchId": "l-1-0",
                "loserNextMatchSlot": "radiant",
            },
            {
                "id": "w-1-1",
                "round": 1,
                "position": 1,
                "bracketType": "winners",
                "eliminationType": "double",
                "radiantTeam": {"pk": self.teams[1].pk},
                "direTeam": {"pk": self.teams[2].pk},
                "status": "pending",
                "nextMatchId": "w-2-0",
                "nextMatchSlot": "dire",
                "loserNextMatchId": "l-1-0",
                "loserNextMatchSlot": "dire",
            },
            {
                "id": "w-2-0",
                "round": 2,
                "position": 0,
                "bracketType": "winners",
                "eliminationType": "double",
                "status": "pending",
                "nextMatchId": "gf-1-0",
                "nextMatchSlot": "radiant",
                "loserNextMatchId": "l-2-0",
                "loserNextMatchSlot": "dire",
            },
            {
                "id": "l-1-0",
                "round": 1,
                "position": 0,
                "bracketType": "losers",
                "eliminationType": "double",
                "status": "pending",
                "nextMatchId": "l-2-0",
                "nextMatchSlot": "radiant",
            },
            {
                "id": "l-2-0",
                "round": 2,
                "position": 0,
                "bracketType": "losers",
                "eliminationType": "double",
                "status": "pending",
                "nextMatchId": "gf-1-0",
                "nextMatchSlot": "dire",
            },
            {
                "id": "gf-1-0",
                "round": 1,
                "position": 0,
                "bracketType": "grand_finals",
                "eliminationType": "double",
                "status": "pending",
            },
        ]

        response = self.client.post(
            f"/api/bracket/tournaments/{self.tournament.pk}/save/",
            {"matches": matches},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Game.objects.filter(tournament=self.tournament).count(), 6)

    def test_save_bracket_wires_next_game_relationships(self):
        """Save bracket correctly sets next_game foreign keys."""
        matches = [
            {
                "id": "w-1-0",
                "round": 1,
                "position": 0,
                "bracketType": "winners",
                "eliminationType": "double",
                "status": "pending",
                "nextMatchId": "w-2-0",
                "nextMatchSlot": "radiant",
            },
            {
                "id": "w-2-0",
                "round": 2,
                "position": 0,
                "bracketType": "winners",
                "eliminationType": "double",
                "status": "pending",
            },
        ]

        self.client.post(
            f"/api/bracket/tournaments/{self.tournament.pk}/save/",
            {"matches": matches},
            format="json",
        )

        game_w1 = Game.objects.get(
            tournament=self.tournament, bracket_type="winners", round=1, position=0
        )
        game_w2 = Game.objects.get(
            tournament=self.tournament, bracket_type="winners", round=2, position=0
        )

        self.assertEqual(game_w1.next_game, game_w2)
        self.assertEqual(game_w1.next_game_slot, "radiant")

    def test_save_bracket_clears_existing_bracket_games(self):
        """Save bracket deletes existing bracket games before creating new ones."""
        # Create an existing game
        Game.objects.create(
            tournament=self.tournament,
            round=1,
            position=0,
            bracket_type="winners",
        )
        self.assertEqual(Game.objects.filter(tournament=self.tournament).count(), 1)

        # Save new bracket
        matches = [
            {
                "id": "w-1-0",
                "round": 1,
                "position": 0,
                "bracketType": "winners",
                "eliminationType": "double",
                "status": "pending",
            },
            {
                "id": "w-1-1",
                "round": 1,
                "position": 1,
                "bracketType": "winners",
                "eliminationType": "double",
                "status": "pending",
            },
        ]

        self.client.post(
            f"/api/bracket/tournaments/{self.tournament.pk}/save/",
            {"matches": matches},
            format="json",
        )

        # Should have 2 games (old one deleted, 2 new created)
        self.assertEqual(Game.objects.filter(tournament=self.tournament).count(), 2)

    def test_save_bracket_returns_games_with_pks(self):
        """Save bracket returns games with database PKs."""
        matches = [
            {
                "id": "w-1-0",
                "round": 1,
                "position": 0,
                "bracketType": "winners",
                "eliminationType": "double",
                "status": "pending",
            },
        ]

        response = self.client.post(
            f"/api/bracket/tournaments/{self.tournament.pk}/save/",
            {"matches": matches},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("matches", response.data)
        self.assertEqual(len(response.data["matches"]), 1)
        self.assertIn("pk", response.data["matches"][0])

    def test_save_bracket_requires_admin(self):
        """Save bracket requires admin permission."""
        regular_user = CustomUser.objects.create_user(
            username="regular",
            password="test123",
        )
        self.client.force_authenticate(user=regular_user)

        response = self.client.post(
            f"/api/bracket/tournaments/{self.tournament.pk}/save/",
            {"matches": []},
            format="json",
        )

        self.assertEqual(response.status_code, 403)
```

**Step 2: Run tests to verify they fail**

```bash
docker exec backend python /app/backend/manage.py test app.tests.test_bracket -v 2
```

Expected: Tests fail (save_bracket not implemented)

**Step 3: Commit test file**

```bash
cd /home/kettle/git_repos/website/.worktrees/bracket-save-placement
git add backend/app/tests/test_bracket.py
git commit -m "test: add save_bracket tests (red)"
```

---

## Task 3: Implement save_bracket Endpoint

**Files:**
- Modify: `backend/app/views/bracket.py:66-84`

**Step 1: Replace save_bracket stub with implementation**

Replace the entire `save_bracket` function in `backend/app/views/bracket.py` (lines 66-84) with:

```python
@api_view(["POST"])
@permission_classes([IsAdminUser])
@transaction.atomic
def save_bracket(request, tournament_id):
    """Save bracket structure to database."""
    try:
        tournament = Tournament.objects.get(pk=tournament_id)
    except Tournament.DoesNotExist:
        return Response(
            {"error": "Tournament not found"}, status=status.HTTP_404_NOT_FOUND
        )

    serializer = BracketSaveSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    matches = serializer.validated_data["matches"]

    # Delete existing bracket games for this tournament
    Game.objects.filter(tournament=tournament).delete()

    # Pass 1: Create all games without FK relationships
    # Map frontend ID -> database PK
    id_to_game = {}

    for match in matches:
        game = Game.objects.create(
            tournament=tournament,
            round=match.get("round", 1),
            position=match.get("position", 0),
            bracket_type=match.get("bracketType", "winners"),
            elimination_type=match.get("eliminationType", "double"),
            status=match.get("status", "pending"),
            next_game_slot=match.get("nextMatchSlot"),
            loser_next_game_slot=match.get("loserNextMatchSlot"),
            swiss_record_wins=match.get("swissRecordWins", 0),
            swiss_record_losses=match.get("swissRecordLosses", 0),
        )

        # Set teams if provided
        radiant_team = match.get("radiantTeam")
        if radiant_team and radiant_team.get("pk"):
            game.radiant_team_id = radiant_team["pk"]

        dire_team = match.get("direTeam")
        if dire_team and dire_team.get("pk"):
            game.dire_team_id = dire_team["pk"]

        game.save()
        id_to_game[match["id"]] = game

    # Pass 2: Wire up FK relationships
    for match in matches:
        game = id_to_game[match["id"]]
        updated = False

        next_match_id = match.get("nextMatchId")
        if next_match_id and next_match_id in id_to_game:
            game.next_game = id_to_game[next_match_id]
            updated = True

        loser_next_match_id = match.get("loserNextMatchId")
        if loser_next_match_id and loser_next_match_id in id_to_game:
            game.loser_next_game = id_to_game[loser_next_match_id]
            updated = True

        if updated:
            game.save()

    # Return saved games
    saved_games = Game.objects.filter(tournament=tournament).select_related(
        "radiant_team", "dire_team", "winning_team", "next_game", "loser_next_game"
    )
    result_serializer = BracketGameSerializer(saved_games, many=True)

    return Response(
        {"tournamentId": tournament_id, "matches": result_serializer.data}
    )
```

**Step 2: Run tests to verify they pass**

```bash
docker exec backend python /app/backend/manage.py test app.tests.test_bracket -v 2
```

Expected: All 5 tests pass

**Step 3: Commit**

```bash
cd /home/kettle/git_repos/website/.worktrees/bracket-save-placement
git add backend/app/views/bracket.py
git commit -m "feat: implement save_bracket endpoint"
```

---

## Task 4: Add Placement Calculation Tests

**Files:**
- Modify: `backend/app/tests/test_bracket.py`

**Step 1: Add placement calculation tests**

Append to `backend/app/tests/test_bracket.py`:

```python


class CalculatePlacementTest(TestCase):
    """Test placement calculation logic."""

    def test_grand_finals_loser_gets_2nd(self):
        """Loser of grand finals gets 2nd place."""
        from app.views.bracket import calculate_placement

        tournament = Tournament.objects.create(
            name="Test", date_played=date.today()
        )
        game = Game.objects.create(
            tournament=tournament,
            bracket_type="grand_finals",
            round=1,
            position=0,
        )

        placement = calculate_placement(game)
        self.assertEqual(placement, 2)

    def test_losers_finals_loser_gets_3rd(self):
        """Loser of losers finals gets 3rd place."""
        from app.views.bracket import calculate_placement

        tournament = Tournament.objects.create(
            name="Test", date_played=date.today()
        )
        # Create losers bracket with 2 rounds (finals is round 2)
        Game.objects.create(
            tournament=tournament,
            bracket_type="losers",
            round=1,
            position=0,
        )
        losers_finals = Game.objects.create(
            tournament=tournament,
            bracket_type="losers",
            round=2,
            position=0,
        )

        placement = calculate_placement(losers_finals)
        self.assertEqual(placement, 3)

    def test_losers_semi_loser_gets_4th(self):
        """Loser of losers semi gets 4th place."""
        from app.views.bracket import calculate_placement

        tournament = Tournament.objects.create(
            name="Test", date_played=date.today()
        )
        # Create losers bracket with 3 rounds
        losers_semi = Game.objects.create(
            tournament=tournament,
            bracket_type="losers",
            round=1,
            position=0,
        )
        Game.objects.create(
            tournament=tournament,
            bracket_type="losers",
            round=2,
            position=0,
        )
        Game.objects.create(
            tournament=tournament,
            bracket_type="losers",
            round=3,
            position=0,
        )

        placement = calculate_placement(losers_semi)
        self.assertEqual(placement, 4)

    def test_winners_bracket_elimination_returns_none(self):
        """Winners bracket games don't set placement (loser goes to losers)."""
        from app.views.bracket import calculate_placement

        tournament = Tournament.objects.create(
            name="Test", date_played=date.today()
        )
        game = Game.objects.create(
            tournament=tournament,
            bracket_type="winners",
            round=1,
            position=0,
        )

        placement = calculate_placement(game)
        self.assertIsNone(placement)


class AdvanceWinnerPlacementTest(TestCase):
    """Test advance_winner sets placement correctly."""

    def setUp(self):
        """Create test data."""
        self.admin = CustomUser.objects.create_superuser(
            username="admin",
            password="admin123",
            email="admin@test.com",
        )
        self.tournament = Tournament.objects.create(
            name="Test Tournament",
            date_played=date.today(),
        )
        self.captain1 = CustomUser.objects.create_user(
            username="cap1", password="test"
        )
        self.captain2 = CustomUser.objects.create_user(
            username="cap2", password="test"
        )
        self.team1 = Team.objects.create(
            name="Team 1",
            captain=self.captain1,
            tournament=self.tournament,
        )
        self.team2 = Team.objects.create(
            name="Team 2",
            captain=self.captain2,
            tournament=self.tournament,
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.admin)

    def test_advance_winner_sets_loser_placement_when_eliminated(self):
        """When loser has no loser_next_game, their placement is set."""
        # Losers finals - no loser path, loser gets 3rd
        losers_finals = Game.objects.create(
            tournament=self.tournament,
            bracket_type="losers",
            round=1,  # Only losers round = finals
            position=0,
            radiant_team=self.team1,
            dire_team=self.team2,
        )

        response = self.client.post(
            f"/api/bracket/games/{losers_finals.pk}/advance-winner/",
            {"winner": "radiant"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.team2.refresh_from_db()
        self.assertEqual(self.team2.placement, 3)

    def test_advance_winner_sets_winner_placement_in_grand_finals(self):
        """Grand finals winner gets 1st place."""
        grand_finals = Game.objects.create(
            tournament=self.tournament,
            bracket_type="grand_finals",
            round=1,
            position=0,
            radiant_team=self.team1,
            dire_team=self.team2,
        )

        response = self.client.post(
            f"/api/bracket/games/{grand_finals.pk}/advance-winner/",
            {"winner": "radiant"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.team1.refresh_from_db()
        self.team2.refresh_from_db()
        self.assertEqual(self.team1.placement, 1)
        self.assertEqual(self.team2.placement, 2)

    def test_advance_winner_no_placement_when_loser_has_path(self):
        """When loser has loser_next_game, no placement is set."""
        losers_game = Game.objects.create(
            tournament=self.tournament,
            bracket_type="losers",
            round=2,
            position=0,
        )
        winners_game = Game.objects.create(
            tournament=self.tournament,
            bracket_type="winners",
            round=1,
            position=0,
            radiant_team=self.team1,
            dire_team=self.team2,
            loser_next_game=losers_game,
            loser_next_game_slot="radiant",
            elimination_type="double",
        )

        response = self.client.post(
            f"/api/bracket/games/{winners_game.pk}/advance-winner/",
            {"winner": "radiant"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.team2.refresh_from_db()
        self.assertIsNone(self.team2.placement)
```

**Step 2: Run tests to verify they fail**

```bash
docker exec backend python /app/backend/manage.py test app.tests.test_bracket -v 2
```

Expected: New tests fail (calculate_placement not implemented)

**Step 3: Commit**

```bash
cd /home/kettle/git_repos/website/.worktrees/bracket-save-placement
git add backend/app/tests/test_bracket.py
git commit -m "test: add placement calculation tests (red)"
```

---

## Task 5: Implement Placement Calculation

**Files:**
- Modify: `backend/app/views/bracket.py` (add function before advance_winner)

**Step 1: Add calculate_placement function**

Add this function in `backend/app/views/bracket.py` before the `advance_winner` function (around line 87):

```python
from django.db.models import Max


def calculate_placement(game):
    """
    Calculate placement for a team eliminated from this game.

    Returns placement number or None if team isn't eliminated
    (e.g., winners bracket losers go to losers bracket).
    """
    # Grand finals loser = 2nd place
    if game.bracket_type == "grand_finals":
        return 2

    # Losers bracket elimination
    if game.bracket_type == "losers":
        # Find max losers round for this tournament
        max_round = Game.objects.filter(
            tournament=game.tournament,
            bracket_type="losers",
        ).aggregate(Max("round"))["round__max"]

        if max_round is None:
            return 3  # Only one losers game = losers finals

        rounds_from_final = max_round - game.round

        if rounds_from_final == 0:  # Losers finals
            return 3
        else:
            # Each earlier round: 4th, then 5th-6th, 7th-8th, etc.
            base = 4
            for i in range(rounds_from_final - 1):
                base += 2 ** i
            return base

    # Winners bracket elimination → goes to losers (no placement yet)
    return None
```

**Step 2: Run placement calculation tests**

```bash
docker exec backend python /app/backend/manage.py test app.tests.test_bracket.CalculatePlacementTest -v 2
```

Expected: All 4 CalculatePlacementTest tests pass

**Step 3: Commit**

```bash
cd /home/kettle/git_repos/website/.worktrees/bracket-save-placement
git add backend/app/views/bracket.py
git commit -m "feat: add calculate_placement function"
```

---

## Task 6: Update advance_winner to Set Placement

**Files:**
- Modify: `backend/app/views/bracket.py` (update advance_winner function)

**Step 1: Update advance_winner**

Replace the `advance_winner` function in `backend/app/views/bracket.py` with:

```python
@api_view(["POST"])
@permission_classes([IsAdminUser])
@transaction.atomic
def advance_winner(request, game_id):
    """Mark winner and advance to next match, setting placement if eliminated."""
    try:
        game = Game.objects.get(pk=game_id)
    except Game.DoesNotExist:
        return Response({"error": "Game not found"}, status=status.HTTP_404_NOT_FOUND)

    winner_slot = request.data.get("winner")  # 'radiant' or 'dire'
    if winner_slot not in ["radiant", "dire"]:
        return Response(
            {"error": "Invalid winner slot"}, status=status.HTTP_400_BAD_REQUEST
        )

    # Validate team exists in the slot
    if winner_slot == "radiant":
        if not game.radiant_team:
            return Response(
                {"error": "No radiant team assigned"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        winning_team = game.radiant_team
        losing_team = game.dire_team
    else:
        if not game.dire_team:
            return Response(
                {"error": "No dire team assigned"}, status=status.HTTP_400_BAD_REQUEST
            )
        winning_team = game.dire_team
        losing_team = game.radiant_team

    game.winning_team = winning_team
    game.status = "completed"
    game.save()

    # Advance winner to next game if exists
    if game.next_game and game.next_game_slot:
        next_game = game.next_game
        if game.next_game_slot == "radiant":
            next_game.radiant_team = winning_team
        else:
            next_game.dire_team = winning_team
        next_game.save()

    # Handle loser path
    if losing_team:
        if (
            game.elimination_type == "double"
            and game.loser_next_game
            and game.loser_next_game_slot
        ):
            # Advance loser to losers bracket
            loser_game = game.loser_next_game
            if game.loser_next_game_slot == "radiant":
                loser_game.radiant_team = losing_team
            else:
                loser_game.dire_team = losing_team
            loser_game.save()
        else:
            # No loser path - team is eliminated, set placement
            placement = calculate_placement(game)
            if placement:
                losing_team.placement = placement
                losing_team.save()

    # Grand finals - also set winner's placement
    if game.bracket_type == "grand_finals":
        winning_team.placement = 1
        winning_team.save()

    return Response(BracketGameSerializer(game).data)
```

**Step 2: Run all bracket tests**

```bash
docker exec backend python /app/backend/manage.py test app.tests.test_bracket -v 2
```

Expected: All 12 tests pass

**Step 3: Commit**

```bash
cd /home/kettle/git_repos/website/.worktrees/bracket-save-placement
git add backend/app/views/bracket.py
git commit -m "feat: update advance_winner to set team placement"
```

---

## Task 7: Add Manual Placement Override Endpoint

**Files:**
- Modify: `backend/app/views/bracket.py` (add new endpoint)
- Modify: `backend/bracket/urls.py` (add route)
- Modify: `backend/app/tests/test_bracket.py` (add tests)

**Step 1: Add tests for manual placement override**

Append to `backend/app/tests/test_bracket.py`:

```python


class ManualPlacementOverrideTest(TestCase):
    """Test manual placement override endpoint."""

    def setUp(self):
        """Create test data."""
        self.admin = CustomUser.objects.create_superuser(
            username="admin",
            password="admin123",
            email="admin@test.com",
        )
        self.tournament = Tournament.objects.create(
            name="Test Tournament",
            date_played=date.today(),
        )
        self.captain = CustomUser.objects.create_user(
            username="cap", password="test"
        )
        self.team = Team.objects.create(
            name="Team 1",
            captain=self.captain,
            tournament=self.tournament,
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.admin)

    def test_set_placement_success(self):
        """Admin can set team placement manually."""
        response = self.client.patch(
            f"/api/bracket/tournaments/{self.tournament.pk}/teams/{self.team.pk}/placement/",
            {"placement": 3},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.team.refresh_from_db()
        self.assertEqual(self.team.placement, 3)

    def test_clear_placement(self):
        """Admin can clear placement by setting to null."""
        self.team.placement = 2
        self.team.save()

        response = self.client.patch(
            f"/api/bracket/tournaments/{self.tournament.pk}/teams/{self.team.pk}/placement/",
            {"placement": None},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.team.refresh_from_db()
        self.assertIsNone(self.team.placement)

    def test_invalid_placement_rejected(self):
        """Invalid placement values are rejected."""
        response = self.client.patch(
            f"/api/bracket/tournaments/{self.tournament.pk}/teams/{self.team.pk}/placement/",
            {"placement": 0},
            format="json",
        )

        self.assertEqual(response.status_code, 400)

    def test_requires_admin(self):
        """Regular users cannot set placement."""
        regular_user = CustomUser.objects.create_user(
            username="regular",
            password="test123",
        )
        self.client.force_authenticate(user=regular_user)

        response = self.client.patch(
            f"/api/bracket/tournaments/{self.tournament.pk}/teams/{self.team.pk}/placement/",
            {"placement": 1},
            format="json",
        )

        self.assertEqual(response.status_code, 403)

    def test_team_must_belong_to_tournament(self):
        """Cannot set placement for team in different tournament."""
        other_tournament = Tournament.objects.create(
            name="Other Tournament",
            date_played=date.today(),
        )
        other_team = Team.objects.create(
            name="Other Team",
            tournament=other_tournament,
        )

        response = self.client.patch(
            f"/api/bracket/tournaments/{self.tournament.pk}/teams/{other_team.pk}/placement/",
            {"placement": 1},
            format="json",
        )

        self.assertEqual(response.status_code, 404)
```

**Step 2: Run tests to verify they fail**

```bash
docker exec backend python /app/backend/manage.py test app.tests.test_bracket.ManualPlacementOverrideTest -v 2
```

Expected: Tests fail (endpoint doesn't exist)

**Step 3: Add the endpoint**

Add to `backend/app/views/bracket.py` after `advance_winner`:

```python
@api_view(["PATCH"])
@permission_classes([IsAdminUser])
def set_team_placement(request, tournament_id, team_id):
    """Manually set or clear a team's tournament placement."""
    try:
        tournament = Tournament.objects.get(pk=tournament_id)
    except Tournament.DoesNotExist:
        return Response(
            {"error": "Tournament not found"}, status=status.HTTP_404_NOT_FOUND
        )

    try:
        team = Team.objects.get(pk=team_id, tournament=tournament)
    except Team.DoesNotExist:
        return Response(
            {"error": "Team not found in this tournament"},
            status=status.HTTP_404_NOT_FOUND,
        )

    placement = request.data.get("placement")

    # Validate placement
    if placement is not None:
        if not isinstance(placement, int) or placement < 1:
            return Response(
                {"error": "Placement must be a positive integer or null"},
                status=status.HTTP_400_BAD_REQUEST,
            )

    team.placement = placement
    team.save()

    return Response({"team_id": team.pk, "placement": team.placement})
```

**Step 4: Add URL route**

In `backend/bracket/urls.py`, add the import and route:

```python
from app.views.bracket import (
    advance_winner,
    generate_bracket,
    get_bracket,
    save_bracket,
    set_team_placement,
)

# Add to urlpatterns:
    path(
        "tournaments/<int:tournament_id>/teams/<int:team_id>/placement/",
        set_team_placement,
        name="set_team_placement",
    ),
```

**Step 5: Run tests**

```bash
docker exec backend python /app/backend/manage.py test app.tests.test_bracket -v 2
```

Expected: All 17 tests pass

**Step 6: Commit**

```bash
cd /home/kettle/git_repos/website/.worktrees/bracket-save-placement
git add backend/app/views/bracket.py backend/bracket/urls.py backend/app/tests/test_bracket.py
git commit -m "feat: add manual placement override endpoint"
```

---

## Task 8: Update TeamSerializer to Include Placement

**Files:**
- Modify: `backend/app/serializers.py`

**Step 1: Find and update TeamSerializer**

Search for TeamSerializer in `backend/app/serializers.py` and add `placement` to its fields.

```bash
grep -n "class Team.*Serializer" backend/app/serializers.py
```

Add `"placement"` to the `fields` tuple of any Team serializers that should expose placement.

**Step 2: Verify API returns placement**

```bash
# Manual verification via API if dev server is running
```

**Step 3: Commit**

```bash
cd /home/kettle/git_repos/website/.worktrees/bracket-save-placement
git add backend/app/serializers.py
git commit -m "feat: include placement in team serializers"
```

---

## Task 9: Run Full Test Suite and Final Commit

**Step 1: Run all tests**

```bash
docker exec backend python /app/backend/manage.py test app.tests -v 2
```

Expected: All tests pass

**Step 2: Create summary commit if needed**

If any loose changes remain:

```bash
cd /home/kettle/git_repos/website/.worktrees/bracket-save-placement
git status
# If changes exist:
git add -A
git commit -m "chore: cleanup bracket save implementation"
```

---

## Summary

| Task | Description | Tests |
|------|-------------|-------|
| 1 | Add placement field to Team | Migration |
| 2 | Create test file with save tests | 5 tests |
| 3 | Implement save_bracket | Pass 5 tests |
| 4 | Add placement calculation tests | 7 tests (4 new) |
| 5 | Implement calculate_placement | Pass 4 tests |
| 6 | Update advance_winner | Pass 3 tests |
| 7 | Add manual placement override | Pass 5 tests |
| 8 | Update serializers | Manual verify |
| 9 | Full test suite | All pass |

**Total new tests:** 17
