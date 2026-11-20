from datetime import timedelta
from typing import override

from django.db import transaction
from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from app.models import CustomUser, Organization
from events.constants import EventState
from events.models import Event
from org.feature_keys import FeatureKey
from org.features import set_org_feature
from org.models import OrgUser
from org.standing import api as standing
from org.standing.base import TrackBase
from org.standing.cache import StandingCache
from org.standing.periods import parse_period
from org.standing.registry import override_tracks
from org.standing.types import EMPTY_OUTPUT, TrackAccess, TrackOutput
from org.tests.standing_fakes import FakeTrack, atomic_baseline


class NoopTrack(FakeTrack):
    def __init__(self) -> None:
        super().__init__("noop")
        self.output_keys = {}  # type: ignore[misc]


for _name in (
    "on_event_closed",
    "on_event_reopened",
    "on_event_deleted",
    "on_event_changed",
    "on_signup_withdrawn",
    "merge_members",
    "repoint_user",
    "on_user_deleted",
):
    setattr(NoopTrack, _name, getattr(TrackBase, _name))


class StandingAtomicGuardTest(SimpleTestCase):
    def test_hook_outside_atomic_raises(self) -> None:
        fake = FakeTrack()
        event = Event(pk=1, organization_id=1)
        user = CustomUser(pk=1)
        with override_tracks(fake):
            calls = [
                lambda: standing.on_event_closed(
                    event, cancelled=False, source="admin", actor=None
                ),
                lambda: standing.on_event_reopened(event, actor=None),
                lambda: standing.on_event_deleted(event, actor=None),
                lambda: standing.on_event_changed(event, fields=frozenset({"name"})),
                lambda: standing.merge_users(user, CustomUser(pk=2), member_pairs=[]),
                lambda: standing.on_user_deleted(user, actor=None),
            ]
            for call in calls:
                with self.assertRaises(RuntimeError):
                    call()
        self.assertEqual(fake.calls, [])

    def test_api_reexports_survive_ruff(self) -> None:
        for name in (
            "HookResult",
            "LogValue",
            "StandingCache",
            "FeatureLocked",
            "UnknownTrack",
            "UnknownMetric",
        ):
            self.assertTrue(hasattr(standing, name), name)
            self.assertIn(name, standing.__all__)


class StandingApiTest(TestCase):
    def setUp(self) -> None:
        self.owner = CustomUser.objects.create_user(username="sa_owner", password="x")
        self.org = Organization.objects.create(name="SA Org", owner=self.owner)
        self.event = Event.objects.create(
            organization=self.org,
            name="SA Event",
            scheduled_at=timezone.now() - timedelta(hours=2),
            created_by=self.owner,
            state=EventState.IN_PROGRESS,
        )

    def _pair(self) -> tuple[CustomUser, CustomUser, OrgUser, OrgUser]:
        drop = CustomUser.objects.create_user(username="sa_drop", password="x")
        keep = CustomUser.objects.create_user(username="sa_keep", password="x")
        return (
            drop,
            keep,
            OrgUser.objects.create(user=drop, organization=self.org),
            OrgUser.objects.create(user=keep, organization=self.org),
        )

    def test_each_hook_dispatches_in_registry_order_with_one_now(self) -> None:
        a, b = FakeTrack("fake"), FakeTrack("fake2")
        with override_tracks(a, b), transaction.atomic():
            result = standing.on_event_closed(
                self.event, cancelled=False, source="admin", actor=None
            )
            standing.on_event_reopened(self.event, actor=None)
            standing.on_event_deleted(self.event, actor=None)
            standing.on_event_changed(self.event, fields=frozenset({"name"}))
            standing.on_user_deleted(self.owner, actor=None)
        self.assertEqual(list(result.by_track), ["fake", "fake2"])
        self.assertEqual(
            list(result.orglog_details().items()),
            [("fake_count", 1), ("fake2_count", 1)],
        )
        self.assertEqual(result.log_fields(), {"fake_ran": True, "fake2_ran": True})
        expected = [
            "on_event_closed",
            "on_event_reopened",
            "on_event_deleted",
            "on_event_changed",
            "on_user_deleted",
        ]
        self.assertEqual(a.hooks, expected)
        self.assertEqual(b.hooks, expected)
        self.assertEqual(a.calls[0].kwargs["now"], b.calls[0].kwargs["now"])

    def test_caller_now_is_passed_through(self) -> None:
        fake = FakeTrack()
        at = timezone.now() - timedelta(days=3)
        with override_tracks(fake), transaction.atomic():
            standing.on_event_changed(self.event, fields=frozenset({"name"}), now=at)
        self.assertEqual(fake.calls[0].kwargs["now"], at)

    def test_unoverridden_hooks_are_noops(self) -> None:
        drop, keep, drop_ou, keep_ou = self._pair()
        with override_tracks(NoopTrack()), transaction.atomic():
            results = [
                standing.on_event_closed(
                    self.event, cancelled=False, source="admin", actor=None
                ),
                standing.on_event_reopened(self.event, actor=None),
                standing.on_event_deleted(self.event, actor=None),
                standing.on_event_changed(self.event, fields=frozenset({"name"})),
                standing.merge_users(drop, keep, member_pairs=[(drop_ou, keep_ou)]),
                standing.on_user_deleted(drop, actor=None),
            ]
        for result in results:
            self.assertEqual(dict(result.by_track), {"noop": EMPTY_OUTPUT})

    def test_hook_records_atomic_depth(self) -> None:
        fake = FakeTrack()
        with override_tracks(fake):
            baseline = atomic_baseline()
            with transaction.atomic():
                standing.on_event_deleted(self.event, actor=None)
        self.assertEqual(fake.calls[-1].atomic_depth, baseline + 1)

    def test_exception_propagates(self) -> None:
        fake = FakeTrack()
        fake.raise_on = {"on_event_closed"}
        with override_tracks(fake), transaction.atomic():
            with self.assertRaisesMessage(RuntimeError, "fake"):
                standing.on_event_closed(
                    self.event, cancelled=False, source="admin", actor=None
                )

    def test_undeclared_output_key_raises(self) -> None:
        class Sloppy(FakeTrack):
            @override
            def on_event_deleted(self, event, *, actor, now):  # type: ignore[no-untyped-def]
                return TrackOutput(orglog={"surprise": 1})

        with override_tracks(Sloppy()), transaction.atomic():
            with self.assertRaises(RuntimeError):
                standing.on_event_deleted(self.event, actor=None)

    def test_merge_users_order_and_sums(self) -> None:
        drop, keep, drop_ou, keep_ou = self._pair()
        other = Organization.objects.create(name="SA Org 2", owner=self.owner)
        drop_ou2 = OrgUser.objects.create(user=drop, organization=other)
        keep_ou2 = OrgUser.objects.create(user=keep, organization=other)
        fake = FakeTrack()
        with override_tracks(fake), transaction.atomic():
            result = standing.merge_users(
                drop, keep, member_pairs=[(drop_ou, keep_ou), (drop_ou2, keep_ou2)]
            )
        self.assertEqual(fake.hooks, ["merge_members", "merge_members", "repoint_user"])
        self.assertEqual(
            dict(result.by_track["fake"].orglog), {"fake_count": 2, "fake_repointed": 1}
        )
        self.assertEqual(dict(result.by_track["fake"].log), {"fake_ran": True})

    def test_merge_users_rejects_cross_org_pair(self) -> None:
        drop, keep, drop_ou, _ = self._pair()
        other = Organization.objects.create(name="SA Other", owner=self.owner)
        keep_other = OrgUser.objects.create(user=keep, organization=other)
        with override_tracks(FakeTrack()), transaction.atomic():
            with self.assertRaises(ValueError):
                standing.merge_users(drop, keep, member_pairs=[(drop_ou, keep_other)])

    def test_merge_users_rejects_foreign_user_pair(self) -> None:
        drop, keep, drop_ou, keep_ou = self._pair()
        with override_tracks(FakeTrack()), transaction.atomic():
            with self.assertRaises(ValueError):
                standing.merge_users(keep, drop, member_pairs=[(drop_ou, keep_ou)])

    def test_feature_toggle_only_reaches_matching_track(self) -> None:
        promo = FakeTrack("fake")
        contrib = FakeTrack("fake2", feature=FeatureKey.CONTRIBUTIONS)
        with override_tracks(promo, contrib), transaction.atomic():
            standing.on_feature_toggled(self.org.pk, FeatureKey.PROMOTION, enabled=True)
        self.assertEqual(promo.hooks, ["on_feature_toggled"])
        self.assertEqual(contrib.hooks, [])

    def test_reopen_reset_fields_union(self) -> None:
        fake = FakeTrack()
        fake.reopen_reset_fields = ("contributions_awarded_at",)  # type: ignore[misc]
        with override_tracks(fake, FakeTrack("fake2")):
            self.assertEqual(
                standing.reopen_reset_fields(), {"contributions_awarded_at": None}
            )

    def test_promotion_order_permutation_kept(self) -> None:
        items = [OrgUser(user_id=1), OrgUser(user_id=2)]
        fake = FakeTrack()
        fake.order_fn = lambda c: list(reversed(c))
        with override_tracks(fake):
            ordered = standing.promotion_order(self.event, items, cache=StandingCache())
        self.assertEqual(ordered, list(reversed(items)))

    def test_promotion_order_dropping_track_rejected(self) -> None:
        items = [OrgUser(user_id=1), OrgUser(user_id=2)]
        fake = FakeTrack()
        fake.order_fn = lambda c: list(c)[1:]
        with override_tracks(fake), self.assertRaises(ValueError):
            standing.promotion_order(self.event, items, cache=StandingCache())

    def test_leaderboard_unknown_track_and_metric(self) -> None:
        period = parse_period(self.org, None)
        with override_tracks(FakeTrack()):
            with self.assertRaises(standing.UnknownTrack):
                standing.leaderboard(self.org, "nope", "points", period, viewer=None)
            with self.assertRaises(standing.UnknownMetric):
                standing.leaderboard(self.org, "fake", "nope", period, viewer=None)

    def test_leaderboard_locked_feature(self) -> None:
        period = parse_period(self.org, None)
        set_org_feature(self.org, FeatureKey.PROMOTION, enabled=False, actor=self.owner)
        with override_tracks(FakeTrack()), self.assertRaises(standing.FeatureLocked):
            standing.leaderboard(self.org, "fake", "points", period, viewer=None)

    def test_leaderboard_blanks_rows_and_own_row(self) -> None:
        period = parse_period(self.org, None)
        set_org_feature(self.org, FeatureKey.PROMOTION, enabled=True, actor=self.owner)
        fake = FakeTrack()
        fake.track_access = TrackAccess(can_view_rows=False, can_view_own=False)
        with override_tracks(fake):
            board = standing.leaderboard(
                self.org, "fake", "points", period, viewer=None
            )
        self.assertEqual(tuple(board.rows), ())
        self.assertIsNone(board.own_row)
        self.assertEqual(board.total, 42)
        self.assertFalse(board.rows_visible)
