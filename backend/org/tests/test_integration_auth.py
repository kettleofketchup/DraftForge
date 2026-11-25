"""Operation-scoped org app tokens for the promotion integration.

A token carries explicit operation grants. Tokens that existed before grants,
and tokens issued without naming operations, stay MMR-only. Every request
rechecks the grant, the owner, the owner's admin role, the feature, the org
and the request budget, so a replayed request gets no more than a new one.
"""

import unittest

from django.core.cache import cache
from django.test import override_settings
from django.urls import path
from django.utils import timezone
from rest_framework.response import Response
from rest_framework.test import APIClient

from backend.urls import urlpatterns as project_urlpatterns
from org.api_tokens.auth import gate_token_request
from org.api_tokens.operations import (
    Operation,
    default_operations,
    entitlement_for,
    parse_operations,
)
from org.api_tokens.tokens import issue_token
from org.features import FeatureKey, set_org_feature
from org.integration.base import IntegrationAPIView
from org.models import OrgApiLimits, OrgApiToken, OrgApiTokenUsage
from org.tests.test_api_tokens import LOCMEM_CACHE, ApiTokenBase

try:
    from django_test_migrations.contrib.unittest_case import MigratorTestCase
except ImportError as _import_error:  # pragma: no cover
    raise unittest.SkipTest(
        "django-test-migrations not installed — rebuild backend-dev image "
        "to pick up the new dev dep from pyproject.toml."
    ) from _import_error


class _PromotionReadProbe(IntegrationAPIView):
    def get(self, request, org_id: int) -> Response:
        org = gate_token_request(request, org_id, operation=Operation.PROMOTION_READ)
        return Response({"org_id": org.pk})


urlpatterns = [
    path("probe/<int:org_id>/promotion/", _PromotionReadProbe.as_view()),
    *project_urlpatterns,
]

PROMO_OPS = [Operation.PROMOTION_READ, Operation.PROMOTION_IMPORT]


class OperationCatalogTests(unittest.TestCase):
    def test_default_operations_are_mmr_pair_only(self) -> None:
        self.assertEqual(default_operations(), ["mmr:read", "mmr:write"])

    def test_values_and_entitlements(self) -> None:
        self.assertEqual(
            {op.value: entitlement_for(op) for op in Operation},
            {
                "mmr:read": FeatureKey.MMR_SYNC,
                "mmr:write": FeatureKey.MMR_SYNC,
                "promotion:read": FeatureKey.PROMOTION,
                "promotion:import": FeatureKey.PROMOTION,
            },
        )

    def test_parse_rejects_unknown_empty_and_non_strings(self) -> None:
        for bad in ([], ["promotion:write"], ["MMR:READ"], [1], "mmr:read", None):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                parse_operations(bad)

    def test_contributions_read_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "unknown operation"):
            parse_operations(["contributions:read"])

    def test_parse_dedupes_and_sorts_canonically(self) -> None:
        self.assertEqual(
            parse_operations(["promotion:read", "mmr:read", "promotion:read"]),
            ["mmr:read", "promotion:read"],
        )


@override_settings(ROOT_URLCONF=__name__, CACHES=LOCMEM_CACHE)
class GrantTests(ApiTokenBase):
    def setUp(self) -> None:
        super().setUp()
        set_org_feature(self.org, FeatureKey.PROMOTION, enabled=True, actor=None)

    def promo_url(self, org=None) -> str:
        return f"/probe/{(org or self.org).pk}/promotion/"

    def tokens_url(self) -> str:
        return f"/api/organizations/{self.org.pk}/api-tokens/"

    def test_grants_backfill_and_default_are_mmr_only(self) -> None:
        issued = issue_token(self.org, self.admin, "legacy")
        self.assertEqual(issued.token.operations, ["mmr:read", "mmr:write"])
        self.client.force_authenticate(self.admin)
        resp = self.client.post(self.tokens_url(), {"name": "api"}, format="json")
        self.assertEqual(resp.status_code, 201, resp.data)
        self.assertEqual(resp.data["operations"], ["mmr:read", "mmr:write"])
        self.assertEqual(
            OrgApiToken.objects.get(pk=resp.data["id"]).operations,
            ["mmr:read", "mmr:write"],
        )
        denied = self.bearer(issued.raw).get(self.promo_url())
        self.assertEqual(denied.status_code, 403)
        self.assertEqual(denied.json()["error"]["code"], "operation_not_granted")
        listed = self.client.get(self.tokens_url()).data
        self.assertTrue(all(row["operations"] for row in listed))

    def test_promotions_only_token_issuable_without_mmr_entitlement(self) -> None:
        set_org_feature(self.org, FeatureKey.MMR_SYNC, enabled=False, actor=None)
        self.client.force_authenticate(self.admin)
        resp = self.client.post(
            self.tokens_url(),
            {"name": "adaptor", "operations": ["promotion:import", "promotion:read"]},
            format="json",
        )
        self.assertEqual(resp.status_code, 201, resp.data)
        self.assertEqual(
            resp.data["operations"], ["promotion:import", "promotion:read"]
        )
        raw = resp.data["token"]
        self.assertEqual(self.bearer(raw).get(self.promo_url()).status_code, 200)
        mmr = self.bearer(raw).get(self.sync_url())
        self.assertEqual(mmr.status_code, 403)

    def test_issuance_requires_each_requested_entitlement(self) -> None:
        set_org_feature(self.org, FeatureKey.MMR_SYNC, enabled=False, actor=None)
        self.client.force_authenticate(self.admin)
        resp = self.client.post(
            self.tokens_url(),
            {"name": "x", "operations": ["promotion:read", "mmr:read"]},
            format="json",
        )
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.data["code"], "feature_locked")
        self.assertFalse(OrgApiToken.objects.filter(name="x").exists())

    def test_issuance_rejects_unknown_and_empty_operations(self) -> None:
        self.client.force_authenticate(self.admin)
        for ops in ([], ["promotion:write"], ["nope"], "promotion:read"):
            with self.subTest(ops=ops):
                resp = self.client.post(
                    self.tokens_url(), {"name": "x", "operations": ops}, format="json"
                )
                self.assertEqual(resp.status_code, 400)
        self.assertFalse(OrgApiToken.objects.filter(name="x").exists())

    def test_staff_cannot_issue_scoped_token(self) -> None:
        self.client.force_authenticate(self.staff)
        resp = self.client.post(
            self.tokens_url(),
            {"name": "x", "operations": ["promotion:read"]},
            format="json",
        )
        self.assertEqual(resp.status_code, 403)

    def test_gate_checks_grant_owner_admin_feature_org_and_budget_before_replay(
        self,
    ) -> None:
        issued = issue_token(self.org, self.admin, "adaptor", operations=PROMO_OPS)
        client = self.bearer(issued.raw)
        url = self.promo_url()
        self.assertEqual(client.get(url).status_code, 200)

        self.org.admins.remove(self.admin)
        self.assertEqual(client.get(url).status_code, 403)
        self.org.admins.add(self.admin)

        set_org_feature(self.org, FeatureKey.PROMOTION, enabled=False, actor=None)
        resp = client.get(url)
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.json()["error"]["code"], "feature_locked")
        set_org_feature(self.org, FeatureKey.PROMOTION, enabled=True, actor=None)

        OrgApiToken.objects.filter(pk=issued.token.pk).update(
            operations=["promotion:import"]
        )
        self.assertEqual(client.get(url).status_code, 403)
        OrgApiToken.objects.filter(pk=issued.token.pk).update(operations=PROMO_OPS)

        self.admin.is_active = False
        self.admin.save()
        self.assertEqual(client.get(url).status_code, 401)
        self.admin.is_active = True
        self.admin.save()

        self.assertEqual(client.get(self.promo_url(self.other_org)).status_code, 404)

        # Only the first request passed every check, so only it was counted.
        OrgApiLimits.objects.create(organization=self.org, per_minute=100, per_day=1)
        cache.clear()
        resp = client.get(url)
        self.assertEqual(resp.status_code, 429)
        self.assertIn("Retry-After", resp)
        self.assertEqual(resp.json()["error"]["code"], "rate_limited")

        OrgApiToken.objects.filter(pk=issued.token.pk).update(revoked_at=timezone.now())
        self.assertEqual(client.get(url).status_code, 401)

    def test_denied_requests_do_not_consume_budget(self) -> None:
        issued = issue_token(self.org, self.admin, "mmr")
        self.assertEqual(self.bearer(issued.raw).get(self.promo_url()).status_code, 403)
        self.assertFalse(
            OrgApiTokenUsage.objects.filter(
                token=issued.token, request_count__gt=0
            ).exists()
        )

    def test_wrong_org_is_404(self) -> None:
        issued = issue_token(self.org, self.admin, "adaptor", operations=PROMO_OPS)
        resp = self.bearer(issued.raw).get(self.promo_url(self.other_org))
        self.assertEqual(resp.status_code, 404)
        self.assertEqual(resp.json()["error"]["code"], "not_found")

    def test_contributions_route_removed(self) -> None:
        issued = issue_token(
            self.org, self.admin, "all", operations=[op.value for op in Operation]
        )
        resp = self.bearer(issued.raw).get(
            f"/api/organizations/{self.org.pk}/integration/v1/contributions/"
        )
        self.assertEqual(resp.status_code, 404)

    def test_session_and_internal_service_tokens_not_accepted(self) -> None:
        self.client.force_authenticate(self.admin)
        resp = self.client.get(self.promo_url())
        self.assertEqual(resp.status_code, 401)
        self.assertEqual(resp.json()["error"]["code"], "unauthorized")
        with override_settings(
            INTERNAL_SERVICE_TOKEN="internal-secret",
            INTERNAL_SERVICE_ALLOWED_IPS=["127.0.0.1"],
        ):
            resp = APIClient().get(
                self.promo_url(), HTTP_X_INTERNAL_TOKEN="internal-secret"
            )
        self.assertEqual(resp.status_code, 401)
        self.assertEqual(
            APIClient().get(self.promo_url()).json()["error"]["code"], "unauthorized"
        )

    def test_failure_envelope_shape_hides_details(self) -> None:
        resp = self.bearer("dfk_deadbeef_wrong").get(self.promo_url())
        self.assertEqual(resp.status_code, 401)
        body = resp.json()
        self.assertEqual(set(body), {"error"})
        self.assertEqual(set(body["error"]), {"code", "message", "request_id"})
        self.assertNotIn("dfk_", resp.content.decode())
        self.assertEqual(resp["X-Request-ID"], body["error"]["request_id"])
        self.assertIn("Bearer", resp["WWW-Authenticate"])


@override_settings(CACHES=LOCMEM_CACHE)
class MmrOperationRegressionTests(ApiTokenBase):
    def test_mmr_read_only_token_can_get_but_not_post(self) -> None:
        raw = issue_token(self.org, self.admin, "ro", operations=["mmr:read"]).raw
        self.assertEqual(self.bearer(raw).get(self.sync_url()).status_code, 200)
        resp = self.bearer(raw).post(
            self.sync_url(),
            {"entries": [{"steam_id": 1001, "mmr": 1}]},
            format="json",
        )
        self.assertEqual(resp.status_code, 403)

    def test_mmr_write_only_token_can_post_but_not_get(self) -> None:
        raw = issue_token(self.org, self.admin, "wo", operations=["mmr:write"]).raw
        self.assertEqual(self.bearer(raw).get(self.sync_url()).status_code, 403)
        resp = self.bearer(raw).post(
            self.sync_url(),
            {"entries": [{"steam_id": 1001, "mmr": 1}]},
            format="json",
        )
        self.assertEqual(resp.status_code, 200, resp.data)

    def test_mmr_legacy_success_and_error_shapes_unchanged(self) -> None:
        raw = issue_token(self.org, self.admin, "bot").raw
        resp = self.bearer(raw).get(self.sync_url())
        self.assertEqual(set(resp.data), {"game_type", "members"})
        set_org_feature(self.org, FeatureKey.MMR_SYNC, enabled=False, actor=None)
        resp = self.bearer(raw).get(self.sync_url())
        self.assertEqual(resp.data["code"], "feature_locked")
        self.assertNotIn("error", resp.data)


class OperationsBackfillMigrationTest(MigratorTestCase):
    migrate_from = ("org", "0025_mmrchangerequest")
    migrate_to = ("org", "0026_api_token_operations")

    def prepare(self) -> None:
        apps = self.old_state.apps
        CustomUser = apps.get_model("app", "CustomUser")
        Organization = apps.get_model("org", "Organization")
        Token = apps.get_model("org", "OrgApiToken")
        owner = CustomUser.objects.create(username="legacy_owner")
        org = Organization.objects.create(name="Legacy Org", owner=owner)
        self.token_pk = Token.objects.create(
            organization=org,
            user=owner,
            name="legacy",
            prefix="abc123def456",
            secret_hash="0" * 64,
        ).pk

    def test_existing_token_gets_both_mmr_grants_and_no_promotion_grants(
        self,
    ) -> None:
        Token = self.new_state.apps.get_model("org", "OrgApiToken")
        self.assertEqual(
            Token.objects.get(pk=self.token_pk).operations, ["mmr:read", "mmr:write"]
        )
