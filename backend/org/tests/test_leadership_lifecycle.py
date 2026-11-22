from datetime import timedelta

from django.db import connection, transaction
from django.test.utils import CaptureQueriesContext, override_settings
from django.utils import timezone as tz

from events.constants import EventState
from events.models import Event
from events.reopen import reopen_event
from events.services import teardown_event
from org.feature_keys import FeatureKey
from org.features import set_org_feature
from org.leadership import lifecycle
from org.models import ContributionEntry, ContributionPointValue
from org.models_leadership import CaptainReview, EventCaptain
from org.standing import api as standing
from org.tests.leadership_base import LeadershipTestCase


class SnapshotTest(LeadershipTestCase):
    def test_close_snapshots_captains_and_pool(self) -> None:
        self.close()
        snap = self.snapshot(self.cap_a)
        self.assertEqual(snap.team_name, "Alpha")
        self.assertEqual(snap.placement, 1)
        self.assertEqual(
            set(snap.teammates.values_list("user_id", flat=True)),
            {u.pk for u in self.mates_a},
        )
        self.assertGreater(snap.window_closes_at, tz.now() + timedelta(hours=71))

    def test_awards_captained_and_placement(self) -> None:
        self.close()
        self.assertEqual(self.points(self.cap_a, "captained"), 5)
        self.assertEqual(self.points(self.cap_a, "placement_1"), 10)
        self.assertEqual(self.points(self.cap_b, "placement_2"), 6)
        self.assertIsNone(self.points(self.cap_a, "draft_completed"))

    def test_draft_completed_award_and_override(self) -> None:
        self.complete_draft()
        ContributionPointValue.objects.create(
            organization=self.org, kind="captained", points=7
        )
        self.close()
        self.assertEqual(self.points(self.cap_a, "draft_completed"), 2)
        self.assertEqual(self.points(self.cap_a, "captained"), 7)

    def test_orglog_counts(self) -> None:
        self.close()
        log = self.org.logs.get(action="complete_event")
        self.assertEqual(log.details["captains_snapshotted"], 2)
        self.assertEqual(log.details["leadership_awarded"], 4)

    def test_no_tournament_produces_nothing(self) -> None:
        self.event.tournament = None
        self.event.save(update_fields=["tournament"])
        self.close()
        self.assertFalse(EventCaptain.objects.exists())

    def test_locked_feature_writes_nothing(self) -> None:
        set_org_feature(self.org, FeatureKey.LEADERSHIP, enabled=False, actor=None)
        self.close()
        self.assertFalse(EventCaptain.objects.exists())
        self.assertFalse(ContributionEntry.objects.filter(track="leadership").exists())

    def test_captainless_team_and_unadmitted_users_skipped(self) -> None:
        stranger = self.make_user("ld_stranger")
        self.make_team("NoCap", None, [stranger])
        self.team_b.members.add(stranger)
        self.close()
        self.assertEqual(EventCaptain.objects.count(), 2)
        self.assertNotIn(
            stranger.pk,
            self.snapshot(self.cap_b).teammates.values_list("user_id", flat=True),
        )

    def test_unadmitted_captain_skipped(self) -> None:
        self.event.signups.filter(user=self.cap_b).delete()
        self.close()
        self.assertFalse(EventCaptain.objects.filter(captain__user=self.cap_b).exists())

    def test_cancel_writes_nothing(self) -> None:
        self.close(state=EventState.CANCELLED)
        self.assertFalse(EventCaptain.objects.exists())

    @override_settings(CACHEOPS_ENABLED=False)
    def test_snapshot_query_budget_bounded_by_teams(self) -> None:
        event, tournament = self.make_event("Big")
        for t in range(8):
            cap = self.make_user(f"big_cap{t}")
            mates = [self.make_user(f"big_{t}_{i}") for i in range(4)]
            self.make_team(f"T{t}", cap, mates, placement=t + 1, tournament=tournament)
            for user in [cap, *mates]:
                self.admit(user, event)
        with transaction.atomic(), CaptureQueriesContext(connection) as ctx:
            result = lifecycle.snapshot_event(event, now=tz.now())
        self.assertEqual(result.captains, 8)
        self.assertLessEqual(len(ctx.captured_queries), 16)


class ReopenTest(LeadershipTestCase):
    def test_reopen_voids_and_revokes(self) -> None:
        self.close()
        self.review(self.mates_a[0], self.cap_a)
        self.event.refresh_from_db()
        result = reopen_event(self.event, actor=self.admin)
        self.assertEqual(result.details["captain_reviews_voided"], 1)
        self.assertGreater(result.details["leadership_revoked"], 0)
        self.assertIsNotNone(self.snapshot(self.cap_a).voided_at)
        review = CaptainReview.objects.get()
        self.assertEqual(review.void_kind, "lifecycle")
        self.assertFalse(ContributionEntry.objects.filter(track="leadership").exists())

    def test_reclose_unvoids_and_rater_can_resubmit(self) -> None:
        self.close()
        self.review(self.mates_a[0], self.cap_a, 2)
        self.event.refresh_from_db()
        reopen_event(self.event, actor=self.admin)
        Event.objects.filter(pk=self.event.pk).update(state=EventState.IN_PROGRESS)
        self.event.refresh_from_db()
        self.close()
        self.assertIsNone(self.snapshot(self.cap_a).voided_at)
        self.assertEqual(CaptainReview.objects.get().void_kind, "lifecycle")
        self.review(self.mates_a[0], self.cap_a, 4)
        review = CaptainReview.objects.get()
        self.assertEqual(review.void_kind, "")
        self.assertEqual(set(review.scores.values_list("score", flat=True)), {4})

    def test_reclose_with_new_captain(self) -> None:
        self.close()
        self.event.refresh_from_db()
        reopen_event(self.event, actor=self.admin)
        Event.objects.filter(pk=self.event.pk).update(state=EventState.IN_PROGRESS)
        self.event.refresh_from_db()
        self.team_a.captain = self.mates_a[0]
        self.team_a.save()
        self.close()
        self.assertIsNotNone(self.snapshot(self.cap_a).voided_at)
        self.assertIsNone(self.snapshot(self.mates_a[0]).voided_at)
        self.assertIsNone(self.points(self.cap_a, "captained"))
        self.assertEqual(self.points(self.mates_a[0], "captained"), 5)


class DeleteTest(LeadershipTestCase):
    def test_delete_removes_rows_and_reviews(self) -> None:
        self.close()
        self.review(self.mates_a[0], self.cap_a)
        self.event.refresh_from_db()
        teardown_event(self.event, actor=self.admin)
        self.assertFalse(ContributionEntry.objects.filter(track="leadership").exists())
        self.assertFalse(CaptainReview.objects.exists())
        self.assertFalse(EventCaptain.objects.exists())

    def test_org_delete_cascades_through_restrict(self) -> None:
        self.close()
        self.review(self.mates_a[0], self.cap_a)
        self.review(self.mates_a[1], self.cap_a)
        ContributionEntry.objects.filter(organization=self.org).delete()
        self.org.delete()
        self.assertFalse(CaptainReview.objects.exists())

    def test_standing_on_event_deleted_hook(self) -> None:
        self.close()
        with transaction.atomic():
            standing.on_event_deleted(self.event, actor=None)
        self.assertFalse(ContributionEntry.objects.filter(track="leadership").exists())
