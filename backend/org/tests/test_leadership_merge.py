from django.db import IntegrityError, transaction
from django.utils import timezone as tz

from org.contributions.services import award_entry, delete_user_entries
from org.models import ContributionEntry, OrgLog, OrgUser
from org.models_leadership import CaptainReview, EventCaptain
from org.standing import api as standing
from org.tests.leadership_base import LeadershipTestCase


class MergeTest(LeadershipTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.close()

    def merge(self, drop_user, keep_user) -> None:  # noqa: ANN001
        drop = self.ou(drop_user)
        keep = self.ou(keep_user)
        with transaction.atomic():
            standing.merge_users(drop_user, keep_user, member_pairs=[(drop, keep)])
            drop.delete()

    def test_rater_collision_keeps_latest(self) -> None:
        self.review(self.mates_a[0], self.cap_a, 2)
        self.review(self.mates_a[1], self.cap_a, 5)
        ContributionEntry.objects.filter(org_user__user=self.mates_a[0]).delete()
        self.merge(self.mates_a[0], self.mates_a[1])
        review = CaptainReview.objects.get()
        self.assertEqual(review.rater.user, self.mates_a[1])
        self.assertEqual(set(review.scores.values_list("score", flat=True)), {5})

    def test_self_review_dropped_and_pool_cleaned(self) -> None:
        self.review(self.mates_a[0], self.cap_a, 4)
        self.merge(self.mates_a[0], self.cap_a)
        self.assertFalse(CaptainReview.objects.exists())
        snap = self.snapshot(self.cap_a)
        self.assertNotIn(
            self.ou(self.cap_a).pk, snap.teammates.values_list("pk", flat=True)
        )

    def test_both_captained_same_event(self) -> None:
        self.review(self.mates_b[0], self.cap_b, 4)
        self.merge(self.cap_b, self.cap_a)
        self.assertEqual(EventCaptain.objects.filter(event=self.event).count(), 1)
        self.assertEqual(
            ContributionEntry.objects.filter(
                org_user=self.ou(self.cap_a), kind="captained"
            ).count(),
            1,
        )
        self.assertEqual(
            CaptainReview.objects.get().event_captain.captain.user, self.cap_a
        )

    def test_merge_after_window_keeps_points(self) -> None:
        self.review(self.mates_a[0], self.cap_a, 5)
        self.review(self.mates_a[1], self.cap_a, 5)
        self.expire_window()
        self.merge(self.mates_a[0], self.cap_a)
        self.assertEqual(self.points(self.cap_a, "captain_rating"), 10)

    def test_merge_inside_window_recomputes(self) -> None:
        self.review(self.mates_a[0], self.cap_a, 5)
        self.review(self.mates_a[1], self.cap_a, 5)
        self.merge(self.mates_a[0], self.cap_a)
        self.assertIsNone(self.points(self.cap_a, "captain_rating"))


class UserDeleteTest(LeadershipTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.close()
        self.review(self.mates_a[0], self.cap_a, 5)
        self.review(self.mates_a[1], self.cap_a, 5)

    def delete(self, user) -> None:  # noqa: ANN001
        with transaction.atomic():
            standing.on_user_deleted(user, actor=self.admin)
            user.delete()

    def test_rater_deleted_inside_window_recomputes(self) -> None:
        self.delete(self.mates_a[0])
        self.assertIsNone(self.points(self.cap_a, "captain_rating"))

    def test_rater_deleted_after_window_keeps_points(self) -> None:
        self.expire_window()
        self.delete(self.mates_a[0])
        self.assertEqual(self.points(self.cap_a, "captain_rating"), 10)

    def test_each_track_logs_only_its_rows(self) -> None:
        award_entry(
            org=self.org,
            user=self.cap_a,
            kind="manual",
            points=3,
            reason="help",
            occurred_at=tz.now(),
        )
        self.delete(self.cap_a)
        contrib = OrgLog.objects.get(action="delete_user_contributions")
        lead = OrgLog.objects.get(action="delete_user_leadership")
        self.assertEqual(contrib.details["count"], 1)
        self.assertEqual(lead.details["count"], 3)


class TrackColumnTest(LeadershipTestCase):
    def test_contribution_delete_leaves_leadership_rows(self) -> None:
        self.close()
        with transaction.atomic():
            delete_user_entries(self.cap_a, actor=None)
        self.assertTrue(
            ContributionEntry.objects.filter(
                org_user__user=self.cap_a, track="leadership"
            ).exists()
        )

    def test_award_stores_track(self) -> None:
        entry = award_entry(
            org=self.org,
            user=self.cap_a,
            kind="manual",
            points=3,
            reason="help",
            occurred_at=tz.now(),
        )
        self.assertEqual(entry.track, "contribution")

    def test_once_per_event_constraint_still_rejects_staff_duplicates(self) -> None:
        award_entry(
            org=self.org,
            user=self.cap_a,
            kind="event_host",
            occurred_at=tz.now(),
            event=self.event,
        )
        with self.assertRaises(IntegrityError), transaction.atomic():
            ContributionEntry.objects.create(
                org_user=OrgUser.objects.get(user=self.cap_a),
                organization=self.org,
                kind="event_host",
                points=1,
                event=self.event,
                occurred_at=tz.now(),
            )
