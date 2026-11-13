from django.test import TestCase
from rest_framework.test import APIClient

from app.models import CustomUser, Organization, OrgLog
from org.features import FeatureKey, org_has_feature, set_org_feature
from org.models import OrgFeature


def features_url(org_id: int) -> str:
    return f"/api/organizations/{org_id}/features/"


class OrgFeaturesApiTest(TestCase):
    def setUp(self) -> None:
        self.site_admin = CustomUser.objects.create_user(
            username="features_site_admin", password="x", is_staff=True
        )
        self.owner = CustomUser.objects.create_user(
            username="features_owner", password="x"
        )
        self.org = Organization.objects.create(
            name="Features API Org", owner=self.owner
        )
        self.client = APIClient()

    def test_site_admin_get_lists_every_feature(self) -> None:
        self.client.force_authenticate(self.site_admin)
        response = self.client.get(features_url(self.org.pk))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [row["feature"] for row in response.json()],
            sorted(FeatureKey.values),
        )
        for row in response.json():
            self.assertIs(row["enabled"], False)
            self.assertEqual(row["notes"], "")
            self.assertIsNone(row["enabled_by"])
            self.assertIsNone(row["enabled_at"])

    def test_get_shows_existing_row(self) -> None:
        set_org_feature(
            self.org,
            FeatureKey.PROMOTION,
            enabled=True,
            actor=self.site_admin,
            notes="paid via PayPal",
        )
        self.client.force_authenticate(self.site_admin)
        rows = {
            r["feature"]: r for r in self.client.get(features_url(self.org.pk)).json()
        }
        promo = rows["promotion"]
        self.assertIs(promo["enabled"], True)
        self.assertEqual(promo["notes"], "paid via PayPal")
        self.assertEqual(
            promo["enabled_by"],
            {"pk": self.site_admin.pk, "username": self.site_admin.username},
        )
        self.assertIsNotNone(promo["enabled_at"])
        self.assertIs(rows["contributions"]["enabled"], False)

    def test_put_enables_and_writes_orglog(self) -> None:
        self.client.force_authenticate(self.site_admin)
        response = self.client.put(
            features_url(self.org.pk),
            {"feature": "promotion", "enabled": True, "notes": "invoice 12"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        rows = {r["feature"]: r for r in response.json()}
        self.assertIs(rows["promotion"]["enabled"], True)
        self.assertEqual(rows["promotion"]["notes"], "invoice 12")
        self.assertTrue(org_has_feature(self.org, FeatureKey.PROMOTION))
        log = OrgLog.objects.get(organization=self.org, action="enable_feature")
        self.assertEqual(log.actor, self.site_admin)
        self.assertEqual(log.details["feature"], "promotion")

    def test_put_disable_without_notes_keeps_notes(self) -> None:
        set_org_feature(
            self.org,
            FeatureKey.PROMOTION,
            enabled=True,
            actor=self.site_admin,
            notes="paid",
        )
        self.client.force_authenticate(self.site_admin)
        response = self.client.put(
            features_url(self.org.pk),
            {"feature": "promotion", "enabled": False},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        row = OrgFeature.objects.get(organization=self.org, feature="promotion")
        self.assertIs(row.enabled, False)
        self.assertEqual(row.notes, "paid")
        self.assertTrue(
            OrgLog.objects.filter(
                organization=self.org, action="disable_feature"
            ).exists()
        )

    def test_owner_gets_not_permitted(self) -> None:
        self.client.force_authenticate(self.owner)
        for response in (
            self.client.get(features_url(self.org.pk)),
            self.client.put(
                features_url(self.org.pk),
                {"feature": "promotion", "enabled": True},
                format="json",
            ),
        ):
            self.assertEqual(response.status_code, 403)
            self.assertEqual(response.json()["code"], "not_permitted")
        self.assertFalse(org_has_feature(self.org, FeatureKey.PROMOTION))

    def test_anon_gets_plain_403(self) -> None:
        response = self.client.get(features_url(self.org.pk))
        self.assertEqual(response.status_code, 403)
        self.assertNotIn("code", response.json())

    def test_unknown_feature_is_400(self) -> None:
        self.client.force_authenticate(self.site_admin)
        response = self.client.put(
            features_url(self.org.pk),
            {"feature": "bogus", "enabled": True},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(OrgFeature.objects.filter(organization=self.org).exists())

    def test_missing_enabled_is_400(self) -> None:
        self.client.force_authenticate(self.site_admin)
        response = self.client.put(
            features_url(self.org.pk), {"feature": "promotion"}, format="json"
        )
        self.assertEqual(response.status_code, 400)

    def test_unknown_org_is_404(self) -> None:
        self.client.force_authenticate(self.site_admin)
        response = self.client.get(features_url(999999))
        self.assertEqual(response.status_code, 404)
