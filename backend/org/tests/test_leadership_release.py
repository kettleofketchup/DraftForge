from datetime import datetime, timedelta
from itertools import product

from django.utils import timezone as tz

from org.leadership.constants import VoidKind
from org.leadership.release import (
    auto_release_at,
    is_released,
    release_floor,
    release_state,
    released_snapshots,
)
from org.models_leadership import CaptainReview, EventCaptain, OrgLeadershipSettings
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
