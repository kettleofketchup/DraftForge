from collections.abc import Callable
from datetime import datetime, timedelta
from unittest import mock

from django.core.exceptions import ValidationError
from django.db import connection
from django.test import override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone as tz

from app.models import CustomUser
from org.leadership import reviews as reviews_module
from org.leadership.errors import ReviewRefused
from org.leadership.lifecycle import void_event
from org.leadership.reviews import (
    unvoid_review,
    void_review,
    withdraw_review,
)
from org.leadership.traits import upsert_traits
from org.models import ContributionEntry, Organization
from org.models_leadership import CaptainReview, CaptainTrait, EventCaptain
from org.tests.leadership_base import LeadershipTestCase, scores


class ReviewTestCase(LeadershipTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.close()

    def refused(self, code: str, fn: Callable[[], object]) -> ReviewRefused:
        with self.assertRaises(ReviewRefused) as ctx:
            fn()
        self.assertEqual(ctx.exception.code, code)
        return ctx.exception

    def withdraw(
        self, rater: CustomUser, captain: CustomUser, *, now: datetime | None = None
    ) -> None:
        withdraw_review(
            self.org,
            event_id=self.event.pk,
            captain_org_user_id=self.ou(captain).pk,
            rater=self.ou(rater),
            now=now or tz.now(),
        )

    def void(
        self,
        review: CaptainReview,
        actor: CustomUser | None = None,
        *,
        reason: str = "abusive",
        org: Organization | None = None,
    ) -> CaptainReview:
        return void_review(
            org or self.org,
            review_id=review.pk,
            actor=actor or self.admin,
            reason=reason,
            now=tz.now(),
        )

    def unvoid(
        self, review: CaptainReview, actor: CustomUser | None = None
    ) -> CaptainReview:
        return unvoid_review(
            self.org, review_id=review.pk, actor=actor or self.admin, now=tz.now()
        )

    def trait_keys(self, review: CaptainReview) -> set[str]:
        return set(
            CaptainReview.objects.nocache()
            .get(pk=review.pk)
            .scores.values_list("trait__key", flat=True)
        )


class SubmitTest(ReviewTestCase):
    def test_submit_requires_every_active_trait(self) -> None:
        missing = scores(4)
        missing.pop("drafting")
        for bad in (
            missing,
            {**scores(4), "bogus": 3},
            {**scores(4), "drafting": 6},
            {**scores(4), "drafting": True},
        ):
            exc = self.refused(
                "invalid_scores",
                lambda b=bad: self.review(self.mates_a[0], self.cap_a, b),
            )
            self.assertEqual(exc.status, 400)
        self.assertFalse(CaptainReview.objects.exists())

    def test_submit_creates_scores_and_materializes_traits(self) -> None:
        self.assertFalse(CaptainTrait.objects.filter(organization=self.org).exists())
        review = self.review(self.mates_a[0], self.cap_a, 4)
        self.assertEqual(CaptainTrait.objects.filter(organization=self.org).count(), 4)
        self.assertEqual(review.scores.count(), 4)

    def test_edit_replaces_scores(self) -> None:
        first = self.review(self.mates_a[0], self.cap_a, 5)
        second = self.review(self.mates_a[0], self.cap_a, 3)
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(CaptainReview.objects.count(), 1)
        self.assertEqual(
            sorted(second.scores.values_list("score", flat=True)), [3, 3, 3, 3]
        )

    def test_edit_after_trait_change_replaces_all_scores(self) -> None:
        review = self.review(self.mates_a[0], self.cap_a, 4)
        upsert_traits(
            self.org,
            actor=self.admin,
            items=[
                {"key": "drafting", "label": "Drafting", "order": 1, "active": False},
                {
                    "key": "shotcalling",
                    "label": "Shotcalling",
                    "order": 4,
                    "active": True,
                },
            ],
        )
        self.refused(
            "invalid_scores", lambda: self.review(self.mates_a[0], self.cap_a, 4)
        )
        new = {"communication": 3, "composure": 3, "sportsmanship": 3, "shotcalling": 3}
        self.review(self.mates_a[0], self.cap_a, new)
        self.assertEqual(self.trait_keys(review), set(new))

    def test_pool_enforced(self) -> None:
        outsider = self.make_user("ld_outsider")
        self.admit(outsider)
        for rater in (self.cap_a, outsider, self.mates_b[0]):
            exc = self.refused(
                "not_in_pool", lambda r=rater: self.review(r, self.cap_a)
            )
            self.assertEqual(exc.status, 403)

    def test_window_edges(self) -> None:
        closes = self.snapshot(self.cap_a).window_closes_at
        self.review(self.mates_a[0], self.cap_a, now=closes - timedelta(microseconds=1))
        exc = self.refused(
            "review_window_closed",
            lambda: self.review(self.mates_a[1], self.cap_a, now=closes),
        )
        self.assertEqual(exc.status, 409)

    def test_reopen_between_listing_and_submit(self) -> None:
        pending = list(self.snapshot(self.cap_a).teammates.all())
        self.assertTrue(pending)
        void_event(self.event, now=tz.now())
        exc = self.refused(
            "snapshot_voided", lambda: self.review(self.mates_a[0], self.cap_a)
        )
        self.assertEqual(exc.status, 409)

    def test_unknown_captain_not_found(self) -> None:
        exc = self.refused(
            "not_found", lambda: self.review(self.mates_a[0], self.mates_a[1])
        )
        self.assertEqual(exc.status, 404)

    def test_self_review_rejected_by_clean(self) -> None:
        snap = self.snapshot(self.cap_a)
        review = CaptainReview(
            event_captain=snap, rater=snap.captain, submitted_at=tz.now()
        )
        with self.assertRaises(ValidationError):
            review.clean()


class RatingTest(ReviewTestCase):
    def test_captain_rating_formula_live(self) -> None:
        self.review(self.mates_a[0], self.cap_a, 4)
        self.assertIsNone(self.points(self.cap_a, "captain_rating"))
        self.review(self.mates_a[1], self.cap_a, 5)
        self.assertEqual(self.points(self.cap_a, "captain_rating"), 9)
        self.withdraw(self.mates_a[1], self.cap_a)
        self.assertIsNone(self.points(self.cap_a, "captain_rating"))

    def test_frozen_after_window(self) -> None:
        self.review(self.mates_a[0], self.cap_a, 5)
        self.review(self.mates_a[1], self.cap_a, 5)
        self.expire_window()
        self.refused(
            "review_window_closed", lambda: self.review(self.mates_a[2], self.cap_a, 1)
        )
        self.refused(
            "review_window_closed", lambda: self.withdraw(self.mates_a[0], self.cap_a)
        )
        self.assertEqual(self.points(self.cap_a, "captain_rating"), 10)

    def test_resubmit_revives_withdrawn_and_lifecycle(self) -> None:
        review = self.review(self.mates_a[0], self.cap_a, 5)
        self.withdraw(self.mates_a[0], self.cap_a)
        review.refresh_from_db()
        self.assertEqual(review.void_kind, "withdrawn")
        self.review(self.mates_a[0], self.cap_a, 5)
        review.refresh_from_db()
        self.assertIsNone(review.voided_at)
        self.assertEqual(review.void_kind, "")

        void_event(self.event, now=tz.now())
        review.refresh_from_db()
        self.assertEqual(review.void_kind, "lifecycle")
        self.run_snapshot()
        self.review(self.mates_a[0], self.cap_a, 4)
        review.refresh_from_db()
        self.assertIsNone(review.voided_at)
        self.assertEqual(review.void_kind, "")

    def test_withdraw_without_review_not_found(self) -> None:
        self.refused("not_found", lambda: self.withdraw(self.mates_a[0], self.cap_a))


class ModerationTest(ReviewTestCase):
    def test_staff_void_after_window_recomputes(self) -> None:
        first = self.review(self.mates_a[0], self.cap_a, 5)
        self.review(self.mates_a[1], self.cap_a, 5)
        self.review(self.mates_a[2], self.cap_a, 1)
        self.assertEqual(self.points(self.cap_a, "captain_rating"), 7)
        self.expire_window()
        voided = self.void(first)
        self.assertEqual(voided.void_kind, "moderated")
        self.assertEqual(voided.voided_by_id, self.admin.pk)
        self.assertEqual(voided.void_reason, "abusive")
        self.assertEqual(self.points(self.cap_a, "captain_rating"), 5)
        entry = self.org.logs.get(action="void_captain_review")
        self.assertEqual(entry.details["points_before"], 7)
        self.assertEqual(entry.details["points_after"], 5)
        self.assertEqual(entry.details["reason"], "abusive")
        self.assertEqual(entry.details["event_id"], self.event.pk)
        self.assertEqual(entry.details["captain_org_user_id"], self.ou(self.cap_a).pk)
        self.assertEqual(
            entry.details["rater_org_user_id"], self.ou(self.mates_a[0]).pk
        )

    def test_void_sticks(self) -> None:
        review = self.review(self.mates_a[0], self.cap_a, 5)
        self.void(review)
        exc = self.refused(
            "review_moderated", lambda: self.review(self.mates_a[0], self.cap_a, 1)
        )
        self.assertEqual(exc.status, 403)
        self.refused(
            "review_moderated", lambda: self.withdraw(self.mates_a[0], self.cap_a)
        )
        review.refresh_from_db()
        self.assertEqual(review.void_kind, "moderated")
        self.assertEqual(
            sorted(review.scores.values_list("score", flat=True)), [5, 5, 5, 5]
        )

    def test_void_turns_withdrawn_into_moderated(self) -> None:
        review = self.review(self.mates_a[0], self.cap_a, 5)
        self.withdraw(self.mates_a[0], self.cap_a)
        self.void(review)
        review.refresh_from_db()
        self.assertEqual(review.void_kind, "moderated")
        self.refused(
            "review_moderated", lambda: self.review(self.mates_a[0], self.cap_a, 5)
        )

    def test_unvoid_only_moderated(self) -> None:
        live = self.review(self.mates_a[0], self.cap_a, 5)
        exc = self.refused("not_moderated", lambda: self.unvoid(live))
        self.assertEqual(exc.status, 409)
        withdrawn = self.review(self.mates_a[1], self.cap_a, 5)
        self.withdraw(self.mates_a[1], self.cap_a)
        self.refused("not_moderated", lambda: self.unvoid(withdrawn))

    def test_unvoid_restores_points(self) -> None:
        first = self.review(self.mates_a[0], self.cap_a, 5)
        self.review(self.mates_a[1], self.cap_a, 5)
        self.void(first)
        self.assertIsNone(self.points(self.cap_a, "captain_rating"))
        self.expire_window()
        restored = self.unvoid(first)
        self.assertIsNone(restored.voided_at)
        self.assertEqual(restored.void_kind, "")
        self.assertIsNone(restored.voided_by_id)
        self.assertEqual(self.points(self.cap_a, "captain_rating"), 10)
        entry = self.org.logs.get(action="unvoid_captain_review")
        self.assertEqual(entry.details["points_before"], 0)
        self.assertEqual(entry.details["points_after"], 10)
        self.assertNotIn("reason", entry.details)

    def test_unvoid_restores_a_withdrawn_review_as_withdrawn(self) -> None:
        review = self.review(self.mates_a[0], self.cap_a, 5)
        self.review(self.mates_a[1], self.cap_a, 5)
        self.review(self.mates_a[2], self.cap_a, 1)
        self.withdraw(self.mates_a[0], self.cap_a)
        withdrawn_at = CaptainReview.objects.nocache().get(pk=review.pk).voided_at
        self.void(review)
        self.expire_window()
        restored = self.unvoid(review)
        self.assertEqual(restored.void_kind, "withdrawn")
        self.assertEqual(restored.voided_at, withdrawn_at)
        self.assertIsNone(restored.voided_by_id)
        self.assertEqual(restored.void_reason, "")
        self.assertEqual(self.points(self.cap_a, "captain_rating"), 5)

    def test_unvoid_after_reclose_restores_lifecycle(self) -> None:
        lifecycle = self.review(self.mates_a[0], self.cap_a, 5)
        live = self.review(self.mates_a[1], self.cap_a, 5)
        self.void(live)
        void_event(self.event, now=tz.now())
        self.void(lifecycle)
        self.run_snapshot()
        for review in (lifecycle, live):
            restored = self.unvoid(review)
            self.assertEqual(restored.void_kind, "lifecycle")
            self.assertIsNotNone(restored.voided_at)
        self.assertIsNone(self.points(self.cap_a, "captain_rating"))
        self.review(self.mates_a[0], self.cap_a, 4)

    def test_unvoid_refused_when_rater_left_the_pool(self) -> None:
        review = self.review(self.mates_a[0], self.cap_a, 5)
        self.void(review)
        EventCaptain.teammates.through.objects.filter(
            eventcaptain_id=self.snapshot(self.cap_a).pk,
            orguser_id=self.ou(self.mates_a[0]).pk,
        ).delete()
        exc = self.refused("not_in_pool", lambda: self.unvoid(review))
        self.assertEqual(exc.status, 409)
        review.refresh_from_db()
        self.assertEqual(review.void_kind, "moderated")

    def test_unvoid_refused_on_voided_snapshot(self) -> None:
        review = self.review(self.mates_a[0], self.cap_a, 5)
        self.void(review)
        void_event(self.event, now=tz.now())
        self.refused("snapshot_voided", lambda: self.unvoid(review))

    def test_admin_own_reviews_look_missing(self) -> None:
        event, tournament = self.make_event("Admin Cup")
        mate = self.make_user("ld_admin_mate")
        self.make_team("Admins", self.admin, [mate], tournament=tournament)
        self.admit(self.admin, event)
        self.admit(mate, event)
        self.run_snapshot(event)
        review = self.review(mate, self.admin, 5, event=event)
        exc = self.refused("not_found", lambda: self.void(review))
        self.assertEqual(exc.status, 404)
        other = self.make_user("ld_admin_two")
        self.org.admins.add(other)
        self.void(review, other)
        self.refused("not_found", lambda: self.unvoid(review))
        self.unvoid(review, other)

    def test_org_staff_can_void_others(self) -> None:
        review = self.review(self.mates_a[0], self.cap_a, 5)
        staff = self.make_user("ld_org_staff")
        self.org.staff.add(staff)
        voided = self.void(review, staff)
        self.assertEqual(voided.voided_by_id, staff.pk)
        self.unvoid(review, staff)

    def test_every_role_refused_on_own_review(self) -> None:
        event, tournament = self.make_event("Role Cup")
        captains = {
            "owner": self.admin,
            "admin": self.make_user("ld_own_admin"),
            "staff": self.make_user("ld_own_staff"),
            "site_staff": CustomUser.objects.create_user(
                username="ld_own_site", password="x", is_staff=True
            ),
            "superuser": CustomUser.objects.create_user(
                username="ld_own_super", password="x", is_superuser=True
            ),
        }
        self.org.admins.add(captains["admin"])
        self.org.staff.add(captains["staff"])
        mates = {name: self.make_user(f"ld_own_mate_{name}") for name in captains}
        for name, captain in captains.items():
            self.make_team(name, captain, [mates[name]], tournament=tournament)
            self.admit(captain, event)
            self.admit(mates[name], event)
        self.run_snapshot(event)
        for name, captain in captains.items():
            with self.subTest(name):
                review = self.review(mates[name], captain, 5, event=event)
                exc = self.refused("not_found", lambda: self.void(review, captain))
                self.assertEqual(exc.status, 404)
                self.assertEqual(exc.detail, "Review not found.")
                CaptainReview.objects.filter(pk=review.pk).update(
                    voided_at=tz.now(), void_kind="moderated"
                )
                self.refused("not_found", lambda: self.unvoid(review, captain))

    def test_non_admin_cannot_moderate(self) -> None:
        review = self.review(self.mates_a[0], self.cap_a, 5)
        exc = self.refused("not_permitted", lambda: self.void(review, self.mates_a[1]))
        self.assertEqual(exc.status, 403)
        self.refused("not_permitted", lambda: self.unvoid(review, self.mates_a[1]))

    def test_cross_org_review_id_not_found(self) -> None:
        review = self.review(self.mates_a[0], self.cap_a, 5)
        other_admin = self.make_user("ld_other_admin")
        other = Organization.objects.create(name="Other Org", owner=other_admin)
        other.admins.add(other_admin)
        exc = self.refused(
            "not_found", lambda: self.void(review, other_admin, org=other)
        )
        self.assertEqual(exc.status, 404)
        review.refresh_from_db()
        self.assertIsNone(review.voided_at)

    def test_reason_required(self) -> None:
        review = self.review(self.mates_a[0], self.cap_a, 5)
        for reason in ("", "   ", "x" * 501):
            exc = self.refused(
                "reason_required", lambda r=reason: self.void(review, reason=r)
            )
            self.assertEqual(exc.status, 400)
        self.void(review, reason="  x  ")
        review.refresh_from_db()
        self.assertEqual(review.void_reason, "x")


class ReviewRaceTest(ReviewTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.real_lock = reviews_module._lock_snapshot

    def test_void_lands_between_precheck_and_lock(self) -> None:
        def lock_after_reopen(*args: object, **kwargs: object) -> EventCaptain:
            void_event(self.event, now=tz.now())
            return self.real_lock(*args, **kwargs)

        with mock.patch.object(reviews_module, "_lock_snapshot", lock_after_reopen):
            self.refused(
                "snapshot_voided", lambda: self.review(self.mates_a[1], self.cap_a)
            )
        self.assertFalse(
            CaptainReview.objects.nocache().filter(voided_at__isnull=True).exists()
        )
        self.assertIsNone(self.points(self.cap_a, "captain_rating"))

    def test_window_expires_between_precheck_and_lock(self) -> None:
        self.review(self.mates_a[0], self.cap_a, 5)
        self.review(self.mates_a[1], self.cap_a, 5)
        closes = self.snapshot(self.cap_a).window_closes_at
        locked = {"done": False}
        real_now = tz.now

        def lock_and_tick(*args: object, **kwargs: object) -> EventCaptain:
            result = self.real_lock(*args, **kwargs)
            locked["done"] = True
            return result

        def clock() -> datetime:
            return closes if locked["done"] else real_now()

        before = list(ContributionEntry.objects.nocache().values_list("pk", "points"))
        with (
            mock.patch.object(reviews_module, "_lock_snapshot", lock_and_tick),
            mock.patch.object(reviews_module.timezone, "now", side_effect=clock),
        ):
            self.refused(
                "review_window_closed",
                lambda: self.review(
                    self.mates_a[2],
                    self.cap_a,
                    1,
                    now=closes - timedelta(seconds=1),
                ),
            )
        self.assertEqual(
            list(ContributionEntry.objects.nocache().values_list("pk", "points")),
            before,
        )
        self.assertEqual(CaptainReview.objects.count(), 2)


class ReviewBudgetTest(ReviewTestCase):
    def submit_queries(
        self, rater: CustomUser, captain: CustomUser, keys: list[str]
    ) -> int:
        with CaptureQueriesContext(connection) as ctx:
            self.review(rater, captain, dict.fromkeys(keys, 4))
        return len(ctx.captured_queries)

    @override_settings(CACHEOPS_ENABLED=False)
    def test_submit_query_budget(self) -> None:
        upsert_traits(self.org, actor=self.admin, items=[])
        four = self.submit_queries(self.mates_a[0], self.cap_a, list(scores(4)))
        extra = [f"trait{i}" for i in range(4)]
        upsert_traits(
            self.org,
            actor=self.admin,
            items=[
                {"key": key, "label": key.title(), "order": 4 + i, "active": True}
                for i, key in enumerate(extra)
            ],
        )
        eight = self.submit_queries(self.mates_b[0], self.cap_b, [*scores(4), *extra])
        self.assertEqual(four, eight)
