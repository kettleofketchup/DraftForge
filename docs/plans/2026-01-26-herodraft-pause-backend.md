# HeroDraft Pause/Resume Backend Implementation

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix timer pause behavior so grace/reserve time freezes immediately when a captain disconnects.

**Architecture:** Add `paused_at` field to HeroDraft model. On pause, store timestamp. On resume, calculate pause duration and adjust the active round's `started_at` forward by that amount. This ensures elapsed time calculations exclude pause time.

**Tech Stack:** Django, Django Channels, Python

---

## Task 1: Add paused_at field to HeroDraft model

**Files:**
- Modify: `backend/app/models.py:1376-1403` (HeroDraft class)
- Create: `backend/app/migrations/0072_herodraft_paused_at.py`

**Step 1: Add paused_at field to HeroDraft model**

In `backend/app/models.py`, add the field after `updated_at`:

```python
class HeroDraft(models.Model):
    """Captain's Mode hero draft for a tournament game."""

    game = models.OneToOneField(
        "app.Game", on_delete=models.CASCADE, related_name="herodraft"
    )
    state = models.CharField(
        max_length=32,
        choices=HeroDraftState.choices,
        default=HeroDraftState.WAITING_FOR_CAPTAINS,
    )
    roll_winner = models.ForeignKey(
        "DraftTeam",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="won_rolls",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    paused_at = models.DateTimeField(null=True, blank=True)  # NEW FIELD
```

**Step 2: Create and run migration**

Run:
```bash
cd /home/kettle/git_repos/website/.worktrees/responsiveness
source .venv/bin/activate
python backend/manage.py makemigrations app --name herodraft_paused_at
python backend/manage.py migrate
```

Expected: Migration created and applied successfully

**Step 3: Commit**

```bash
git add backend/app/models.py backend/app/migrations/0072_herodraft_paused_at.py
git commit -m "Add paused_at field to HeroDraft model"
```

---

## Task 2: Update mark_captain_connected to track pause time

**Files:**
- Modify: `backend/app/consumers.py:314-422` (mark_captain_connected method)

**Step 1: Update pause logic to store paused_at timestamp**

In `mark_captain_connected`, update the pause block (around line 350):

```python
# Handle pause/resume on disconnect - only during DRAFTING phase
# (when timers are running and picks matter)
if not is_connected and draft.state == HeroDraftState.DRAFTING:
    draft.state = HeroDraftState.PAUSED
    draft.paused_at = timezone.now()  # ADD THIS LINE
    draft.save()
    HeroDraftEvent.objects.create(
        draft=draft,
        event_type="draft_paused",
        draft_team=draft_team,
        metadata={"reason": "captain_disconnected"},
    )
    log.info(
        f"HeroDraft {draft_id} paused: captain {user.username} disconnected"
    )
    broadcast_event_type = "draft_paused"
    should_broadcast = True
```

**Step 2: Update resume logic to adjust round started_at**

Update the resume block (around line 364):

```python
elif is_connected and draft.state == HeroDraftState.PAUSED:
    # Check if both captains connected - use fresh query to avoid
    # Django ORM caching issues with related manager
    all_connected = not DraftTeam.objects.filter(
        draft_id=draft_id, is_connected=False
    ).exists()
    if all_connected:
        # Calculate pause duration and adjust active round's started_at
        if draft.paused_at:
            pause_duration = timezone.now() - draft.paused_at
            current_round = draft.rounds.filter(state="active").first()
            if current_round and current_round.started_at:
                # Push started_at forward by pause duration
                current_round.started_at += pause_duration
                current_round.save(update_fields=["started_at"])
                log.info(
                    f"HeroDraft {draft_id} adjusted round {current_round.round_number} "
                    f"started_at by {pause_duration.total_seconds():.1f}s"
                )

        draft.state = HeroDraftState.DRAFTING
        draft.paused_at = None  # Clear paused_at
        draft.save()
        HeroDraftEvent.objects.create(
            draft=draft,
            event_type="draft_resumed",
            metadata={"pause_duration_ms": int(pause_duration.total_seconds() * 1000) if draft.paused_at else 0},
        )
        log.info(
            f"HeroDraft {draft_id} resumed: all captains connected"
        )
        broadcast_event_type = "draft_resumed"
        should_broadcast = True
        should_restart_tick_broadcaster = True
```

**Step 3: Add timezone import if not present**

At top of file, ensure:
```python
from django.utils import timezone
```

**Step 4: Commit**

```bash
git add backend/app/consumers.py
git commit -m "Track pause duration and adjust round started_at on resume"
```

---

## Task 3: Add resume countdown broadcast

**Files:**
- Modify: `backend/app/consumers.py:314-422` (mark_captain_connected method)

**Step 1: Add resume_countdown event before actual resume**

The design calls for a "Resuming in 3... 2... 1..." countdown. We need to:
1. Broadcast `resume_countdown` event with countdown seconds
2. Wait 3 seconds (handled by frontend)
3. Then broadcast `draft_resumed`

Update the resume block to add countdown:

```python
elif is_connected and draft.state == HeroDraftState.PAUSED:
    all_connected = not DraftTeam.objects.filter(
        draft_id=draft_id, is_connected=False
    ).exists()
    if all_connected:
        # Calculate pause duration for later
        pause_duration = None
        if draft.paused_at:
            pause_duration = timezone.now() - draft.paused_at

        # Broadcast resume countdown BEFORE changing state
        # Frontend will show "Resuming in 3... 2... 1..."
        broadcast_herodraft_state(draft, "resume_countdown", metadata={"countdown_seconds": 3})

        # The actual resume will happen after countdown
        # For now, we set state to RESUMING (a transitional state)
        # OR we can handle the countdown entirely on frontend
        # DECISION: Handle countdown on frontend, just send the event

        # Adjust round started_at by pause duration + countdown time
        current_round = draft.rounds.filter(state="active").first()
        if current_round and current_round.started_at and pause_duration:
            # Add 3 seconds for countdown
            total_adjustment = pause_duration + timedelta(seconds=3)
            current_round.started_at += total_adjustment
            current_round.save(update_fields=["started_at"])
            log.info(
                f"HeroDraft {draft_id} adjusted round {current_round.round_number} "
                f"started_at by {total_adjustment.total_seconds():.1f}s (includes 3s countdown)"
            )

        draft.state = HeroDraftState.DRAFTING
        draft.paused_at = None
        draft.save()

        HeroDraftEvent.objects.create(
            draft=draft,
            event_type="draft_resumed",
            metadata={"pause_duration_ms": int(pause_duration.total_seconds() * 1000) if pause_duration else 0},
        )
        log.info(f"HeroDraft {draft_id} resumed: all captains connected")
        broadcast_event_type = "draft_resumed"
        should_broadcast = True
        should_restart_tick_broadcaster = True
```

**Step 2: Add timedelta import**

```python
from datetime import timedelta
```

**Step 3: Update broadcast_herodraft_state to accept metadata**

Check if `broadcast_herodraft_state` supports metadata parameter. If not, we need to modify it.

**Step 4: Commit**

```bash
git add backend/app/consumers.py
git commit -m "Add resume countdown broadcast before resuming draft"
```

---

## Task 4: Update broadcast_herodraft_state for metadata

**Files:**
- Modify: `backend/app/broadcast.py`

**Step 1: Find and read broadcast.py**

Run:
```bash
grep -n "def broadcast_herodraft_state" backend/app/broadcast.py
```

**Step 2: Add metadata parameter**

Update the function signature to accept optional metadata:

```python
def broadcast_herodraft_state(draft, event_type, draft_team=None, metadata=None):
    """Broadcast herodraft state update to all connected clients."""
    # ... existing code ...

    # In the message dict, add metadata if provided
    message = {
        "type": "herodraft.event",
        "event_type": event_type,
        # ... other fields ...
    }
    if metadata:
        message["metadata"] = metadata
```

**Step 3: Commit**

```bash
git add backend/app/broadcast.py
git commit -m "Add metadata parameter to broadcast_herodraft_state"
```

---

## Task 5: Write test for pause/resume timing

**Files:**
- Modify: `backend/app/tests/test_herodraft_consumers.py`

**Step 1: Add test for pause timing adjustment**

```python
def test_pause_resume_adjusts_round_started_at(self):
    """Test that pausing and resuming adjusts the round's started_at to exclude pause time."""
    from django.utils import timezone
    from datetime import timedelta

    # Setup: Get draft into DRAFTING state with active round
    draft = self.draft
    draft.state = HeroDraftState.DRAFTING
    draft.save()

    # Create active round with started_at 10 seconds ago
    round_started = timezone.now() - timedelta(seconds=10)
    active_round = draft.rounds.filter(state="active").first()
    active_round.started_at = round_started
    active_round.save()

    original_started_at = active_round.started_at

    # Simulate captain disconnect (pause)
    captain_a = self.team_a.tournament_team.captain
    # Call mark_captain_connected with is_connected=False
    # ... (depends on how test is structured)

    # Wait 2 seconds (simulated pause)
    # ...

    # Simulate captain reconnect (resume)
    # ...

    # Verify: started_at should have moved forward by ~2 seconds + 3 seconds countdown
    active_round.refresh_from_db()
    adjustment = active_round.started_at - original_started_at
    # Should be approximately 5 seconds (2s pause + 3s countdown)
    self.assertGreater(adjustment.total_seconds(), 4.5)
    self.assertLess(adjustment.total_seconds(), 6.0)
```

**Step 2: Run tests**

```bash
inv test.run --cmd 'python manage.py test app.tests.test_herodraft_consumers -v 2'
```

**Step 3: Commit**

```bash
git add backend/app/tests/test_herodraft_consumers.py
git commit -m "Add test for pause/resume timing adjustment"
```

---

## Task 6: Handle edge case - pause during countdown

**Files:**
- Modify: `backend/app/consumers.py`

**Step 1: Track countdown state**

If captain B disconnects during the "Resuming in 3...2...1..." countdown, we need to cancel it and go back to paused.

Options:
1. Add `RESUMING` state to HeroDraftState (backend tracks countdown)
2. Handle entirely on frontend (simpler)

**Decision:** Handle on frontend. Backend immediately goes to DRAFTING, frontend shows countdown. If another disconnect happens during countdown, backend will see DRAFTING state and pause again normally.

The current logic already handles this:
- Backend is in DRAFTING state during countdown
- If captain disconnects, `if not is_connected and draft.state == HeroDraftState.DRAFTING` triggers pause

**Step 2: Verify edge case is handled**

No code changes needed - existing logic handles it. The frontend will need to:
1. Show countdown overlay
2. If `draft_paused` event arrives during countdown, cancel countdown and show pause overlay

**Step 3: Commit (documentation only)**

```bash
git commit --allow-empty -m "Verify: pause during countdown handled by existing logic"
```

---

## Summary

After completing these tasks:

1. **HeroDraft.paused_at** - Tracks when draft was paused
2. **Round.started_at adjustment** - On resume, started_at is pushed forward by pause duration + 3s countdown
3. **resume_countdown event** - Sent before draft_resumed so frontend can show countdown
4. **Edge cases** - Pause during countdown works because backend is in DRAFTING state during countdown

**Next steps:** Frontend implementation to handle:
- `draft_paused` event → show overlay
- `resume_countdown` event → show "Resuming in 3...2...1..."
- `draft_resumed` event → hide overlay, resume local timer
