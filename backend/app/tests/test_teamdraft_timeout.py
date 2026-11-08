"""skip_turn strategies, reassign_round_captain, check_timeout guards and pick-vs-timeout ordering (spec §2)."""

from unittest.mock import patch

from django.test import TestCase

from app.functions import shuffle_draft
from app.tests.teamdraft_fixtures import TimedDraftFixture

CAPTAIN_MMRS = [1000, 2000, 3000, 4000]  # teams[0] is lowest -> shuffle's first captain, no tie roll


class ReassignRoundCaptainTests(TestCase):
    def setUp(self):
        self.fx = TimedDraftFixture(style="shuffle", captain_mmrs=CAPTAIN_MMRS)

    def test_reassigns_lowest_eligible_excluding_given_team_with_reason(self):
        rnd = self.fx.round(1)
        self.assertEqual(rnd.captain, self.fx.teams[0].captain)
        rnd.was_tie = True
        rnd.tie_roll_data = {"x": 1}
        rnd.save()
        with patch("app.functions.shuffle_draft.broadcast_event") as mock_bc, self.captureOnCommitCallbacks(execute=True):
            tie = shuffle_draft.reassign_round_captain(self.fx.draft, rnd, {self.fx.teams[0].pk}, reason="timeout_skip")
        rnd.refresh_from_db()
        self.assertIsNone(tie)
        self.assertEqual(rnd.captain, self.fx.teams[1].captain)
        self.assertFalse(rnd.was_tie)
        self.assertIsNone(rnd.tie_roll_data)
        ev = self.fx.events("captain_assigned").get()
        self.assertEqual(ev.payload["reason"], "timeout_skip")
        self.assertEqual(ev.payload["pick_number"], 1)
        mock_bc.assert_called_once()

    def test_no_eligible_team_returns_none_and_leaves_round(self):
        rnd = self.fx.round(1)
        result = shuffle_draft.reassign_round_captain(self.fx.draft, rnd, {t.pk for t in self.fx.teams})
        self.assertIsNone(result)
        rnd.refresh_from_db()
        self.assertEqual(rnd.captain, self.fx.teams[0].captain)
        self.assertFalse(self.fx.events("captain_assigned").exists())

    def test_assign_next_wraps_reassign_without_exclusions_and_no_reason(self):
        with self.captureOnCommitCallbacks(execute=True):
            shuffle_draft.assign_next_shuffle_captain(self.fx.draft)
        rnd2 = self.fx.round(2)
        self.assertEqual(rnd2.captain, self.fx.teams[0].captain)
        self.assertNotIn("reason", self.fx.events("captain_assigned").get().payload)
