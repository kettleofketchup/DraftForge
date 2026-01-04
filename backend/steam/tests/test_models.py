from django.test import TestCase

from steam.models import LeagueSyncState


class LeagueSyncStateModelTest(TestCase):
    def test_create_sync_state(self):
        state = LeagueSyncState.objects.create(
            league_id=17929,
            last_match_id=123456789,
            is_syncing=False,
        )
        self.assertEqual(state.league_id, 17929)
        self.assertEqual(state.last_match_id, 123456789)
        self.assertEqual(state.failed_match_ids, [])
        self.assertFalse(state.is_syncing)
        self.assertIsNone(state.last_sync_at)

    def test_unique_league_id(self):
        LeagueSyncState.objects.create(league_id=17929)
        with self.assertRaises(Exception):
            LeagueSyncState.objects.create(league_id=17929)
