from django.db import connection
from django.test.utils import CaptureQueriesContext, override_settings
from rest_framework.test import APIClient

from org.feature_keys import FeatureKey
from org.features import set_org_feature
from org.tests.leadership_base import LeadershipTestCase

FLAGS = ("can_review_captains", "pending_captain_reviews")


@override_settings(CACHEOPS_ENABLED=False)
class EventViewerFlagsTest(LeadershipTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.close()

    def detail(self, client: APIClient) -> tuple[dict, int]:
        with CaptureQueriesContext(connection) as ctx:
            res = client.get(f"/api/events/{self.event.pk}/")
        self.assertEqual(res.status_code, 200)
        return res.json(), len(ctx.captured_queries)

    def test_pool_member_sees_pending_until_reviewed(self) -> None:
        client = self.client_for(self.mates_a[0])
        body, _ = self.detail(client)
        self.assertEqual(body["pending_captain_reviews"], 1)
        self.assertTrue(body["can_review_captains"])
        self.review(self.mates_a[0], self.cap_a)
        body, _ = self.detail(client)
        self.assertEqual(body["pending_captain_reviews"], 0)
        self.assertFalse(body["can_review_captains"])

    def test_other_viewer_gets_their_own_values(self) -> None:
        self.review(self.mates_a[0], self.cap_a)
        self.detail(self.client_for(self.mates_a[0]))
        body, _ = self.detail(self.client_for(self.mates_a[1]))
        self.assertEqual(body["pending_captain_reviews"], 1)
        body, _ = self.detail(self.client_for(self.cap_a))
        self.assertEqual(body["pending_captain_reviews"], 0)

    def test_anonymous_gets_no_flags(self) -> None:
        body, _ = self.detail(APIClient())
        for key in FLAGS:
            self.assertNotIn(key, body)

    def test_locked_feature_omits_flags_and_skips_the_pool_count(self) -> None:
        client = self.client_for(self.mates_a[0])
        _, unlocked = self.detail(client)
        set_org_feature(self.org, FeatureKey.LEADERSHIP, enabled=False, actor=None)
        body, locked = self.detail(client)
        for key in FLAGS:
            self.assertNotIn(key, body)
        self.assertEqual(unlocked - locked, 1)
