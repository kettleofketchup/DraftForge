from datetime import datetime, timedelta
from itertools import product
from typing import Any
from unittest import mock

from django.utils import timezone as tz

from app.models import CustomUser
from org.leadership.constants import VoidKind
from org.leadership.errors import ReviewRefused
from org.leadership.queries import points_board, rating_board
from org.leadership.release import (
    auto_release_at,
    is_released,
    release_floor,
    release_state,
    released_snapshots,
)
from org.leadership.settings import (
    get_leadership_settings,
    moderator_count,
    update_leadership_settings,
)
from org.leadership.traits import effective_traits
from org.models import Organization, OrgLog
from org.models_leadership import CaptainReview, EventCaptain, OrgLeadershipSettings
from org.standing.periods import parse_period
from org.tests.leadership_base import LeadershipTestCase


class ReleasePredicateTest(LeadershipTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.run_snapshot()
        for mate in self.mates_a[:2]:
            self.review(mate, self.cap_a)
        self.snap = self.snapshot(self.cap_a)
        self.now = tz.now()

    def settings(
        self, *, gate: bool = False, hours: int | None = None
    ) -> OrgLeadershipSettings:
        return OrgLeadershipSettings(
            organization_id=self.org.pk,
            require_staff_release=gate,
            auto_release_after_hours=hours,
        )

    def floor(self) -> int:
        return release_floor(self.settings().rating_min_reviewers)

    def set_snapshot(
        self,
        *,
        closes: datetime,
        stamped: bool = False,
        voided: bool = False,
        live: int | None = None,
    ) -> EventCaptain:
        EventCaptain.objects.filter(pk=self.snap.pk).update(
            window_closes_at=closes,
            released_at=self.now if stamped else None,
            voided_at=self.now if voided else None,
        )
        reviews = list(
            CaptainReview.objects.nocache()
            .filter(event_captain_id=self.snap.pk)
            .order_by("pk")
            .values_list("pk", flat=True)
        )
        keep = len(reviews) if live is None else live
        CaptainReview.objects.filter(pk__in=reviews[:keep]).update(
            voided_at=None, void_kind=""
        )
        CaptainReview.objects.filter(pk__in=reviews[keep:]).update(
            voided_at=self.now, void_kind=VoidKind.MODERATED.value
        )
        return EventCaptain.objects.nocache().get(pk=self.snap.pk)

    def live(self) -> int:
        return (
            CaptainReview.objects.nocache()
            .filter(event_captain_id=self.snap.pk, voided_at__isnull=True)
            .count()
        )

    def in_q(self, settings: OrgLeadershipSettings) -> bool:
        return self.snap.pk in set(
            released_snapshots(
                self.org.pk, now=self.now, settings=settings
            ).values_list("pk", flat=True)
        )

    def both(self, snap: EventCaptain, settings: OrgLeadershipSettings) -> bool:
        python = is_released(snap, live=self.live(), settings=settings, now=self.now)
        self.assertEqual(python, self.in_q(settings))
        return python

    def test_predicate_parity_grid(self) -> None:
        windows = {
            "open": self.now + timedelta(hours=1),
            "closed_1h": self.now - timedelta(hours=1),
            "closed_25h": self.now - timedelta(hours=25),
        }
        floor = self.floor()
        for gate, hours, stamped, window, live, voided in product(
            (False, True),
            (None, 24),
            (False, True),
            windows,
            (floor - 1, floor),
            (False, True),
        ):
            with self.subTest(
                gate=gate,
                hours=hours,
                stamped=stamped,
                window=window,
                live=live,
                voided=voided,
            ):
                snap = self.set_snapshot(
                    closes=windows[window], stamped=stamped, voided=voided, live=live
                )
                settings = self.settings(gate=gate, hours=hours)
                released = self.both(snap, settings)
                base = not voided and window != "open" and live >= floor
                gated = stamped or (hours is not None and window == "closed_25h")
                self.assertEqual(released, base and (not gate or gated))

    def test_release_state_grid(self) -> None:
        floor = self.floor()
        closed = self.now - timedelta(hours=1)
        cases = [
            ("voided", dict(closes=closed, voided=True), {}, "voided"),
            ("open", dict(closes=self.now + timedelta(hours=1)), {}, "open"),
            ("short", dict(closes=closed, live=floor - 1), {}, "short"),
            (
                "short_stamped",
                dict(closes=closed, live=floor - 1, stamped=True),
                dict(gate=True),
                "short",
            ),
            ("gate_off", dict(closes=closed), {}, "released"),
            ("pending", dict(closes=closed), dict(gate=True), "pending"),
            (
                "pending_hours",
                dict(closes=closed),
                dict(gate=True, hours=24),
                "pending",
            ),
            ("stamped", dict(closes=closed, stamped=True), dict(gate=True), "released"),
            (
                "auto",
                dict(closes=self.now - timedelta(hours=25)),
                dict(gate=True, hours=24),
                "released",
            ),
        ]
        for name, snap_kwargs, settings_kwargs, expected in cases:
            with self.subTest(name):
                snap = self.set_snapshot(**snap_kwargs)
                state = release_state(
                    snap,
                    live=self.live(),
                    settings=self.settings(**settings_kwargs),
                    now=self.now,
                )
                self.assertEqual(state, expected)

    def test_auto_release_boundary(self) -> None:
        settings = self.settings(gate=True, hours=24)
        for delta, expected in (
            (timedelta(seconds=1), False),
            (timedelta(0), True),
            (timedelta(seconds=-1), True),
        ):
            with self.subTest(delta=delta):
                snap = self.set_snapshot(closes=self.now - timedelta(hours=24) + delta)
                self.assertEqual(self.both(snap, settings), expected)

    def test_gate_off_ignores_stamp_absence(self) -> None:
        self.review(self.mates_b[0], self.cap_b)
        self.expire_window()
        floor = self.floor()
        expected = {
            snap.pk
            for snap in EventCaptain.objects.nocache().filter(
                organization_id=self.org.pk
            )
            if snap.voided_at is None
            and snap.released_at is None
            and snap.window_closes_at <= self.now
            and snap.reviews.filter(voided_at__isnull=True).count() >= floor
        }
        self.assertEqual(expected, {self.snap.pk})
        got = set(
            released_snapshots(
                self.org.pk, now=self.now, settings=self.settings()
            ).values_list("pk", flat=True)
        )
        self.assertEqual(got, expected)

    def test_auto_release_at_none_when_gate_off_or_no_hours(self) -> None:
        self.assertIsNone(auto_release_at(self.snap, self.settings(hours=24)))
        self.assertIsNone(auto_release_at(self.snap, self.settings(gate=True)))
        self.assertEqual(
            auto_release_at(self.snap, self.settings(gate=True, hours=24)),
            self.snap.window_closes_at + timedelta(hours=24),
        )


class SettingsGateTest(LeadershipTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.run_snapshot()
        for mate in self.mates_a:
            self.review(mate, self.cap_a)
        for mate in self.mates_b:
            self.review(mate, self.cap_b)
        self.org.admins.add(self.cap_b)
        self.snap_a = self.snapshot(self.cap_a)
        self.snap_b = self.snapshot(self.cap_b)

    def configure(self, **fields: Any) -> None:
        OrgLeadershipSettings.objects.update_or_create(
            organization=self.org, defaults=fields
        )

    def close_window(self, snap: EventCaptain, hours_ago: float) -> None:
        EventCaptain.objects.filter(pk=snap.pk).update(
            window_closes_at=tz.now() - timedelta(hours=hours_ago),
            released_at=None,
            released_by=None,
        )

    def fresh(self, snap: EventCaptain) -> EventCaptain:
        return EventCaptain.objects.nocache().get(pk=snap.pk)

    def rated(self) -> set[int]:
        return set(
            rating_board(
                self.org.pk,
                now=tz.now(),
                settings=get_leadership_settings(self.org),
                traits=effective_traits(self.org),
            )
        )

    def board_points(self) -> dict[int, int]:
        return {
            row["org_user"]: row["total"]
            for row in points_board(
                self.org.pk,
                parse_period(self.org, None),
                now=tz.now(),
                settings=get_leadership_settings(self.org),
            )
        }

    def update(self, actor: CustomUser, **changes: object) -> OrgLeadershipSettings:
        return update_leadership_settings(self.org, actor=actor, changes=changes)

    def settings_log(self) -> OrgLog:
        return OrgLog.objects.get(
            organization=self.org, action="update_leadership_settings"
        )

    def test_gate_on_stamps_public_results(self) -> None:
        self.close_window(self.snap_a, 1)
        self.update(self.admin, require_staff_release=True)
        a = self.fresh(self.snap_a)
        self.assertIsNotNone(a.released_at)
        self.assertIsNone(a.released_by_id)
        self.assertIsNone(self.fresh(self.snap_b).released_at)
        details = self.settings_log().details
        self.assertEqual(details["release_stamped"], 1)
        self.assertEqual(details["release_unlocked"], 0)
        self.assertIn(self.ou(self.cap_a).pk, self.rated())

    def test_hours_lengthened_keeps_auto_released(self) -> None:
        self.assert_auto_released_kept(720)

    def test_hours_cleared_keeps_auto_released(self) -> None:
        self.assert_auto_released_kept(None)

    def assert_auto_released_kept(self, hours: int | None) -> None:
        self.configure(require_staff_release=True, auto_release_after_hours=24)
        self.close_window(self.snap_a, 30)
        cap = self.ou(self.cap_a).pk
        self.assertIn(cap, self.rated())
        points = self.board_points()[cap]
        self.update(self.admin, auto_release_after_hours=hours)
        self.assertIsNotNone(self.fresh(self.snap_a).released_at)
        self.assertIn(cap, self.rated())
        self.assertEqual(self.board_points()[cap], points)

    def test_floor_raise_with_gate_on_still_hides_short(self) -> None:
        self.configure(require_staff_release=True)
        self.close_window(self.snap_b, 1)
        EventCaptain.objects.filter(pk=self.snap_b.pk).update(released_at=tz.now())
        cap = self.ou(self.cap_b).pk
        self.assertIn(cap, self.rated())
        self.update(self.admin, rating_min_reviewers=3)
        self.assertNotIn(cap, self.rated())

    def test_self_release_refused(self) -> None:
        cases: list[tuple[str, dict[str, Any], float, dict[str, object]]] = [
            (
                "gate_off",
                {"require_staff_release": True, "auto_release_after_hours": None},
                1,
                {"require_staff_release": False},
            ),
            (
                "hours_shortened",
                {"require_staff_release": True, "auto_release_after_hours": 720},
                30,
                {"auto_release_after_hours": 24},
            ),
            (
                "hours_set",
                {"require_staff_release": True, "auto_release_after_hours": None},
                30,
                {"auto_release_after_hours": 24},
            ),
            (
                "floor_lowered",
                {
                    "require_staff_release": True,
                    "auto_release_after_hours": 24,
                    "rating_min_reviewers": 3,
                },
                30,
                {"rating_min_reviewers": 2},
            ),
        ]
        for name, initial, hours_ago, changes in cases:
            with self.subTest(name):
                self.configure(
                    **{
                        "require_staff_release": False,
                        "auto_release_after_hours": None,
                        "rating_min_reviewers": 2,
                        **initial,
                    }
                )
                self.close_window(self.snap_b, hours_ago)
                OrgLog.objects.filter(organization=self.org).delete()
                with self.assertRaises(ReviewRefused) as ctx:
                    self.update(self.cap_b, **changes)
                self.assertEqual(ctx.exception.code, "would_release_own_results")
                self.assertEqual(ctx.exception.status, 409)
                row = OrgLeadershipSettings.objects.nocache().get(organization=self.org)
                for field, value in initial.items():
                    self.assertEqual(getattr(row, field), value)
                self.assertIsNone(self.fresh(self.snap_b).released_at)
                self.assertFalse(OrgLog.objects.filter(organization=self.org).exists())
                self.update(self.admin, **changes)
                self.assertIn(self.ou(self.cap_b).pk, self.rated())

    def test_floor_change_with_gate_off_not_refused(self) -> None:
        self.configure(rating_min_reviewers=3)
        self.close_window(self.snap_b, 1)
        self.update(self.cap_b, rating_min_reviewers=2)
        self.assertIn(self.ou(self.cap_b).pk, self.rated())

    def test_resending_same_values_is_noop(self) -> None:
        self.configure(require_staff_release=True, auto_release_after_hours=24)
        self.close_window(self.snap_a, 30)
        self.close_window(self.snap_b, 30)
        with mock.patch(
            "org.leadership.settings.invalidate_after_commit"
        ) as invalidate:
            self.update(
                self.cap_b, require_staff_release=True, auto_release_after_hours=24
            )
        invalidate.assert_not_called()
        self.assertIsNone(self.fresh(self.snap_a).released_at)
        self.assertIsNone(self.fresh(self.snap_b).released_at)
        self.assertFalse(
            OrgLog.objects.filter(action="update_leadership_settings").exists()
        )

    def test_settings_change_invalidates_stamped(self) -> None:
        self.close_window(self.snap_a, 1)
        self.close_window(self.snap_b, 1)
        with mock.patch(
            "org.leadership.settings.invalidate_after_commit"
        ) as invalidate:
            row = self.update(self.admin, require_staff_release=True)
        invalidate.assert_called_once()
        args = invalidate.call_args.args
        self.assertEqual(args[-1], row)
        self.assertIsInstance(args[-1], OrgLeadershipSettings)
        stamped = args[:-1]
        self.assertTrue(all(isinstance(a, EventCaptain) for a in stamped))
        self.assertEqual({a.pk for a in stamped}, {self.snap_a.pk, self.snap_b.pk})
        self.assertEqual(self.settings_log().details["release_stamped"], 2)

    def test_moderator_count(self) -> None:
        owner = self.make_user("mc_owner")
        org = Organization.objects.create(name="Mod Count Org", owner=owner)
        self.assertEqual(moderator_count(org), 1)
        org.admins.add(owner)
        self.assertEqual(moderator_count(org), 1)
        org.staff.add(self.make_user("mc_staff"))
        self.assertEqual(moderator_count(org), 2)
