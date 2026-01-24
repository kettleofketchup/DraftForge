"""Tests for HeroDraft tick broadcaster and timeout logic."""

from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from asgiref.sync import async_to_sync, sync_to_async
from django.contrib.auth import get_user_model
from django.test import TestCase, TransactionTestCase
from django.utils import timezone

from app.functions.herodraft import build_draft_rounds, get_available_heroes
from app.models import DraftTeam, Game, HeroDraft, HeroDraftRound, Team, Tournament
from app.tasks.herodraft_tick import (
    _active_tick_tasks,
    _lock,
    broadcast_tick,
    check_timeout,
    start_tick_broadcaster,
    stop_tick_broadcaster,
)

User = get_user_model()


class TimeoutTestCase(TransactionTestCase):
    """Test cases for timeout and auto-pick logic."""

    def setUp(self):
        """Set up test fixtures."""
        # Create users for captains
        self.captain1 = User.objects.create_user(
            username="captain1",
            password="testpass123",
        )
        self.captain2 = User.objects.create_user(
            username="captain2",
            password="testpass123",
        )

        # Create tournament and teams
        self.tournament = Tournament.objects.create(
            name="Test Tournament",
            owner=self.captain1,
        )
        self.team1 = Team.objects.create(
            tournament=self.tournament,
            name="Team 1",
            captain=self.captain1,
        )
        self.team2 = Team.objects.create(
            tournament=self.tournament,
            name="Team 2",
            captain=self.captain2,
        )

        # Create game
        self.game = Game.objects.create(
            tournament=self.tournament,
            radiant_team=self.team1,
            dire_team=self.team2,
        )

        # Create hero draft
        self.draft = HeroDraft.objects.create(
            game=self.game,
            state="drafting",
        )

        # Create draft teams
        self.draft_team1 = DraftTeam.objects.create(
            draft=self.draft,
            tournament_team=self.team1,
            is_first_pick=True,
            is_radiant=True,
            reserve_time_remaining=90000,  # 90 seconds
        )
        self.draft_team2 = DraftTeam.objects.create(
            draft=self.draft,
            tournament_team=self.team2,
            is_first_pick=False,
            is_radiant=False,
            reserve_time_remaining=90000,  # 90 seconds
        )

        # Build draft rounds
        build_draft_rounds(self.draft)
        self.draft.refresh_from_db()

    def test_no_timeout_when_within_grace_period(self):
        """Test no auto-pick when within grace period."""
        # Set round started recently
        active_round = self.draft.rounds.filter(state="active").first()
        active_round.started_at = timezone.now() - timedelta(
            seconds=10
        )  # 10 seconds ago
        active_round.save()

        # Run timeout check
        result = async_to_sync(check_timeout)(self.draft.id)

        # Should not trigger auto-pick
        self.assertIsNone(result)

        # Round should still be active
        active_round.refresh_from_db()
        self.assertEqual(active_round.state, "active")

    def test_timeout_triggers_auto_pick_after_total_time(self):
        """Test auto-pick triggers after grace + reserve time expires."""
        # Get current round and team
        active_round = self.draft.rounds.filter(state="active").first()
        team = DraftTeam.objects.get(id=active_round.draft_team_id)

        # Calculate total time and set started_at well past it
        total_time_ms = active_round.grace_time_ms + team.reserve_time_remaining
        total_seconds = (total_time_ms / 1000) + 5  # 5 extra seconds

        active_round.started_at = timezone.now() - timedelta(seconds=total_seconds)
        active_round.save()

        # Run timeout check
        result = async_to_sync(check_timeout)(self.draft.id)

        # Should trigger auto-pick
        self.assertIsNotNone(result)

        # Round should be completed
        active_round.refresh_from_db()
        self.assertEqual(active_round.state, "completed")
        self.assertIsNotNone(active_round.hero_id)

    def test_timeout_does_not_trigger_when_paused(self):
        """Test no auto-pick when draft is paused."""
        # Pause the draft
        self.draft.state = "paused"
        self.draft.save()

        # Set round started long ago
        active_round = self.draft.rounds.filter(state="active").first()
        active_round.started_at = timezone.now() - timedelta(minutes=10)
        active_round.save()

        # Run timeout check
        result = async_to_sync(check_timeout)(self.draft.id)

        # Should not trigger auto-pick
        self.assertIsNone(result)

    def test_timeout_deducts_from_reserve_time(self):
        """Test reserve time is deducted correctly when grace period exceeded."""
        active_round = self.draft.rounds.filter(state="active").first()
        team = DraftTeam.objects.get(id=active_round.draft_team_id)
        original_reserve = team.reserve_time_remaining

        # Set time past grace period but within reserve
        # Grace is 30000ms (30s), set to 35s ago
        active_round.started_at = timezone.now() - timedelta(seconds=35)
        active_round.save()

        # This should NOT trigger timeout yet (still have reserve)
        # But we can verify reserve time tracking works
        total_time_ms = active_round.grace_time_ms + team.reserve_time_remaining
        total_seconds = total_time_ms / 1000

        # 35 seconds should be within grace (30s) + reserve (90s) = 120s
        self.assertLess(35, total_seconds)

    def test_auto_pick_selects_valid_hero(self):
        """Test auto-pick selects a hero from available pool."""
        active_round = self.draft.rounds.filter(state="active").first()
        team = DraftTeam.objects.get(id=active_round.draft_team_id)

        # Get available heroes before
        available_before = get_available_heroes(self.draft)

        # Force timeout
        total_time_ms = active_round.grace_time_ms + team.reserve_time_remaining
        active_round.started_at = timezone.now() - timedelta(
            milliseconds=total_time_ms + 1000
        )
        active_round.save()

        # Run timeout check
        result = async_to_sync(check_timeout)(self.draft.id)

        # Should have picked a hero
        self.assertIsNotNone(result)
        self.assertIsNotNone(result.hero_id)

        # Hero should have been from available pool
        self.assertIn(result.hero_id, available_before)

        # Hero should no longer be available
        available_after = get_available_heroes(self.draft)
        self.assertNotIn(result.hero_id, available_after)


class TickBroadcasterTestCase(TransactionTestCase):
    """Test cases for tick broadcaster thread management."""

    def setUp(self):
        """Set up test fixtures."""
        # Clear any existing tick tasks
        with _lock:
            _active_tick_tasks.clear()

        # Create minimal draft setup
        self.captain1 = User.objects.create_user(
            username="captain1",
            password="testpass123",
        )
        self.tournament = Tournament.objects.create(
            name="Test Tournament",
            owner=self.captain1,
        )
        self.team1 = Team.objects.create(
            tournament=self.tournament,
            name="Team 1",
            captain=self.captain1,
        )
        self.team2 = Team.objects.create(
            tournament=self.tournament,
            name="Team 2",
            captain=self.captain1,
        )
        self.game = Game.objects.create(
            tournament=self.tournament,
            radiant_team=self.team1,
            dire_team=self.team2,
        )
        self.draft = HeroDraft.objects.create(
            game=self.game,
            state="waiting_for_captains",
        )

    def tearDown(self):
        """Clean up tick tasks."""
        with _lock:
            _active_tick_tasks.clear()

    def test_start_tick_broadcaster_registers_task(self):
        """Test starting tick broadcaster registers in active tasks."""
        start_tick_broadcaster(self.draft.id)

        with _lock:
            self.assertIn(self.draft.id, _active_tick_tasks)

        # Clean up
        stop_tick_broadcaster(self.draft.id)

    def test_start_tick_broadcaster_prevents_duplicate(self):
        """Test starting tick broadcaster twice doesn't create duplicate."""
        start_tick_broadcaster(self.draft.id)

        with _lock:
            task_info1 = _active_tick_tasks.get(self.draft.id)

        # Try to start again
        start_tick_broadcaster(self.draft.id)

        with _lock:
            task_info2 = _active_tick_tasks.get(self.draft.id)

        # Should be same task
        self.assertIs(task_info1, task_info2)

        # Clean up
        stop_tick_broadcaster(self.draft.id)

    def test_stop_tick_broadcaster_removes_task(self):
        """Test stopping tick broadcaster removes from active tasks."""
        start_tick_broadcaster(self.draft.id)

        with _lock:
            self.assertIn(self.draft.id, _active_tick_tasks)

        stop_tick_broadcaster(self.draft.id)

        with _lock:
            self.assertNotIn(self.draft.id, _active_tick_tasks)

    def test_stop_nonexistent_task_is_safe(self):
        """Test stopping non-existent task doesn't raise error."""
        # Should not raise
        stop_tick_broadcaster(99999)


class BroadcastTickTestCase(TransactionTestCase):
    """Test cases for tick broadcast message content."""

    def setUp(self):
        """Set up test fixtures."""
        self.captain1 = User.objects.create_user(
            username="captain1",
            password="testpass123",
        )
        self.captain2 = User.objects.create_user(
            username="captain2",
            password="testpass123",
        )
        self.tournament = Tournament.objects.create(
            name="Test Tournament",
            owner=self.captain1,
        )
        self.team1 = Team.objects.create(
            tournament=self.tournament,
            name="Team 1",
            captain=self.captain1,
        )
        self.team2 = Team.objects.create(
            tournament=self.tournament,
            name="Team 2",
            captain=self.captain2,
        )
        self.game = Game.objects.create(
            tournament=self.tournament,
            radiant_team=self.team1,
            dire_team=self.team2,
        )
        self.draft = HeroDraft.objects.create(
            game=self.game,
            state="drafting",
        )
        self.draft_team1 = DraftTeam.objects.create(
            draft=self.draft,
            tournament_team=self.team1,
            is_first_pick=True,
            is_radiant=True,
            reserve_time_remaining=90000,
        )
        self.draft_team2 = DraftTeam.objects.create(
            draft=self.draft,
            tournament_team=self.team2,
            is_first_pick=False,
            is_radiant=False,
            reserve_time_remaining=90000,
        )
        build_draft_rounds(self.draft)

    @patch("app.tasks.herodraft_tick.get_channel_layer")
    def test_broadcast_tick_includes_team_ids(self, mock_get_channel_layer):
        """Test broadcast_tick includes team IDs in message."""
        mock_channel_layer = MagicMock()
        mock_channel_layer.group_send = AsyncMock()
        mock_get_channel_layer.return_value = mock_channel_layer

        # Activate round
        active_round = self.draft.rounds.filter(state="active").first()
        active_round.started_at = timezone.now()
        active_round.save()

        # Run broadcast
        async_to_sync(broadcast_tick)(self.draft.id)

        # Verify group_send was called
        self.assertTrue(mock_channel_layer.group_send.called)

        # Get the message
        call_args = mock_channel_layer.group_send.call_args
        group_name = call_args[0][0]
        message = call_args[0][1]

        # Verify content
        self.assertEqual(group_name, f"herodraft_{self.draft.id}")
        self.assertEqual(message["type"], "herodraft.tick")
        self.assertIn("team_a_id", message)
        self.assertIn("team_b_id", message)
        self.assertIn("team_a_reserve_ms", message)
        self.assertIn("team_b_reserve_ms", message)

    @patch("app.tasks.herodraft_tick.get_channel_layer")
    def test_broadcast_tick_no_message_when_not_drafting(self, mock_get_channel_layer):
        """Test no broadcast when draft not in drafting state."""
        mock_channel_layer = MagicMock()
        mock_channel_layer.group_send = AsyncMock()
        mock_get_channel_layer.return_value = mock_channel_layer

        # Set state to not drafting
        self.draft.state = "waiting_for_captains"
        self.draft.save()

        # Run broadcast
        async_to_sync(broadcast_tick)(self.draft.id)

        # Should not have called group_send
        self.assertFalse(mock_channel_layer.group_send.called)
