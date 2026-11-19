from decimal import Decimal
from typing import Any

from django.test import TestCase
from rest_framework.response import Response
from rest_framework.test import APIClient

from app.models import CustomUser, Organization, OrgLog
from org.features import FeatureKey, set_org_feature
from org.models import OrgUser
from org.models_conduct import OrgConductSettings

ROLES = (
    "owner",
    "admin",
    "staff",
    "promoter",
    "member",
    "outsider",
    "site_admin",
    "anon",
)
ADMIN_ROLES = {"owner", "admin", "site_admin"}
STAFF_TIER = {"owner", "admin", "staff", "site_admin"}
MEMBER_ROLES = {"promoter", "member"}


def base(org_id: int) -> str:
    return f"/api/organizations/{org_id}/conduct/"


class ConductApiBase(TestCase):
    def setUp(self) -> None:
        self.users: dict[str, CustomUser | None] = {"anon": None}
        for role in ROLES[:-1]:
            self.users[role] = CustomUser.objects.create_user(
                username=f"conapi_{role}",
                password="x",
                is_staff=role == "site_admin",
            )
        self.org = Organization.objects.create(
            name="Conduct API Org", owner=self.users["owner"]
        )
        self.org.admins.add(self.users["admin"])
        self.org.staff.add(self.users["staff"])
        self.org.promoters.add(self.users["promoter"])
        self.org_users: dict[str, OrgUser] = {}
        for role in ("promoter", "member"):
            self.org_users[role] = OrgUser.objects.create(
                user=self.users[role], organization=self.org
            )
        self.site_admin = self.users["site_admin"]
        self.client = APIClient()

    def unlock(self, org: Organization | None = None) -> None:
        set_org_feature(
            org or self.org,
            FeatureKey.CONDUCT,
            enabled=True,
            actor=self.site_admin,
        )

    def as_role(self, role: str) -> APIClient:
        self.client.force_authenticate(user=self.users[role])
        return self.client

    def request(self, role: str, method: str, path: str, data: Any = None) -> Response:
        client = self.as_role(role)
        return getattr(client, method)(path, data, format="json")

    def assertCode(self, response: Response, code: str | None) -> None:
        self.assertEqual(response.status_code, 403, response.content)
        body = response.json()
        if code is None:
            self.assertNotIn("code", body)
        else:
            self.assertEqual(body.get("code"), code)

    def assertDenied(self, response: Response, role: str) -> None:
        if role == "anon":
            self.assertCode(response, None)
            self.assertEqual(
                response.json()["detail"],
                "Authentication credentials were not provided.",
            )
            return
        self.assertCode(response, "not_permitted")


class ConductSettingsApiTest(ConductApiBase):
    def settings_url(self) -> str:
        return f"{base(self.org.pk)}settings/"

    def patch(self, data: dict[str, Any], role: str = "owner") -> Response:
        return self.request(role, "patch", self.settings_url(), data)

    def test_settings_role_matrix(self) -> None:
        self.unlock()
        for role in ROLES:
            with self.subTest(role=role):
                response = self.request(role, "get", self.settings_url())
                if role in ADMIN_ROLES:
                    self.assertEqual(response.status_code, 200, response.content)
                else:
                    self.assertDenied(response, role)

    def test_settings_feature_locked(self) -> None:
        response = self.request("owner", "get", self.settings_url())
        self.assertCode(response, "feature_locked")
        response = self.patch({"min_events": 5})
        self.assertCode(response, "feature_locked")

    def test_settings_get_does_not_create_row(self) -> None:
        self.unlock()
        response = self.request("owner", "get", self.settings_url())
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(OrgConductSettings.objects.nocache().count(), 0)
        body = response.json()
        self.assertEqual(body["half_life_days"], 90)
        self.assertEqual(body["late_cancel_weight"], 0.5)
        self.assertIsInstance(body["late_cancel_weight"], float)
        self.assertIs(body["leaderboard_public"], True)
        self.assertEqual(body["defaults"]["prior_show_rate"], 0.85)
        self.assertEqual(body["defaults"]["min_events"], 3)
        self.assertIs(body["defaults"]["block_enabled"], False)
        self.assertNotIn("organization", body)
        self.assertNotIn("updated_by", body)

    def test_patch_validates_ranges(self) -> None:
        self.unlock()
        response = self.patch({"half_life_days": 5})
        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn("half_life_days", response.json())
        response = self.patch({"block_below": "1.5"})
        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(OrgConductSettings.objects.nocache().count(), 0)

    def test_patch_partial_cross_field_uses_stored_values(self) -> None:
        self.unlock()
        response = self.patch({"half_life_days": 200})
        self.assertEqual(response.status_code, 200, response.content)
        response = self.patch({"max_age_days": 150})
        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn("max_age_days", response.json())
        response = self.patch({"half_life_days": 400})
        self.assertEqual(response.status_code, 400, response.content)
        row = OrgConductSettings.objects.nocache().get(organization=self.org)
        self.assertEqual(row.half_life_days, 200)
        self.assertEqual(row.max_age_days, 365)

        response = self.patch({"late_cancel_weight": "0.5"})
        self.assertEqual(response.status_code, 200, response.content)
        response = self.patch({"late_cancel_weight": 0.25})
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["late_cancel_weight"], 0.25)
        row = OrgConductSettings.objects.nocache().get(organization=self.org)
        self.assertEqual(row.late_cancel_weight, Decimal("0.25"))

    def test_patch_unknown_field_400(self) -> None:
        self.unlock()
        response = self.patch({"min_events": 4, "bogus": 1})
        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn("bogus", response.json())
        response = self.patch({"updated_by": self.users["owner"].pk})
        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(OrgConductSettings.objects.nocache().count(), 0)

    def test_patch_non_admin_denied(self) -> None:
        self.unlock()
        for role in ("staff", "member", "outsider", "anon"):
            with self.subTest(role=role):
                self.assertDenied(self.patch({"min_events": 4}, role=role), role)
        self.assertEqual(OrgConductSettings.objects.nocache().count(), 0)

    def test_patch_writes_orglog_and_updated_by(self) -> None:
        self.unlock()
        before = OrgLog.objects.filter(organization=self.org).count()
        response = self.patch(
            {"min_events": 5, "block_enabled": True, "leaderboard_public": True}
        )
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertEqual(body["min_events"], 5)
        self.assertIs(body["block_enabled"], True)
        row = OrgConductSettings.objects.nocache().get(organization=self.org)
        self.assertEqual(row.updated_by_id, self.users["owner"].pk)
        self.assertEqual(row.min_events, 5)
        logs = OrgLog.objects.filter(organization=self.org).order_by("-pk")
        self.assertEqual(logs.count(), before + 1)
        entry = logs.first()
        self.assertEqual(entry.action, "update")
        self.assertEqual(entry.actor_id, self.users["owner"].pk)
        self.assertEqual(
            entry.details,
            {
                "area": "conduct_settings",
                "changed_fields": ["min_events", "block_enabled"],
            },
        )

        response = self.patch({"min_events": 5}, role="admin")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(
            OrgLog.objects.filter(organization=self.org).count(), before + 1
        )

    def test_patch_reflected_in_get_after_cache(self) -> None:
        self.unlock()
        self.request("owner", "get", self.settings_url())
        self.patch({"prior_strength": "4.5"})
        response = self.request("owner", "get", self.settings_url())
        self.assertEqual(response.json()["prior_strength"], 4.5)
