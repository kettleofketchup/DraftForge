from datetime import datetime

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Model, RestrictedError
from django.utils import timezone as tz

from events.models import Event
from events.tests.base import EventTestCase
from org.leadership.constants import RATER_REVIVABLE, VoidKind
from org.models import Organization, OrgLog, OrgUser
from org.models_leadership import (
    CaptainReview,
    CaptainReviewDraft,
    CaptainTrait,
    CaptainTraitScore,
    EventCaptain,
    OrgLeadershipSettings,
)


class LeadershipModelsTest(EventTestCase):
    def setUp(self) -> None:
        self.captain = OrgUser.objects.create(user=self.admin, organization=self.org)
        self.rater = OrgUser.objects.create(user=self.user, organization=self.org)
        self.trait = CaptainTrait.objects.create(
            organization=self.org, key="communication", label="Communication"
        )
        self.snapshot = self._snapshot(self.org, self.event, self.captain)

    def _snapshot(
        self, org: Organization, event: Event, captain: OrgUser
    ) -> EventCaptain:
        return EventCaptain.objects.create(
            event=event,
            organization=org,
            captain=captain,
            team_name="Alpha",
            window_closes_at=tz.now(),
        )

    def _review(
        self,
        rater: OrgUser | None = None,
        *,
        voided_at: datetime | None = None,
        void_kind: str = "",
    ) -> CaptainReview:
        return CaptainReview.objects.create(
            event_captain=self.snapshot,
            rater=rater or self.rater,
            submitted_at=tz.now(),
            voided_at=voided_at,
            void_kind=void_kind,
        )

    def test_min_reviewers_floor(self) -> None:
        with self.assertRaises(IntegrityError), transaction.atomic():
            OrgLeadershipSettings.objects.create(
                organization=self.org, rating_min_reviewers=1
            )

    def test_auto_release_range_constraint(self) -> None:
        row = OrgLeadershipSettings.objects.create(organization=self.org)
        with self.assertRaises(IntegrityError), transaction.atomic():
            OrgLeadershipSettings.objects.filter(pk=row.pk).update(
                auto_release_after_hours=0
            )

    def test_orglog_release_action(self) -> None:
        self.assertIn("release_captain_reviews", {a for a, _ in OrgLog.ACTION_CHOICES})

    def test_release_stamp_defaults(self) -> None:
        self.assertIsNone(self.snapshot.released_at)
        self.assertIsNone(self.snapshot.released_by)

    def test_settings_defaults(self) -> None:
        row = OrgLeadershipSettings.objects.create(organization=self.org)
        self.assertEqual(
            (
                row.review_window_hours,
                row.rating_max_points,
                row.rating_min_reviewers,
                row.ranked_min_reviews,
                row.prior_rating,
                row.prior_strength,
                row.half_life_days,
                row.max_age_days,
                row.leaderboard_public,
            ),
            (72, 10, 2, 3, 3.0, 2.0, 180, 730, False),
        )
        self.assertIsNotNone(row.created_at)

    def test_score_range(self) -> None:
        review = self._review()
        for bad in (0, 6):
            with self.subTest(score=bad):
                with self.assertRaises(IntegrityError), transaction.atomic():
                    CaptainTraitScore.objects.create(
                        review=review, trait=self.trait, score=bad
                    )

    def test_void_pair_check(self) -> None:
        with self.assertRaises(IntegrityError), transaction.atomic():
            self._review(voided_at=tz.now(), void_kind="")
        with self.assertRaises(IntegrityError), transaction.atomic():
            self._review(void_kind=VoidKind.WITHDRAWN)
        review = self._review(voided_at=tz.now(), void_kind=VoidKind.MODERATED)
        self.assertEqual(review.void_kind, "moderated")

    def test_unique_event_captain_and_review(self) -> None:
        with self.assertRaises(IntegrityError), transaction.atomic():
            self._snapshot(self.org, self.event, self.captain)
        self._review()
        with self.assertRaises(IntegrityError), transaction.atomic():
            self._review()

    def test_unique_review_trait(self) -> None:
        review = self._review()
        CaptainTraitScore.objects.create(review=review, trait=self.trait, score=3)
        with self.assertRaises(IntegrityError), transaction.atomic():
            CaptainTraitScore.objects.create(review=review, trait=self.trait, score=4)

    def test_unique_trait_key_per_org(self) -> None:
        with self.assertRaises(IntegrityError), transaction.atomic():
            CaptainTrait.objects.create(
                organization=self.org, key="communication", label="Again"
            )

    def test_clean_rejects_self_review(self) -> None:
        review = CaptainReview(
            event_captain=self.snapshot, rater=self.captain, submitted_at=tz.now()
        )
        with self.assertRaises(ValidationError):
            review.clean()
        CaptainReview(
            event_captain=self.snapshot, rater=self.rater, submitted_at=tz.now()
        ).clean()

    def test_scored_trait_is_restricted(self) -> None:
        CaptainTraitScore.objects.create(
            review=self._review(), trait=self.trait, score=4
        )
        with self.assertRaises(RestrictedError), transaction.atomic():
            self.trait.delete()
        self.assertTrue(
            CaptainTrait.objects.nocache().filter(pk=self.trait.pk).exists()
        )

    def test_unscored_trait_deletes(self) -> None:
        self.trait.delete()
        self.assertFalse(CaptainTrait.objects.nocache().exists())

    def test_org_delete_cascades_through_scores(self) -> None:
        OrgLeadershipSettings.objects.create(organization=self.org)
        self.snapshot.teammates.add(self.rater)
        CaptainTraitScore.objects.create(
            review=self._review(), trait=self.trait, score=4
        )
        self.org.delete()
        for model in (
            OrgLeadershipSettings,
            CaptainTrait,
            EventCaptain,
            CaptainReview,
            CaptainTraitScore,
        ):
            with self.subTest(model=model.__name__):
                self.assertFalse(model.objects.nocache().exists())

    def test_rater_revivable(self) -> None:
        self.assertEqual(RATER_REVIVABLE, frozenset({"withdrawn", "lifecycle"}))

    def test_cacheops_scope(self) -> None:
        self.assertIn("org.orgleadershipsettings", settings.CACHEOPS)
        for label in (
            "org.captaintrait",
            "org.eventcaptain",
            "org.captainreview",
            "org.captaintraitscore",
        ):
            with self.subTest(label=label):
                self.assertNotIn(label, settings.CACHEOPS)

    def test_constraint_and_index_names(self) -> None:
        def names(model: type[Model]) -> set[str]:
            meta = model._meta
            return {c.name for c in meta.constraints} | {i.name for i in meta.indexes}

        self.assertEqual(
            names(OrgLeadershipSettings),
            {"leadership_min_reviewers_floor", "leadership_auto_release_range"},
        )
        self.assertEqual(names(CaptainTrait), {"uniq_captain_trait_key"})
        self.assertEqual(
            names(EventCaptain), {"uniq_event_captain", "leadership_ec_org_window_idx"}
        )
        self.assertEqual(
            names(CaptainReview),
            {
                "uniq_captain_review",
                "captain_review_void_pair",
                "leadership_review_ec_void_idx",
                "leadership_review_rater_idx",
            },
        )
        self.assertEqual(
            names(CaptainTraitScore), {"uniq_review_trait", "captain_trait_score_range"}
        )

    def test_draft_unique_per_snapshot_rater(self) -> None:
        draft = CaptainReviewDraft.objects.create(
            event_captain=self.snapshot, rater=self.rater, scores={"1": 3}
        )
        self.assertEqual(draft.scores, {"1": 3})
        self.assertIsNone(draft.seeded_from_review_at)
        with transaction.atomic(), self.assertRaises(IntegrityError):
            CaptainReviewDraft.objects.create(
                event_captain=self.snapshot, rater=self.rater
            )
        other = CaptainReviewDraft.objects.create(
            event_captain=self.snapshot, rater=self.captain
        )
        self.assertEqual(other.scores, {})

    def test_draft_not_cached(self) -> None:
        self.assertNotIn("org.captainreviewdraft", settings.CACHEOPS)
        self.assertNotIn("org.*", settings.CACHEOPS)
