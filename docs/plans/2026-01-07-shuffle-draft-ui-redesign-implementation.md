# Shuffle Draft UI Redesign Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix shuffle draft auto-advance bug and redesign UI to show pick order, projected MMR, and double-pick opportunities.

**Architecture:** Backend creates all 16 rounds upfront with null captains, assigning captains dynamically after each pick. Frontend gets new shuffle-specific components (ShufflePickOrder, DoublePickThreshold) and enhanced DraftTable with projected column.

**Tech Stack:** Django/Python backend, React/TypeScript frontend, Zustand state management, Shadcn UI components, TailwindCSS

---

## Task 1: Backend - Create shuffle_draft.py Module

**Files:**
- Create: `backend/app/functions/shuffle_draft.py`
- Test: `backend/app/tests/test_shuffle_draft.py`

**Step 1: Write the failing test for get_team_total_mmr**

Create `backend/app/tests/test_shuffle_draft.py`:

```python
"""Tests for shuffle draft logic."""
from django.test import TestCase
from app.models import CustomUser, Tournament, Team, Draft


class GetTeamTotalMmrTest(TestCase):
    """Test get_team_total_mmr function."""

    def setUp(self):
        """Create test data."""
        self.captain = CustomUser.objects.create_user(
            username="captain1",
            password="test123",
            mmr=5000,
        )
        self.member1 = CustomUser.objects.create_user(
            username="member1",
            password="test123",
            mmr=4000,
        )
        self.member2 = CustomUser.objects.create_user(
            username="member2",
            password="test123",
            mmr=3500,
        )
        self.tournament = Tournament.objects.create(name="Test Tournament")
        self.team = Team.objects.create(
            name="Test Team",
            captain=self.captain,
            tournament=self.tournament,
        )
        self.team.members.add(self.captain, self.member1, self.member2)

    def test_calculates_total_mmr(self):
        """Total MMR = captain + all members (excluding captain duplicate)."""
        from app.functions.shuffle_draft import get_team_total_mmr

        result = get_team_total_mmr(self.team)

        # 5000 (captain) + 4000 (member1) + 3500 (member2) = 12500
        self.assertEqual(result, 12500)

    def test_handles_null_mmr(self):
        """Members with null MMR contribute 0."""
        from app.functions.shuffle_draft import get_team_total_mmr

        self.member2.mmr = None
        self.member2.save()

        result = get_team_total_mmr(self.team)

        # 5000 + 4000 + 0 = 9000
        self.assertEqual(result, 9000)
```

**Step 2: Run test to verify it fails**

```bash
cd /home/kettle/git_repos/website/.worktrees/shuffle-draft-ui-redesign/backend
source /home/kettle/git_repos/website/.venv/bin/activate
DISABLE_CACHE=true python manage.py test app.tests.test_shuffle_draft -v 2
```

Expected: FAIL with "No module named 'app.functions.shuffle_draft'"

**Step 3: Write minimal implementation**

Create `backend/app/functions/shuffle_draft.py`:

```python
"""Shuffle draft logic - lowest MMR picks first."""
import random
from typing import Optional


def get_team_total_mmr(team) -> int:
    """
    Calculate total MMR for a team (captain + members).

    Args:
        team: Team model instance

    Returns:
        Total MMR as integer
    """
    total = team.captain.mmr or 0 if team.captain else 0
    for member in team.members.exclude(id=team.captain_id):
        total += member.mmr or 0
    return total
```

**Step 4: Run test to verify it passes**

```bash
DISABLE_CACHE=true python manage.py test app.tests.test_shuffle_draft -v 2
```

Expected: PASS (2 tests)

**Step 5: Commit**

```bash
git add backend/app/functions/shuffle_draft.py backend/app/tests/test_shuffle_draft.py
git commit -m "feat(shuffle): add get_team_total_mmr function"
```

---

## Task 2: Backend - Add roll_until_winner Function

**Files:**
- Modify: `backend/app/functions/shuffle_draft.py`
- Modify: `backend/app/tests/test_shuffle_draft.py`

**Step 1: Write the failing test**

Add to `backend/app/tests/test_shuffle_draft.py`:

```python
from unittest.mock import patch


class RollUntilWinnerTest(TestCase):
    """Test roll_until_winner function."""

    def setUp(self):
        """Create test teams."""
        self.tournament = Tournament.objects.create(name="Test Tournament")
        self.captain1 = CustomUser.objects.create_user(
            username="cap1", password="test", mmr=5000
        )
        self.captain2 = CustomUser.objects.create_user(
            username="cap2", password="test", mmr=5000
        )
        self.team1 = Team.objects.create(
            name="Team 1", captain=self.captain1, tournament=self.tournament
        )
        self.team2 = Team.objects.create(
            name="Team 2", captain=self.captain2, tournament=self.tournament
        )

    @patch("app.functions.shuffle_draft.random.randint")
    def test_returns_winner_on_first_roll(self, mock_randint):
        """First team wins if they roll higher."""
        from app.functions.shuffle_draft import roll_until_winner

        mock_randint.side_effect = [6, 3]  # Team1 rolls 6, Team2 rolls 3

        winner, roll_rounds = roll_until_winner([self.team1, self.team2])

        self.assertEqual(winner.pk, self.team1.pk)
        self.assertEqual(len(roll_rounds), 1)
        self.assertEqual(roll_rounds[0][0]["roll"], 6)
        self.assertEqual(roll_rounds[0][1]["roll"], 3)

    @patch("app.functions.shuffle_draft.random.randint")
    def test_rerolls_on_tie(self, mock_randint):
        """Re-rolls when teams tie."""
        from app.functions.shuffle_draft import roll_until_winner

        # First round: tie (4, 4), Second round: team2 wins (2, 5)
        mock_randint.side_effect = [4, 4, 2, 5]

        winner, roll_rounds = roll_until_winner([self.team1, self.team2])

        self.assertEqual(winner.pk, self.team2.pk)
        self.assertEqual(len(roll_rounds), 2)
```

**Step 2: Run test to verify it fails**

```bash
DISABLE_CACHE=true python manage.py test app.tests.test_shuffle_draft.RollUntilWinnerTest -v 2
```

Expected: FAIL with "cannot import name 'roll_until_winner'"

**Step 3: Write minimal implementation**

Add to `backend/app/functions/shuffle_draft.py`:

```python
def roll_until_winner(teams: list) -> tuple:
    """
    Roll dice until one winner emerges.

    Args:
        teams: List of Team model instances

    Returns:
        Tuple of (winner_team, roll_rounds)
        roll_rounds is list of rounds, each round is list of {"team_id": N, "roll": N}
    """
    roll_rounds = []
    remaining = list(teams)

    while len(remaining) > 1:
        rolls = [{"team_id": t.id, "roll": random.randint(1, 6)} for t in remaining]
        roll_rounds.append(rolls)

        max_roll = max(r["roll"] for r in rolls)
        remaining = [
            t
            for t in remaining
            if next(r["roll"] for r in rolls if r["team_id"] == t.id) == max_roll
        ]

    return remaining[0], roll_rounds
```

**Step 4: Run test to verify it passes**

```bash
DISABLE_CACHE=true python manage.py test app.tests.test_shuffle_draft.RollUntilWinnerTest -v 2
```

Expected: PASS (2 tests)

**Step 5: Commit**

```bash
git add backend/app/functions/shuffle_draft.py backend/app/tests/test_shuffle_draft.py
git commit -m "feat(shuffle): add roll_until_winner function"
```

---

## Task 3: Backend - Add get_lowest_mmr_team Function

**Files:**
- Modify: `backend/app/functions/shuffle_draft.py`
- Modify: `backend/app/tests/test_shuffle_draft.py`

**Step 1: Write the failing test**

Add to `backend/app/tests/test_shuffle_draft.py`:

```python
class GetLowestMmrTeamTest(TestCase):
    """Test get_lowest_mmr_team function."""

    def setUp(self):
        """Create test teams with different MMRs."""
        self.tournament = Tournament.objects.create(name="Test Tournament")

        self.captain1 = CustomUser.objects.create_user(
            username="cap1", password="test", mmr=5000
        )
        self.captain2 = CustomUser.objects.create_user(
            username="cap2", password="test", mmr=4000
        )
        self.captain3 = CustomUser.objects.create_user(
            username="cap3", password="test", mmr=6000
        )

        self.team1 = Team.objects.create(
            name="Team 1", captain=self.captain1, tournament=self.tournament
        )
        self.team1.members.add(self.captain1)

        self.team2 = Team.objects.create(
            name="Team 2", captain=self.captain2, tournament=self.tournament
        )
        self.team2.members.add(self.captain2)

        self.team3 = Team.objects.create(
            name="Team 3", captain=self.captain3, tournament=self.tournament
        )
        self.team3.members.add(self.captain3)

    def test_returns_lowest_mmr_team(self):
        """Returns team with lowest total MMR."""
        from app.functions.shuffle_draft import get_lowest_mmr_team

        teams = [self.team1, self.team2, self.team3]
        winner, tie_data = get_lowest_mmr_team(teams)

        self.assertEqual(winner.pk, self.team2.pk)  # 4000 MMR
        self.assertIsNone(tie_data)

    @patch("app.functions.shuffle_draft.roll_until_winner")
    def test_handles_tie_with_roll(self, mock_roll):
        """Calls roll_until_winner when teams tie."""
        from app.functions.shuffle_draft import get_lowest_mmr_team

        # Make team1 and team2 have same MMR
        self.captain1.mmr = 4000
        self.captain1.save()

        mock_roll.return_value = (self.team1, [[{"team_id": self.team1.id, "roll": 5}]])

        teams = [self.team1, self.team2, self.team3]
        winner, tie_data = get_lowest_mmr_team(teams)

        self.assertEqual(winner.pk, self.team1.pk)
        self.assertIsNotNone(tie_data)
        self.assertEqual(len(tie_data["tied_teams"]), 2)
        mock_roll.assert_called_once()
```

**Step 2: Run test to verify it fails**

```bash
DISABLE_CACHE=true python manage.py test app.tests.test_shuffle_draft.GetLowestMmrTeamTest -v 2
```

Expected: FAIL with "cannot import name 'get_lowest_mmr_team'"

**Step 3: Write minimal implementation**

Add to `backend/app/functions/shuffle_draft.py`:

```python
def get_lowest_mmr_team(teams: list) -> tuple:
    """
    Find team with lowest total MMR.

    Args:
        teams: List of Team model instances

    Returns:
        Tuple of (winner_team, tie_resolution_data or None)
    """
    team_mmrs = [(team, get_team_total_mmr(team)) for team in teams]
    min_mmr = min(mmr for _, mmr in team_mmrs)
    tied = [t for t, mmr in team_mmrs if mmr == min_mmr]

    if len(tied) > 1:
        winner, roll_rounds = roll_until_winner(tied)
        tie_data = {
            "tied_teams": [
                {"id": t.id, "name": t.name, "mmr": get_team_total_mmr(t)} for t in tied
            ],
            "roll_rounds": roll_rounds,
            "winner_id": winner.id,
        }
        return winner, tie_data

    return tied[0], None
```

**Step 4: Run test to verify it passes**

```bash
DISABLE_CACHE=true python manage.py test app.tests.test_shuffle_draft.GetLowestMmrTeamTest -v 2
```

Expected: PASS (2 tests)

**Step 5: Commit**

```bash
git add backend/app/functions/shuffle_draft.py backend/app/tests/test_shuffle_draft.py
git commit -m "feat(shuffle): add get_lowest_mmr_team function"
```

---

## Task 4: Backend - Add build_shuffle_rounds Function

**Files:**
- Modify: `backend/app/functions/shuffle_draft.py`
- Modify: `backend/app/tests/test_shuffle_draft.py`

**Step 1: Write the failing test**

Add to `backend/app/tests/test_shuffle_draft.py`:

```python
from app.models import Draft, DraftRound


class BuildShuffleRoundsTest(TestCase):
    """Test build_shuffle_rounds function."""

    def setUp(self):
        """Create tournament with 4 teams."""
        self.tournament = Tournament.objects.create(name="Test Tournament")

        # Create 4 captains with different MMRs
        self.captains = []
        for i, mmr in enumerate([5000, 4000, 6000, 4500]):
            captain = CustomUser.objects.create_user(
                username=f"cap{i}", password="test", mmr=mmr
            )
            self.captains.append(captain)

        # Create 4 teams
        self.teams = []
        for i, captain in enumerate(self.captains):
            team = Team.objects.create(
                name=f"Team {i}", captain=captain, tournament=self.tournament
            )
            team.members.add(captain)
            self.teams.append(team)

        # Create draft
        self.draft = Draft.objects.create(
            tournament=self.tournament, draft_style="shuffle"
        )

    def test_creates_all_rounds_upfront(self):
        """Creates num_teams * 4 rounds."""
        from app.functions.shuffle_draft import build_shuffle_rounds

        build_shuffle_rounds(self.draft)

        # 4 teams * 4 picks each = 16 rounds
        self.assertEqual(self.draft.draft_rounds.count(), 16)

    def test_first_round_has_captain_assigned(self):
        """First round captain is lowest MMR team."""
        from app.functions.shuffle_draft import build_shuffle_rounds

        build_shuffle_rounds(self.draft)

        first_round = self.draft.draft_rounds.order_by("pick_number").first()
        # Captain with 4000 MMR should pick first
        self.assertEqual(first_round.captain.pk, self.captains[1].pk)

    def test_remaining_rounds_have_null_captain(self):
        """Rounds 2-16 have null captain."""
        from app.functions.shuffle_draft import build_shuffle_rounds

        build_shuffle_rounds(self.draft)

        rounds = self.draft.draft_rounds.order_by("pick_number")[1:]
        for draft_round in rounds:
            self.assertIsNone(draft_round.captain)

    def test_pick_phases_assigned_correctly(self):
        """Pick phases are 1-4 based on round number."""
        from app.functions.shuffle_draft import build_shuffle_rounds

        build_shuffle_rounds(self.draft)

        rounds = list(self.draft.draft_rounds.order_by("pick_number"))
        # Rounds 1-4 = phase 1, 5-8 = phase 2, etc.
        self.assertEqual(rounds[0].pick_phase, 1)
        self.assertEqual(rounds[3].pick_phase, 1)
        self.assertEqual(rounds[4].pick_phase, 2)
        self.assertEqual(rounds[15].pick_phase, 4)
```

**Step 2: Run test to verify it fails**

```bash
DISABLE_CACHE=true python manage.py test app.tests.test_shuffle_draft.BuildShuffleRoundsTest -v 2
```

Expected: FAIL with "cannot import name 'build_shuffle_rounds'"

**Step 3: Write minimal implementation**

Add to `backend/app/functions/shuffle_draft.py`:

```python
def build_shuffle_rounds(draft) -> None:
    """
    Create all rounds for shuffle draft, assign first captain.

    Args:
        draft: Draft model instance
    """
    from app.models import DraftRound

    teams = list(draft.tournament.teams.all())
    num_teams = len(teams)
    total_picks = num_teams * 4

    # Create all rounds with null captains
    rounds = [
        DraftRound(
            draft=draft,
            captain=None,
            pick_number=i,
            pick_phase=(i - 1) // num_teams + 1,
        )
        for i in range(1, total_picks + 1)
    ]
    DraftRound.objects.bulk_create(rounds)

    # Assign first captain based on lowest captain MMR
    first_team, tie_data = get_lowest_mmr_team(teams)
    first_round = draft.draft_rounds.order_by("pick_number").first()
    first_round.captain = first_team.captain
    if tie_data:
        first_round.was_tie = True
        first_round.tie_roll_data = tie_data
    first_round.save()
```

**Step 4: Run test to verify it passes**

```bash
DISABLE_CACHE=true python manage.py test app.tests.test_shuffle_draft.BuildShuffleRoundsTest -v 2
```

Expected: PASS (4 tests)

**Step 5: Commit**

```bash
git add backend/app/functions/shuffle_draft.py backend/app/tests/test_shuffle_draft.py
git commit -m "feat(shuffle): add build_shuffle_rounds function"
```

---

## Task 5: Backend - Add assign_next_shuffle_captain Function

**Files:**
- Modify: `backend/app/functions/shuffle_draft.py`
- Modify: `backend/app/tests/test_shuffle_draft.py`

**Step 1: Write the failing test**

Add to `backend/app/tests/test_shuffle_draft.py`:

```python
class AssignNextShuffleCaptainTest(TestCase):
    """Test assign_next_shuffle_captain function."""

    def setUp(self):
        """Create tournament with draft and make first pick."""
        self.tournament = Tournament.objects.create(name="Test Tournament")

        # Create 2 captains
        self.captain1 = CustomUser.objects.create_user(
            username="cap1", password="test", mmr=5000
        )
        self.captain2 = CustomUser.objects.create_user(
            username="cap2", password="test", mmr=4000
        )

        # Create player to be picked
        self.player = CustomUser.objects.create_user(
            username="player1", password="test", mmr=3000
        )

        # Create 2 teams
        self.team1 = Team.objects.create(
            name="Team 1", captain=self.captain1, tournament=self.tournament
        )
        self.team1.members.add(self.captain1)

        self.team2 = Team.objects.create(
            name="Team 2", captain=self.captain2, tournament=self.tournament
        )
        self.team2.members.add(self.captain2)

        # Create draft and build rounds
        self.draft = Draft.objects.create(
            tournament=self.tournament, draft_style="shuffle"
        )
        self.draft.users_remaining.add(self.player)

        from app.functions.shuffle_draft import build_shuffle_rounds

        build_shuffle_rounds(self.draft)

    def test_assigns_captain_to_next_null_round(self):
        """Assigns captain to next round with null captain."""
        from app.functions.shuffle_draft import assign_next_shuffle_captain

        # First round should have captain2 (4000 MMR)
        first_round = self.draft.draft_rounds.order_by("pick_number").first()
        self.assertEqual(first_round.captain.pk, self.captain2.pk)

        # Simulate pick - add player to team2
        first_round.choice = self.player
        first_round.save()
        self.team2.members.add(self.player)

        # Now team2 has 7000 MMR, team1 has 5000 MMR
        # Team1 should pick next
        tie_data = assign_next_shuffle_captain(self.draft)

        second_round = self.draft.draft_rounds.order_by("pick_number")[1]
        self.assertEqual(second_round.captain.pk, self.captain1.pk)
        self.assertIsNone(tie_data)

    def test_returns_none_when_no_more_rounds(self):
        """Returns None when all rounds have captains."""
        from app.functions.shuffle_draft import assign_next_shuffle_captain

        # Assign captains to all rounds
        for draft_round in self.draft.draft_rounds.all():
            draft_round.captain = self.captain1
            draft_round.save()

        result = assign_next_shuffle_captain(self.draft)

        self.assertIsNone(result)
```

**Step 2: Run test to verify it fails**

```bash
DISABLE_CACHE=true python manage.py test app.tests.test_shuffle_draft.AssignNextShuffleCaptainTest -v 2
```

Expected: FAIL with "cannot import name 'assign_next_shuffle_captain'"

**Step 3: Write minimal implementation**

Add to `backend/app/functions/shuffle_draft.py`:

```python
def assign_next_shuffle_captain(draft) -> Optional[dict]:
    """
    After a pick, assign captain to next round.

    Args:
        draft: Draft model instance

    Returns:
        tie_resolution data if tie occurred, else None
    """
    next_round = draft.draft_rounds.filter(captain__isnull=True).order_by("pick_number").first()
    if not next_round:
        return None

    teams = list(draft.tournament.teams.all())
    next_team, tie_data = get_lowest_mmr_team(teams)

    next_round.captain = next_team.captain
    if tie_data:
        next_round.was_tie = True
        next_round.tie_roll_data = tie_data
    next_round.save()

    return tie_data
```

**Step 4: Run test to verify it passes**

```bash
DISABLE_CACHE=true python manage.py test app.tests.test_shuffle_draft.AssignNextShuffleCaptainTest -v 2
```

Expected: PASS (2 tests)

**Step 5: Commit**

```bash
git add backend/app/functions/shuffle_draft.py backend/app/tests/test_shuffle_draft.py
git commit -m "feat(shuffle): add assign_next_shuffle_captain function"
```

---

## Task 6: Backend - Integrate shuffle_draft with models.py

**Files:**
- Modify: `backend/app/models.py` (around line 830-870, the `build_rounds` method)

**Step 1: Write the failing test**

Add to `backend/app/tests/test_shuffle_draft.py`:

```python
class DraftBuildRoundsIntegrationTest(TestCase):
    """Test Draft.build_rounds() integration with shuffle draft."""

    def setUp(self):
        """Create tournament with 4 teams."""
        self.tournament = Tournament.objects.create(name="Test Tournament")

        for i, mmr in enumerate([5000, 4000, 6000, 4500]):
            captain = CustomUser.objects.create_user(
                username=f"cap{i}", password="test", mmr=mmr
            )
            team = Team.objects.create(
                name=f"Team {i}", captain=captain, tournament=self.tournament
            )
            team.members.add(captain)

        self.draft = Draft.objects.create(
            tournament=self.tournament, draft_style="shuffle"
        )

    def test_build_rounds_delegates_to_shuffle_module(self):
        """Draft.build_rounds() uses shuffle module for shuffle style."""
        self.draft.build_rounds()

        # Should have 16 rounds
        self.assertEqual(self.draft.draft_rounds.count(), 16)

        # First round should have captain assigned
        first_round = self.draft.draft_rounds.order_by("pick_number").first()
        self.assertIsNotNone(first_round.captain)

        # Remaining rounds should have null captain
        remaining = self.draft.draft_rounds.order_by("pick_number")[1:]
        for draft_round in remaining:
            self.assertIsNone(draft_round.captain)
```

**Step 2: Run test to verify it fails**

```bash
DISABLE_CACHE=true python manage.py test app.tests.test_shuffle_draft.DraftBuildRoundsIntegrationTest -v 2
```

Expected: FAIL (build_rounds doesn't delegate to shuffle module yet)

**Step 3: Modify Draft.build_rounds() in models.py**

Find the `build_rounds` method in `backend/app/models.py` and add shuffle handling at the beginning:

```python
def build_rounds(self):
    """Build draft rounds based on draft style."""
    # Clear existing rounds
    self.draft_rounds.all().delete()

    # Delegate to shuffle module for shuffle style
    if self.draft_style == "shuffle":
        from app.functions.shuffle_draft import build_shuffle_rounds
        build_shuffle_rounds(self)
        return

    # ... existing snake/normal logic continues unchanged ...
```

**Step 4: Run test to verify it passes**

```bash
DISABLE_CACHE=true python manage.py test app.tests.test_shuffle_draft.DraftBuildRoundsIntegrationTest -v 2
```

Expected: PASS

**Step 5: Commit**

```bash
git add backend/app/models.py backend/app/tests/test_shuffle_draft.py
git commit -m "feat(shuffle): integrate shuffle_draft module with Draft.build_rounds"
```

---

## Task 7: Backend - Update pick_player_for_round View

**Files:**
- Modify: `backend/app/functions/tournament.py` (around line 115-140)

**Step 1: Write the failing test**

Add to `backend/app/tests/test_shuffle_draft.py`:

```python
from django.test import Client
from rest_framework.test import APIClient


class PickPlayerForRoundShuffleTest(TestCase):
    """Test pick_player_for_round view with shuffle draft."""

    def setUp(self):
        """Create tournament, draft, and make API client."""
        self.tournament = Tournament.objects.create(name="Test Tournament")

        # Create staff user for API calls
        self.staff = CustomUser.objects.create_user(
            username="staff", password="test", is_staff=True
        )

        # Create captains and players
        self.captain1 = CustomUser.objects.create_user(
            username="cap1", password="test", mmr=5000
        )
        self.captain2 = CustomUser.objects.create_user(
            username="cap2", password="test", mmr=4000
        )
        self.player1 = CustomUser.objects.create_user(
            username="player1", password="test", mmr=3000
        )
        self.player2 = CustomUser.objects.create_user(
            username="player2", password="test", mmr=2000
        )

        # Create teams
        self.team1 = Team.objects.create(
            name="Team 1", captain=self.captain1, tournament=self.tournament
        )
        self.team1.members.add(self.captain1)
        self.team2 = Team.objects.create(
            name="Team 2", captain=self.captain2, tournament=self.tournament
        )
        self.team2.members.add(self.captain2)

        # Create draft
        self.draft = Draft.objects.create(
            tournament=self.tournament, draft_style="shuffle"
        )
        self.draft.users_remaining.add(self.player1, self.player2)
        self.draft.build_rounds()

        self.client = APIClient()
        self.client.force_authenticate(user=self.staff)

    def test_assigns_next_captain_after_pick(self):
        """After pick, next round gets captain assigned."""
        first_round = self.draft.draft_rounds.order_by("pick_number").first()
        second_round = self.draft.draft_rounds.order_by("pick_number")[1]

        # Second round should have no captain yet
        self.assertIsNone(second_round.captain)

        # Make pick
        response = self.client.post(
            "/api/pick_player_for_round/",
            {"draft_round_pk": first_round.pk, "user_pk": self.player1.pk},
        )

        self.assertEqual(response.status_code, 201)

        # Refresh and check second round now has captain
        second_round.refresh_from_db()
        self.assertIsNotNone(second_round.captain)
```

**Step 2: Run test to verify it fails**

```bash
DISABLE_CACHE=true python manage.py test app.tests.test_shuffle_draft.PickPlayerForRoundShuffleTest -v 2
```

Expected: FAIL (second round captain not assigned)

**Step 3: Modify pick_player_for_round in tournament.py**

Find the section after the successful pick (around line 115-135) and add:

```python
    # After successful pick, for shuffle draft assign next captain
    if draft.draft_style == "shuffle" and draft.users_remaining.exists():
        from app.functions.shuffle_draft import assign_next_shuffle_captain

        tie_data = assign_next_shuffle_captain(draft)
        if tie_data:
            response_data["tie_resolution"] = tie_data
```

**Step 4: Run test to verify it passes**

```bash
DISABLE_CACHE=true python manage.py test app.tests.test_shuffle_draft.PickPlayerForRoundShuffleTest -v 2
```

Expected: PASS

**Step 5: Commit**

```bash
git add backend/app/functions/tournament.py backend/app/tests/test_shuffle_draft.py
git commit -m "feat(shuffle): assign next captain after pick in shuffle draft"
```

---

## Task 8: Backend - Run All Tests

**Step 1: Run full test suite**

```bash
cd /home/kettle/git_repos/website/.worktrees/shuffle-draft-ui-redesign/backend
source /home/kettle/git_repos/website/.venv/bin/activate
DISABLE_CACHE=true python manage.py test -v 2
```

Expected: All tests pass

**Step 2: Commit if any fixes needed**

```bash
git status
# If clean, proceed to frontend
```

---

## Task 9: Frontend - Rename liveReload to autoAdvance

**Files:**
- Modify: `frontend/app/store/tournamentStore.ts`
- Modify: `frontend/app/components/draft/draftModal.tsx`
- Modify: `frontend/app/components/draft/liveView.tsx`

**Step 1: Update tournamentStore.ts**

Find and replace `liveReload` with `autoAdvance` and `setLiveReload` with `setAutoAdvance`:

```typescript
// In the store interface and implementation
autoAdvance: boolean;
setAutoAdvance: (autoAdvance: boolean) => void;

// In the create function
autoAdvance: false,
setAutoAdvance: (autoAdvance) => set({ autoAdvance }),
```

**Step 2: Update draftModal.tsx**

Replace all instances of `liveReload` with `autoAdvance`:

```typescript
const autoAdvance = useTournamentStore((state) => state.autoAdvance);
// ... update all usages
```

**Step 3: Update liveView.tsx**

Update prop name and display text:

```typescript
interface LiveViewProps {
  isPolling: boolean;
}

// Update button text to say "Auto Advance: ON/OFF"
```

**Step 4: Verify no TypeScript errors**

```bash
cd /home/kettle/git_repos/website/.worktrees/shuffle-draft-ui-redesign/frontend
npm run typecheck 2>&1 | grep -v "node_modules" | head -20
```

**Step 5: Commit**

```bash
git add frontend/app/store/tournamentStore.ts frontend/app/components/draft/draftModal.tsx frontend/app/components/draft/liveView.tsx
git commit -m "refactor(frontend): rename liveReload to autoAdvance"
```

---

## Task 10: Frontend - Create ShufflePickOrder Component

**Files:**
- Create: `frontend/app/components/draft/shuffle/ShufflePickOrder.tsx`

**Step 1: Create the shuffle directory**

```bash
mkdir -p /home/kettle/git_repos/website/.worktrees/shuffle-draft-ui-redesign/frontend/app/components/draft/shuffle
```

**Step 2: Create ShufflePickOrder.tsx**

```typescript
import { cn } from '~/lib/utils';
import { Badge } from '~/components/ui/badge';
import { Card } from '~/components/ui/card';
import { useUserStore } from '~/store/userStore';
import type { TeamType } from '~/index';

interface TeamPickStatus {
  team: TeamType;
  totalMmr: number;
  picksMade: number;
  pickOrder: number;
}

export const ShufflePickOrder: React.FC = () => {
  const tournament = useUserStore((state) => state.tournament);
  const draft = useUserStore((state) => state.draft);
  const curDraftRound = useUserStore((state) => state.curDraftRound);

  const getTeamMmr = (team: TeamType): number => {
    let total = team.captain?.mmr || 0;
    team.members?.forEach((member) => {
      if (member.pk !== team.captain?.pk) {
        total += member.mmr || 0;
      }
    });
    return total;
  };

  const getTeamPickStatus = (): TeamPickStatus[] => {
    const teams = tournament?.teams || [];

    const statuses = teams.map((team) => {
      const totalMmr = getTeamMmr(team);

      const picksMade =
        draft?.draft_rounds?.filter(
          (r) => r.choice && r.captain?.pk === team.captain?.pk
        ).length || 0;

      return { team, totalMmr, picksMade, pickOrder: 0 };
    });

    statuses.sort((a, b) => a.totalMmr - b.totalMmr);
    statuses.forEach((s, idx) => {
      s.pickOrder = idx + 1;
    });

    return statuses;
  };

  const getPickDelta = (
    picksMade: number,
    allStatuses: TeamPickStatus[]
  ): string => {
    const avgPicks =
      allStatuses.reduce((sum, s) => sum + s.picksMade, 0) / allStatuses.length;
    const delta = picksMade - avgPicks;

    if (delta > 0.5) return `▲${Math.round(delta)}`;
    if (delta < -0.5) return `▼${Math.abs(Math.round(delta))}`;
    return '━';
  };

  const isCurrentPicker = (team: TeamType): boolean => {
    return curDraftRound?.captain?.pk === team.captain?.pk;
  };

  const statuses = getTeamPickStatus();

  return (
    <div className="mb-4">
      <h3 className="text-sm font-medium text-muted-foreground mb-2">
        Pick Order
      </h3>
      <div className="flex gap-2 overflow-x-auto pb-2">
        {statuses.map((status) => (
          <Card
            key={status.team.pk}
            className={cn(
              'flex-shrink-0 p-3 min-w-[140px]',
              isCurrentPicker(status.team)
                ? 'border-green-500 border-2 bg-green-950/20'
                : 'border-muted'
            )}
          >
            <div className="flex flex-col gap-1">
              <span className="font-medium text-sm truncate">
                {status.team.name}
              </span>

              <span className="text-xs text-muted-foreground">
                {status.totalMmr.toLocaleString()} MMR
              </span>

              <div className="flex items-center gap-2 text-xs">
                <span>{status.picksMade} picks</span>
                <span
                  className={cn(
                    getPickDelta(status.picksMade, statuses).startsWith('▼')
                      ? 'text-red-400'
                      : getPickDelta(status.picksMade, statuses).startsWith('▲')
                        ? 'text-green-400'
                        : 'text-muted-foreground'
                  )}
                >
                  {getPickDelta(status.picksMade, statuses)}
                </span>
              </div>

              {isCurrentPicker(status.team) && (
                <Badge variant="default" className="mt-1 bg-green-600 text-xs">
                  PICKING
                </Badge>
              )}
            </div>
          </Card>
        ))}
      </div>
    </div>
  );
};
```

**Step 3: Commit**

```bash
git add frontend/app/components/draft/shuffle/ShufflePickOrder.tsx
git commit -m "feat(frontend): add ShufflePickOrder component"
```

---

## Task 11: Frontend - Create DoublePickThreshold Component

**Files:**
- Create: `frontend/app/components/draft/shuffle/DoublePickThreshold.tsx`

**Step 1: Create DoublePickThreshold.tsx**

```typescript
import { Zap } from 'lucide-react';
import { Alert, AlertDescription, AlertTitle } from '~/components/ui/alert';
import { cn } from '~/lib/utils';
import { useUserStore } from '~/store/userStore';
import type { TeamType } from '~/index';

export const DoublePickThreshold: React.FC = () => {
  const tournament = useUserStore((state) => state.tournament);
  const draft = useUserStore((state) => state.draft);
  const curDraftRound = useUserStore((state) => state.curDraftRound);
  const user = useUserStore((state) => state.user);
  const isStaff = useUserStore((state) => state.isStaff);

  if (draft?.draft_style !== 'shuffle') return null;

  const isCurrentPicker = curDraftRound?.captain?.pk === user?.pk;
  if (!isCurrentPicker && !isStaff()) return null;

  const getTeamMmr = (team: TeamType): number => {
    let total = team.captain?.mmr || 0;
    team.members?.forEach((member) => {
      if (member.pk !== team.captain?.pk) {
        total += member.mmr || 0;
      }
    });
    return total;
  };

  const getCurrentTeam = (): TeamType | undefined => {
    return tournament?.teams?.find(
      (t) => t.captain?.pk === curDraftRound?.captain?.pk
    );
  };

  const getThresholdTeam = (): { team: TeamType; mmr: number } | null => {
    const teams = tournament?.teams || [];
    const currentTeam = getCurrentTeam();
    if (!currentTeam) return null;

    const otherTeams = teams
      .filter((t) => t.pk !== currentTeam.pk)
      .map((t) => ({ team: t, mmr: getTeamMmr(t) }))
      .sort((a, b) => a.mmr - b.mmr);

    return otherTeams[0] || null;
  };

  const currentTeam = getCurrentTeam();
  const threshold = getThresholdTeam();

  if (!currentTeam || !threshold) return null;

  const currentMmr = getTeamMmr(currentTeam);
  const canDoublePick = currentMmr < threshold.mmr;

  return (
    <Alert
      className={cn(
        'mb-4',
        canDoublePick ? 'border-green-500 bg-green-950/20' : 'border-muted'
      )}
    >
      <Zap
        className={cn(
          'h-4 w-4',
          canDoublePick ? 'text-green-500' : 'text-muted-foreground'
        )}
      />
      <AlertTitle className="text-sm font-medium">
        Double Pick Threshold
      </AlertTitle>
      <AlertDescription className="text-sm">
        <div className="flex flex-col gap-1 mt-1">
          <span>
            Stay under{' '}
            <span className="font-semibold">
              {threshold.mmr.toLocaleString()} MMR
            </span>{' '}
            to pick again
            <span className="text-muted-foreground">
              {' '}
              ({threshold.team.name})
            </span>
          </span>
          <span className="text-muted-foreground">
            Your current MMR:{' '}
            <span
              className={cn(
                'font-medium',
                canDoublePick ? 'text-green-400' : 'text-foreground'
              )}
            >
              {currentMmr.toLocaleString()}
            </span>
            {canDoublePick && (
              <span className="text-green-400 ml-2">
                ({(threshold.mmr - currentMmr).toLocaleString()} buffer)
              </span>
            )}
          </span>
        </div>
      </AlertDescription>
    </Alert>
  );
};
```

**Step 2: Commit**

```bash
git add frontend/app/components/draft/shuffle/DoublePickThreshold.tsx
git commit -m "feat(frontend): add DoublePickThreshold component"
```

---

## Task 12: Frontend - Update DraftTable with Projected Column

**Files:**
- Modify: `frontend/app/components/draft/roundView/draftTable.tsx`

**Step 1: Read current file**

Read the current draftTable.tsx to understand existing structure.

**Step 2: Add projected column logic and rendering**

Add imports, helper functions, and new column. Key additions:

- `isShuffle` check
- `getTeamMmr`, `getCurrentTeam`, `teamMmrs` calculations
- `getProjectedData` function
- `getOrdinal` helper
- New "Projected" table header (conditional)
- New projected cell (conditional)
- Green row highlighting with `cn(projected?.isDoublePick && 'bg-green-950/30')`

**Step 3: Verify no TypeScript errors**

```bash
cd /home/kettle/git_repos/website/.worktrees/shuffle-draft-ui-redesign/frontend
npm run typecheck 2>&1 | grep -v "node_modules" | head -20
```

**Step 4: Commit**

```bash
git add frontend/app/components/draft/roundView/draftTable.tsx
git commit -m "feat(frontend): add projected MMR column to DraftTable"
```

---

## Task 13: Frontend - Update DraftRoundView to Use ShufflePickOrder

**Files:**
- Modify: `frontend/app/components/draft/draftRoundView.tsx`

**Step 1: Add import and conditional rendering**

```typescript
import { ShufflePickOrder } from './shuffle/ShufflePickOrder';

// In the render, replace CaptainCards usage:
{draft.draft_style === 'shuffle' ? (
  <ShufflePickOrder />
) : (
  <CaptainCards />
)}
```

**Step 2: Commit**

```bash
git add frontend/app/components/draft/draftRoundView.tsx
git commit -m "feat(frontend): conditionally render ShufflePickOrder in DraftRoundView"
```

---

## Task 14: Frontend - Update PlayerChoiceView to Include DoublePickThreshold

**Files:**
- Modify: `frontend/app/components/draft/roundView/choiceCard.tsx` (or wherever PlayerChoiceView is)

**Step 1: Add import and render DoublePickThreshold**

```typescript
import { DoublePickThreshold } from '../shuffle/DoublePickThreshold';

// In render, above DraftTable:
return (
  <div>
    <DoublePickThreshold />
    <DraftTable />
  </div>
);
```

**Step 2: Commit**

```bash
git add frontend/app/components/draft/roundView/choiceCard.tsx
git commit -m "feat(frontend): add DoublePickThreshold to PlayerChoiceView"
```

---

## Task 15: Frontend - Fix Auto-Advance After Pick

**Files:**
- Modify: `frontend/app/components/draft/hooks/choosePlayerHook.tsx`

**Step 1: Update success handler to advance to next round**

In the success callback, after setting tournament and draft:

```typescript
success: (data) => {
  setTournament(data);
  setDraft(data.draft);

  // Find and advance to next round (first with captain assigned but no choice)
  const nextRound = data.draft.draft_rounds?.find(
    (r: DraftRoundType) => r.captain && !r.choice
  );

  if (nextRound) {
    setCurDraftRound(nextRound);
    const idx = data.draft.draft_rounds?.findIndex(
      (r: DraftRoundType) => r.pk === nextRound.pk
    );
    if (idx !== undefined && idx >= 0) {
      setDraftIndex(idx);
    }
  }

  // Handle tie overlay for shuffle
  if (
    data.draft?.draft_style === 'shuffle' &&
    data.tie_resolution &&
    onTieResolution
  ) {
    onTieResolution(data.tie_resolution);
  }

  return `Pick ${curDraftRound?.pick_number} complete!`;
}
```

**Step 2: Commit**

```bash
git add frontend/app/components/draft/hooks/choosePlayerHook.tsx
git commit -m "fix(frontend): auto-advance to next round after pick"
```

---

## Task 16: Final - Run All Tests and Verify

**Step 1: Run backend tests**

```bash
cd /home/kettle/git_repos/website/.worktrees/shuffle-draft-ui-redesign/backend
source /home/kettle/git_repos/website/.venv/bin/activate
DISABLE_CACHE=true python manage.py test -v 1
```

Expected: All tests pass

**Step 2: Run frontend typecheck**

```bash
cd /home/kettle/git_repos/website/.worktrees/shuffle-draft-ui-redesign/frontend
npm run typecheck 2>&1 | grep -v "node_modules"
```

Expected: Only pre-existing errors (dotaconstants, cypress test)

**Step 3: Final commit if needed**

```bash
git status
git log --oneline -10
```

---

## Summary

**Backend tasks (1-8):**
1. get_team_total_mmr function
2. roll_until_winner function
3. get_lowest_mmr_team function
4. build_shuffle_rounds function
5. assign_next_shuffle_captain function
6. Integrate with Draft.build_rounds()
7. Update pick_player_for_round view
8. Run all tests

**Frontend tasks (9-16):**
9. Rename liveReload to autoAdvance
10. ShufflePickOrder component
11. DoublePickThreshold component
12. DraftTable projected column
13. DraftRoundView conditional rendering
14. PlayerChoiceView include threshold
15. Fix auto-advance after pick
16. Final verification
