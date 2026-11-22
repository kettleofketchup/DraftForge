from datetime import timedelta
from unittest import mock

from django.core.exceptions import ValidationError
from django.utils import timezone as tz

from org.leadership import reviews as reviews_module
from org.leadership.lifecycle import void_event
from org.leadership.reviews import ReviewRefused, void_review, withdraw_review
from org.models_leadership import CaptainReview, EventCaptain
from org.tests.leadership_base import LeadershipTestCase, scores


class ReviewTest(LeadershipTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.close()

    def test_below_min_reviewers_no_row(self) -> None:
        self.review(self.mates_a[0], self.cap_a)
        self.assertIsNone(self.points(self.cap_a, "captain_rating"))

    def test_upsert_on_submit_and_edit(self) -> None:
        self.review(self.mates_a[0], self.cap_a, 5)
        self.review(self.mates_a[1], self.cap_a, 5)
        self.assertEqual(self.points(self.cap_a, "captain_rating"), 10)
        self.review(self.mates_a[1], self.cap_a, 1)
        self.assertEqual(self.points(self.cap_a, "captain_rating"), 5)
        self.assertEqual(CaptainReview.objects.count(), 2)

    def test_all_ones_deletes_row(self) -> None:
        self.review(self.mates_a[0], self.cap_a, 1)
        self.review(self.mates_a[1], self.cap_a, 1)
        self.assertIsNone(self.points(self.cap_a, "captain_rating"))

    def test_requires_every_active_trait(self) -> None:
        partial = scores(4)
        partial.pop("drafting")
        with self.assertRaises(ReviewRefused) as ctx:
            self.review(self.mates_a[0], self.cap_a, partial)
        self.assertEqual(ctx.exception.status, 400)
        with self.assertRaises(ReviewRefused):
            self.review(self.mates_a[0], self.cap_a, {**scores(4), "bogus": 3})

    def test_pool_enforced(self) -> None:
        with self.assertRaises(ReviewRefused) as ctx:
            self.review(self.mates_b[0], self.cap_a)
        self.assertEqual(ctx.exception.status, 403)
        with self.assertRaises(ReviewRefused):
            self.review(self.cap_a, self.cap_a)

    def test_window_edges(self) -> None:
        closes = self.snapshot(self.cap_a).window_closes_at
        self.review(self.mates_a[0], self.cap_a, now=closes - timedelta(seconds=1))
        with self.assertRaises(ReviewRefused) as ctx:
            self.review(self.mates_a[1], self.cap_a, now=closes)
        self.assertEqual(ctx.exception.code, "review_window_closed")

    def test_frozen_after_window(self) -> None:
        self.review(self.mates_a[0], self.cap_a, 5)
        self.review(self.mates_a[1], self.cap_a, 5)
        self.expire_window()
        with self.assertRaises(ReviewRefused):
            withdraw_review(
                org_id=self.org.pk,
                event_id=self.event.pk,
                captain_id=self.ou(self.cap_a).pk,
                rater=self.ou(self.mates_a[0]),
                now=tz.now(),
            )
        self.assertEqual(self.points(self.cap_a, "captain_rating"), 10)

    def test_withdraw_then_resubmit(self) -> None:
        self.review(self.mates_a[0], self.cap_a, 5)
        self.review(self.mates_a[1], self.cap_a, 5)
        withdraw_review(
            org_id=self.org.pk,
            event_id=self.event.pk,
            captain_id=self.ou(self.cap_a).pk,
            rater=self.ou(self.mates_a[0]),
            now=tz.now(),
        )
        self.assertIsNone(self.points(self.cap_a, "captain_rating"))
        self.review(self.mates_a[0], self.cap_a, 5)
        self.assertEqual(self.points(self.cap_a, "captain_rating"), 10)

    def test_staff_void_sticks_and_recomputes_after_window(self) -> None:
        first = self.review(self.mates_a[0], self.cap_a, 5)
        self.review(self.mates_a[1], self.cap_a, 5)
        self.review(self.mates_a[2], self.cap_a, 1)
        self.expire_window()
        before = self.points(self.cap_a, "captain_rating")
        void_review(
            org_id=self.org.pk,
            review_pk=first.pk,
            actor=self.admin,
            reason="abusive",
            now=tz.now(),
        )
        self.assertNotEqual(self.points(self.cap_a, "captain_rating"), before)
        log = self.org.logs.get(action="void_captain_review")
        self.assertEqual(log.details["points_before"], before)

    def test_rater_cannot_undo_moderation(self) -> None:
        first = self.review(self.mates_a[0], self.cap_a, 5)
        void_review(
            org_id=self.org.pk,
            review_pk=first.pk,
            actor=self.admin,
            reason="abusive",
            now=tz.now(),
        )
        with self.assertRaises(ReviewRefused) as ctx:
            self.review(self.mates_a[0], self.cap_a, 5)
        self.assertEqual(ctx.exception.code, "review_moderated")

    def test_self_review_rejected_by_clean(self) -> None:
        snap = self.snapshot(self.cap_a)
        review = CaptainReview(
            event_captain=snap, rater=snap.captain, submitted_at=tz.now()
        )
        with self.assertRaises(ValidationError):
            review.clean()

    def test_cross_org_lock_is_not_found(self) -> None:
        with self.assertRaises(ReviewRefused) as ctx:
            withdraw_review(
                org_id=self.org.pk + 999,
                event_id=self.event.pk,
                captain_id=self.ou(self.cap_a).pk,
                rater=self.ou(self.mates_a[0]),
                now=tz.now(),
            )
        self.assertEqual(ctx.exception.status, 404)


class ReviewRaceTest(LeadershipTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.close()
        self.real_lock = reviews_module.lock_snapshot

    def test_void_between_precheck_and_lock(self) -> None:
        def lock_after_reopen(*args: int) -> EventCaptain:
            void_event(self.event, now=tz.now())
            return self.real_lock(*args)

        with mock.patch.object(reviews_module, "lock_snapshot", lock_after_reopen):
            with self.assertRaises(ReviewRefused) as ctx:
                self.review(self.mates_a[0], self.cap_a)
        self.assertEqual(ctx.exception.code, "snapshot_voided")
        self.assertFalse(CaptainReview.objects.filter(voided_at__isnull=True).exists())
        self.assertIsNone(self.points(self.cap_a, "captain_rating"))

    def test_window_checked_with_the_clock_inside_the_lock(self) -> None:
        closes = self.snapshot(self.cap_a).window_closes_at
        with mock.patch.object(reviews_module.timezone, "now", return_value=closes):
            with self.assertRaises(ReviewRefused) as ctx:
                self.review(
                    self.mates_a[0], self.cap_a, now=closes - timedelta(seconds=1)
                )
        self.assertEqual(ctx.exception.code, "review_window_closed")
        self.assertFalse(CaptainReview.objects.exists())

    def test_reopened_snapshot_refuses_with_snapshot_voided(self) -> None:
        void_event(self.event, now=tz.now())
        with self.assertRaises(ReviewRefused) as ctx:
            self.review(self.mates_a[0], self.cap_a)
        self.assertEqual(ctx.exception.code, "snapshot_voided")
