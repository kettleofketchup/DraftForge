# HeroDraft Captain's Mode Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement a real-time Captain's Mode hero draft system where two captains pick/ban heroes with reserve time mechanics, while spectators watch live.

**Architecture:** Django models for draft state, WebSocket consumer extending existing `draftevents` pattern for real-time updates with 1-second ticks during active rounds. React frontend with full-screen modal, Dota-style draft panel, and hero grid.

**Tech Stack:** Django, Django Channels, Redis, React, TypeScript, Zustand, dotaconstants (hero data), Shadcn UI

---

## ⚠️ CRITICAL FIXES FROM CODE REVIEW

**These fixes MUST be applied during implementation. The task descriptions below contain outdated patterns.**

### Backend File Structure (CRITICAL)
- **DO NOT** create `backend/app/models/herodraft.py` or `backend/app/serializers/herodraft.py`
- **DO** add all models to the **existing** `backend/app/models.py` (after line ~1230)
- **DO** add all serializers to the **existing** `backend/app/serializers.py`
- The codebase uses single files, NOT module directories

### URL Routing (CRITICAL)
- **DO NOT** create or modify `backend/app/urls.py` (this file doesn't exist)
- **DO** add URLs to `backend/backend/urls.py` following existing patterns
- Create `backend/herodraft/urls.py` and include with `path("api/herodraft/", include("herodraft.urls"))`

### WebSocket Routing (CRITICAL)
- **DO NOT** add routes to `backend/routing.py`
- **DO** add WebSocket routes to `backend/app/routing.py` (existing file)

### Logger Naming (IMPORTANT)
- Use `log = logging.getLogger(__name__)` and `log.debug/warning/error`
- **DO NOT** use `logger.` - the codebase uses `log.`

### Race Conditions (CRITICAL)
All state-changing functions in `herodraft.py` must use database locking:
```python
from django.db import transaction

def submit_choice(draft: HeroDraft, team: DraftTeam, choice_type: str, value: str):
    with transaction.atomic():
        draft = HeroDraft.objects.select_for_update().get(id=draft.id)
        team = DraftTeam.objects.select_for_update().get(id=team.id)
        # ... rest of implementation

def submit_pick(draft: HeroDraft, team: DraftTeam, hero_id: int):
    with transaction.atomic():
        draft = HeroDraft.objects.select_for_update().get(id=draft.id)
        current_round = draft.rounds.select_for_update().filter(state="active").first()
        # ... rest of implementation
```

### Tick Broadcaster Thread Safety (CRITICAL)
Add thread registry to prevent multiple threads per draft:
```python
_active_tick_tasks = {}  # draft_id -> threading.Event (stop signal)

def start_tick_broadcaster(draft_id: int):
    if draft_id in _active_tick_tasks:
        return  # Already running
    stop_event = threading.Event()
    _active_tick_tasks[draft_id] = stop_event
    # ... start thread with stop_event check in loop

def stop_tick_broadcaster(draft_id: int):
    if draft_id in _active_tick_tasks:
        _active_tick_tasks[draft_id].set()  # Signal stop
        del _active_tick_tasks[draft_id]
```

### Missing GameSerializer Field (CRITICAL)
Add `herodraft_id` to `GameSerializer` and `GameSerializerForTournament` in `serializers.py`:
```python
herodraft_id = serializers.SerializerMethodField()

def get_herodraft_id(self, obj):
    if hasattr(obj, 'herodraft'):
        return obj.herodraft.id
    return None
```

### Frontend Patterns (CRITICAL)

**Use Zod schemas** (not raw TypeScript interfaces):
```typescript
// frontend/app/components/herodraft/schemas.ts
import { z } from 'zod';

export const DraftTeamSchema = z.object({
  id: z.number(),
  // ... fields
});

export type DraftTeam = z.infer<typeof DraftTeamSchema>;
```

**Use refs for WebSocket callbacks** (prevents reconnection loops):
```typescript
const onEventRef = useRef(onEvent);
useEffect(() => { onEventRef.current = onEvent; }, [onEvent]);

const connect = useCallback(() => {
  // Use onEventRef.current in handlers
}, [draftId]); // Only depend on draftId
```

**Use TanStack Query** for API calls (follow `useTangoes.ts` pattern):
```typescript
export function useHeroDraft(draftId: number | null) {
  return useQuery({
    queryKey: ['herodraft', draftId],
    queryFn: () => getHeroDraft(draftId!),
    enabled: !!draftId,
  });
}
```

**Use `currentUser` not `user`**:
```typescript
const currentUser = useUserStore((state) => state.currentUser);
// NOT: const { user } = useUserStore();
```

**Use `getLogger`** (not console.log):
```typescript
import { getLogger } from '~/lib/logger';
const log = getLogger('HeroDraftModal');
```

### Bracket Integration (IMPORTANT)
- The component is `MatchNode.tsx` at `frontend/app/components/bracket/nodes/MatchNode.tsx`
- **NOT** `BracketGameNode.tsx` (doesn't exist)
- Integrate with `MatchStatsModal` for "View Draft" button

---

## Task 1: Create HeroDraft Models

> ⚠️ **REVIEW FIX APPLIED**: Models go in existing `models.py`, not a new module

**Files:**
- Modify: `backend/app/models.py` (add at end of file, after line ~1230)
- Create: `backend/app/tests/test_herodraft_models.py`

**Step 1: Write failing test for HeroDraft model**

```python
# backend/app/tests/test_herodraft_models.py
from django.test import TestCase
from app.models import Game, Tournament, Team, CustomUser, HeroDraft, DraftTeam, HeroDraftRound, HeroDraftEvent


class HeroDraftModelTest(TestCase):
    def setUp(self):
        self.user1 = CustomUser.objects.create_user(username="captain1", password="test")
        self.user2 = CustomUser.objects.create_user(username="captain2", password="test")
        self.tournament = Tournament.objects.create(name="Test Tournament")
        self.team1 = Team.objects.create(tournament=self.tournament, captain=self.user1)
        self.team2 = Team.objects.create(tournament=self.tournament, captain=self.user2)
        self.game = Game.objects.create(
            tournament=self.tournament,
            radiant_team=self.team1,
            dire_team=self.team2
        )

    def test_create_herodraft(self):
        """HeroDraft can be created and linked to a game."""
        draft = HeroDraft.objects.create(game=self.game)
        self.assertEqual(draft.state, "waiting_for_captains")
        self.assertIsNone(draft.roll_winner)
        self.assertEqual(draft.game, self.game)
```

**Step 2: Run test to verify it fails**

Run: `cd /home/kettle/git_repos/website/.worktrees/herodraft && source .venv/bin/activate && cd backend && DISABLE_CACHE=true python manage.py test app.tests.test_herodraft_models -v 2`

Expected: FAIL with "cannot import name 'HeroDraft' from 'app.models'"

**Step 3: Add HeroDraft models to existing models.py**

```python
# Add to backend/app/models.py (at end of file, after line ~1230)
from django.db import models
from cacheops import invalidate_model


class HeroDraft(models.Model):
    """Captain's Mode hero draft for a tournament game."""

    STATE_CHOICES = [
        ("waiting_for_captains", "Waiting for Captains"),
        ("rolling", "Rolling"),
        ("choosing", "Choosing"),
        ("drafting", "Drafting"),
        ("paused", "Paused"),
        ("completed", "Completed"),
    ]

    game = models.OneToOneField(
        "app.Game",
        on_delete=models.CASCADE,
        related_name="herodraft"
    )
    state = models.CharField(
        max_length=32,
        choices=STATE_CHOICES,
        default="waiting_for_captains"
    )
    roll_winner = models.ForeignKey(
        "DraftTeam",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="won_rolls"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        invalidate_model(HeroDraft)

    def __str__(self):
        return f"HeroDraft for {self.game}"


class DraftTeam(models.Model):
    """One of the two teams in a hero draft."""

    draft = models.ForeignKey(
        HeroDraft,
        on_delete=models.CASCADE,
        related_name="draft_teams"
    )
    tournament_team = models.ForeignKey(
        "app.Team",
        on_delete=models.CASCADE,
        related_name="hero_draft_teams"
    )
    is_first_pick = models.BooleanField(null=True, blank=True)
    is_radiant = models.BooleanField(null=True, blank=True)
    reserve_time_remaining = models.IntegerField(default=90000)  # 90 seconds in ms
    is_ready = models.BooleanField(default=False)
    is_connected = models.BooleanField(default=False)

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        invalidate_model(DraftTeam)

    @property
    def captain(self):
        return self.tournament_team.captain

    def __str__(self):
        return f"DraftTeam: {self.tournament_team} in {self.draft}"


class HeroDraftRound(models.Model):
    """A single pick or ban action in the draft."""

    ACTION_CHOICES = [
        ("ban", "Ban"),
        ("pick", "Pick"),
    ]

    STATE_CHOICES = [
        ("planned", "Planned"),
        ("active", "Active"),
        ("completed", "Completed"),
    ]

    draft = models.ForeignKey(
        HeroDraft,
        on_delete=models.CASCADE,
        related_name="rounds"
    )
    draft_team = models.ForeignKey(
        DraftTeam,
        on_delete=models.CASCADE,
        related_name="rounds"
    )
    round_number = models.IntegerField()
    action_type = models.CharField(max_length=8, choices=ACTION_CHOICES)
    hero_id = models.IntegerField(null=True, blank=True)
    state = models.CharField(max_length=16, choices=STATE_CHOICES, default="planned")
    grace_time_ms = models.IntegerField(default=30000)  # 30 seconds
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["round_number"]

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        invalidate_model(HeroDraftRound)

    def __str__(self):
        return f"Round {self.round_number}: {self.action_type} by {self.draft_team}"


class HeroDraftEvent(models.Model):
    """Audit log for hero draft events."""

    EVENT_CHOICES = [
        ("captain_connected", "Captain Connected"),
        ("captain_disconnected", "Captain Disconnected"),
        ("draft_paused", "Draft Paused"),
        ("draft_resumed", "Draft Resumed"),
        ("roll_triggered", "Roll Triggered"),
        ("roll_result", "Roll Result"),
        ("choice_made", "Choice Made"),
        ("round_started", "Round Started"),
        ("hero_selected", "Hero Selected"),
        ("round_timeout", "Round Timeout"),
        ("draft_completed", "Draft Completed"),
    ]

    draft = models.ForeignKey(
        HeroDraft,
        on_delete=models.CASCADE,
        related_name="events"
    )
    event_type = models.CharField(max_length=32, choices=EVENT_CHOICES)
    draft_team = models.ForeignKey(
        DraftTeam,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="events"
    )
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.event_type} at {self.created_at}"
```

**Step 4: Run test to verify it passes**

Run: `cd /home/kettle/git_repos/website/.worktrees/herodraft && source .venv/bin/activate && cd backend && DISABLE_CACHE=true python manage.py test app.tests.test_herodraft_models -v 2`

Expected: PASS

**Step 5: Commit**

```bash
git add backend/app/models.py backend/app/tests/test_herodraft_models.py
git commit -m "feat(herodraft): add HeroDraft, DraftTeam, HeroDraftRound, HeroDraftEvent models"
```

---

## Task 2: Create Database Migration

**Files:**
- Create: `backend/app/migrations/0060_herodraft.py` (number may vary)

**Step 1: Generate migration**

Run: `cd /home/kettle/git_repos/website/.worktrees/herodraft && source .venv/bin/activate && cd backend && python manage.py makemigrations app --name herodraft`

**Step 2: Review generated migration**

Verify it creates all 4 tables: `app_herodraft`, `app_draftteam`, `app_herodraftround`, `app_herodraftevent`

**Step 3: Apply migration**

Run: `cd /home/kettle/git_repos/website/.worktrees/herodraft && source .venv/bin/activate && inv db.migrate.all`

**Step 4: Commit**

```bash
git add backend/app/migrations/
git commit -m "feat(herodraft): add database migration for herodraft models"
```

---

## Task 3: Add DraftTeam and HeroDraftRound Tests

**Files:**
- Modify: `backend/app/tests/test_herodraft_models.py`

**Step 1: Write failing tests for DraftTeam**

```python
# Add to backend/app/tests/test_herodraft_models.py

class DraftTeamModelTest(TestCase):
    def setUp(self):
        self.user1 = CustomUser.objects.create_user(username="captain1", password="test")
        self.user2 = CustomUser.objects.create_user(username="captain2", password="test")
        self.tournament = Tournament.objects.create(name="Test Tournament")
        self.team1 = Team.objects.create(tournament=self.tournament, captain=self.user1)
        self.team2 = Team.objects.create(tournament=self.tournament, captain=self.user2)
        self.game = Game.objects.create(
            tournament=self.tournament,
            radiant_team=self.team1,
            dire_team=self.team2
        )
        self.draft = HeroDraft.objects.create(game=self.game)

    def test_create_draft_team(self):
        """DraftTeam can be created with default values."""
        draft_team = DraftTeam.objects.create(
            draft=self.draft,
            tournament_team=self.team1
        )
        self.assertEqual(draft_team.reserve_time_remaining, 90000)
        self.assertFalse(draft_team.is_ready)
        self.assertFalse(draft_team.is_connected)
        self.assertIsNone(draft_team.is_first_pick)
        self.assertIsNone(draft_team.is_radiant)

    def test_captain_property(self):
        """DraftTeam.captain returns the tournament team's captain."""
        draft_team = DraftTeam.objects.create(
            draft=self.draft,
            tournament_team=self.team1
        )
        self.assertEqual(draft_team.captain, self.user1)


class HeroDraftRoundModelTest(TestCase):
    def setUp(self):
        self.user1 = CustomUser.objects.create_user(username="captain1", password="test")
        self.user2 = CustomUser.objects.create_user(username="captain2", password="test")
        self.tournament = Tournament.objects.create(name="Test Tournament")
        self.team1 = Team.objects.create(tournament=self.tournament, captain=self.user1)
        self.team2 = Team.objects.create(tournament=self.tournament, captain=self.user2)
        self.game = Game.objects.create(
            tournament=self.tournament,
            radiant_team=self.team1,
            dire_team=self.team2
        )
        self.draft = HeroDraft.objects.create(game=self.game)
        self.draft_team = DraftTeam.objects.create(
            draft=self.draft,
            tournament_team=self.team1
        )

    def test_create_round(self):
        """HeroDraftRound can be created."""
        round = HeroDraftRound.objects.create(
            draft=self.draft,
            draft_team=self.draft_team,
            round_number=1,
            action_type="ban"
        )
        self.assertEqual(round.state, "planned")
        self.assertEqual(round.grace_time_ms, 30000)
        self.assertIsNone(round.hero_id)

    def test_rounds_ordered_by_number(self):
        """Rounds are ordered by round_number."""
        r3 = HeroDraftRound.objects.create(
            draft=self.draft, draft_team=self.draft_team,
            round_number=3, action_type="pick"
        )
        r1 = HeroDraftRound.objects.create(
            draft=self.draft, draft_team=self.draft_team,
            round_number=1, action_type="ban"
        )
        r2 = HeroDraftRound.objects.create(
            draft=self.draft, draft_team=self.draft_team,
            round_number=2, action_type="ban"
        )
        rounds = list(self.draft.rounds.all())
        self.assertEqual([r.round_number for r in rounds], [1, 2, 3])
```

**Step 2: Run tests to verify they pass**

Run: `cd /home/kettle/git_repos/website/.worktrees/herodraft && source .venv/bin/activate && cd backend && DISABLE_CACHE=true python manage.py test app.tests.test_herodraft_models -v 2`

Expected: PASS (4 tests)

**Step 3: Commit**

```bash
git add backend/app/tests/test_herodraft_models.py
git commit -m "test(herodraft): add DraftTeam and HeroDraftRound model tests"
```

---

## Task 4: Create Draft Sequence Builder

> ⚠️ **REVIEW FIX APPLIED**: All state-changing functions MUST use `transaction.atomic()` with `select_for_update()` to prevent race conditions. See Critical Fixes section above.

**Files:**
- Create: `backend/app/functions/herodraft.py`
- Create: `backend/app/tests/test_herodraft_functions.py`

**Step 1: Write failing test for draft sequence**

```python
# backend/app/tests/test_herodraft_functions.py
from django.test import TestCase
from app.models import Game, Tournament, Team, CustomUser, HeroDraft, DraftTeam, HeroDraftRound
from app.functions.herodraft import build_draft_rounds, CAPTAINS_MODE_SEQUENCE


class BuildDraftRoundsTest(TestCase):
    def setUp(self):
        self.user1 = CustomUser.objects.create_user(username="captain1", password="test")
        self.user2 = CustomUser.objects.create_user(username="captain2", password="test")
        self.tournament = Tournament.objects.create(name="Test Tournament")
        self.team1 = Team.objects.create(tournament=self.tournament, captain=self.user1)
        self.team2 = Team.objects.create(tournament=self.tournament, captain=self.user2)
        self.game = Game.objects.create(
            tournament=self.tournament,
            radiant_team=self.team1,
            dire_team=self.team2
        )

    def test_builds_24_rounds(self):
        """build_draft_rounds creates exactly 24 rounds."""
        draft = HeroDraft.objects.create(game=self.game)
        first_team = DraftTeam.objects.create(
            draft=draft, tournament_team=self.team1, is_first_pick=True
        )
        second_team = DraftTeam.objects.create(
            draft=draft, tournament_team=self.team2, is_first_pick=False
        )

        build_draft_rounds(draft, first_team, second_team)

        self.assertEqual(draft.rounds.count(), 24)

    def test_correct_sequence(self):
        """Rounds follow the updated Captain's Mode sequence."""
        draft = HeroDraft.objects.create(game=self.game)
        first_team = DraftTeam.objects.create(
            draft=draft, tournament_team=self.team1, is_first_pick=True
        )
        second_team = DraftTeam.objects.create(
            draft=draft, tournament_team=self.team2, is_first_pick=False
        )

        build_draft_rounds(draft, first_team, second_team)

        rounds = list(draft.rounds.all())

        # Verify first ban phase: F-F-S-S-F-S-S
        self.assertEqual(rounds[0].draft_team, first_team)
        self.assertEqual(rounds[0].action_type, "ban")
        self.assertEqual(rounds[1].draft_team, first_team)
        self.assertEqual(rounds[1].action_type, "ban")
        self.assertEqual(rounds[2].draft_team, second_team)
        self.assertEqual(rounds[3].draft_team, second_team)
        self.assertEqual(rounds[4].draft_team, first_team)
        self.assertEqual(rounds[5].draft_team, second_team)
        self.assertEqual(rounds[6].draft_team, second_team)

        # Verify first pick phase: F-S (rounds 8-9)
        self.assertEqual(rounds[7].action_type, "pick")
        self.assertEqual(rounds[7].draft_team, first_team)
        self.assertEqual(rounds[8].action_type, "pick")
        self.assertEqual(rounds[8].draft_team, second_team)

    def test_ban_and_pick_counts(self):
        """First team has 6 bans, 5 picks. Second team has 8 bans, 5 picks."""
        draft = HeroDraft.objects.create(game=self.game)
        first_team = DraftTeam.objects.create(
            draft=draft, tournament_team=self.team1, is_first_pick=True
        )
        second_team = DraftTeam.objects.create(
            draft=draft, tournament_team=self.team2, is_first_pick=False
        )

        build_draft_rounds(draft, first_team, second_team)

        first_bans = draft.rounds.filter(draft_team=first_team, action_type="ban").count()
        first_picks = draft.rounds.filter(draft_team=first_team, action_type="pick").count()
        second_bans = draft.rounds.filter(draft_team=second_team, action_type="ban").count()
        second_picks = draft.rounds.filter(draft_team=second_team, action_type="pick").count()

        self.assertEqual(first_bans, 6)
        self.assertEqual(first_picks, 5)
        self.assertEqual(second_bans, 8)
        self.assertEqual(second_picks, 5)
```

**Step 2: Run test to verify it fails**

Run: `cd /home/kettle/git_repos/website/.worktrees/herodraft && source .venv/bin/activate && cd backend && DISABLE_CACHE=true python manage.py test app.tests.test_herodraft_functions -v 2`

Expected: FAIL with "No module named 'app.functions.herodraft'"

**Step 3: Implement build_draft_rounds**

```python
# backend/app/functions/herodraft.py
"""Functions for Captain's Mode hero draft."""
import random
from django.utils import timezone
from app.models.herodraft import HeroDraft, DraftTeam, HeroDraftRound, HeroDraftEvent


# Updated Captain's Mode sequence (2024 patch)
# F = First pick team, S = Second pick team
# Format: (team_is_first, action_type)
CAPTAINS_MODE_SEQUENCE = [
    # Ban Phase 1: F-F-S-S-F-S-S
    (True, "ban"),   # 1
    (True, "ban"),   # 2
    (False, "ban"),  # 3
    (False, "ban"),  # 4
    (True, "ban"),   # 5
    (False, "ban"),  # 6
    (False, "ban"),  # 7
    # Pick Phase 1: F-S
    (True, "pick"),  # 8
    (False, "pick"), # 9
    # Ban Phase 2: S-F-S
    (False, "ban"),  # 10
    (True, "ban"),   # 11
    (False, "ban"),  # 12
    # Pick Phase 2: F-S-F-S-F-S
    (True, "pick"),  # 13
    (False, "pick"), # 14
    (True, "pick"),  # 15
    (False, "pick"), # 16
    (True, "pick"),  # 17
    (False, "pick"), # 18
    # Ban Phase 3: F-S-F-S (NEW order)
    (True, "ban"),   # 19
    (False, "ban"),  # 20
    (True, "ban"),   # 21
    (False, "ban"),  # 22
    # Pick Phase 3: F-S
    (True, "pick"),  # 23
    (False, "pick"), # 24
]


def build_draft_rounds(draft: HeroDraft, first_team: DraftTeam, second_team: DraftTeam):
    """
    Create all 24 HeroDraftRound objects for the draft.

    Args:
        draft: The HeroDraft instance
        first_team: DraftTeam with is_first_pick=True
        second_team: DraftTeam with is_first_pick=False
    """
    rounds_to_create = []

    for i, (is_first, action_type) in enumerate(CAPTAINS_MODE_SEQUENCE):
        team = first_team if is_first else second_team
        rounds_to_create.append(
            HeroDraftRound(
                draft=draft,
                draft_team=team,
                round_number=i + 1,
                action_type=action_type,
                state="planned"
            )
        )

    HeroDraftRound.objects.bulk_create(rounds_to_create)


def trigger_roll(draft: HeroDraft, actor_team: DraftTeam) -> DraftTeam:
    """
    Perform the coin flip to determine who chooses first.

    Returns the winning DraftTeam.
    """
    teams = list(draft.draft_teams.all())
    winner = random.choice(teams)

    draft.roll_winner = winner
    draft.state = "choosing"
    draft.save()

    HeroDraftEvent.objects.create(
        draft=draft,
        event_type="roll_result",
        draft_team=winner,
        metadata={
            "triggered_by": actor_team.id,
            "winner_id": winner.id,
            "winner_captain": winner.captain.username if winner.captain else None,
        }
    )

    return winner


def submit_choice(draft: HeroDraft, team: DraftTeam, choice_type: str, value: str):
    """
    Submit a choice for pick order or side.

    Args:
        choice_type: "pick_order" or "side"
        value: "first"/"second" for pick_order, "radiant"/"dire" for side
    """
    other_team = draft.draft_teams.exclude(id=team.id).first()

    if choice_type == "pick_order":
        team.is_first_pick = (value == "first")
        other_team.is_first_pick = (value != "first")
    elif choice_type == "side":
        team.is_radiant = (value == "radiant")
        other_team.is_radiant = (value != "radiant")

    team.save()
    other_team.save()

    HeroDraftEvent.objects.create(
        draft=draft,
        event_type="choice_made",
        draft_team=team,
        metadata={
            "choice_type": choice_type,
            "value": value,
        }
    )

    # Check if both choices have been made
    teams = list(draft.draft_teams.all())
    all_choices_made = all(
        t.is_first_pick is not None and t.is_radiant is not None
        for t in teams
    )

    if all_choices_made:
        # Build the draft rounds now that we know who picks first
        first_team = next(t for t in teams if t.is_first_pick)
        second_team = next(t for t in teams if not t.is_first_pick)
        build_draft_rounds(draft, first_team, second_team)

        draft.state = "drafting"
        draft.save()

        # Activate first round
        first_round = draft.rounds.first()
        first_round.state = "active"
        first_round.started_at = timezone.now()
        first_round.save()


def submit_pick(draft: HeroDraft, team: DraftTeam, hero_id: int) -> HeroDraftRound:
    """
    Submit a hero pick or ban for the current round.

    Returns the completed round.
    """
    current_round = draft.rounds.filter(state="active").first()

    if not current_round:
        raise ValueError("No active round")

    if current_round.draft_team_id != team.id:
        raise ValueError("Not your turn")

    # Check hero not already picked/banned
    used_heroes = draft.rounds.exclude(hero_id=None).values_list("hero_id", flat=True)
    if hero_id in used_heroes:
        raise ValueError("Hero already picked or banned")

    # Calculate time spent and update reserve time
    now = timezone.now()
    elapsed_ms = int((now - current_round.started_at).total_seconds() * 1000)
    grace_used = min(elapsed_ms, current_round.grace_time_ms)
    reserve_used = max(0, elapsed_ms - current_round.grace_time_ms)

    team.reserve_time_remaining = max(0, team.reserve_time_remaining - reserve_used)
    team.save()

    # Complete the round
    current_round.hero_id = hero_id
    current_round.state = "completed"
    current_round.completed_at = now
    current_round.save()

    HeroDraftEvent.objects.create(
        draft=draft,
        event_type="hero_selected",
        draft_team=team,
        metadata={
            "round_number": current_round.round_number,
            "hero_id": hero_id,
            "action_type": current_round.action_type,
            "time_elapsed_ms": elapsed_ms,
            "reserve_used_ms": reserve_used,
        }
    )

    # Activate next round or complete draft
    next_round = draft.rounds.filter(state="planned").first()
    if next_round:
        next_round.state = "active"
        next_round.started_at = timezone.now()
        next_round.save()

        HeroDraftEvent.objects.create(
            draft=draft,
            event_type="round_started",
            draft_team=next_round.draft_team,
            metadata={
                "round_number": next_round.round_number,
                "action_type": next_round.action_type,
            }
        )
    else:
        draft.state = "completed"
        draft.save()

        HeroDraftEvent.objects.create(
            draft=draft,
            event_type="draft_completed",
            metadata={}
        )

    return current_round


def get_available_heroes(draft: HeroDraft) -> list[int]:
    """Return list of hero IDs not yet picked or banned."""
    # All Dota 2 hero IDs (1-138 with some gaps)
    # This should be synced with dotaconstants on frontend
    ALL_HERO_IDS = list(range(1, 139))  # Simplified; actual list from dotaconstants

    used_heroes = set(
        draft.rounds.exclude(hero_id=None).values_list("hero_id", flat=True)
    )

    return [h for h in ALL_HERO_IDS if h not in used_heroes]
```

**Step 4: Run test to verify it passes**

Run: `cd /home/kettle/git_repos/website/.worktrees/herodraft && source .venv/bin/activate && cd backend && DISABLE_CACHE=true python manage.py test app.tests.test_herodraft_functions -v 2`

Expected: PASS (3 tests)

**Step 5: Commit**

```bash
git add backend/app/functions/herodraft.py backend/app/tests/test_herodraft_functions.py
git commit -m "feat(herodraft): add build_draft_rounds and draft action functions"
```

---

## Task 5: Create HeroDraft Serializers

> ⚠️ **REVIEW FIX APPLIED**: Serializers go in existing `serializers.py`, not a new module. Also adds `herodraft_id` to GameSerializer.

**Files:**
- Modify: `backend/app/serializers.py` (add at end of file)

**Step 1: Add herodraft_id to GameSerializer and GameSerializerForTournament**

First, update the existing `GameSerializer` and `GameSerializerForTournament` classes to include `herodraft_id`:

```python
# In backend/app/serializers.py - Add to GameSerializerForTournament class (around line 368):
herodraft_id = serializers.SerializerMethodField()

def get_herodraft_id(self, obj):
    if hasattr(obj, 'herodraft'):
        return obj.herodraft.id
    return None

# Also add 'herodraft_id' to the fields tuple in Meta class

# In backend/app/serializers.py - Add to GameSerializer class (around line 640):
herodraft_id = serializers.SerializerMethodField()

def get_herodraft_id(self, obj):
    if hasattr(obj, 'herodraft'):
        return obj.herodraft.id
    return None

# Also add 'herodraft_id' to the fields tuple in Meta class
```

**Step 2: Add HeroDraft serializers to existing serializers.py**

```python
# Add to backend/app/serializers.py (at end of file)
from app.models import HeroDraft, DraftTeam, HeroDraftRound, HeroDraftEvent


class HeroDraftEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = HeroDraftEvent
        fields = ["id", "event_type", "draft_team", "metadata", "created_at"]


class HeroDraftRoundSerializer(serializers.ModelSerializer):
    class Meta:
        model = HeroDraftRound
        fields = [
            "id", "round_number", "action_type", "hero_id", "state",
            "grace_time_ms", "started_at", "completed_at", "draft_team"
        ]


class DraftTeamSerializer(serializers.ModelSerializer):
    captain = TournamentUserSerializer(read_only=True)
    team_name = serializers.CharField(source="tournament_team.name", read_only=True)

    class Meta:
        model = DraftTeam
        fields = [
            "id", "tournament_team", "captain", "team_name",
            "is_first_pick", "is_radiant", "reserve_time_remaining",
            "is_ready", "is_connected"
        ]


class HeroDraftSerializer(serializers.ModelSerializer):
    draft_teams = DraftTeamSerializer(many=True, read_only=True)
    rounds = HeroDraftRoundSerializer(many=True, read_only=True)
    game = GameSerializer(read_only=True)
    roll_winner = DraftTeamSerializer(read_only=True)
    current_round = serializers.SerializerMethodField()

    class Meta:
        model = HeroDraft
        fields = [
            "id", "game", "state", "roll_winner", "draft_teams",
            "rounds", "current_round", "created_at", "updated_at"
        ]

    def get_current_round(self, obj):
        active_round = obj.rounds.filter(state="active").first()
        if active_round:
            return HeroDraftRoundSerializer(active_round).data
        return None


class HeroDraftTickSerializer(serializers.Serializer):
    """Serializer for WebSocket tick updates."""
    current_round = serializers.IntegerField()
    active_team_id = serializers.IntegerField()
    grace_time_remaining_ms = serializers.IntegerField()
    team_a_reserve_ms = serializers.IntegerField()
    team_b_reserve_ms = serializers.IntegerField()
    draft_state = serializers.CharField()
```

**Step 2: Update serializers __init__.py**

```python
# backend/app/serializers/__init__.py
# Add at end:
from app.serializers.herodraft import (
    HeroDraftSerializer,
    DraftTeamSerializer,
    HeroDraftRoundSerializer,
    HeroDraftEventSerializer,
    HeroDraftTickSerializer,
)
```

**Step 3: Commit**

```bash
git add backend/app/serializers/herodraft.py backend/app/serializers/__init__.py
git commit -m "feat(herodraft): add HeroDraft serializers"
```

---

## Task 6: Create HeroDraft API Views

> ⚠️ **REVIEW FIX APPLIED**: URLs go in `backend/backend/urls.py`, not `backend/app/urls.py` (which doesn't exist)

**Files:**
- Create: `backend/app/functions/herodraft_views.py`
- Modify: `backend/backend/urls.py` (add URL patterns)

**Step 1: Create API views**

```python
# backend/app/functions/herodraft_views.py
import logging
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from django.shortcuts import get_object_or_404

log = logging.getLogger(__name__)

from app.models import Game, HeroDraft, DraftTeam, HeroDraftEvent
from app.serializers import HeroDraftSerializer, HeroDraftEventSerializer
from app.functions.herodraft import (
    trigger_roll, submit_choice, submit_pick, get_available_heroes
)
from app.broadcast import broadcast_herodraft_event


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def create_herodraft(request, game_pk):
    """Create a new HeroDraft for a game."""
    game = get_object_or_404(Game, pk=game_pk)

    # Check if draft already exists
    if hasattr(game, "herodraft"):
        return Response(
            {"error": "Draft already exists for this game"},
            status=status.HTTP_400_BAD_REQUEST
        )

    # Verify user is a captain of one of the teams
    user = request.user
    if not (
        (game.radiant_team and game.radiant_team.captain == user) or
        (game.dire_team and game.dire_team.captain == user)
    ):
        return Response(
            {"error": "Only team captains can create a draft"},
            status=status.HTTP_403_FORBIDDEN
        )

    # Create the draft
    draft = HeroDraft.objects.create(game=game)

    # Create draft teams
    if game.radiant_team:
        DraftTeam.objects.create(draft=draft, tournament_team=game.radiant_team)
    if game.dire_team:
        DraftTeam.objects.create(draft=draft, tournament_team=game.dire_team)

    serializer = HeroDraftSerializer(draft)
    return Response(serializer.data, status=status.HTTP_201_CREATED)


@api_view(["GET"])
@permission_classes([AllowAny])
def get_herodraft(request, draft_pk):
    """Get HeroDraft details including all rounds and teams."""
    draft = get_object_or_404(HeroDraft, pk=draft_pk)
    serializer = HeroDraftSerializer(draft)
    return Response(serializer.data)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def set_ready(request, draft_pk):
    """Mark captain as ready."""
    draft = get_object_or_404(HeroDraft, pk=draft_pk)
    user = request.user

    # Find user's draft team
    draft_team = draft.draft_teams.filter(tournament_team__captain=user).first()
    if not draft_team:
        return Response(
            {"error": "You are not a captain in this draft"},
            status=status.HTTP_403_FORBIDDEN
        )

    draft_team.is_ready = True
    draft_team.save()

    # Check if both teams are ready
    all_ready = all(t.is_ready for t in draft.draft_teams.all())
    if all_ready:
        draft.state = "rolling"
        draft.save()

    broadcast_herodraft_event(draft, "captain_ready", draft_team)

    serializer = HeroDraftSerializer(draft)
    return Response(serializer.data)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def do_trigger_roll(request, draft_pk):
    """Trigger the coin flip."""
    draft = get_object_or_404(HeroDraft, pk=draft_pk)
    user = request.user

    if draft.state != "rolling":
        return Response(
            {"error": "Draft is not in rolling state"},
            status=status.HTTP_400_BAD_REQUEST
        )

    draft_team = draft.draft_teams.filter(tournament_team__captain=user).first()
    if not draft_team:
        return Response(
            {"error": "You are not a captain in this draft"},
            status=status.HTTP_403_FORBIDDEN
        )

    winner = trigger_roll(draft, draft_team)
    broadcast_herodraft_event(draft, "roll_result", winner)

    serializer = HeroDraftSerializer(draft)
    return Response(serializer.data)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def do_submit_choice(request, draft_pk):
    """Submit pick order or side choice."""
    draft = get_object_or_404(HeroDraft, pk=draft_pk)
    user = request.user

    if draft.state != "choosing":
        return Response(
            {"error": "Draft is not in choosing state"},
            status=status.HTTP_400_BAD_REQUEST
        )

    draft_team = draft.draft_teams.filter(tournament_team__captain=user).first()
    if not draft_team:
        return Response(
            {"error": "You are not a captain in this draft"},
            status=status.HTTP_403_FORBIDDEN
        )

    choice_type = request.data.get("choice_type")
    value = request.data.get("value")

    if choice_type not in ["pick_order", "side"]:
        return Response(
            {"error": "Invalid choice_type"},
            status=status.HTTP_400_BAD_REQUEST
        )

    if choice_type == "pick_order" and value not in ["first", "second"]:
        return Response(
            {"error": "Invalid value for pick_order"},
            status=status.HTTP_400_BAD_REQUEST
        )

    if choice_type == "side" and value not in ["radiant", "dire"]:
        return Response(
            {"error": "Invalid value for side"},
            status=status.HTTP_400_BAD_REQUEST
        )

    # Determine who can make which choice
    is_roll_winner = (draft.roll_winner_id == draft_team.id)

    # Roll winner picks first, then loser picks the remaining choice
    if is_roll_winner:
        # Roll winner can pick either (first choice)
        pass
    else:
        # Non-winner must pick the remaining choice type
        winner_chose_pick_order = draft.roll_winner.is_first_pick is not None
        winner_chose_side = draft.roll_winner.is_radiant is not None

        if choice_type == "pick_order" and winner_chose_pick_order:
            return Response(
                {"error": "Pick order already chosen by roll winner"},
                status=status.HTTP_400_BAD_REQUEST
            )
        if choice_type == "side" and winner_chose_side:
            return Response(
                {"error": "Side already chosen by roll winner"},
                status=status.HTTP_400_BAD_REQUEST
            )

    submit_choice(draft, draft_team, choice_type, value)
    broadcast_herodraft_event(draft, "choice_made", draft_team)

    # If draft state changed to "drafting", broadcast round_started
    draft.refresh_from_db()
    if draft.state == "drafting":
        first_round = draft.rounds.first()
        broadcast_herodraft_event(draft, "round_started", first_round.draft_team)

    serializer = HeroDraftSerializer(draft)
    return Response(serializer.data)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def do_submit_pick(request, draft_pk):
    """Submit a hero pick or ban."""
    draft = get_object_or_404(HeroDraft, pk=draft_pk)
    user = request.user

    if draft.state != "drafting":
        return Response(
            {"error": "Draft is not in drafting state"},
            status=status.HTTP_400_BAD_REQUEST
        )

    draft_team = draft.draft_teams.filter(tournament_team__captain=user).first()
    if not draft_team:
        return Response(
            {"error": "You are not a captain in this draft"},
            status=status.HTTP_403_FORBIDDEN
        )

    hero_id = request.data.get("hero_id")
    if not hero_id:
        return Response(
            {"error": "hero_id is required"},
            status=status.HTTP_400_BAD_REQUEST
        )

    try:
        completed_round = submit_pick(draft, draft_team, hero_id)
    except ValueError as e:
        return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    broadcast_herodraft_event(draft, "hero_selected", draft_team)

    # Check if draft completed
    draft.refresh_from_db()
    if draft.state == "completed":
        broadcast_herodraft_event(draft, "draft_completed", None)
    else:
        # Broadcast next round started
        next_round = draft.rounds.filter(state="active").first()
        if next_round:
            broadcast_herodraft_event(draft, "round_started", next_round.draft_team)

    serializer = HeroDraftSerializer(draft)
    return Response(serializer.data)


@api_view(["GET"])
@permission_classes([AllowAny])
def list_events(request, draft_pk):
    """Get all events for a draft."""
    draft = get_object_or_404(HeroDraft, pk=draft_pk)
    events = draft.events.all()
    serializer = HeroDraftEventSerializer(events, many=True)
    return Response(serializer.data)


@api_view(["GET"])
@permission_classes([AllowAny])
def list_available_heroes(request, draft_pk):
    """Get list of available hero IDs."""
    draft = get_object_or_404(HeroDraft, pk=draft_pk)
    available = get_available_heroes(draft)
    return Response({"available_heroes": available})
```

**Step 2: Add URL patterns**

```python
# backend/backend/urls.py (this is where all URLs are defined in this codebase)
# Add these imports at top of file:
from app.functions.herodraft_views import (
    create_herodraft, get_herodraft, set_ready, do_trigger_roll,
    do_submit_choice, do_submit_pick, list_events, list_available_heroes
)

# Add these URL patterns to the urlpatterns list:
urlpatterns += [
    # HeroDraft endpoints
    path("api/games/<int:game_pk>/create-herodraft/", create_herodraft, name="create_herodraft"),
    path("api/herodraft/<int:draft_pk>/", get_herodraft, name="get_herodraft"),
    path("api/herodraft/<int:draft_pk>/set-ready/", set_ready, name="herodraft_set_ready"),
    path("api/herodraft/<int:draft_pk>/trigger-roll/", do_trigger_roll, name="herodraft_trigger_roll"),
    path("api/herodraft/<int:draft_pk>/submit-choice/", do_submit_choice, name="herodraft_submit_choice"),
    path("api/herodraft/<int:draft_pk>/submit-pick/", do_submit_pick, name="herodraft_submit_pick"),
    path("api/herodraft/<int:draft_pk>/list-events/", list_events, name="herodraft_list_events"),
    path("api/herodraft/<int:draft_pk>/list-available-heroes/", list_available_heroes, name="herodraft_list_available_heroes"),
]
```

**Step 3: Commit**

```bash
git add backend/app/functions/herodraft_views.py backend/backend/urls.py
git commit -m "feat(herodraft): add HeroDraft API views and URL routes"
```

---

## Task 7: Add Broadcast Function for HeroDraft

**Files:**
- Modify: `backend/app/broadcast.py`

**Step 1: Add herodraft broadcast function**

```python
# Add to backend/app/broadcast.py

def broadcast_herodraft_event(draft, event_type: str, draft_team=None, include_state=True):
    """
    Broadcast a HeroDraft event to WebSocket consumers.

    Args:
        draft: HeroDraft instance
        event_type: Type of event (e.g., "captain_ready", "hero_selected")
        draft_team: DraftTeam instance (optional)
        include_state: Whether to include full draft state in broadcast
    """
    from app.models.herodraft import HeroDraftEvent
    from app.serializers.herodraft import HeroDraftSerializer, DraftTeamSerializer

    # Create event record
    event = HeroDraftEvent.objects.create(
        draft=draft,
        event_type=event_type,
        draft_team=draft_team,
        metadata={}
    )

    # Build payload
    payload = {
        "type": "herodraft.event",
        "event_type": event_type,
        "event_id": event.id,
        "draft_team": DraftTeamSerializer(draft_team).data if draft_team else None,
        "timestamp": event.created_at.isoformat(),
    }

    if include_state:
        payload["draft_state"] = HeroDraftSerializer(draft).data

    # Send to channel group
    channel_layer = get_channel_layer()
    room_group_name = f"herodraft_{draft.id}"

    try:
        async_to_sync(channel_layer.group_send)(room_group_name, payload)
    except Exception as e:
        logger.warning(
            f"Failed to broadcast {event_type} to channels: {e}. "
            "WebSocket clients will not receive real-time updates for this event."
        )
```

**Step 2: Commit**

```bash
git add backend/app/broadcast.py
git commit -m "feat(herodraft): add broadcast_herodraft_event function"
```

---

## Task 8: Create HeroDraft WebSocket Consumer

> ⚠️ **REVIEW FIX APPLIED**: WebSocket routes go in `backend/app/routing.py`, NOT `backend/routing.py`. Use `log` not `logger`.

**Files:**
- Modify: `backend/app/consumers.py`
- Modify: `backend/app/routing.py` (WebSocket routes are here, NOT in backend/routing.py)

**Step 1: Add HeroDraftConsumer**

```python
# Add to backend/app/consumers.py

class HeroDraftConsumer(AsyncWebsocketConsumer):
    """WebSocket consumer for Captain's Mode hero draft."""

    async def connect(self):
        self.draft_id = self.scope["url_route"]["kwargs"]["draft_id"]
        self.room_group_name = f"herodraft_{self.draft_id}"
        self.user = self.scope.get("user")

        # Verify draft exists
        draft_exists = await self.draft_exists(self.draft_id)
        if not draft_exists:
            await self.close()
            return

        # Join room group
        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        await self.accept()

        # Send initial state
        initial_state = await self.get_draft_state(self.draft_id)
        await self.send(text_data=json.dumps({
            "type": "initial_state",
            "draft_state": initial_state,
        }))

        # Mark captain as connected if authenticated
        if self.user and self.user.is_authenticated:
            await self.mark_captain_connected(self.draft_id, self.user, True)

    async def disconnect(self, close_code):
        # Mark captain as disconnected
        if self.user and self.user.is_authenticated:
            await self.mark_captain_connected(self.draft_id, self.user, False)

        # Leave room group
        await self.channel_layer.group_discard(self.room_group_name, self.channel_name)

    async def receive(self, text_data):
        # Read-only consumer - ignore incoming messages
        pass

    async def herodraft_event(self, event):
        """Handle herodraft events from channel layer."""
        await self.send(text_data=json.dumps({
            "type": "herodraft_event",
            "event_type": event.get("event_type"),
            "event_id": event.get("event_id"),
            "draft_team": event.get("draft_team"),
            "draft_state": event.get("draft_state"),
            "timestamp": event.get("timestamp"),
        }))

    async def herodraft_tick(self, event):
        """Handle tick updates during active drafting."""
        await self.send(text_data=json.dumps({
            "type": "herodraft_tick",
            "current_round": event.get("current_round"),
            "active_team_id": event.get("active_team_id"),
            "grace_time_remaining_ms": event.get("grace_time_remaining_ms"),
            "team_a_reserve_ms": event.get("team_a_reserve_ms"),
            "team_b_reserve_ms": event.get("team_b_reserve_ms"),
            "draft_state": event.get("draft_state"),
        }))

    @database_sync_to_async
    def draft_exists(self, draft_id):
        from app.models.herodraft import HeroDraft
        return HeroDraft.objects.filter(id=draft_id).exists()

    @database_sync_to_async
    def get_draft_state(self, draft_id):
        from app.models.herodraft import HeroDraft
        from app.serializers.herodraft import HeroDraftSerializer
        draft = HeroDraft.objects.get(id=draft_id)
        return HeroDraftSerializer(draft).data

    @database_sync_to_async
    def mark_captain_connected(self, draft_id, user, is_connected):
        from app.models.herodraft import HeroDraft, HeroDraftEvent
        from app.serializers.herodraft import HeroDraftSerializer

        draft = HeroDraft.objects.get(id=draft_id)
        draft_team = draft.draft_teams.filter(tournament_team__captain=user).first()

        if draft_team:
            draft_team.is_connected = is_connected
            draft_team.save()

            event_type = "captain_connected" if is_connected else "captain_disconnected"
            HeroDraftEvent.objects.create(
                draft=draft,
                event_type=event_type,
                draft_team=draft_team,
                metadata={"user_id": user.id}
            )

            # Handle pause/resume on disconnect
            if not is_connected and draft.state == "drafting":
                draft.state = "paused"
                draft.save()
                HeroDraftEvent.objects.create(
                    draft=draft,
                    event_type="draft_paused",
                    draft_team=draft_team,
                    metadata={"reason": "captain_disconnected"}
                )
            elif is_connected and draft.state == "paused":
                # Check if both captains connected
                all_connected = all(t.is_connected for t in draft.draft_teams.all())
                if all_connected:
                    draft.state = "drafting"
                    draft.save()
                    HeroDraftEvent.objects.create(
                        draft=draft,
                        event_type="draft_resumed",
                        metadata={}
                    )
```

**Step 2: Add URL route**

```python
# Add to backend/app/routing.py websocket_urlpatterns (this is where WS routes are defined):
from app.consumers import HeroDraftConsumer

websocket_urlpatterns = [
    # ... existing routes
    path("ws/herodraft/<int:draft_id>/", HeroDraftConsumer.as_asgi()),
]
```

**Step 3: Commit**

```bash
git add backend/app/consumers.py backend/app/routing.py
git commit -m "feat(herodraft): add HeroDraftConsumer for WebSocket updates"
```

---

## Task 9: Create Tick Broadcaster (Background Task)

> ⚠️ **REVIEW FIX APPLIED**: Add thread registry to prevent multiple threads per draft. Use `log` not `logger`. See Critical Fixes section.

**Files:**
- Create: `backend/app/tasks/__init__.py` (new directory)
- Create: `backend/app/tasks/herodraft_tick.py`

**Step 1: Create tasks directory and __init__.py**

```bash
mkdir -p backend/app/tasks
touch backend/app/tasks/__init__.py
```

**Step 2: Create tick broadcaster with stop mechanism**

```python
# backend/app/tasks/herodraft_tick.py
"""Background task to broadcast tick updates during active drafts."""
import asyncio
import logging
import threading
from django.utils import timezone
from channels.layers import get_channel_layer
from asgiref.sync import sync_to_async

log = logging.getLogger(__name__)

# Thread registry to prevent multiple threads per draft and enable stopping
_active_tick_tasks = {}  # draft_id -> threading.Event (stop signal)


async def broadcast_tick(draft_id: int):
    """Broadcast current timing state to all connected clients."""
    from app.models.herodraft import HeroDraft
    from app.serializers.herodraft import HeroDraftSerializer

    channel_layer = get_channel_layer()
    room_group_name = f"herodraft_{draft_id}"

    @sync_to_async
    def get_tick_data():
        draft = HeroDraft.objects.get(id=draft_id)
        if draft.state != "drafting":
            return None

        current_round = draft.rounds.filter(state="active").first()
        if not current_round:
            return None

        teams = list(draft.draft_teams.all())
        team_a = teams[0] if teams else None
        team_b = teams[1] if len(teams) > 1 else None

        # Calculate grace time remaining
        now = timezone.now()
        elapsed_ms = int((now - current_round.started_at).total_seconds() * 1000)
        grace_remaining = max(0, current_round.grace_time_ms - elapsed_ms)

        return {
            "type": "herodraft.tick",
            "current_round": current_round.round_number,
            "active_team_id": current_round.draft_team_id,
            "grace_time_remaining_ms": grace_remaining,
            "team_a_reserve_ms": team_a.reserve_time_remaining if team_a else 0,
            "team_b_reserve_ms": team_b.reserve_time_remaining if team_b else 0,
            "draft_state": draft.state,
        }

    tick_data = await get_tick_data()
    if tick_data:
        await channel_layer.group_send(room_group_name, tick_data)


async def run_tick_loop(draft_id: int):
    """Run tick broadcasts every second while draft is active."""
    from app.models.herodraft import HeroDraft

    @sync_to_async
    def is_draft_active():
        try:
            draft = HeroDraft.objects.get(id=draft_id)
            return draft.state == "drafting"
        except HeroDraft.DoesNotExist:
            return False

    while await is_draft_active():
        await broadcast_tick(draft_id)
        await asyncio.sleep(1)


def start_tick_broadcaster(draft_id: int):
    """Start the tick broadcaster for a draft."""
    # Check if already running
    if draft_id in _active_tick_tasks:
        log.debug(f"Tick broadcaster already running for draft {draft_id}")
        return

    stop_event = threading.Event()
    _active_tick_tasks[draft_id] = stop_event

    def run_in_thread():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(run_tick_loop(draft_id, stop_event))
        loop.close()
        # Cleanup when loop ends
        if draft_id in _active_tick_tasks:
            del _active_tick_tasks[draft_id]

    thread = threading.Thread(target=run_in_thread, daemon=True)
    thread.start()
    log.info(f"Started tick broadcaster for draft {draft_id}")


def stop_tick_broadcaster(draft_id: int):
    """Stop the tick broadcaster for a draft."""
    if draft_id in _active_tick_tasks:
        log.info(f"Stopping tick broadcaster for draft {draft_id}")
        _active_tick_tasks[draft_id].set()  # Signal stop
```

**Note:** Update `run_tick_loop` to accept and check the `stop_event`:
```python
async def run_tick_loop(draft_id: int, stop_event: threading.Event):
    """Run the tick loop until draft completes or is stopped."""
    while not stop_event.is_set():
        # ... existing loop logic
        await asyncio.sleep(1)
```

**Step 3: Commit**

```bash
git add backend/app/tasks/__init__.py backend/app/tasks/herodraft_tick.py
git commit -m "feat(herodraft): add background tick broadcaster with stop mechanism"
```

---

## Task 10: Create Frontend Types

> ⚠️ **REVIEW FIX APPLIED**: Use Zod schemas (not raw interfaces), use `getLogger` (not console), use TanStack Query for API. See Critical Fixes section.

**Files:**
- Create: `frontend/app/components/herodraft/schemas.ts`
- Create: `frontend/app/components/herodraft/types.ts`

**Step 1: Create Zod schemas for runtime validation**

```typescript
// frontend/app/components/herodraft/schemas.ts
import { z } from 'zod';

export const DraftTeamCaptainSchema = z.object({
  id: z.number(),
  username: z.string(),
  nickname: z.string().nullable(),
  avatar: z.string().nullable(),
});

export const DraftTeamSchema = z.object({
  id: z.number(),
  tournament_team: z.number(),
  captain: DraftTeamCaptainSchema.nullable(),
  team_name: z.string(),
  is_first_pick: z.boolean().nullable(),
  is_radiant: z.boolean().nullable(),
  reserve_time_remaining: z.number(), // milliseconds
  is_ready: z.boolean(),
  is_connected: z.boolean(),
});

export const HeroDraftRoundSchema = z.object({
  id: z.number(),
  round_number: z.number(),
  action_type: z.enum(["ban", "pick"]),
  hero_id: z.number().nullable(),
  state: z.enum(["planned", "active", "completed"]),
  grace_time_ms: z.number(),
  started_at: z.string().nullable(),
  completed_at: z.string().nullable(),
  draft_team: z.number(),
});

export const HeroDraftSchema = z.object({
  id: z.number(),
  game: z.number(),
  state: z.enum(["waiting_for_captains", "rolling", "choosing", "drafting", "paused", "completed"]),
  roll_winner: z.number().nullable(),
  draft_teams: z.array(DraftTeamSchema),
  rounds: z.array(HeroDraftRoundSchema),
  current_round: z.number().nullable(),
  created_at: z.string(),
  updated_at: z.string(),
});

// WebSocket message schemas for runtime validation
export const HeroDraftTickSchema = z.object({
  type: z.literal("herodraft_tick"),
  current_round: z.number(),
  active_team_id: z.number().nullable(),
  grace_time_remaining_ms: z.number(),
  team_a_reserve_ms: z.number(),
  team_b_reserve_ms: z.number(),
  draft_state: z.string(),
});

export const HeroDraftEventSchema = z.object({
  type: z.literal("herodraft_event"),
  event_type: z.string(),
  draft_state: HeroDraftSchema.optional(),
});
```

**Step 2: Create types derived from schemas**

```typescript
// frontend/app/components/herodraft/types.ts
import { z } from 'zod';
import {
  DraftTeamSchema,
  HeroDraftRoundSchema,
  HeroDraftSchema,
  HeroDraftTickSchema,
  HeroDraftEventSchema,
} from './schemas';

export type DraftTeam = z.infer<typeof DraftTeamSchema>;
export type HeroDraftRound = z.infer<typeof HeroDraftRoundSchema>;
export type HeroDraft = z.infer<typeof HeroDraftSchema>;
export type HeroDraftTick = z.infer<typeof HeroDraftTickSchema>;
export type HeroDraftEvent = z.infer<typeof HeroDraftEventSchema>;

// Additional utility types
export type HeroDraftState = HeroDraft["state"];
export type DraftRoundAction = HeroDraftRound["action_type"];

// Hero from dotaconstants - type-safe wrapper
export interface DotaHero {
  id: number;
  name: string;
  localized_name: string;
  primary_attr: "str" | "agi" | "int" | "all";
  attack_type: string;
  roles: string[];
  img: string;
  icon: string;
}
```

**Step 3: Commit**

```bash
git add frontend/app/components/herodraft/schemas.ts frontend/app/components/herodraft/types.ts
git commit -m "feat(herodraft): add frontend Zod schemas and TypeScript types"
```

---

## Task 11: Create HeroDraft API Hooks

> ⚠️ **REVIEW FIX APPLIED**: Use TanStack Query (useQuery/useMutation) for API calls. Follow pattern from `useTangoes.ts`. Use `getLogger` not console.

**Files:**
- Create: `frontend/app/hooks/useHeroDraft.ts`
- Create: `frontend/app/components/herodraft/api.ts`

**Step 1: Create API functions**

```typescript
// frontend/app/components/herodraft/api.ts
import api from "../api/axios";
import { HeroDraftSchema } from "./schemas";
import type { HeroDraft } from "./types";

export async function createHeroDraft(gameId: number): Promise<HeroDraft> {
  const response = await api.post(`/games/${gameId}/create-herodraft/`);
  return response.data;
}

export async function getHeroDraft(draftId: number): Promise<HeroDraft> {
  const response = await api.get(`/herodraft/${draftId}/`);
  return response.data;
}

export async function setReady(draftId: number): Promise<HeroDraft> {
  const response = await api.post(`/herodraft/${draftId}/set-ready/`);
  return response.data;
}

export async function triggerRoll(draftId: number): Promise<HeroDraft> {
  const response = await api.post(`/herodraft/${draftId}/trigger-roll/`);
  return response.data;
}

export async function submitChoice(
  draftId: number,
  choiceType: "pick_order" | "side",
  value: "first" | "second" | "radiant" | "dire"
): Promise<HeroDraft> {
  const response = await api.post(`/herodraft/${draftId}/submit-choice/`, {
    choice_type: choiceType,
    value,
  });
  return response.data;
}

export async function submitPick(
  draftId: number,
  heroId: number
): Promise<HeroDraft> {
  const response = await api.post(`/herodraft/${draftId}/submit-pick/`, {
    hero_id: heroId,
  });
  return response.data;
}

export async function listEvents(draftId: number): Promise<HeroDraftEvent[]> {
  const response = await api.get(`/herodraft/${draftId}/list-events/`);
  return response.data;
}

export async function listAvailableHeroes(
  draftId: number
): Promise<{ available_heroes: number[] }> {
  const response = await api.get(`/herodraft/${draftId}/list-available-heroes/`);
  return response.data;
}
```

**Step 2: Create TanStack Query hooks**

```typescript
// frontend/app/hooks/useHeroDraft.ts
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { getLogger } from "~/lib/logger";
import {
  createHeroDraft,
  getHeroDraft,
  setReady,
  triggerRoll,
  submitChoice,
  submitPick,
} from "~/components/herodraft/api";
import type { HeroDraft } from "~/components/herodraft/types";

const log = getLogger("useHeroDraft");

export function useHeroDraft(draftId: number | null) {
  return useQuery({
    queryKey: ["herodraft", draftId],
    queryFn: () => {
      if (!draftId) throw new Error("No draft ID");
      return getHeroDraft(draftId);
    },
    enabled: !!draftId,
  });
}

export function useCreateHeroDraft() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: createHeroDraft,
    onSuccess: (data) => {
      queryClient.setQueryData(["herodraft", data.id], data);
      log.debug("Created hero draft", data.id);
    },
  });
}

export function useSetReady() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: setReady,
    onSuccess: (data) => {
      queryClient.setQueryData(["herodraft", data.id], data);
    },
  });
}

export function useTriggerRoll() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: triggerRoll,
    onSuccess: (data) => {
      queryClient.setQueryData(["herodraft", data.id], data);
    },
  });
}

export function useSubmitChoice() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      draftId,
      choiceType,
      value,
    }: {
      draftId: number;
      choiceType: "pick_order" | "side";
      value: "first" | "second" | "radiant" | "dire";
    }) => submitChoice(draftId, choiceType, value),
    onSuccess: (data) => {
      queryClient.setQueryData(["herodraft", data.id], data);
    },
  });
}

export function useSubmitPick() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ draftId, heroId }: { draftId: number; heroId: number }) =>
      submitPick(draftId, heroId),
    onSuccess: (data) => {
      queryClient.setQueryData(["herodraft", data.id], data);
    },
  });
}

// Helper to update draft state from WebSocket events
export function useUpdateHeroDraftFromWebSocket() {
  const queryClient = useQueryClient();
  return (draft: HeroDraft) => {
    queryClient.setQueryData(["herodraft", draft.id], draft);
  };
}
```

**Step 3: Commit**

```bash
git add frontend/app/components/herodraft/api.ts frontend/app/hooks/useHeroDraft.ts
git commit -m "feat(herodraft): add frontend API functions and TanStack Query hooks"
```

---

## Task 12: Create HeroDraft WebSocket Hook

> ⚠️ **REVIEW FIX APPLIED**: Use refs for callbacks to prevent reconnection loops. Follow pattern from `useDraftWebSocket.ts`. Use `getLogger`.

**Files:**
- Create: `frontend/app/components/herodraft/hooks/useHeroDraftWebSocket.ts`

**Step 1: Create WebSocket hook with refs pattern**

```typescript
// frontend/app/components/herodraft/hooks/useHeroDraftWebSocket.ts
import { useEffect, useRef, useCallback, useState } from "react";
import { getLogger } from "~/lib/logger";
import type { HeroDraft, HeroDraftTick } from "../types";

const log = getLogger("useHeroDraftWebSocket");

interface UseHeroDraftWebSocketOptions {
  draftId: number | null;
  onStateUpdate?: (draft: HeroDraft) => void;
  onTick?: (tick: HeroDraftTick) => void;
  onEvent?: (eventType: string, draftTeam: unknown) => void;
}

export function useHeroDraftWebSocket({
  draftId,
  onStateUpdate,
  onTick,
  onEvent,
}: UseHeroDraftWebSocketOptions) {
  const wsRef = useRef<WebSocket | null>(null);
  const [isConnected, setIsConnected] = useState(false);
  const [connectionError, setConnectionError] = useState<string | null>(null);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);

  // Store callbacks in refs to avoid triggering reconnects when they change
  const onStateUpdateRef = useRef(onStateUpdate);
  const onTickRef = useRef(onTick);
  const onEventRef = useRef(onEvent);

  // Keep refs up to date without triggering reconnects
  useEffect(() => { onStateUpdateRef.current = onStateUpdate; }, [onStateUpdate]);
  useEffect(() => { onTickRef.current = onTick; }, [onTick]);
  useEffect(() => { onEventRef.current = onEvent; }, [onEvent]);

  const connect = useCallback(() => {
    if (!draftId) return;

    // Don't reconnect if already connected
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      log.debug("WebSocket already connected, skipping reconnect");
      return;
    }

    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const wsUrl = `${protocol}//${window.location.host}/ws/herodraft/${draftId}/`;

    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onopen = () => {
      setIsConnected(true);
      console.log(`HeroDraft WebSocket connected for draft ${draftId}`);
    };

    ws.onmessage = (event) => {
      const data: HeroDraftWebSocketMessage = JSON.parse(event.data);

      switch (data.type) {
        case "initial_state":
          if (data.draft_state) {
            onStateUpdate(data.draft_state);
          }
          break;

        case "herodraft_event":
          if (data.draft_state) {
            onStateUpdate(data.draft_state);
          }
          if (data.event_type) {
            onEvent(data.event_type, data.draft_team);
          }
          break;

        case "herodraft_tick":
          onTick({
            current_round: data.current_round!,
            active_team_id: data.active_team_id!,
            grace_time_remaining_ms: data.grace_time_remaining_ms!,
            team_a_reserve_ms: data.team_a_reserve_ms!,
            team_b_reserve_ms: data.team_b_reserve_ms!,
            draft_state: data.draft_state?.state || "",
          });
          break;
      }
    };

    ws.onclose = () => {
      setIsConnected(false);
      console.log("HeroDraft WebSocket disconnected, reconnecting...");
      reconnectTimeoutRef.current = setTimeout(connect, 3000);
    };

    ws.onerror = (error) => {
      console.error("HeroDraft WebSocket error:", error);
    };
  }, [draftId, onStateUpdate, onTick, onEvent]);

  useEffect(() => {
    connect();

    return () => {
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, [connect]);

  return { isConnected };
}
```

**Step 2: Commit**

```bash
git add frontend/app/components/herodraft/useHeroDraftWebSocket.ts
git commit -m "feat(herodraft): add WebSocket hook for real-time updates"
```

---

## Task 13: Create HeroDraft Zustand Store

**Files:**
- Create: `frontend/app/store/heroDraftStore.ts`

**Step 1: Create Zustand store**

```typescript
// frontend/app/store/heroDraftStore.ts
import { create } from "zustand";
import type { HeroDraft, HeroDraftTick, DraftTeam } from "~/types/herodraft";

interface HeroDraftState {
  draft: HeroDraft | null;
  tick: HeroDraftTick | null;
  selectedHeroId: number | null;
  searchQuery: string;

  // Actions
  setDraft: (draft: HeroDraft) => void;
  setTick: (tick: HeroDraftTick) => void;
  setSelectedHeroId: (heroId: number | null) => void;
  setSearchQuery: (query: string) => void;
  reset: () => void;

  // Computed helpers
  getCurrentTeam: () => DraftTeam | null;
  getOtherTeam: () => DraftTeam | null;
  isMyTurn: (userId: number) => boolean;
  getUsedHeroIds: () => number[];
}

export const useHeroDraftStore = create<HeroDraftState>((set, get) => ({
  draft: null,
  tick: null,
  selectedHeroId: null,
  searchQuery: "",

  setDraft: (draft) => set({ draft }),
  setTick: (tick) => set({ tick }),
  setSelectedHeroId: (heroId) => set({ selectedHeroId: heroId }),
  setSearchQuery: (query) => set({ searchQuery: query }),
  reset: () => set({ draft: null, tick: null, selectedHeroId: null, searchQuery: "" }),

  getCurrentTeam: () => {
    const { draft, tick } = get();
    if (!draft || !tick) return null;
    return draft.draft_teams.find((t) => t.id === tick.active_team_id) || null;
  },

  getOtherTeam: () => {
    const { draft, tick } = get();
    if (!draft || !tick) return null;
    return draft.draft_teams.find((t) => t.id !== tick.active_team_id) || null;
  },

  isMyTurn: (userId: number) => {
    const currentTeam = get().getCurrentTeam();
    return currentTeam?.captain?.id === userId;
  },

  getUsedHeroIds: () => {
    const { draft } = get();
    if (!draft) return [];
    return draft.rounds
      .filter((r) => r.hero_id !== null)
      .map((r) => r.hero_id as number);
  },
}));
```

**Step 2: Commit**

```bash
git add frontend/app/store/heroDraftStore.ts
git commit -m "feat(herodraft): add Zustand store for draft state management"
```

---

## Task 14: Create HeroGrid Component

**Files:**
- Create: `frontend/app/components/herodraft/HeroGrid.tsx`

**Step 1: Create HeroGrid component**

```typescript
// frontend/app/components/herodraft/HeroGrid.tsx
import { useMemo } from "react";
import { heroes } from "dotaconstants";
import { Input } from "~/components/ui/input";
import { useHeroDraftStore } from "~/store/heroDraftStore";
import { cn } from "~/lib/utils";

interface HeroGridProps {
  onHeroClick: (heroId: number) => void;
  disabled: boolean;
  showActionButton: boolean;
}

type HeroAttribute = "str" | "agi" | "int" | "all";

const ATTRIBUTE_ORDER: HeroAttribute[] = ["str", "agi", "int", "all"];
const ATTRIBUTE_LABELS: Record<HeroAttribute, string> = {
  str: "Strength",
  agi: "Agility",
  int: "Intelligence",
  all: "Universal",
};

export function HeroGrid({ onHeroClick, disabled, showActionButton }: HeroGridProps) {
  const { searchQuery, setSearchQuery, getUsedHeroIds, selectedHeroId, setSelectedHeroId } =
    useHeroDraftStore();

  const usedHeroIds = getUsedHeroIds();

  const heroList = useMemo(() => {
    return Object.values(heroes).map((hero: any) => ({
      id: hero.id,
      name: hero.localized_name,
      attr: hero.primary_attr as HeroAttribute,
      img: `https://cdn.cloudflare.steamstatic.com${hero.img}`,
      icon: `https://cdn.cloudflare.steamstatic.com${hero.icon}`,
    }));
  }, []);

  const filteredHeroes = useMemo(() => {
    const query = searchQuery.toLowerCase();
    return heroList.filter((hero) => hero.name.toLowerCase().includes(query));
  }, [heroList, searchQuery]);

  const heroesByAttribute = useMemo(() => {
    const grouped: Record<HeroAttribute, typeof heroList> = {
      str: [],
      agi: [],
      int: [],
      all: [],
    };
    filteredHeroes.forEach((hero) => {
      grouped[hero.attr]?.push(hero);
    });
    return grouped;
  }, [filteredHeroes]);

  const isHeroAvailable = (heroId: number) => !usedHeroIds.includes(heroId);
  const matchesSearch = (heroId: number) =>
    filteredHeroes.some((h) => h.id === heroId);

  return (
    <div className="flex flex-col h-full">
      <div className="p-2">
        <Input
          type="text"
          placeholder="Search heroes..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          className="w-full"
        />
      </div>

      <div className="flex-1 overflow-y-auto p-2 space-y-4">
        {ATTRIBUTE_ORDER.map((attr) => (
          <div key={attr}>
            <h3 className="text-sm font-semibold mb-2 text-muted-foreground">
              {ATTRIBUTE_LABELS[attr]}
            </h3>
            <div className="grid grid-cols-8 gap-1">
              {heroList
                .filter((h) => h.attr === attr)
                .map((hero) => {
                  const available = isHeroAvailable(hero.id);
                  const matches = matchesSearch(hero.id);
                  const isSelected = selectedHeroId === hero.id;

                  return (
                    <button
                      key={hero.id}
                      onClick={() => {
                        if (!disabled && available) {
                          setSelectedHeroId(hero.id);
                          onHeroClick(hero.id);
                        }
                      }}
                      disabled={disabled || !available}
                      title={hero.name}
                      className={cn(
                        "relative aspect-[4/5] rounded overflow-hidden transition-all",
                        "hover:ring-2 hover:ring-primary",
                        isSelected && "ring-2 ring-yellow-400",
                        !available && "opacity-30",
                        !matches && searchQuery && "grayscale opacity-50",
                        disabled && "cursor-not-allowed"
                      )}
                    >
                      <img
                        src={hero.icon}
                        alt={hero.name}
                        className="w-full h-full object-cover"
                      />
                      {!available && (
                        <div className="absolute inset-0 bg-black/50 flex items-center justify-center">
                          <span className="text-red-500 text-xs">✕</span>
                        </div>
                      )}
                    </button>
                  );
                })}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
```

**Step 2: Commit**

```bash
git add frontend/app/components/herodraft/HeroGrid.tsx
git commit -m "feat(herodraft): add HeroGrid component with search and filtering"
```

---

## Task 15: Create DraftPanel Component

**Files:**
- Create: `frontend/app/components/herodraft/DraftPanel.tsx`

**Step 1: Create DraftPanel component**

```typescript
// frontend/app/components/herodraft/DraftPanel.tsx
import { useMemo } from "react";
import { heroes } from "dotaconstants";
import { cn } from "~/lib/utils";
import type { HeroDraft, HeroDraftRound } from "~/types/herodraft";

interface DraftPanelProps {
  draft: HeroDraft;
  currentRound: number | null;
}

function getHeroImage(heroId: number | null): string | null {
  if (!heroId) return null;
  const hero = Object.values(heroes).find((h: any) => h.id === heroId);
  return hero ? `https://cdn.cloudflare.steamstatic.com${(hero as any).img}` : null;
}

function getHeroName(heroId: number | null): string {
  if (!heroId) return "";
  const hero = Object.values(heroes).find((h: any) => h.id === heroId);
  return hero ? (hero as any).localized_name : "";
}

export function DraftPanel({ draft, currentRound }: DraftPanelProps) {
  const radiantTeam = draft.draft_teams.find((t) => t.is_radiant);
  const direTeam = draft.draft_teams.find((t) => !t.is_radiant);

  const roundsByTeam = useMemo(() => {
    const radiantRounds: HeroDraftRound[] = [];
    const direRounds: HeroDraftRound[] = [];

    draft.rounds.forEach((round) => {
      const team = draft.draft_teams.find((t) => t.id === round.draft_team);
      if (team?.is_radiant) {
        radiantRounds.push(round);
      } else {
        direRounds.push(round);
      }
    });

    return { radiant: radiantRounds, dire: direRounds };
  }, [draft]);

  return (
    <div className="h-full flex flex-col bg-black/80 rounded-lg overflow-hidden">
      {/* Headers */}
      <div className="flex">
        <div className="flex-1 p-3 text-center">
          <h3 className="text-lg font-bold text-green-400 drop-shadow-[0_0_10px_rgba(34,197,94,0.5)]">
            RADIANT
          </h3>
          <p className="text-sm text-muted-foreground">
            {radiantTeam?.captain?.nickname || radiantTeam?.captain?.username}
          </p>
        </div>
        <div className="flex-1 p-3 text-center">
          <h3 className="text-lg font-bold text-red-400 drop-shadow-[0_0_10px_rgba(239,68,68,0.5)]">
            DIRE
          </h3>
          <p className="text-sm text-muted-foreground">
            {direTeam?.captain?.nickname || direTeam?.captain?.username}
          </p>
        </div>
      </div>

      {/* Draft slots */}
      <div className="flex-1 overflow-y-auto p-2">
        {draft.rounds.map((round) => {
          const isRadiant = draft.draft_teams.find(
            (t) => t.id === round.draft_team
          )?.is_radiant;
          const heroImg = getHeroImage(round.hero_id);
          const heroName = getHeroName(round.hero_id);
          const isActive = round.round_number === currentRound;
          const isPick = round.action_type === "pick";

          return (
            <div
              key={round.id}
              className={cn(
                "flex items-center gap-2 py-1",
                isActive && "bg-yellow-500/20 rounded"
              )}
            >
              {/* Radiant slot */}
              <div
                className={cn(
                  "flex-1 flex justify-end",
                  !isRadiant && "invisible"
                )}
              >
                {isRadiant && (
                  <div
                    className={cn(
                      "rounded border-2 overflow-hidden transition-all",
                      isPick ? "w-16 h-10" : "w-12 h-8",
                      round.state === "completed"
                        ? "border-green-500/50"
                        : isActive
                        ? "border-yellow-400 animate-pulse"
                        : "border-gray-700",
                      round.action_type === "ban" && round.state === "completed" && "grayscale"
                    )}
                    title={heroName}
                  >
                    {heroImg ? (
                      <img
                        src={heroImg}
                        alt={heroName}
                        className="w-full h-full object-cover"
                      />
                    ) : (
                      <div className="w-full h-full bg-gray-800 flex items-center justify-center text-xs text-muted-foreground">
                        {round.action_type === "ban" ? "BAN" : "PICK"}
                      </div>
                    )}
                  </div>
                )}
              </div>

              {/* Round number */}
              <div
                className={cn(
                  "w-8 text-center text-sm font-mono",
                  isActive ? "text-yellow-400 font-bold" : "text-muted-foreground"
                )}
              >
                {round.round_number}
              </div>

              {/* Dire slot */}
              <div
                className={cn(
                  "flex-1 flex justify-start",
                  isRadiant && "invisible"
                )}
              >
                {!isRadiant && (
                  <div
                    className={cn(
                      "rounded border-2 overflow-hidden transition-all",
                      isPick ? "w-16 h-10" : "w-12 h-8",
                      round.state === "completed"
                        ? "border-red-500/50"
                        : isActive
                        ? "border-yellow-400 animate-pulse"
                        : "border-gray-700",
                      round.action_type === "ban" && round.state === "completed" && "grayscale"
                    )}
                    title={heroName}
                  >
                    {heroImg ? (
                      <img
                        src={heroImg}
                        alt={heroName}
                        className="w-full h-full object-cover"
                      />
                    ) : (
                      <div className="w-full h-full bg-gray-800 flex items-center justify-center text-xs text-muted-foreground">
                        {round.action_type === "ban" ? "BAN" : "PICK"}
                      </div>
                    )}
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
```

**Step 2: Commit**

```bash
git add frontend/app/components/herodraft/DraftPanel.tsx
git commit -m "feat(herodraft): add DraftPanel component with Dota-style layout"
```

---

## Task 16: Create DraftTopBar Component

**Files:**
- Create: `frontend/app/components/herodraft/DraftTopBar.tsx`

**Step 1: Create DraftTopBar component**

```typescript
// frontend/app/components/herodraft/DraftTopBar.tsx
import { CaptainPopover } from "~/components/tournament/CaptainPopover";
import { cn } from "~/lib/utils";
import type { HeroDraft, HeroDraftTick } from "~/types/herodraft";

interface DraftTopBarProps {
  draft: HeroDraft;
  tick: HeroDraftTick | null;
}

function formatTime(ms: number): string {
  const totalSeconds = Math.max(0, Math.floor(ms / 1000));
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes}:${seconds.toString().padStart(2, "0")}`;
}

export function DraftTopBar({ draft, tick }: DraftTopBarProps) {
  const teamA = draft.draft_teams[0];
  const teamB = draft.draft_teams[1];

  const activeTeamId = tick?.active_team_id;
  const graceRemaining = tick?.grace_time_remaining_ms ?? 0;

  const teamAReserve = tick?.team_a_reserve_ms ?? teamA?.reserve_time_remaining ?? 90000;
  const teamBReserve = tick?.team_b_reserve_ms ?? teamB?.reserve_time_remaining ?? 90000;

  const currentAction = draft.current_round?.action_type ?? "pick";

  return (
    <div className="bg-black/90 border-b border-gray-800">
      {/* Row 1: Captains */}
      <div className="grid grid-cols-5 items-center p-2">
        {/* Team A Captain */}
        <div className="flex items-center gap-2">
          {teamA?.captain && (
            <CaptainPopover captain={teamA.captain}>
              <button className="flex items-center gap-2 hover:bg-white/10 rounded p-1">
                <img
                  src={teamA.captain.avatar || "/default-avatar.png"}
                  alt={teamA.captain.username}
                  className="w-10 h-10 rounded-full"
                />
                <div className="text-left">
                  <p className="font-semibold text-sm">
                    {teamA.captain.nickname || teamA.captain.username}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    {teamA.is_radiant ? "Radiant" : "Dire"}
                  </p>
                </div>
              </button>
            </CaptainPopover>
          )}
          {activeTeamId === teamA?.id && (
            <span className="text-yellow-400 text-sm animate-pulse">◀ PICKING</span>
          )}
        </div>

        {/* Team A Bans/Picks summary */}
        <div className="text-center text-xs text-muted-foreground">
          {draft.rounds
            .filter((r) => r.draft_team === teamA?.id && r.state === "completed")
            .length}{" "}
          / {draft.rounds.filter((r) => r.draft_team === teamA?.id).length}
        </div>

        {/* VS / Current action */}
        <div className="text-center">
          <span className="text-2xl font-bold text-muted-foreground">VS</span>
        </div>

        {/* Team B Bans/Picks summary */}
        <div className="text-center text-xs text-muted-foreground">
          {draft.rounds
            .filter((r) => r.draft_team === teamB?.id && r.state === "completed")
            .length}{" "}
          / {draft.rounds.filter((r) => r.draft_team === teamB?.id).length}
        </div>

        {/* Team B Captain */}
        <div className="flex items-center gap-2 justify-end">
          {activeTeamId === teamB?.id && (
            <span className="text-yellow-400 text-sm animate-pulse">PICKING ▶</span>
          )}
          {teamB?.captain && (
            <CaptainPopover captain={teamB.captain}>
              <button className="flex items-center gap-2 hover:bg-white/10 rounded p-1">
                <div className="text-right">
                  <p className="font-semibold text-sm">
                    {teamB.captain.nickname || teamB.captain.username}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    {teamB.is_radiant ? "Radiant" : "Dire"}
                  </p>
                </div>
                <img
                  src={teamB.captain.avatar || "/default-avatar.png"}
                  alt={teamB.captain.username}
                  className="w-10 h-10 rounded-full"
                />
              </button>
            </CaptainPopover>
          )}
        </div>
      </div>

      {/* Row 2: Timers */}
      <div className="grid grid-cols-5 items-center p-2 border-t border-gray-800">
        {/* Team A Reserve */}
        <div
          className={cn(
            "text-center font-mono text-lg",
            teamAReserve < 30000 && "text-red-400"
          )}
        >
          <span className="text-xs text-muted-foreground block">Reserve</span>
          {formatTime(teamAReserve)}
        </div>

        <div />

        {/* Current pick timer */}
        <div className="text-center">
          <span className="text-xs text-muted-foreground block uppercase">
            {currentAction} Time
          </span>
          <span
            className={cn(
              "font-mono text-2xl font-bold",
              graceRemaining < 10000 ? "text-red-400" : "text-yellow-400"
            )}
          >
            {formatTime(graceRemaining)}
          </span>
        </div>

        <div />

        {/* Team B Reserve */}
        <div
          className={cn(
            "text-center font-mono text-lg",
            teamBReserve < 30000 && "text-red-400"
          )}
        >
          <span className="text-xs text-muted-foreground block">Reserve</span>
          {formatTime(teamBReserve)}
        </div>
      </div>
    </div>
  );
}
```

**Step 2: Commit**

```bash
git add frontend/app/components/herodraft/DraftTopBar.tsx
git commit -m "feat(herodraft): add DraftTopBar component with captain info and timers"
```

---

## Task 17: Create HeroDraftModal Component

**Files:**
- Create: `frontend/app/components/herodraft/HeroDraftModal.tsx`

**Step 1: Create HeroDraftModal component**

```typescript
// frontend/app/components/herodraft/HeroDraftModal.tsx
import { useEffect, useCallback, useState } from "react";
import { useNavigate, useParams } from "react-router";
import { toast } from "sonner";
import { Dialog, DialogContent } from "~/components/ui/dialog";
import { Button } from "~/components/ui/button";
import { useHeroDraftStore } from "~/store/heroDraftStore";
import { useHeroDraftWebSocket } from "./useHeroDraftWebSocket";
import { useUserStore } from "~/store/userStore";
import { DraftTopBar } from "./DraftTopBar";
import { HeroGrid } from "./HeroGrid";
import { DraftPanel } from "./DraftPanel";
import { submitPick, setReady, triggerRoll, submitChoice } from "./api";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "~/components/ui/alert-dialog";

interface HeroDraftModalProps {
  draftId: number;
  open: boolean;
  onClose: () => void;
}

export function HeroDraftModal({ draftId, open, onClose }: HeroDraftModalProps) {
  const navigate = useNavigate();
  const { user } = useUserStore();
  const { draft, tick, setDraft, setTick, selectedHeroId, setSelectedHeroId } =
    useHeroDraftStore();

  const [confirmHeroId, setConfirmHeroId] = useState<number | null>(null);

  const handleStateUpdate = useCallback(
    (newDraft: any) => {
      setDraft(newDraft);
    },
    [setDraft]
  );

  const handleTick = useCallback(
    (newTick: any) => {
      setTick(newTick);
    },
    [setTick]
  );

  const handleEvent = useCallback((eventType: string, draftTeam: any) => {
    switch (eventType) {
      case "captain_ready":
        toast.info(`${draftTeam?.captain?.username} is ready`);
        break;
      case "roll_result":
        toast.success(`${draftTeam?.captain?.username} won the coin flip!`);
        break;
      case "hero_selected":
        toast.info(`Hero selected`);
        break;
      case "draft_completed":
        toast.success("Draft completed!");
        break;
    }
  }, []);

  const { isConnected } = useHeroDraftWebSocket({
    draftId,
    onStateUpdate: handleStateUpdate,
    onTick: handleTick,
    onEvent: handleEvent,
  });

  const handleHeroClick = (heroId: number) => {
    if (!draft || !user) return;

    const myTeam = draft.draft_teams.find((t) => t.captain?.id === user.id);
    if (!myTeam) return;

    const currentRound = draft.current_round;
    if (!currentRound || currentRound.draft_team !== myTeam.id) {
      toast.error("It's not your turn");
      return;
    }

    setConfirmHeroId(heroId);
  };

  const handleConfirmPick = async () => {
    if (!confirmHeroId || !draft) return;

    try {
      const updated = await submitPick(draft.id, confirmHeroId);
      setDraft(updated);
      setConfirmHeroId(null);
      setSelectedHeroId(null);
    } catch (error: any) {
      toast.error(error.response?.data?.error || "Failed to submit pick");
    }
  };

  const handleReady = async () => {
    if (!draft) return;
    try {
      const updated = await setReady(draft.id);
      setDraft(updated);
      toast.success("You are ready!");
    } catch (error: any) {
      toast.error(error.response?.data?.error || "Failed to set ready");
    }
  };

  const handleTriggerRoll = async () => {
    if (!draft) return;
    try {
      const updated = await triggerRoll(draft.id);
      setDraft(updated);
    } catch (error: any) {
      toast.error(error.response?.data?.error || "Failed to trigger roll");
    }
  };

  const handleChoiceSubmit = async (
    choiceType: "pick_order" | "side",
    value: string
  ) => {
    if (!draft) return;
    try {
      const updated = await submitChoice(
        draft.id,
        choiceType,
        value as "first" | "second" | "radiant" | "dire"
      );
      setDraft(updated);
    } catch (error: any) {
      toast.error(error.response?.data?.error || "Failed to submit choice");
    }
  };

  const isMyTurn = draft?.current_round
    ? draft.draft_teams.find((t) => t.id === draft.current_round?.draft_team)
        ?.captain?.id === user?.id
    : false;

  const isCaptain = draft?.draft_teams.some((t) => t.captain?.id === user?.id);
  const myTeam = draft?.draft_teams.find((t) => t.captain?.id === user?.id);

  const currentAction = draft?.current_round?.action_type;

  return (
    <>
      <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
        <DialogContent className="max-w-[100vw] max-h-[100vh] w-screen h-screen p-0 gap-0">
          {draft && (
            <div className="flex flex-col h-full bg-gray-900">
              {/* Top Bar */}
              <DraftTopBar draft={draft} tick={tick} />

              {/* Pre-draft phases */}
              {draft.state === "waiting_for_captains" && (
                <div className="flex-1 flex items-center justify-center">
                  <div className="text-center space-y-4">
                    <h2 className="text-2xl font-bold">Waiting for Captains</h2>
                    <div className="flex gap-8">
                      {draft.draft_teams.map((team) => (
                        <div key={team.id} className="text-center">
                          <p className="font-semibold">
                            {team.captain?.nickname || team.captain?.username}
                          </p>
                          <p
                            className={
                              team.is_ready ? "text-green-400" : "text-yellow-400"
                            }
                          >
                            {team.is_ready ? "Ready" : "Not Ready"}
                          </p>
                        </div>
                      ))}
                    </div>
                    {isCaptain && !myTeam?.is_ready && (
                      <Button onClick={handleReady}>Ready</Button>
                    )}
                  </div>
                </div>
              )}

              {draft.state === "rolling" && (
                <div className="flex-1 flex items-center justify-center">
                  <div className="text-center space-y-4">
                    <h2 className="text-2xl font-bold">Both Captains Ready!</h2>
                    <p>Click to trigger the coin flip</p>
                    {isCaptain && (
                      <Button onClick={handleTriggerRoll}>Flip Coin</Button>
                    )}
                  </div>
                </div>
              )}

              {draft.state === "choosing" && (
                <div className="flex-1 flex items-center justify-center">
                  <div className="text-center space-y-4">
                    <h2 className="text-2xl font-bold">
                      {draft.roll_winner?.captain?.username} won the flip!
                    </h2>
                    {draft.roll_winner?.id === myTeam?.id ? (
                      <div className="space-y-2">
                        <p>Choose your preference:</p>
                        <div className="flex gap-4 justify-center">
                          <Button
                            onClick={() => handleChoiceSubmit("pick_order", "first")}
                          >
                            First Pick
                          </Button>
                          <Button
                            onClick={() => handleChoiceSubmit("pick_order", "second")}
                          >
                            Second Pick
                          </Button>
                          <Button
                            onClick={() => handleChoiceSubmit("side", "radiant")}
                          >
                            Radiant
                          </Button>
                          <Button
                            onClick={() => handleChoiceSubmit("side", "dire")}
                          >
                            Dire
                          </Button>
                        </div>
                      </div>
                    ) : myTeam && !draft.roll_winner ? (
                      <p>Waiting for {draft.roll_winner?.captain?.username} to choose...</p>
                    ) : myTeam ? (
                      <div className="space-y-2">
                        <p>Choose the remaining option:</p>
                        <div className="flex gap-4 justify-center">
                          {draft.roll_winner?.is_first_pick === null && (
                            <>
                              <Button
                                onClick={() =>
                                  handleChoiceSubmit("pick_order", "first")
                                }
                              >
                                First Pick
                              </Button>
                              <Button
                                onClick={() =>
                                  handleChoiceSubmit("pick_order", "second")
                                }
                              >
                                Second Pick
                              </Button>
                            </>
                          )}
                          {draft.roll_winner?.is_radiant === null && (
                            <>
                              <Button
                                onClick={() => handleChoiceSubmit("side", "radiant")}
                              >
                                Radiant
                              </Button>
                              <Button
                                onClick={() => handleChoiceSubmit("side", "dire")}
                              >
                                Dire
                              </Button>
                            </>
                          )}
                        </div>
                      </div>
                    ) : (
                      <p>Spectating...</p>
                    )}
                  </div>
                </div>
              )}

              {/* Main draft area */}
              {(draft.state === "drafting" || draft.state === "paused" || draft.state === "completed") && (
                <div className="flex-1 flex overflow-hidden">
                  {/* Left: Hero Grid */}
                  <div className="flex-1 border-r border-gray-800">
                    <HeroGrid
                      onHeroClick={handleHeroClick}
                      disabled={!isMyTurn || draft.state !== "drafting"}
                      showActionButton={isCaptain ?? false}
                    />
                  </div>

                  {/* Right: Draft Panel */}
                  <div className="w-80">
                    <DraftPanel
                      draft={draft}
                      currentRound={tick?.current_round ?? null}
                    />
                  </div>
                </div>
              )}

              {/* Bottom: Chat placeholder */}
              <div className="h-20 border-t border-gray-800 flex items-center justify-center text-muted-foreground">
                <span>💬 Team Chat - Under Construction 🚧</span>
              </div>

              {/* Paused overlay */}
              {draft.state === "paused" && (
                <div className="absolute inset-0 bg-black/70 flex items-center justify-center">
                  <div className="text-center">
                    <h2 className="text-3xl font-bold text-yellow-400">
                      Draft Paused
                    </h2>
                    <p className="text-muted-foreground">
                      Waiting for captain to reconnect...
                    </p>
                  </div>
                </div>
              )}

              {/* Connection status */}
              {!isConnected && (
                <div className="absolute top-2 right-2 bg-red-500/80 text-white px-2 py-1 rounded text-sm">
                  Reconnecting...
                </div>
              )}
            </div>
          )}
        </DialogContent>
      </Dialog>

      {/* Confirm pick dialog */}
      <AlertDialog
        open={confirmHeroId !== null}
        onOpenChange={() => setConfirmHeroId(null)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              {currentAction === "ban" ? "Ban" : "Pick"} this hero?
            </AlertDialogTitle>
            <AlertDialogDescription>
              Are you sure you want to {currentAction} this hero?
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={handleConfirmPick}>
              Confirm {currentAction === "ban" ? "Ban" : "Pick"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
```

**Step 2: Commit**

```bash
git add frontend/app/components/herodraft/HeroDraftModal.tsx
git commit -m "feat(herodraft): add HeroDraftModal full-screen component"
```

---

## Task 18: Integrate with Bracket View

> ⚠️ **REVIEW FIX APPLIED**: The component is `MatchNode.tsx` at `frontend/app/components/bracket/nodes/MatchNode.tsx` (NOT `BracketGameNode.tsx`). Integrate with `MatchStatsModal` for the "View Draft" button.

**Files:**
- Modify: `frontend/app/components/bracket/nodes/MatchNode.tsx`
- Modify: `frontend/app/components/bracket/modals/MatchStatsModal.tsx`
- Modify: `frontend/app/components/bracket/types.ts` (add `herodraft_id` to BracketMatch type)

**Step 1: Update BracketMatch type**

```typescript
// frontend/app/components/bracket/types.ts
// Add to BracketMatch interface:
export interface BracketMatch {
  // ... existing fields
  herodraft_id?: number;
}
```

**Step 2: Add "View Draft" button to MatchStatsModal**

The MatchStatsModal already displays match details. Add a button to open the HeroDraft modal:

```typescript
// Add to the bracket game node component
import { useState } from "react";
import { HeroDraftModal } from "~/components/herodraft/HeroDraftModal";
import { createHeroDraft, getHeroDraft } from "~/components/herodraft/api";

// Inside component:
const [draftModalOpen, setDraftModalOpen] = useState(false);
const [draftId, setDraftId] = useState<number | null>(null);

const handleOpenDraft = async () => {
  try {
    // Check if draft exists
    if (game.herodraft_id) {
      setDraftId(game.herodraft_id);
    } else {
      // Create new draft
      const draft = await createHeroDraft(game.id);
      setDraftId(draft.id);
    }
    setDraftModalOpen(true);
  } catch (error) {
    console.error("Failed to open draft:", error);
  }
};

// In the render:
<Button variant="outline" size="sm" onClick={handleOpenDraft}>
  View Draft
</Button>

{draftId && (
  <HeroDraftModal
    draftId={draftId}
    open={draftModalOpen}
    onClose={() => setDraftModalOpen(false)}
  />
)}
```

**Step 2: Commit**

```bash
git add frontend/app/components/bracket/
git commit -m "feat(herodraft): integrate HeroDraft modal with bracket view"
```

---

## Task 19: Add URL Routing for Draft Modal

**Files:**
- Modify: `frontend/app/routes.ts` or relevant routing file

**Step 1: Add route for draft view**

```typescript
// Add route that opens modal and syncs URL
// Route: /tournament/:tournamentId/games/:gameId/draft

// In the game/tournament page component:
const { draftId } = useParams();

useEffect(() => {
  if (draftId) {
    // Open modal with this draft
    setDraftModalOpen(true);
    setDraftId(Number(draftId));
  }
}, [draftId]);

// When opening modal, update URL:
const handleOpenDraft = async (gameId: number) => {
  // ... create or get draft
  navigate(`/tournament/${tournamentId}/games/${gameId}/draft`);
};

// When closing modal, restore URL:
const handleCloseDraft = () => {
  setDraftModalOpen(false);
  navigate(`/tournament/${tournamentId}`);
};
```

**Step 2: Commit**

```bash
git add frontend/app/routes.ts
git commit -m "feat(herodraft): add URL routing for draft modal"
```

---

## Task 20: Add Auto-Random Pick on Timeout

**Files:**
- Modify: `backend/app/tasks/herodraft_tick.py`
- Modify: `backend/app/functions/herodraft.py`

**Step 1: Add timeout check to tick loop**

```python
# Add to backend/app/tasks/herodraft_tick.py

async def check_timeout(draft_id: int):
    """Check if current round has timed out and auto-pick if needed."""
    from app.models.herodraft import HeroDraft, HeroDraftEvent
    from app.functions.herodraft import auto_random_pick

    @sync_to_async
    def check_and_auto_pick():
        draft = HeroDraft.objects.get(id=draft_id)
        if draft.state != "drafting":
            return None

        current_round = draft.rounds.filter(state="active").first()
        if not current_round:
            return None

        now = timezone.now()
        elapsed_ms = int((now - current_round.started_at).total_seconds() * 1000)

        team = current_round.draft_team
        total_time = current_round.grace_time_ms + team.reserve_time_remaining

        if elapsed_ms >= total_time:
            # Time's up - auto pick
            return auto_random_pick(draft, team)

        return None

    return await check_and_auto_pick()


async def run_tick_loop(draft_id: int):
    """Run tick broadcasts every second while draft is active."""
    from app.models.herodraft import HeroDraft

    @sync_to_async
    def is_draft_active():
        try:
            draft = HeroDraft.objects.get(id=draft_id)
            return draft.state == "drafting"
        except HeroDraft.DoesNotExist:
            return False

    while await is_draft_active():
        await broadcast_tick(draft_id)
        await check_timeout(draft_id)
        await asyncio.sleep(1)
```

**Step 2: Add auto_random_pick function**

```python
# Add to backend/app/functions/herodraft.py

def auto_random_pick(draft: HeroDraft, team: DraftTeam) -> HeroDraftRound:
    """Auto-pick a random available hero when time runs out."""
    available = get_available_heroes(draft)
    if not available:
        raise ValueError("No heroes available")

    hero_id = random.choice(available)

    # Record timeout event
    HeroDraftEvent.objects.create(
        draft=draft,
        event_type="round_timeout",
        draft_team=team,
        metadata={"auto_picked_hero": hero_id}
    )

    # Submit the pick
    return submit_pick(draft, team, hero_id)
```

**Step 3: Commit**

```bash
git add backend/app/tasks/herodraft_tick.py backend/app/functions/herodraft.py
git commit -m "feat(herodraft): add auto-random pick on timeout"
```

---

## Task 21: Write Integration Tests

**Files:**
- Create: `backend/app/tests/test_herodraft_integration.py`

**Step 1: Write integration tests**

```python
# backend/app/tests/test_herodraft_integration.py
from django.test import TestCase
from rest_framework.test import APIClient
from app.models import Game, Tournament, Team, CustomUser
from app.models.herodraft import HeroDraft, DraftTeam


class HeroDraftAPITest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.captain1 = CustomUser.objects.create_user(
            username="captain1", password="test123"
        )
        self.captain2 = CustomUser.objects.create_user(
            username="captain2", password="test123"
        )
        self.tournament = Tournament.objects.create(name="Test Tournament")
        self.team1 = Team.objects.create(
            tournament=self.tournament, captain=self.captain1
        )
        self.team2 = Team.objects.create(
            tournament=self.tournament, captain=self.captain2
        )
        self.game = Game.objects.create(
            tournament=self.tournament,
            radiant_team=self.team1,
            dire_team=self.team2
        )

    def test_create_herodraft(self):
        """Captain can create a hero draft for a game."""
        self.client.force_authenticate(user=self.captain1)

        response = self.client.post(f"/api/games/{self.game.id}/create-herodraft/")

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["state"], "waiting_for_captains")
        self.assertEqual(len(response.data["draft_teams"]), 2)

    def test_non_captain_cannot_create(self):
        """Non-captain cannot create a draft."""
        other_user = CustomUser.objects.create_user(username="other", password="test")
        self.client.force_authenticate(user=other_user)

        response = self.client.post(f"/api/games/{self.game.id}/create-herodraft/")

        self.assertEqual(response.status_code, 403)

    def test_full_ready_flow(self):
        """Both captains can ready up and state changes to rolling."""
        # Create draft
        self.client.force_authenticate(user=self.captain1)
        create_response = self.client.post(f"/api/games/{self.game.id}/create-herodraft/")
        draft_id = create_response.data["id"]

        # Captain 1 ready
        response = self.client.post(f"/api/herodraft/{draft_id}/set-ready/")
        self.assertEqual(response.data["state"], "waiting_for_captains")

        # Captain 2 ready
        self.client.force_authenticate(user=self.captain2)
        response = self.client.post(f"/api/herodraft/{draft_id}/set-ready/")
        self.assertEqual(response.data["state"], "rolling")

    def test_roll_and_choose_flow(self):
        """Roll and choice flow works correctly."""
        # Setup: create draft and ready up
        self.client.force_authenticate(user=self.captain1)
        create_response = self.client.post(f"/api/games/{self.game.id}/create-herodraft/")
        draft_id = create_response.data["id"]

        self.client.post(f"/api/herodraft/{draft_id}/set-ready/")
        self.client.force_authenticate(user=self.captain2)
        self.client.post(f"/api/herodraft/{draft_id}/set-ready/")

        # Trigger roll
        response = self.client.post(f"/api/herodraft/{draft_id}/trigger-roll/")
        self.assertEqual(response.data["state"], "choosing")
        self.assertIsNotNone(response.data["roll_winner"])

        # Winner chooses
        winner_id = response.data["roll_winner"]["id"]
        winner_captain = self.captain1 if response.data["roll_winner"]["captain"]["id"] == self.captain1.id else self.captain2
        loser_captain = self.captain2 if winner_captain == self.captain1 else self.captain1

        self.client.force_authenticate(user=winner_captain)
        response = self.client.post(
            f"/api/herodraft/{draft_id}/submit-choice/",
            {"choice_type": "pick_order", "value": "first"}
        )

        # Loser chooses remaining
        self.client.force_authenticate(user=loser_captain)
        response = self.client.post(
            f"/api/herodraft/{draft_id}/submit-choice/",
            {"choice_type": "side", "value": "radiant"}
        )

        self.assertEqual(response.data["state"], "drafting")
        self.assertEqual(len(response.data["rounds"]), 24)
```

**Step 2: Run tests**

Run: `cd /home/kettle/git_repos/website/.worktrees/herodraft && source .venv/bin/activate && cd backend && DISABLE_CACHE=true python manage.py test app.tests.test_herodraft_integration -v 2`

**Step 3: Commit**

```bash
git add backend/app/tests/test_herodraft_integration.py
git commit -m "test(herodraft): add integration tests for API flow"
```

---

## Task 22: Run Full Test Suite

**Step 1: Run all tests**

Run: `cd /home/kettle/git_repos/website/.worktrees/herodraft && source .venv/bin/activate && cd backend && DISABLE_CACHE=true python manage.py test app.tests -v 2`

**Step 2: Fix any failing tests**

Address any failures before proceeding.

**Step 3: Commit any fixes**

```bash
git add -A
git commit -m "fix(herodraft): address test failures"
```

---

## Summary

This implementation plan covers:

1. **Backend Models** (Tasks 1-3): HeroDraft, DraftTeam, HeroDraftRound, HeroDraftEvent
2. **Draft Logic** (Task 4): Captain's Mode sequence builder and action functions
3. **Serializers** (Task 5): Full serialization for API responses
4. **API Views** (Tasks 6-7): REST endpoints for all draft actions
5. **WebSocket** (Tasks 8-9): Real-time updates and tick broadcasting
6. **Frontend Types** (Task 10): TypeScript interfaces
7. **Frontend API** (Tasks 11-12): API hooks and WebSocket integration
8. **State Management** (Task 13): Zustand store
9. **UI Components** (Tasks 14-17): HeroGrid, DraftPanel, DraftTopBar, HeroDraftModal
10. **Integration** (Tasks 18-19): Bracket integration and URL routing
11. **Timeout Logic** (Task 20): Auto-random pick on timeout
12. **Testing** (Tasks 21-22): Integration tests and full test suite

Each task follows TDD with explicit file paths, complete code, and exact commands.

---

## Post-Implementation Code Review Fixes

After implementation, a comprehensive 3-agent code review identified issues across Backend, Frontend, and Integration layers. The following fixes were applied:

### Critical Fixes (C1-C4)

**C1: roll_winner Schema Mismatch** ✅
- **Issue:** Backend returned full DraftTeam object for `roll_winner`, but frontend schema expected just an ID
- **Fix:** Updated `schemas.ts` to use `DraftTeamSchema.nullable()` and modified `HeroDraftModal.tsx` to use the object directly
- **Files:** `frontend/app/components/herodraft/schemas.ts`, `frontend/app/components/herodraft/HeroDraftModal.tsx`

**C2: Team Ordering Indeterminacy in Tick Data** ✅
- **Issue:** `draft_teams.all()` had non-deterministic order, causing reserve times to mismatch teams
- **Fix:** Added `.order_by("id")` to teams query and included explicit `team_a_id`/`team_b_id` in tick data
- **Files:** `backend/app/tasks/herodraft_tick.py`, `backend/app/consumers.py`, `frontend/app/components/herodraft/schemas.ts`

**C3: Array Bounds Checks for draft_teams Access** ✅
- **Issue:** Direct array access `draft.draft_teams[0]` could crash if array empty
- **Fix:** Added optional chaining `draft.draft_teams?.[0] ?? null` and `getTeamReserve()` function to match by team ID
- **Files:** `frontend/app/components/herodraft/DraftTopBar.tsx`

**C4: Missing Loading States During API Calls** ✅
- **Issue:** Users could double-click buttons during async operations
- **Fix:** Added `isSubmitting` state with `try/finally` blocks and `disabled={isSubmitting}` to all action buttons
- **Files:** `frontend/app/components/herodraft/HeroDraftModal.tsx`

### Important Fixes (I1-I8)

**I1: WebSocket State Drift on Reconnection** ✅
- **Issue:** State could drift if `initial_state` wasn't properly handled
- **Fix:** Added documentation comment clarifying full state replace on `initial_state` message
- **Files:** `frontend/app/components/herodraft/hooks/useHeroDraftWebSocket.ts`

**I2: Add WebSocket Consumer Tests** ✅
- **Issue:** No test coverage for WebSocket consumer behavior
- **Fix:** Created `test_herodraft_consumers.py` with 7 test cases covering connection, groups, and message handling
- **Files:** `backend/app/tests/test_herodraft_consumers.py` (new)

**I3: Add Timeout Tests** ✅
- **Issue:** No tests for timeout and tick broadcaster functionality
- **Fix:** Created `test_herodraft_tick.py` with tests for timeout handling and tick broadcasting
- **Files:** `backend/app/tests/test_herodraft_tick.py` (new)

**I4: Add Zod Validation on WebSocket Messages** ✅
- **Issue:** WebSocket messages weren't validated at runtime
- **Fix:** Added discriminated union schema `HeroDraftWebSocketMessageSchema` and `safeParse` validation with error logging
- **Files:** `frontend/app/components/herodraft/schemas.ts`, `frontend/app/components/herodraft/hooks/useHeroDraftWebSocket.ts`

**I5: Add dotaconstants Type Declarations** ✅
- **Issue:** Missing TypeScript types for `dotaconstants` package
- **Fix:** Created `dotaconstants.d.ts` module declaration with full hero data interface
- **Files:** `frontend/app/types/dotaconstants.d.ts` (new)

**I6: Add Abandon/Forfeit Draft Mechanism** ✅
- **Issue:** No way to abandon a draft that can't be completed
- **Fix:** Added "abandoned" state to model, created `abandon_draft` API endpoint, added frontend API function
- **Files:** `backend/app/models.py`, `backend/app/functions/herodraft_views.py`, `backend/backend/urls.py`, `frontend/app/components/herodraft/api.ts`, `frontend/app/components/herodraft/schemas.ts`

**I7: Add URL Route for Deep-Linking to Draft** ✅
- **Issue:** No way to share a direct link to an active draft
- **Fix:** Added URL parsing for `/tournament/:pk/bracket/draft/:draftId`, `pendingDraftId` state in store, and auto-open logic in BracketView/MatchStatsModal
- **Files:** `frontend/app/store/tournamentStore.ts`, `frontend/app/pages/tournament/TournamentDetailPage.tsx`, `frontend/app/components/bracket/BracketView.tsx`, `frontend/app/components/bracket/modals/MatchStatsModal.tsx`

**I8: Add Team Name to Round Data** ✅
- **Issue:** Frontend had to look up team name from ID when displaying rounds
- **Fix:** Added `team_name` field to `HeroDraftRoundSerializerFull` and frontend schema
- **Files:** `backend/app/serializers.py`, `frontend/app/components/herodraft/schemas.ts`

### Summary of Files Changed

**Backend:**
- `backend/app/models.py` - Added "abandoned" state
- `backend/app/serializers.py` - Added team_name to round serializer
- `backend/app/consumers.py` - Added team IDs to tick handler
- `backend/app/tasks/herodraft_tick.py` - Fixed team ordering, added team IDs
- `backend/app/functions/herodraft_views.py` - Added abandon_draft endpoint
- `backend/backend/urls.py` - Added abandon route
- `backend/app/tests/test_herodraft_consumers.py` (new) - WebSocket tests
- `backend/app/tests/test_herodraft_tick.py` (new) - Timeout tests

**Frontend:**
- `frontend/app/components/herodraft/schemas.ts` - Multiple schema fixes
- `frontend/app/components/herodraft/types.ts` - Added WebSocket message type
- `frontend/app/components/herodraft/HeroDraftModal.tsx` - Loading states, roll_winner fix
- `frontend/app/components/herodraft/DraftTopBar.tsx` - Array bounds checks
- `frontend/app/components/herodraft/hooks/useHeroDraftWebSocket.ts` - Zod validation
- `frontend/app/components/herodraft/api.ts` - Added abandonDraft function
- `frontend/app/store/tournamentStore.ts` - Added pendingDraftId state
- `frontend/app/pages/tournament/TournamentDetailPage.tsx` - URL parsing
- `frontend/app/components/bracket/BracketView.tsx` - Deep-link auto-open
- `frontend/app/components/bracket/modals/MatchStatsModal.tsx` - initialDraftId prop
- `frontend/app/types/dotaconstants.d.ts` (new) - Type declarations

---

## Post-Implementation Infrastructure Enhancements

After the code review fixes, additional infrastructure improvements were implemented for production reliability:

### Redis Distributed Locking for Tick Broadcaster

**Problem:** The original tick broadcaster used a simple thread registry, which only prevents duplicate threads within a single Django process. In production with multiple Daphne/Django instances, this could result in multiple broadcasters for the same draft.

**Solution:** Redis distributed locking with automatic expiration.

**Implementation:**

```python
# backend/app/tasks/herodraft_tick.py

# Redis keys
CONN_COUNT_KEY = "herodraft:connections:{draft_id}"
LOCK_KEY = "herodraft:tick_lock:{draft_id}"
LOCK_TIMEOUT = 10  # Lock expires after 10 seconds

def start_tick_broadcaster(draft_id: int) -> bool:
    r = get_redis_client()
    lock_key = LOCK_KEY.format(draft_id=draft_id)

    # SET NX = only set if not exists, EX = expire time
    acquired = r.set(lock_key, "locked", nx=True, ex=LOCK_TIMEOUT)

    if not acquired:
        return False  # Another instance owns the lock

    # Start thread, renew lock each tick
    ...
```

**Key Features:**

1. **Atomic lock acquisition**: `SET NX EX` is atomic - no race conditions
2. **Auto-expiration**: Lock expires after 10 seconds if process crashes
3. **Lock renewal**: Running broadcaster extends lock each tick cycle
4. **Connection tracking**: Uses Redis counters to track WebSocket connections

**Files Modified:**
- `backend/app/tasks/herodraft_tick.py` - Complete rewrite with Redis locking
- `backend/app/consumers.py` - Added connection tracking and tick broadcaster startup

### WebSocket Connection Tracking

**Problem:** Tick broadcaster had no way to know when all WebSocket clients disconnected, causing unnecessary resource usage.

**Solution:** Redis counters for connection tracking.

```python
def increment_connection_count(draft_id: int) -> int:
    r = get_redis_client()
    key = CONN_COUNT_KEY.format(draft_id=draft_id)
    count = r.incr(key)
    r.expire(key, 300)  # Expire after 5 min of no activity
    return count

def decrement_connection_count(draft_id: int) -> int:
    r = get_redis_client()
    key = CONN_COUNT_KEY.format(draft_id=draft_id)
    count = r.decr(key)
    if count <= 0:
        r.delete(key)
        count = 0
    return count
```

The tick loop checks connection count each iteration and stops when count reaches 0:

```python
def should_continue_ticking(draft_id: int, r: redis.Redis) -> tuple[bool, str]:
    conn_count = get_connection_count(draft_id)
    if conn_count <= 0:
        return False, "no_connections"
    # Also check draft state
    ...
```

### Celery Beat for Discord Avatar Refresh

**Problem:** Discord avatar URLs expire and become invalid over time. The UI was previously triggering refreshes, which was inconsistent and unreliable.

**Solution:** Celery Beat scheduled tasks for automatic avatar maintenance.

**Implementation:**

```python
# backend/app/tasks/avatar_refresh.py

@shared_task
def refresh_discord_avatars(batch_size: int = 100):
    """Batch refresh - runs every 5 minutes via Beat."""
    from app.utils.avatar_utils import refresh_invalid_avatars
    results = refresh_invalid_avatars(batch_size=batch_size)
    return results

@shared_task
def refresh_single_user_avatar(user_id: int):
    """On-demand single user refresh (e.g., on login)."""
    from app.utils.avatar_utils import refresh_user_avatar
    return refresh_user_avatar(user_id)

@shared_task
def refresh_all_discord_data():
    """Full refresh - runs daily at 4 AM."""
    # Iterates all users with Discord IDs in batches
    ...
```

**Beat Schedule:**

```python
# backend/config/celery.py

app.conf.beat_schedule = {
    # ... existing tasks ...
    "refresh-discord-avatars": {
        "task": "app.tasks.avatar_refresh.refresh_discord_avatars",
        "schedule": 300.0,  # Every 5 minutes
        "kwargs": {"batch_size": 50},
    },
    "refresh-all-discord-data-daily": {
        "task": "app.tasks.avatar_refresh.refresh_all_discord_data",
        "schedule": crontab(hour=4, minute=0),
    },
}
```

**Files Created/Modified:**
- `backend/app/tasks/avatar_refresh.py` (new) - Celery tasks for avatar refresh
- `backend/app/tasks/__init__.py` - Updated exports
- `backend/config/celery.py` - Added Beat schedule entries

### Summary of Infrastructure Files

| File | Changes |
|------|---------|
| `backend/app/tasks/herodraft_tick.py` | Redis locking, connection tracking, auto-stop |
| `backend/app/consumers.py` | Connection tracking calls, tick broadcaster startup |
| `backend/app/tasks/avatar_refresh.py` | New Celery tasks for Discord avatar maintenance |
| `backend/app/tasks/__init__.py` | Exports for new tasks |
| `backend/config/celery.py` | Beat schedule for avatar refresh tasks |
