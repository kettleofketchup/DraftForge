from django.test import TestCase, override_settings
from rest_framework.test import APIClient

TOKEN = "test-internal-token"
HEADERS = {"HTTP_X_INTERNAL_TOKEN": TOKEN}


@override_settings(INTERNAL_SERVICE_TOKEN=TOKEN)
class SteamSyncStateEndpointTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.url = "/api/internal/steam/sync-state/12345/"

    def test_get_creates_state_if_missing(self):
        resp = self.client.get(self.url, **HEADERS)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["league_id"], 12345)
        self.assertFalse(data["is_syncing"])
        self.assertIsNone(data["last_match_id"])
        self.assertEqual(data["failed_match_ids"], [])

    def test_get_returns_existing_state(self):
        from steam.models import LeagueSyncState

        LeagueSyncState.objects.create(
            league_id=12345,
            is_syncing=True,
            last_match_id=99999,
            failed_match_ids=[111, 222],
        )
        resp = self.client.get(self.url, **HEADERS)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["league_id"], 12345)
        self.assertTrue(data["is_syncing"])
        self.assertEqual(data["last_match_id"], 99999)
        self.assertEqual(data["failed_match_ids"], [111, 222])

    def test_patch_updates_allowed_fields(self):
        from steam.models import LeagueSyncState

        LeagueSyncState.objects.create(league_id=12345)
        resp = self.client.patch(
            self.url,
            {
                "is_syncing": True,
                "last_match_id": 77777,
                "failed_match_ids": [333],
            },
            format="json",
            **HEADERS,
        )
        self.assertEqual(resp.status_code, 200)
        state = LeagueSyncState.objects.get(league_id=12345)
        self.assertTrue(state.is_syncing)
        self.assertEqual(state.last_match_id, 77777)
        self.assertEqual(state.failed_match_ids, [333])
        self.assertIsNotNone(state.last_sync_at)

    def test_patch_ignores_unknown_fields(self):
        from steam.models import LeagueSyncState

        LeagueSyncState.objects.create(league_id=12345)
        resp = self.client.patch(
            self.url,
            {"league_id": 99999, "is_syncing": True},
            format="json",
            **HEADERS,
        )
        self.assertEqual(resp.status_code, 200)
        state = LeagueSyncState.objects.get(league_id=12345)
        # league_id should NOT have changed
        self.assertEqual(state.league_id, 12345)
        self.assertTrue(state.is_syncing)

    def test_rejects_unauthenticated_requests(self):
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 403)

    def test_rejects_wrong_token(self):
        resp = self.client.get(
            self.url, HTTP_X_INTERNAL_TOKEN="wrong-token"
        )
        self.assertEqual(resp.status_code, 403)
