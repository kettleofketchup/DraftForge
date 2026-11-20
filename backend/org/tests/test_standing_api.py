from collections.abc import Collection, Mapping, Sequence
from datetime import datetime, timedelta
from typing import Any, override
from unittest.mock import patch

from django.db import connection, transaction
from django.db.models import QuerySet
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from app.discord_accounts import merge_discord_accounts
from app.models import CustomUser, Organization, OrgLog
from events.completion import close_event
from events.constants import EventState
from events.models import Event
from events.reopen import reopen_event
from events.services import teardown_event
from org.contributions.adapter import CONTRIBUTION
from org.feature_keys import FeatureKey
from org.features import set_org_feature
from org.models import OrgUser
from org.standing import api as standing
from org.standing.base import TrackBase
from org.standing.cache import StandingCache
from org.standing.errors import FeatureLocked, UnknownMetric, UnknownTrack
from org.standing.periods import Period, parse_period
from org.standing.registry import override_tracks, validate
from org.standing.types import (
    CloseSource,
    HookName,
    Leaderboard,
    Metric,
    OutputKeys,
    TrackInfo,
    TrackOutput,
)

POINTS = Metric(key="score", label="Score", format="int", periodic=True, default=True)


class FakeTrack(TrackBase):
    key = "conduct"
    label = "Fake"
    feature = FeatureKey.CONTRIBUTIONS
    metrics = (POINTS,)
    reopen_reset_fields = ()
    output_keys: Mapping[HookName, OutputKeys] = {
        "on_event_closed": OutputKeys(orglog=("fake_closed",)),
        "on_event_reopened": OutputKeys(orglog=("fake_reopened",)),
    }

    def __init__(self, *, raise_on: str | None = None) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.raise_on = raise_on

    def _record(self, hook: str, **kwargs: Any) -> None:
        self.calls.append((hook, kwargs))
        if self.raise_on == hook:
            raise RuntimeError(f"fake {hook} failed")

    def hooks(self) -> list[str]:
        return [hook for hook, _ in self.calls]

    @override
    def on_event_closed(
        self,
        event: Event,
        *,
        cancelled: bool,
        source: CloseSource,
        actor: CustomUser | None,
        now: datetime,
    ) -> TrackOutput:
        self._record(
            "on_event_closed", event=event, cancelled=cancelled, source=source, now=now
        )
        return TrackOutput(orglog={"fake_closed": 7}, log={"fake_ran": True})

    @override
    def on_event_reopened(
        self, event: Event, *, actor: CustomUser | None, now: datetime
    ) -> TrackOutput:
        self._record("on_event_reopened", event=event, now=now)
        return TrackOutput(orglog={"fake_reopened": 2})

    @override
    def on_event_deleted(
        self, event: Event, *, actor: CustomUser | None, now: datetime
    ) -> TrackOutput:
        self._record("on_event_deleted", event=event, now=now)
        return TrackOutput()

    @override
    def on_event_changed(
        self, event: Event, *, fields: frozenset[str], now: datetime
    ) -> TrackOutput:
        self._record("on_event_changed", event=event, fields=fields, now=now)
        return TrackOutput()

    @override
    def merge_members(self, drop: OrgUser, keep: OrgUser) -> TrackOutput:
        self._record("merge_members", drop=drop.pk, keep=keep.pk)
        return TrackOutput()

    @override
    def repoint_user(self, drop: CustomUser, keep: CustomUser) -> TrackOutput:
        self._record("repoint_user", drop=drop.pk, keep=keep.pk)
        return TrackOutput()

    @override
    def on_user_deleted(
        self, user: CustomUser, *, actor: CustomUser | None
    ) -> TrackOutput:
        self._record("on_user_deleted", user=user.pk)
        return TrackOutput()

    @override
    def deletion_blockers(self, user_pks: Collection[int]) -> list[QuerySet[Any]]:
        return []

    @override
    def track_info(self, org: Organization, *, viewer: CustomUser | None) -> TrackInfo:
        return TrackInfo(
            key=self.key,
            label=self.label,
            metrics=self.metrics,
            can_view_rows=False,
            can_view_own=False,
            can_manage=False,
        )

    @override
    def leaderboard(
        self,
        org: Organization,
        metric: Metric,
        period: Any,
        *,
        viewer: CustomUser | None,
        now: datetime,
    ) -> Leaderboard:
        return Leaderboard(
            track=self.key,
            metric=metric,
            period="all",
            rows=[],
            total=1,
            own_row=None,
            rows_visible=True,
        )

    @override
    def member_standing(
        self, org_user: OrgUser, *, viewer: CustomUser | None, now: datetime
    ) -> Mapping[str, object]:
        return {}


class InheritingTrack(TrackBase):
    key = "leadership"
    label = "Inheriting"
    feature = FeatureKey.CONTRIBUTIONS
    metrics = (POINTS,)

    def __init__(self) -> None:
        self.closed = 0

    @override
    def on_event_closed(
        self,
        event: Event,
        *,
        cancelled: bool,
        source: CloseSource,
        actor: CustomUser | None,
        now: datetime,
    ) -> TrackOutput:
        self.closed += 1
        return TrackOutput()

    @override
    def track_info(self, org: Organization, *, viewer: CustomUser | None) -> TrackInfo:
        return FakeTrack.track_info(self, org, viewer=viewer)  # type: ignore[arg-type]

    @override
    def leaderboard(
        self,
        org: Organization,
        metric: Metric,
        period: Any,
        *,
        viewer: CustomUser | None,
        now: datetime,
    ) -> Leaderboard:
        raise NotImplementedError

    @override
    def member_standing(
        self, org_user: OrgUser, *, viewer: CustomUser | None, now: datetime
    ) -> Mapping[str, object]:
        return {}


class _Fixture(TestCase):
    def setUp(self) -> None:
        self.owner = CustomUser.objects.create_user(username="std_owner", password="x")
        self.org = Organization.objects.create(name="Standing Org", owner=self.owner)
        self.event = Event.objects.create(
            organization=self.org,
            name="Standing Event",
            scheduled_at=timezone.now() - timedelta(hours=2),
            created_by=self.owner,
            state=EventState.IN_PROGRESS,
        )


class DispatchTest(_Fixture):
    def test_hooks_run_in_registry_order_with_one_shared_now(self) -> None:
        fake = FakeTrack()
        inheriting = InheritingTrack()
        with override_tracks(CONTRIBUTION, fake, inheriting):
            with transaction.atomic():
                result = standing.on_event_closed(
                    self.event, cancelled=False, source="admin", actor=None
                )
                standing.on_event_reopened(self.event, actor=None)
        self.assertEqual(
            list(result.by_track), ["contribution", "conduct", "leadership"]
        )
        self.assertEqual(inheriting.closed, 1)
        self.assertEqual(fake.hooks(), ["on_event_closed", "on_event_reopened"])
        self.assertEqual(result.orglog_details(), {"awarded": 0, "fake_closed": 7})
        self.assertEqual(
            result.log_fields(), {"awarded": True, "created": 0, "fake_ran": True}
        )

    def test_caller_now_is_passed_through(self) -> None:
        fake = FakeTrack()
        at = timezone.now() - timedelta(days=3)
        with override_tracks(fake), transaction.atomic():
            standing.on_event_changed(self.event, fields=frozenset({"name"}), now=at)
        self.assertEqual(fake.calls[0][1]["now"], at)

    def test_requires_atomic_block(self) -> None:
        with (
            override_tracks(FakeTrack()),
            patch.object(connection, "in_atomic_block", False),
        ):
            with self.assertRaises(RuntimeError):
                standing.on_event_deleted(self.event, actor=None)

    def test_reopen_reset_fields_union(self) -> None:
        with override_tracks(CONTRIBUTION, FakeTrack()):
            self.assertEqual(
                standing.reopen_reset_fields(), {"contributions_awarded_at": None}
            )


class RegistryValidationTest(TestCase):
    def test_duplicate_key(self) -> None:
        with self.assertRaises(ValueError):
            validate((FakeTrack(), FakeTrack()))

    def test_two_default_metrics(self) -> None:
        fake = FakeTrack()
        fake.metrics = (POINTS, POINTS)  # type: ignore[misc]
        with self.assertRaises(ValueError):
            validate((fake,))

    def test_output_key_collision(self) -> None:
        fake = FakeTrack()
        fake.output_keys = {  # type: ignore[misc]
            "on_event_closed": OutputKeys(orglog=("awarded",))
        }
        with self.assertRaises(ValueError):
            validate((CONTRIBUTION, fake))

    def test_unknown_track(self) -> None:
        with self.assertRaises(UnknownTrack):
            standing.leaderboard(
                Organization(pk=1),
                "nope",
                "points",
                Period(None, None, "all"),
                viewer=None,
            )


class PromotionOrderTest(_Fixture):
    def test_permutation_preserved_and_drop_rejected(self) -> None:
        class Dropping(InheritingTrack):
            @override
            def promotion_order[T](  # type: ignore[override]
                self, event: Event, candidates: Sequence[T], *, cache: StandingCache
            ) -> list[T]:
                return list(candidates)[1:]

        items = [OrgUser(user_id=1), OrgUser(user_id=2)]
        with override_tracks(InheritingTrack()):
            self.assertEqual(
                standing.promotion_order(self.event, items, cache=StandingCache()),
                items,
            )
        with override_tracks(Dropping()), self.assertRaises(ValueError):
            standing.promotion_order(self.event, items, cache=StandingCache())


class LeaderboardErrorsTest(_Fixture):
    def test_unknown_metric_and_locked_feature(self) -> None:
        period = parse_period(self.org, None)
        with self.assertRaises(UnknownMetric):
            standing.leaderboard(self.org, "contribution", "nope", period, viewer=None)
        with self.assertRaises(FeatureLocked):
            standing.leaderboard(
                self.org, "contribution", "points", period, viewer=None
            )


class CallSiteTest(_Fixture):
    def test_close_admin_and_auto_completed_and_cancelled(self) -> None:
        cases: list[tuple[EventState, EventState, CloseSource, bool]] = [
            (EventState.IN_PROGRESS, EventState.COMPLETED, "admin", False),
            (EventState.IN_PROGRESS, EventState.COMPLETED, "auto", False),
            (EventState.SIGNUPS_OPEN, EventState.CANCELLED, "admin", True),
            (EventState.SIGNUPS_OPEN, EventState.CANCELLED, "auto", True),
        ]
        for start, new_state, source, cancelled in cases:
            with self.subTest(source=source, new_state=new_state):
                Event.objects.filter(pk=self.event.pk).update(state=start)
                self.event.refresh_from_db()
                fake = FakeTrack()
                with override_tracks(CONTRIBUTION, fake):
                    close_event(
                        self.event, new_state=new_state, source=source, actor=self.owner
                    )
                kwargs = fake.calls[0][1]
                self.assertEqual(fake.hooks(), ["on_event_closed"])
                self.assertEqual(kwargs["cancelled"], cancelled)
                self.assertEqual(kwargs["source"], source)
                self.assertEqual(kwargs["now"], self.event.updated_at)

    def test_close_orglog_carries_track_details(self) -> None:
        with override_tracks(CONTRIBUTION, FakeTrack()):
            close_event(
                self.event,
                new_state=EventState.COMPLETED,
                source="admin",
                actor=self.owner,
            )
        details = OrgLog.objects.get(action="complete_event").details
        self.assertEqual(details["fake_closed"], 7)
        self.assertEqual(details["awarded"], 0)

    def test_reopen_sees_fresh_event(self) -> None:
        Event.objects.filter(pk=self.event.pk).update(state=EventState.COMPLETED)
        fake = FakeTrack()
        with override_tracks(CONTRIBUTION, fake):
            reopen_event(self.event, actor=self.owner)
        self.assertEqual(fake.hooks(), ["on_event_reopened"])
        self.assertEqual(fake.calls[0][1]["event"].state, EventState.SIGNUPS_OPEN)
        details = OrgLog.objects.get(action="reopen_event").details
        self.assertEqual(details["fake_reopened"], 2)

    def test_adapter_exception_rolls_back_transition(self) -> None:
        with override_tracks(FakeTrack(raise_on="on_event_closed")):
            with self.assertRaises(RuntimeError):
                close_event(self.event, new_state=EventState.COMPLETED, source="admin")
        self.assertEqual(
            Event.objects.nocache().get(pk=self.event.pk).state, EventState.IN_PROGRESS
        )
        Event.objects.filter(pk=self.event.pk).update(state=EventState.COMPLETED)
        with override_tracks(FakeTrack(raise_on="on_event_reopened")):
            with self.assertRaises(RuntimeError):
                reopen_event(self.event, actor=None)
        self.assertEqual(
            Event.objects.nocache().get(pk=self.event.pk).state, EventState.COMPLETED
        )
        with override_tracks(FakeTrack(raise_on="on_event_deleted")):
            with self.assertRaises(RuntimeError):
                teardown_event(self.event)
        self.assertTrue(Event.objects.nocache().filter(pk=self.event.pk).exists())

    def test_teardown_calls_on_event_deleted(self) -> None:
        fake = FakeTrack()
        with override_tracks(fake):
            teardown_event(self.event)
        self.assertEqual(fake.hooks(), ["on_event_deleted"])

    def test_patch_timing_and_staff_edit(self) -> None:
        admin = CustomUser.objects.create_user(
            username="std_admin", password="x", is_staff=True, is_superuser=True
        )
        set_org_feature(self.org, FeatureKey.CONTRIBUTIONS, enabled=True, actor=admin)
        client = APIClient()
        client.force_authenticate(admin)
        fake = FakeTrack()
        with override_tracks(CONTRIBUTION, fake):
            client.patch(
                f"/api/events/{self.event.pk}/", {"name": "Renamed"}, format="json"
            )
            client.put(
                f"/api/events/{self.event.pk}/staff/",
                {"host_id": admin.pk, "helper_ids": []},
                format="json",
            )
        changed = [
            kw["fields"] for hook, kw in fake.calls if hook == "on_event_changed"
        ]
        self.assertEqual(changed, [frozenset({"name"}), frozenset({"host", "helpers"})])

    def test_merge_sites_call_merge_users_and_dedupe_resync(self) -> None:
        keep = CustomUser.objects.create_user(username="std_keep", password="x")
        drop = CustomUser.objects.create_user(username="std_drop", password="x")
        keep_ou = OrgUser.objects.create(user=keep, organization=self.org)
        drop_ou = OrgUser.objects.create(user=drop, organization=self.org)
        self.event.host = keep
        self.event.save()
        self.event.helpers.add(drop)
        fake = FakeTrack()
        with override_tracks(CONTRIBUTION, fake):
            merge_discord_accounts(keep=keep, drop=drop)
        self.assertEqual(
            fake.hooks(), ["merge_members", "repoint_user", "on_event_changed"]
        )
        self.assertEqual(fake.calls[0][1], {"drop": drop_ou.pk, "keep": keep_ou.pk})
        self.assertEqual(fake.calls[2][1]["fields"], frozenset({"helpers"}))
        self.assertFalse(self.event.helpers.filter(pk=keep.pk).exists())

    def test_merge_users_rejects_cross_org_pair(self) -> None:
        other = Organization.objects.create(name="Other Standing", owner=self.owner)
        keep = CustomUser.objects.create_user(username="std_keep2", password="x")
        drop = CustomUser.objects.create_user(username="std_drop2", password="x")
        pair = (
            OrgUser.objects.create(user=drop, organization=self.org),
            OrgUser.objects.create(user=keep, organization=other),
        )
        with transaction.atomic(), self.assertRaises(ValueError):
            standing.merge_users(drop, keep, member_pairs=[pair])

    def test_user_delete_api_calls_on_user_deleted(self) -> None:
        admin = CustomUser.objects.create_user(
            username="std_admin2", password="x", is_staff=True, is_superuser=True
        )
        victim = CustomUser.objects.create_user(username="std_victim", password="x")
        client = APIClient()
        client.force_authenticate(admin)
        fake = FakeTrack()
        with override_tracks(CONTRIBUTION, fake):
            response = client.delete(f"/api/users/{victim.pk}/")
        self.assertLess(response.status_code, 300, response.content)
        self.assertEqual(fake.hooks(), ["on_user_deleted"])
