from datetime import timedelta

from django.db import IntegrityError, connection, transaction
from django.test import override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone as tz

from app.models import CustomUser
from events.models import Event
from org.contributions.services import award_entry, delete_user_entries
from org.leadership import maintenance
from org.leadership.settings import get_leadership_settings
from org.leadership.summary import member_payload
from org.models import (
    ContributionEntry,
    ContributionPointValue,
    Organization,
    OrgLog,
    OrgUser,
)
from org.models_leadership import CaptainReview, EventCaptain, OrgLeadershipSettings
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

    def test_released_aggregates_do_not_move_when_a_rater_leaves(self) -> None:
        self.review(self.mates_a[2], self.cap_a, 2)
        self.expire_window()
        captain = self.ou(self.cap_a)

        def view() -> dict:
            return member_payload(captain, now=tz.now(), detail=True, staff=False)

        before = view()
        self.assertEqual(before["events"][0]["reviews"], 3)
        self.delete(self.mates_a[2])
        self.assertEqual(view(), before)

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


class ReassignMemberTest(LeadershipTestCase):
    def reassign(self, drop: CustomUser, keep: CustomUser) -> int:
        with transaction.atomic():
            return maintenance.reassign_member(
                self.ou(drop), self.ou(keep), now=tz.now()
            )

    def pool(self, captain: CustomUser, event: Event | None = None) -> list[int]:
        return list(
            EventCaptain.teammates.through.objects.filter(
                eventcaptain_id=self.snapshot(captain, event).pk
            ).values_list("orguser_id", flat=True)
        )

    def age(self, review: CaptainReview, minutes: int) -> None:
        CaptainReview.objects.filter(pk=review.pk).update(
            updated_at=tz.now() - timedelta(minutes=minutes)
        )

    def test_cross_org_raises(self) -> None:
        other = Organization.objects.create(name="Other", owner=self.admin)
        stranger = OrgUser.objects.create(user=self.cap_b, organization=other)
        with self.assertRaises(ValueError):
            maintenance.reassign_member(stranger, self.ou(self.cap_a), now=tz.now())

    def test_same_member_is_noop(self) -> None:
        self.close()
        self.assertEqual(self.reassign(self.cap_a, self.cap_a), 0)

    def test_captain_collision_moves_reviews(self) -> None:
        self.close()
        self.review(self.mates_b[0], self.cap_b, 4)
        self.reassign(self.cap_b, self.cap_a)
        snap = EventCaptain.objects.get(event=self.event)
        self.assertEqual(snap.captain.user, self.cap_a)
        self.assertEqual(CaptainReview.objects.get().event_captain, snap)
        self.assertIn(self.ou(self.mates_b[0]).pk, self.pool(self.cap_a))
        self.assertEqual(
            ContributionEntry.objects.filter(
                org_user=self.ou(self.cap_a), kind="captained"
            ).count(),
            1,
        )
        self.assertFalse(
            ContributionEntry.objects.filter(
                org_user=self.ou(self.cap_b), track="leadership"
            ).exists()
        )

    def test_rater_collision_keeps_newer(self) -> None:
        self.close()
        newer = self.review(self.mates_a[0], self.cap_a, 2)
        older = self.review(self.mates_a[1], self.cap_a, 5)
        self.age(older, 10)
        self.reassign(self.mates_a[0], self.mates_a[1])
        review = CaptainReview.objects.get()
        self.assertEqual(review.pk, newer.pk)
        self.assertEqual(review.rater.user, self.mates_a[1])
        self.assertEqual(set(review.scores.values_list("score", flat=True)), {2})

    def test_moderated_review_wins_a_rater_collision(self) -> None:
        self.close()
        moderated = self.review(self.mates_a[1], self.cap_a, 1)
        self.review(self.mates_a[0], self.cap_a, 5)
        CaptainReview.objects.filter(pk=moderated.pk).update(
            voided_at=tz.now(),
            void_kind="moderated",
            updated_at=tz.now() - timedelta(minutes=10),
        )
        self.reassign(self.mates_a[0], self.mates_a[1])
        review = CaptainReview.objects.get()
        self.assertEqual(review.pk, moderated.pk)
        self.assertEqual(review.void_kind, "moderated")
        self.assertIsNone(self.points(self.cap_a, "captain_rating"))

    def test_moderated_drop_review_wins_a_rater_collision(self) -> None:
        self.close()
        live = self.review(self.mates_a[1], self.cap_a, 5)
        moderated = self.review(self.mates_a[0], self.cap_a, 1)
        CaptainReview.objects.filter(pk=moderated.pk).update(
            voided_at=tz.now(),
            void_kind="moderated",
            updated_at=tz.now() - timedelta(minutes=10),
        )
        self.reassign(self.mates_a[0], self.mates_a[1])
        review = CaptainReview.objects.get()
        self.assertEqual(review.pk, moderated.pk)
        self.assertEqual(review.rater.user, self.mates_a[1])
        self.assertFalse(CaptainReview.objects.filter(pk=live.pk).exists())

    def test_rater_collision_after_window_anonymizes_the_loser(self) -> None:
        self.close()
        newer = self.review(self.mates_a[0], self.cap_a, 2)
        older = self.review(self.mates_a[1], self.cap_a, 5)
        self.age(older, 10)
        self.expire_window()
        self.reassign(self.mates_a[0], self.mates_a[1])
        self.assertEqual(
            CaptainReview.objects.get(pk=newer.pk).rater.user, self.mates_a[1]
        )
        self.assertIsNone(CaptainReview.objects.get(pk=older.pk).rater_id)

    def test_rater_merged_into_captain_deletes_review(self) -> None:
        self.close()
        self.review(self.mates_a[0], self.cap_a, 4)
        self.reassign(self.mates_a[0], self.cap_a)
        self.assertFalse(CaptainReview.objects.exists())
        self.assertNotIn(self.ou(self.cap_a).pk, self.pool(self.cap_a))
        self.assertNotIn(self.ou(self.mates_a[0]).pk, self.pool(self.cap_a))

    def test_pool_replaces_drop_with_keep(self) -> None:
        self.close()
        newcomer = self.make_user("ld_new")
        keep = self.admit(newcomer)
        self.reassign(self.mates_a[0], newcomer)
        pool = self.pool(self.cap_a)
        self.assertIn(keep.pk, pool)
        self.assertNotIn(self.ou(self.mates_a[0]).pk, pool)

    def test_merge_both_in_same_pool(self) -> None:
        self.close()
        self.reassign(self.mates_a[0], self.mates_a[1])
        pool = self.pool(self.cap_a)
        self.assertEqual(pool.count(self.ou(self.mates_a[1]).pk), 1)
        self.assertNotIn(self.ou(self.mates_a[0]).pk, pool)
        self.assertEqual(len(pool), 2)

    def test_captain_collision_with_shared_rater(self) -> None:
        shared = self.mates_a[0]
        self.team_b.members.add(self.cap_a, shared)
        self.close()
        on_keep = self.review(shared, self.cap_a, 5)
        on_drop = self.review(shared, self.cap_b, 2)
        self.age(on_keep, 10)
        self.review(self.cap_a, self.cap_b, 3)
        self.reassign(self.cap_b, self.cap_a)
        review = CaptainReview.objects.get()
        self.assertEqual(review.pk, on_drop.pk)
        self.assertEqual(review.rater.user, shared)
        self.assertEqual(review.event_captain, self.snapshot(self.cap_a))
        self.assertNotIn(self.ou(self.cap_a).pk, self.pool(self.cap_a))

    def test_open_window_recomputes(self) -> None:
        self.close()
        self.review(self.mates_a[0], self.cap_a, 5)
        self.review(self.mates_a[1], self.cap_a, 5)
        self.reassign(self.mates_a[0], self.mates_a[1])
        self.assertIsNone(self.points(self.cap_a, "captain_rating"))

    def test_closed_window_keeps_points(self) -> None:
        self.close()
        self.review(self.mates_a[0], self.cap_a, 5)
        self.review(self.mates_a[1], self.cap_a, 5)
        self.expire_window()
        self.reassign(self.mates_a[0], self.mates_a[1])
        self.assertEqual(CaptainReview.objects.filter(rater__isnull=False).count(), 1)
        self.assertEqual(CaptainReview.objects.filter(rater__isnull=True).count(), 1)
        self.assertEqual(self.points(self.cap_a, "captain_rating"), 10)

    def test_contribution_rows_untouched(self) -> None:
        self.close()
        award_entry(
            org=self.org,
            user=self.cap_b,
            kind="manual",
            points=3,
            reason="help",
            occurred_at=tz.now(),
        )
        self.reassign(self.cap_b, self.cap_a)
        self.assertTrue(
            ContributionEntry.objects.filter(
                org_user=self.ou(self.cap_b), track="contribution"
            ).exists()
        )

    def _event_with_pair(self, name: str, drop: CustomUser, keep: CustomUser) -> Event:
        event, tournament = self.make_event(name)
        self.make_team(name, self.cap_a, [drop, keep], tournament=tournament)
        for user in (self.cap_a, drop, keep):
            self.admit(user, event)
        return event

    @override_settings(CACHEOPS_ENABLED=False)
    def test_query_budget_independent_of_row_count(self) -> None:
        d1, k1, d2, k2 = (self.make_user(f"ld_q{i}") for i in range(4))
        for user in (d1, k1, d2, k2):
            self.admit(user)
        self.team_a.members.add(d1, k1)
        self.team_b.members.add(d2, k2)
        events = [self._event_with_pair(f"Q{i}", d2, k2) for i in range(2)]
        self.close()
        for event in events:
            self.close(event)
        for rater in (d1, k1):
            self.review(rater, self.cap_a, 4)
        for rater in (d2, k2):
            self.review(rater, self.cap_b, 4)
            for event in events:
                self.review(rater, self.cap_a, 4, event=event)
        EventCaptain.objects.update(window_closes_at=tz.now() - timedelta(minutes=1))
        get_leadership_settings(self.org.pk)
        with CaptureQueriesContext(connection) as small:
            self.reassign(d1, k1)
        with CaptureQueriesContext(connection) as large:
            self.reassign(d2, k2)
        self.assertEqual(len(small), len(large))
        self.assertEqual(CaptainReview.objects.filter(rater__user=k2).count(), 3)


class RepointAttributionTest(LeadershipTestCase):
    def test_moves_only_leadership_attribution(self) -> None:
        self.close()
        drop = self.make_user("ld_drop")
        keep = self.make_user("ld_keep")
        review = self.review(self.mates_a[0], self.cap_a, 4)
        CaptainReview.objects.filter(pk=review.pk).update(voided_by=drop)
        settings = get_leadership_settings(self.org.pk, create=True)
        OrgLeadershipSettings.objects.filter(pk=settings.pk).update(updated_by=drop)
        ContributionEntry.objects.filter(track="leadership", kind="captained").update(
            awarded_by=drop
        )
        contrib = award_entry(
            org=self.org,
            user=self.cap_a,
            kind="manual",
            points=3,
            reason="help",
            occurred_at=tz.now(),
            awarded_by=drop,
        )
        lead_value = ContributionPointValue.objects.create(
            organization=self.org, kind="captained", points=7, updated_by=drop
        )
        contrib_value = ContributionPointValue.objects.create(
            organization=self.org, kind="manual", points=2, updated_by=drop
        )
        with transaction.atomic():
            moved = maintenance.repoint_attribution(drop, keep)
        self.assertEqual(moved, 5)
        review.refresh_from_db()
        settings.refresh_from_db()
        contrib.refresh_from_db()
        lead_value.refresh_from_db()
        contrib_value.refresh_from_db()
        self.assertEqual(review.voided_by, keep)
        self.assertEqual(settings.updated_by, keep)
        self.assertEqual(lead_value.updated_by, keep)
        self.assertEqual(contrib.awarded_by, drop)
        self.assertEqual(contrib_value.updated_by, drop)
        self.assertFalse(
            ContributionEntry.objects.filter(
                track="leadership", awarded_by=drop
            ).exists()
        )


class DeleteUserRowsTest(LeadershipTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.close()
        self.review(self.mates_a[0], self.cap_a, 5)
        self.review(self.mates_a[1], self.cap_a, 5)

    def delete_rows(self, user: CustomUser) -> int:
        with transaction.atomic():
            return maintenance.delete_user_rows(user, actor=self.admin, now=tz.now())

    def test_captain_rows_and_log(self) -> None:
        self.assertEqual(self.delete_rows(self.cap_a), 3)
        self.assertFalse(EventCaptain.objects.filter(captain__user=self.cap_a).exists())
        self.assertFalse(CaptainReview.objects.exists())
        log = OrgLog.objects.get(action="delete_user_leadership")
        self.assertEqual(
            log.details,
            {"user_id": self.cap_a.pk, "username": self.cap_a.username, "count": 3},
        )

    def test_rater_inside_window_recomputes(self) -> None:
        self.assertEqual(self.delete_rows(self.mates_a[0]), 0)
        self.assertIsNone(self.points(self.cap_a, "captain_rating"))
        self.assertFalse(
            OrgLog.objects.filter(action="delete_user_leadership").exists()
        )

    def test_rater_after_window_keeps_points(self) -> None:
        self.expire_window()
        self.delete_rows(self.mates_a[0])
        self.assertEqual(CaptainReview.objects.count(), 2)
        self.assertEqual(CaptainReview.objects.filter(rater__isnull=True).count(), 1)
        self.assertEqual(self.points(self.cap_a, "captain_rating"), 10)

    def test_voided_review_after_window_is_deleted(self) -> None:
        CaptainReview.objects.filter(rater__user=self.mates_a[0]).update(
            voided_at=tz.now(), void_kind="withdrawn"
        )
        self.expire_window()
        self.delete_rows(self.mates_a[0])
        self.assertEqual(CaptainReview.objects.count(), 1)

    def test_user_without_rows_is_noop(self) -> None:
        self.assertEqual(self.delete_rows(self.make_user("ld_none")), 0)
