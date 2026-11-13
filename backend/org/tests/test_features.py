from django.db import IntegrityError
from django.test import TestCase

from app.models import CustomUser, Organization, OrgLog
from org.features import (
    FeatureKey,
    active_features,
    org_has_feature,
    set_org_feature,
)
from org.models import OrgFeature

FEATURE_ACTIONS = ["enable_feature", "disable_feature"]


class OrgFeatureServiceTest(TestCase):
    def setUp(self) -> None:
        self.actor = CustomUser.objects.create_user(
            username="feature_actor", password="x", is_staff=True
        )
        self.org = Organization.objects.create(name="Feature Org")

    def test_default_is_locked(self) -> None:
        self.assertIs(org_has_feature(self.org, "promotion"), False)
        self.assertIs(org_has_feature(self.org.pk, FeatureKey.CONTRIBUTIONS), False)
        self.assertEqual(active_features(self.org), [])

    def test_enable_reports_active(self) -> None:
        set_org_feature(self.org, FeatureKey.PROMOTION, enabled=True, actor=self.actor)
        set_org_feature(
            self.org, FeatureKey.CONTRIBUTIONS, enabled=True, actor=self.actor
        )
        self.assertIs(org_has_feature(self.org, "promotion"), True)
        self.assertEqual(active_features(self.org.pk), ["contributions", "promotion"])

    def test_enable_then_disable_keeps_row_and_notes(self) -> None:
        set_org_feature(
            self.org,
            FeatureKey.PROMOTION,
            enabled=True,
            actor=self.actor,
            notes="paid via PayPal",
        )
        row = set_org_feature(
            self.org, FeatureKey.PROMOTION, enabled=False, actor=self.actor, notes=None
        )
        self.assertEqual(OrgFeature.objects.filter(organization=self.org).count(), 1)
        row.refresh_from_db()
        self.assertIs(row.enabled, False)
        self.assertEqual(row.notes, "paid via PayPal")
        self.assertEqual(row.enabled_by, self.actor)
        self.assertIsNotNone(row.enabled_at)
        self.assertIs(org_has_feature(self.org, "promotion"), False)

    def test_writes_orglog_per_change(self) -> None:
        set_org_feature(self.org, FeatureKey.PROMOTION, enabled=True, actor=self.actor)
        set_org_feature(self.org, FeatureKey.PROMOTION, enabled=True, actor=self.actor)
        set_org_feature(self.org, FeatureKey.PROMOTION, enabled=False, actor=self.actor)
        logs = OrgLog.objects.filter(
            organization=self.org, action__in=FEATURE_ACTIONS
        ).order_by("created_at", "pk")
        self.assertEqual(logs.count(), 2)
        self.assertEqual(
            [log.action for log in logs], ["enable_feature", "disable_feature"]
        )
        for log in logs:
            self.assertEqual(log.details["feature"], "promotion")
            self.assertEqual(log.actor, self.actor)

    def test_notes_change_alone_is_logged(self) -> None:
        set_org_feature(self.org, FeatureKey.PROMOTION, enabled=True, actor=self.actor)
        set_org_feature(
            self.org,
            FeatureKey.PROMOTION,
            enabled=True,
            actor=self.actor,
            notes="renewed",
        )
        self.assertEqual(
            OrgLog.objects.filter(
                organization=self.org, action__in=FEATURE_ACTIONS
            ).count(),
            2,
        )

    def test_unique_per_org_feature(self) -> None:
        OrgFeature.objects.create(organization=self.org, feature="promotion")
        with self.assertRaises(IntegrityError):
            OrgFeature.objects.create(organization=self.org, feature="promotion")

    def test_promoters_m2m(self) -> None:
        user = CustomUser.objects.create_user(username="promo_user", password="x")
        self.org.promoters.add(user)
        self.assertEqual(user.promoter_organizations.first(), self.org)
