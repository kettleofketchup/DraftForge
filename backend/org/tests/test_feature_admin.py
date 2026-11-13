from django.test import TestCase

from app.models import CustomUser, Organization, OrgLog
from org.features import FeatureKey, set_org_feature
from org.models import OrgFeature

ADD_URL = "/admin/org/orgfeature/add/"
CHANGELIST_URL = "/admin/org/orgfeature/"


def change_url(pk: int) -> str:
    return f"/admin/org/orgfeature/{pk}/change/"


class OrgFeatureAdminTest(TestCase):
    def setUp(self) -> None:
        self.superuser = CustomUser.objects.create_superuser(
            username="feature_admin", password="x", email="fa@example.com"
        )
        self.client.force_login(self.superuser)
        self.org = Organization.objects.create(name="Admin Feature Org")
        self.other_org = Organization.objects.create(name="Other Feature Org")

    def test_admin_add_writes_orglog(self) -> None:
        response = self.client.post(
            ADD_URL,
            {
                "organization": self.org.pk,
                "feature": "promotion",
                "enabled": "on",
                "notes": "paid via PayPal",
                "_save": "Save",
            },
        )
        self.assertEqual(response.status_code, 302)
        row = OrgFeature.objects.get(organization=self.org, feature="promotion")
        self.assertIs(row.enabled, True)
        self.assertEqual(row.enabled_by, self.superuser)
        self.assertEqual(row.notes, "paid via PayPal")
        log = OrgLog.objects.get(organization=self.org, action="enable_feature")
        self.assertEqual(log.actor, self.superuser)
        self.assertEqual(log.details["feature"], "promotion")
        self.assertEqual(log.details["notes"], "paid via PayPal")

    def test_admin_change_disable_writes_orglog(self) -> None:
        row = set_org_feature(
            self.org,
            FeatureKey.PROMOTION,
            enabled=True,
            actor=self.superuser,
            notes="paid",
        )
        enabled_by = row.enabled_by
        enabled_at = row.enabled_at
        response = self.client.post(
            change_url(row.pk),
            {"notes": "paid", "_save": "Save"},
        )
        self.assertEqual(response.status_code, 302)
        row.refresh_from_db()
        self.assertIs(row.enabled, False)
        self.assertEqual(row.notes, "paid")
        self.assertEqual(row.enabled_by, enabled_by)
        self.assertEqual(row.enabled_at, enabled_at)
        self.assertTrue(
            OrgLog.objects.filter(
                organization=self.org,
                action="disable_feature",
                actor=self.superuser,
            ).exists()
        )

    def test_admin_add_locked_row_writes_no_orglog(self) -> None:
        response = self.client.post(
            ADD_URL,
            {
                "organization": self.org.pk,
                "feature": "promotion",
                "notes": "quoted, not paid yet",
                "_save": "Save",
            },
        )
        self.assertEqual(response.status_code, 302)
        row = OrgFeature.objects.get(organization=self.org, feature="promotion")
        self.assertIs(row.enabled, False)
        self.assertEqual(row.notes, "quoted, not paid yet")
        self.assertFalse(
            OrgLog.objects.filter(
                organization=self.org,
                action__in=["enable_feature", "disable_feature"],
            ).exists()
        )

    def test_admin_add_duplicate_rejected(self) -> None:
        row = set_org_feature(
            self.org,
            FeatureKey.PROMOTION,
            enabled=True,
            actor=self.superuser,
            notes="paid",
        )
        log_count = OrgLog.objects.count()
        response = self.client.post(
            ADD_URL,
            {
                "organization": self.org.pk,
                "feature": "promotion",
                "notes": "overwrite?",
                "_save": "Save",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["adminform"].form.errors)
        self.assertEqual(OrgFeature.objects.count(), 1)
        self.assertEqual(OrgLog.objects.count(), log_count)
        row.refresh_from_db()
        self.assertIs(row.enabled, True)
        self.assertEqual(row.notes, "paid")

    def test_admin_change_cannot_move_row(self) -> None:
        row = set_org_feature(
            self.org, FeatureKey.PROMOTION, enabled=True, actor=self.superuser
        )
        response = self.client.post(
            change_url(row.pk),
            {
                "organization": self.other_org.pk,
                "feature": "contributions",
                "enabled": "on",
                "notes": "moved?",
                "_save": "Save",
            },
        )
        self.assertEqual(response.status_code, 302)
        row.refresh_from_db()
        self.assertEqual(row.organization_id, self.org.pk)
        self.assertEqual(row.feature, "promotion")
        self.assertFalse(
            OrgFeature.objects.filter(organization=self.other_org).exists()
        )
        self.assertFalse(OrgFeature.objects.filter(feature="contributions").exists())
        self.assertEqual(OrgFeature.objects.count(), 1)

    def test_admin_has_no_delete(self) -> None:
        row = set_org_feature(
            self.org, FeatureKey.PROMOTION, enabled=True, actor=self.superuser
        )
        response = self.client.get(f"/admin/org/orgfeature/{row.pk}/delete/")
        self.assertEqual(response.status_code, 403)
        changelist = self.client.get(CHANGELIST_URL)
        self.assertEqual(changelist.status_code, 200)
        self.assertNotContains(changelist, "delete_selected")
        self.assertTrue(OrgFeature.objects.filter(pk=row.pk).exists())
