from datetime import timedelta

from django.db import connection, transaction
from django.test.utils import CaptureQueriesContext, override_settings
from django.utils import timezone as tz
from structlog.testing import capture_logs

from events.constants import EventState
from events.models import Event
from events.reopen import reopen_event
from events.services import teardown_event
from org.conduct.constants import Outcome
from org.feature_keys import FeatureKey
from org.features import set_org_feature
from org.leadership import lifecycle
from org.models import ContributionEntry, ContributionPointValue, OrgUser
from org.models_leadership import (
    CaptainReview,
    CaptainReviewDraft,
    EventCaptain,
    OrgLeadershipSettings,
)
from org.standing import api as standing
from org.tests.leadership_base import LeadershipTestCase
from tournament.models import Team
from tournament.models.team_log import TeamLogVia
from tournament.services.team_management import replace_captain

SNAPSHOT_QUERIES = 18


def pool(snap: EventCaptain) -> set[int]:
    return set(snap.teammates.values_list("user_id", flat=True))


class SnapshotTest(LeadershipTestCase):
    def test_close_snapshots_captains_and_pool(self) -> None:
        self.close()
        snap = self.snapshot(self.cap_a)
        self.assertEqual(snap.team_name, "Alpha")
        self.assertEqual(snap.placement, 1)
        self.assertEqual(pool(snap), {u.pk for u in self.mates_a})
        self.assertGreater(snap.window_closes_at, tz.now() + timedelta(hours=71))

    def test_snapshot_pool_excludes_captain_and_unadmitted(self) -> None:
        stranger = self.make_user("ld_stranger")
        self.team_a.members.add(stranger)
        self.run_snapshot()
        self.assertEqual(pool(self.snapshot(self.cap_a)), {u.pk for u in self.mates_a})

    def test_awards_captained_and_placement(self) -> None:
        self.close()
        self.assertEqual(self.points(self.cap_a, "captained"), 5)
        self.assertEqual(self.points(self.cap_a, "placement_1"), 10)
        self.assertEqual(self.points(self.cap_b, "placement_2"), 6)
        self.assertIsNone(self.points(self.cap_a, "draft_completed"))

    def test_awards_per_kind_and_overrides(self) -> None:
        cap_c = self.make_user("ld_cap_c")
        self.make_team("Charlie", cap_c, [], placement=4)
        self.admit(cap_c)
        self.complete_draft()
        ContributionPointValue.objects.create(
            organization=self.org, kind="captained", points=7
        )
        self.run_snapshot()
        self.assertEqual(self.points(self.cap_a, "captained"), 7)
        self.assertEqual(self.points(self.cap_a, "placement_1"), 10)
        self.assertEqual(self.points(self.cap_a, "draft_completed"), 2)
        self.assertEqual(
            set(
                ContributionEntry.objects.filter(org_user__user=cap_c).values_list(
                    "kind", flat=True
                )
            ),
            {"captained", "draft_completed"},
        )
        self.assertEqual(
            set(ContributionEntry.objects.values_list("track", flat=True)),
            {"leadership"},
        )

    def test_orglog_counts(self) -> None:
        self.close()
        log = self.org.logs.get(action="complete_event")
        self.assertEqual(log.details["captains_snapshotted"], 2)
        self.assertEqual(log.details["leadership_awarded"], 4)

    def test_window_from_settings(self) -> None:
        OrgLeadershipSettings.objects.create(
            organization=self.org, review_window_hours=24
        )
        now = tz.now()
        self.run_snapshot(now=now)
        self.assertEqual(
            self.snapshot(self.cap_a).window_closes_at, now + timedelta(hours=24)
        )

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

    def test_captainless_team_skipped(self) -> None:
        loner = self.make_user("ld_loner")
        self.admit(loner)
        self.make_team("NoCap", None, [loner])
        self.run_snapshot()
        self.assertEqual(EventCaptain.objects.count(), 2)

    def test_captain_without_signup_skipped(self) -> None:
        self.event.signups.filter(user=self.cap_b).delete()
        self.run_snapshot()
        self.assertFalse(EventCaptain.objects.filter(captain__user=self.cap_b).exists())
        self.assertIsNone(self.points(self.cap_b, "captained"))

    def test_never_creates_org_users(self) -> None:
        OrgUser.objects.filter(user=self.mates_a[0], organization=self.org).delete()
        before = OrgUser.objects.count()
        self.run_snapshot()
        self.assertEqual(OrgUser.objects.count(), before)
        self.assertEqual(
            pool(self.snapshot(self.cap_a)), {u.pk for u in self.mates_a[1:]}
        )

    def test_duplicate_captain_skipped_with_warning(self) -> None:
        self.make_team("Alpha2", self.cap_a, [], placement=3)
        with capture_logs() as logs:
            result = self.run_snapshot()
        self.assertEqual(result.captains, 2)
        self.assertEqual(
            EventCaptain.objects.filter(captain__user=self.cap_a).count(), 1
        )
        self.assertIsNone(self.points(self.cap_a, "placement_3"))
        self.assertIn(
            "leadership_duplicate_captain",
            [e["event"] for e in logs if e["log_level"] == "warning"],
        )

    def test_conduct_pool_requires_attended(self) -> None:
        extra = [self.make_user(f"ld_a_extra{i}") for i in range(2)]
        self.team_a.members.add(*extra)
        for user in extra:
            self.admit(user)
        a, b, c2 = self.mates_a
        d, e = extra
        self.outcome(a, event=self.event, outcome=Outcome.ATTENDED)
        self.outcome(b, event=self.event, outcome=Outcome.NO_SHOW)
        self.outcome(c2, event=self.event, outcome=Outcome.PENDING, finalized=False)
        self.outcome(d, event=self.event, outcome=Outcome.EXCUSED)
        self.outcome(e, event=self.event, outcome=Outcome.LATE_CANCEL)
        self.run_snapshot()
        self.assertEqual(
            pool(self.snapshot(self.cap_a)), {a.pk, b.pk, c2.pk, d.pk, e.pk}
        )
        self.unlock()
        self.run_snapshot()
        self.assertEqual(pool(self.snapshot(self.cap_a)), {a.pk})

    def test_voided_attended_outcome_not_in_pool(self) -> None:
        self.unlock()
        a, b, _ = self.mates_a
        self.outcome(a, event=self.event, outcome=Outcome.ATTENDED)
        self.outcome(b, event=self.event, outcome=Outcome.ATTENDED, voided_at=tz.now())
        self.run_snapshot()
        self.assertEqual(pool(self.snapshot(self.cap_a)), {a.pk})

    def test_idempotent_close(self) -> None:
        self.complete_draft()
        first = self.run_snapshot()
        second = self.run_snapshot()
        self.assertEqual(first.awarded, 6)
        self.assertEqual(second.awarded, 0)
        self.assertEqual(EventCaptain.objects.count(), 2)
        self.assertEqual(ContributionEntry.objects.count(), 6)
        self.assertEqual(pool(self.snapshot(self.cap_a)), {u.pk for u in self.mates_a})

    def test_cancel_writes_nothing(self) -> None:
        self.close(state=EventState.CANCELLED)
        self.assertFalse(EventCaptain.objects.exists())

    def _sized_event(self, name: str, teams: int) -> Event:
        event, tournament = self.make_event(name)
        for t in range(teams):
            cap = self.make_user(f"{name}_cap{t}")
            mates = [self.make_user(f"{name}_{t}_{i}") for i in range(4)]
            self.make_team(f"T{t}", cap, mates, placement=t + 1, tournament=tournament)
            for user in [cap, *mates]:
                self.admit(user, event)
                self.outcome(user, event=event, outcome=Outcome.ATTENDED)
        self.complete_draft(tournament)
        return event

    def _snapshot_queries(self, event: Event) -> int:
        Event.objects.filter(pk=event.pk).update(state=EventState.COMPLETED)
        event.refresh_from_db()
        with transaction.atomic(), CaptureQueriesContext(connection) as ctx:
            lifecycle.snapshot_event(event, now=tz.now())
        return len(ctx.captured_queries)

    @override_settings(CACHEOPS_ENABLED=False)
    def test_close_query_budget_independent_of_team_count(self) -> None:
        self.unlock()
        small = self._snapshot_queries(self._sized_event("small", 2))
        big = self._snapshot_queries(self._sized_event("big", 8))
        self.assertEqual(small, big)
        self.assertEqual(big, SNAPSHOT_QUERIES)
        snaps = EventCaptain.objects.filter(event__name="big")
        self.assertEqual(snaps.count(), 8)
        self.assertEqual(
            EventCaptain.teammates.through.objects.filter(
                eventcaptain__in=snaps
            ).count(),
            32,
        )


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

    def test_void_event_voids_and_revokes(self) -> None:
        self.close()
        self.review(self.mates_a[0], self.cap_a)
        host = ContributionEntry.objects.create(
            org_user=self.org_user(self.admin),
            organization=self.org,
            track="contribution",
            kind="event_host",
            points=3,
            event=self.event,
            event_name=self.event.name,
            occurred_at=tz.now(),
        )
        with transaction.atomic():
            result = lifecycle.void_event(self.event, now=tz.now())
        self.assertEqual(result.reviews_voided, 1)
        self.assertEqual(result.revoked, 4)
        self.assertEqual(CaptainReview.objects.get().void_kind, "lifecycle")
        self.assertFalse(EventCaptain.objects.filter(voided_at__isnull=True).exists())
        self.assertEqual(list(ContributionEntry.objects.all()), [host])

    def test_void_event_deletes_drafts(self) -> None:
        self.close()
        other_event, other_tournament = self.make_event("Other Cup")
        self.make_team("Gamma", self.cap_a, self.mates_a, tournament=other_tournament)
        for user in [self.cap_a, *self.mates_a]:
            self.admit(user, other_event)
        self.close(other_event)
        for snap in (self.snapshot(self.cap_a), self.snapshot(self.cap_b)):
            mate = snap.teammates.order_by("pk")[0]
            CaptainReviewDraft.objects.create(
                event_captain=snap, rater=mate, scores={"1": 3}
            )
        other_snap = self.snapshot(self.cap_a, other_event)
        kept = CaptainReviewDraft.objects.create(
            event_captain=other_snap, rater=self.org_user(self.mates_a[0])
        )
        with transaction.atomic():
            lifecycle.void_event(self.event, now=tz.now())
        self.assertEqual(list(CaptainReviewDraft.objects.all()), [kept])

    def test_cancel_after_close_voids(self) -> None:
        self.close()
        self.review(self.mates_a[0], self.cap_a)
        with transaction.atomic():
            standing.on_event_closed(
                self.event,
                cancelled=True,
                source="admin",
                actor=self.admin,
                now=tz.now(),
            )
        self.assertEqual(CaptainReview.objects.get().void_kind, "lifecycle")
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

    def test_resnapshot_clears_release(self) -> None:
        self.close()
        EventCaptain.objects.filter(event=self.event).update(
            released_at=tz.now(), released_by=self.admin
        )
        self.event.refresh_from_db()
        reopen_event(self.event, actor=self.admin)
        Event.objects.filter(pk=self.event.pk).update(state=EventState.IN_PROGRESS)
        self.event.refresh_from_db()
        self.close()
        snaps = EventCaptain.objects.nocache().filter(event=self.event)
        self.assertTrue(snaps.exists())
        for snap in snaps:
            self.assertIsNone(snap.released_at)
            self.assertIsNone(snap.released_by_id)

    def test_reclose_with_new_captain(self) -> None:
        self.close()
        self.review(self.mates_a[0], self.cap_a)
        self.event.refresh_from_db()
        reopen_event(self.event, actor=self.admin)
        Event.objects.filter(pk=self.event.pk).update(state=EventState.IN_PROGRESS)
        self.event.refresh_from_db()
        self.team_a.captain = self.mates_a[1]
        self.team_a.save()
        self.close()
        self.assertIsNotNone(self.snapshot(self.cap_a).voided_at)
        self.assertIsNone(self.snapshot(self.mates_a[1]).voided_at)
        self.assertIsNone(self.points(self.cap_a, "captained"))
        self.assertEqual(self.points(self.mates_a[1], "captained"), 5)
        old = CaptainReview.objects.get(event_captain__captain__user=self.cap_a)
        self.assertEqual(old.void_kind, "lifecycle")
        self.assertNotIn(self.mates_a[1].pk, pool(self.snapshot(self.mates_a[1])))
        self.assertIn(self.cap_a.pk, pool(self.snapshot(self.mates_a[1])))

    @override_settings(CACHEOPS_ENABLED=False)
    def test_void_without_snapshots_costs_one_query(self) -> None:
        with transaction.atomic(), CaptureQueriesContext(connection) as ctx:
            result = lifecycle.void_event(self.event, now=tz.now())
        self.assertEqual(result, lifecycle.VoidResult(reviews_voided=0, revoked=0))
        self.assertEqual(len(ctx.captured_queries), 1)


class TakeoverSnapshotTest(LeadershipTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.cap_e = self.make_user("ld_cap_e")
        self.mates_e = [self.make_user(f"ld_e{i}") for i in range(2)]
        self.team_e = self.make_team("Echo", self.cap_e, self.mates_e, placement=3)
        for user in [self.cap_e, *self.mates_e]:
            self.admit(user)
        self.assertGreater(self.team_e.pk, self.team_b.pk)
        Team.objects.filter(pk=self.team_b.pk).invalidated_update(placement=None)
        replace_captain(
            self.team_b,
            self.cap_e,
            actor=self.admin,
            via=TeamLogVia.WEB,
            reason="left",
        )
        Team.objects.filter(pk=self.team_b.pk).invalidated_update(placement=2)

    def assert_snapshot_on_original_team(self) -> None:
        snap = self.snapshot(self.cap_e)
        self.assertEqual(snap.team_id, self.team_e.pk)
        self.assertEqual(snap.team_name, "Echo")
        self.assertEqual(snap.placement, 3)
        self.assertEqual(pool(snap), {u.pk for u in self.mates_e})
        self.assertEqual(self.points(self.cap_e, "placement_3"), 3)
        self.assertIsNone(self.points(self.cap_e, "placement_2"))
        self.assertFalse(
            EventCaptain.objects.filter(
                event=self.event, team=self.team_b, voided_at__isnull=True
            ).exists()
        )

    def test_dual_captain_one_snapshot_on_original_team(self) -> None:
        self.close()
        self.assertEqual(
            EventCaptain.objects.filter(captain__user=self.cap_e).count(), 1
        )
        self.assert_snapshot_on_original_team()

    def test_reopen_close_keeps_snapshot_on_original_team(self) -> None:
        self.close()
        self.event.refresh_from_db()
        reopen_event(self.event, actor=self.admin)
        Event.objects.filter(pk=self.event.pk).update(state=EventState.IN_PROGRESS)
        self.event.refresh_from_db()
        self.close()
        self.assertIsNone(self.snapshot(self.cap_e).voided_at)
        self.assert_snapshot_on_original_team()


class DeleteTest(LeadershipTestCase):
    def test_delete_removes_rows_and_reviews(self) -> None:
        self.close()
        self.review(self.mates_a[0], self.cap_a)
        self.event.refresh_from_db()
        teardown_event(self.event, actor=self.admin)
        self.assertFalse(ContributionEntry.objects.filter(track="leadership").exists())
        self.assertFalse(CaptainReview.objects.exists())
        self.assertFalse(EventCaptain.objects.exists())

    def test_delete_event_rows(self) -> None:
        self.close()
        self.review(self.mates_a[0], self.cap_a)
        with transaction.atomic():
            removed = lifecycle.delete_event_rows(self.event)
        self.assertEqual(removed, 4)
        self.assertFalse(ContributionEntry.objects.filter(track="leadership").exists())
        self.event.delete()
        self.assertFalse(EventCaptain.objects.exists())
        self.assertFalse(CaptainReview.objects.exists())

    @override_settings(CACHEOPS_ENABLED=False)
    def test_delete_without_snapshots_costs_one_query(self) -> None:
        with transaction.atomic(), CaptureQueriesContext(connection) as ctx:
            removed = lifecycle.delete_event_rows(self.event)
        self.assertEqual(removed, 0)
        self.assertEqual(len(ctx.captured_queries), 1)

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
