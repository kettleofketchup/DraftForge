from collections.abc import Callable
from typing import Any

from django.db import connection
from django.test import TestCase
from rest_framework.response import Response
from rest_framework.test import APIClient

from app.models import CustomUser, Organization, OrgLog
from app.serializers import OrganizationSerializer
from org.features import FeatureKey, set_org_feature
from org.models import OrgUser


def promoters_url(org_id: int) -> str:
    return f"/api/organizations/{org_id}/promoters/"


def promoter_url(org_id: int, user_id: int) -> str:
    return f"/api/organizations/{org_id}/promoters/{user_id}/"


def _keys(value: Any) -> list[str]:
    if isinstance(value, dict):
        keys = list(value.keys())
        for child in value.values():
            keys.extend(_keys(child))
        return keys
    if isinstance(value, list):
        return [key for child in value for key in _keys(child)]
    return []


class PromoterEndpointsTest(TestCase):
    def setUp(self) -> None:
        self.site_admin = CustomUser.objects.create_user(
            username="promo_site_admin", password="x", is_staff=True
        )
        self.owner = CustomUser.objects.create_user(
            username="promo_owner", password="x"
        )
        self.admin = CustomUser.objects.create_user(
            username="promo_admin", password="x"
        )
        self.staff = CustomUser.objects.create_user(
            username="promo_staff", password="x"
        )
        self.target = CustomUser.objects.create_user(
            username="promo_target", password="x"
        )
        self.org = Organization.objects.create(name="Promoter Org", owner=self.owner)
        self.org.admins.add(self.admin)
        self.org.staff.add(self.staff)
        self.client = APIClient()

    def _unlock(self) -> None:
        set_org_feature(
            self.org, FeatureKey.PROMOTION, enabled=True, actor=self.site_admin
        )

    def test_admin_adds_promoter_on_unlocked_org(self) -> None:
        self._unlock()
        self.client.force_authenticate(self.admin)
        response = self.client.post(
            promoters_url(self.org.pk), {"user_id": self.target.pk}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "added")
        self.assertEqual(response.json()["user"]["pk"], self.target.pk)
        self.assertTrue(self.org.promoters.filter(pk=self.target.pk).exists())
        self.assertTrue(
            OrgUser.objects.filter(user=self.target, organization=self.org).exists()
        )
        log = OrgLog.objects.get(organization=self.org, action="add_promoter")
        self.assertEqual(log.actor, self.admin)
        self.assertEqual(log.target_user, self.target)

    def test_owner_and_site_admin_can_add(self) -> None:
        self._unlock()
        for actor in (self.owner, self.site_admin):
            user = CustomUser.objects.create_user(
                username=f"promo_by_{actor.username}", password="x"
            )
            self.client.force_authenticate(actor)
            response = self.client.post(
                promoters_url(self.org.pk), {"user_id": user.pk}, format="json"
            )
            self.assertEqual(response.status_code, 200)
            self.assertTrue(self.org.promoters.filter(pk=user.pk).exists())

    def test_staff_member_can_be_added(self) -> None:
        self._unlock()
        self.client.force_authenticate(self.admin)
        response = self.client.post(
            promoters_url(self.org.pk), {"user_id": self.staff.pk}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(self.org.promoters.filter(pk=self.staff.pk).exists())

    def test_already_promoter_is_400(self) -> None:
        self._unlock()
        self.org.promoters.add(self.target)
        self.client.force_authenticate(self.admin)
        response = self.client.post(
            promoters_url(self.org.pk), {"user_id": self.target.pk}, format="json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {"error": "already a promoter"})
        self.assertFalse(
            OrgLog.objects.filter(organization=self.org, action="add_promoter").exists()
        )

    def test_missing_user_id_is_400(self) -> None:
        self._unlock()
        self.client.force_authenticate(self.admin)
        response = self.client.post(promoters_url(self.org.pk), {}, format="json")
        self.assertEqual(response.status_code, 400)

    def test_unknown_user_is_404(self) -> None:
        self._unlock()
        self.client.force_authenticate(self.admin)
        response = self.client.post(
            promoters_url(self.org.pk), {"user_id": 999999}, format="json"
        )
        self.assertEqual(response.status_code, 404)

    def test_unknown_org_is_404(self) -> None:
        self.client.force_authenticate(self.site_admin)
        response = self.client.get(promoters_url(999999))
        self.assertEqual(response.status_code, 404)

    def test_locked_org_is_feature_locked(self) -> None:
        self.client.force_authenticate(self.admin)
        for response in (
            self.client.get(promoters_url(self.org.pk)),
            self.client.post(
                promoters_url(self.org.pk), {"user_id": self.target.pk}, format="json"
            ),
            self.client.delete(promoter_url(self.org.pk, self.target.pk)),
        ):
            self.assertEqual(response.status_code, 403)
            self.assertEqual(response.json()["code"], "feature_locked")
        self.assertFalse(self.org.promoters.exists())

    def test_staff_is_not_permitted(self) -> None:
        self._unlock()
        self.client.force_authenticate(self.staff)
        for response in (
            self.client.get(promoters_url(self.org.pk)),
            self.client.post(
                promoters_url(self.org.pk), {"user_id": self.target.pk}, format="json"
            ),
        ):
            self.assertEqual(response.status_code, 403)
            self.assertEqual(response.json()["code"], "not_permitted")
        self.assertFalse(self.org.promoters.exists())

    def test_promoter_cannot_manage_promoters(self) -> None:
        self._unlock()
        self.org.promoters.add(self.target)
        self.client.force_authenticate(self.target)
        response = self.client.get(promoters_url(self.org.pk))
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["code"], "not_permitted")

    def test_anon_on_unlocked_org_is_plain_403(self) -> None:
        self._unlock()
        response = self.client.post(
            promoters_url(self.org.pk), {"user_id": self.target.pk}, format="json"
        )
        self.assertEqual(response.status_code, 403)
        self.assertNotIn("code", response.json())
        self.assertFalse(self.org.promoters.exists())

    def test_admin_lists_promoters(self) -> None:
        self._unlock()
        self.org.promoters.add(self.target)
        self.client.force_authenticate(self.admin)
        response = self.client.get(promoters_url(self.org.pk))
        self.assertEqual(response.status_code, 200)
        self.assertEqual([u["pk"] for u in response.json()], [self.target.pk])
        self.assertEqual(response.json()[0]["username"], self.target.username)

    def _get_counting_queries(self, url: str) -> tuple[Response, int]:
        executed: list[str] = []

        def record(
            execute: Callable[..., Any],
            sql: str,
            params: Any,
            many: bool,
            context: dict[str, Any],
        ) -> Any:
            executed.append(sql)
            return execute(sql, params, many, context)

        with connection.execute_wrapper(record):
            response = self.client.get(url)
        return response, len(executed)

    def test_list_query_count_is_constant_in_promoter_count(self) -> None:
        self._unlock()
        self.org.promoters.add(self.target)
        self.client.force_authenticate(self.admin)
        _, baseline = self._get_counting_queries(promoters_url(self.org.pk))
        for i in range(3):
            self.org.promoters.add(
                CustomUser.objects.create_user(
                    username=f"promo_extra_{i}", password="x"
                )
            )
        response, count = self._get_counting_queries(promoters_url(self.org.pk))
        self.assertEqual(len(response.json()), 4)
        self.assertTrue(all("positions" in row for row in response.json()))
        self.assertEqual(count, baseline)

    def test_list_reflects_add_after_cached_read(self) -> None:
        self._unlock()
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.get(promoters_url(self.org.pk)).json(), [])
        self.client.post(
            promoters_url(self.org.pk), {"user_id": self.target.pk}, format="json"
        )
        response = self.client.get(promoters_url(self.org.pk))
        self.assertEqual([u["pk"] for u in response.json()], [self.target.pk])

    def test_remove_keeps_orguser_and_logs(self) -> None:
        self._unlock()
        self.org.promoters.add(self.target)
        OrgUser.objects.get_or_create(user=self.target, organization=self.org)
        self.client.force_authenticate(self.admin)
        response = self.client.delete(promoter_url(self.org.pk, self.target.pk))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "removed"})
        self.assertFalse(self.org.promoters.filter(pk=self.target.pk).exists())
        self.assertTrue(
            OrgUser.objects.filter(user=self.target, organization=self.org).exists()
        )
        log = OrgLog.objects.get(organization=self.org, action="remove_promoter")
        self.assertEqual(log.actor, self.admin)
        self.assertEqual(log.target_user, self.target)

    def test_remove_non_promoter_is_400(self) -> None:
        self._unlock()
        self.client.force_authenticate(self.admin)
        response = self.client.delete(promoter_url(self.org.pk, self.target.pk))
        self.assertEqual(response.status_code, 400)
        self.assertFalse(
            OrgLog.objects.filter(
                organization=self.org, action="remove_promoter"
            ).exists()
        )

    def test_remove_by_staff_is_not_permitted(self) -> None:
        self._unlock()
        self.org.promoters.add(self.target)
        self.client.force_authenticate(self.staff)
        response = self.client.delete(promoter_url(self.org.pk, self.target.pk))
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["code"], "not_permitted")
        self.assertTrue(self.org.promoters.filter(pk=self.target.pk).exists())


class PromoterRoleDoesNotLeakTest(TestCase):
    def setUp(self) -> None:
        self.owner = CustomUser.objects.create_user(username="leak_owner", password="x")
        self.promoter = CustomUser.objects.create_user(
            username="leak_promoter", password="x"
        )
        self.org = Organization.objects.create(name="Leak Org", owner=self.owner)
        self.org.promoters.add(self.promoter)
        self.client = APIClient()

    def test_anonymous_user_detail_has_no_promoter_key(self) -> None:
        response = self.client.get(f"/api/users/{self.promoter.pk}/")
        self.assertEqual(response.status_code, 200)
        self.assertFalse([k for k in _keys(response.json()) if "promoter" in k.lower()])

    def test_current_user_payload_has_no_promoter_key(self) -> None:
        self.client.force_authenticate(self.promoter)
        response = self.client.get("/api/current_user")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["pk"], self.promoter.pk)
        self.assertFalse([k for k in _keys(response.json()) if "promoter" in k.lower()])

    def test_organization_serializer_has_no_promoters(self) -> None:
        data = OrganizationSerializer(self.org).data
        self.assertNotIn("promoters", data)
        self.assertNotIn("promoter_ids", data)
        self.assertFalse([k for k in _keys(data) if "promoter" in k.lower()])
