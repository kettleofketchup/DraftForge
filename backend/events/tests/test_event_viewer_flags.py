from django.db import connection
from django.test.utils import CaptureQueriesContext, override_settings
from django.utils import timezone as tz
from rest_framework.test import APIClient

from org.feature_keys import FeatureKey
from org.features import set_org_feature
from org.leadership.reviews import void_review, withdraw_review
from org.standing import api as standing
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

    def test_locked_feature_omits_flags_at_the_same_cost(self) -> None:
        client = self.client_for(self.mates_a[0])
        _, unlocked = self.detail(client)
        set_org_feature(self.org, FeatureKey.LEADERSHIP, enabled=False, actor=None)
        body, locked = self.detail(client)
        for key in FLAGS:
            self.assertNotIn(key, body)
        self.assertEqual(unlocked, locked)

    def test_moderated_review_is_not_pending(self) -> None:
        review = self.review(self.mates_a[0], self.cap_a)
        void_review(
            self.org, review_id=review.pk, actor=self.admin, reason="x", now=tz.now()
        )
        body, _ = self.detail(self.client_for(self.mates_a[0]))
        self.assertEqual(body["pending_captain_reviews"], 0)
        self.assertFalse(body["can_review_captains"])

    def test_withdrawn_review_is_pending_again(self) -> None:
        self.review(self.mates_a[0], self.cap_a)
        withdraw_review(
            self.org,
            event_id=self.event.pk,
            captain_org_user_id=self.ou(self.cap_a).pk,
            rater=self.ou(self.mates_a[0]),
            now=tz.now(),
        )
        body, _ = self.detail(self.client_for(self.mates_a[0]))
        self.assertEqual(body["pending_captain_reviews"], 1)

    def test_flags_cost_one_query_locked_or_unlocked(self) -> None:
        def flags() -> dict[str, object]:
            return standing.event_viewer_flags(
                self.event.pk, self.org.pk, self.mates_a[0]
            )

        with self.assertNumQueries(1):
            self.assertEqual(
                flags(), {"can_review_captains": True, "pending_captain_reviews": 1}
            )
        set_org_feature(self.org, FeatureKey.LEADERSHIP, enabled=False, actor=None)
        with self.assertNumQueries(1):
            self.assertEqual(flags(), {})
