import json
from datetime import timedelta
from unittest.mock import patch

from django.contrib import admin
from django.test import RequestFactory, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from org.api_connections.lifecycle import issue_connection_key
from org.api_connections.views import ConnectionRateLimited, check_action_budget
from org.api_tokens.tokens import issue_token
from org.features import FeatureKey, set_org_feature
from org.models import OrgApiConnection, OrgApiToken, OrgLog
from org.tests.test_api_connections_crypto import OLD_KEY
from org.tests.test_api_tokens import ApiTokenBase


class ConnectionApiTests(ApiTokenBase):
    def setUp(self) -> None:
        super().setUp()
        self.client.force_authenticate(self.admin)
        self.url = f"/api/organizations/{self.org.pk}/api-connections/"

    def create(self, **fields: object) -> dict[str, object]:
        response = self.client.post(
            self.url, {"name": "Ratings", **fields}, format="json"
        )
        self.assertEqual(response.status_code, 201, response.data)
        return response.data

    def test_legacy_create_defaults_differ_from_connection_create(self) -> None:
        row = self.create()
        self.assertEqual(row["operations"], [])
        for flag in (
            "enabled",
            "inbound_enabled",
            "mmr_push_enabled",
            "mmr_pull_enabled",
            "promotion_push_enabled",
        ):
            self.assertIs(row[flag], False)
        self.assertFalse(OrgApiToken.objects.exists())
        old = self.client.post(
            f"/api/organizations/{self.org.pk}/api-tokens/",
            {"name": "Old"},
            format="json",
        )
        self.assertEqual(old.status_code, 201)
        self.assertEqual(old.data["operations"], ["mmr:read", "mmr:write"])
        self.assertEqual(old["Cache-Control"], "no-store")
        token = OrgApiToken.objects.get(pk=old.data["id"])
        self.assertIsNotNone(token.connection_id)
        self.assertEqual(
            self.bearer(old.data["token"]).get(self.sync_url()).status_code, 200
        )

    def test_wrong_org_is_404(self) -> None:
        row = self.create()
        self.other_org.admins.add(self.admin)
        for method in (self.client.get, self.client.patch, self.client.delete):
            response = method(
                f"/api/organizations/{self.other_org.pk}/api-connections/{row['id']}/"
            )
            self.assertEqual(response.status_code, 404)

    def test_new_grants_need_explicit_issue(self) -> None:
        row = self.create(operations=["mmr:read"], inbound_enabled=True)
        self.assertFalse(OrgApiToken.objects.exists())
        issued = self.client.post(
            f"{self.url}{row['id']}/issue-key/", {}, format="json"
        )
        self.assertEqual(issued.status_code, 201, issued.data)
        self.assertEqual(issued["Cache-Control"], "no-store")
        self.assertEqual(
            self.bearer(issued.data["credential"]["token"])
            .get(self.sync_url())
            .status_code,
            401,
        )
        token = OrgApiToken.objects.get(pk=issued.data["credential"]["id"])
        self.assertEqual(token.user, self.admin)
        self.assertEqual(token.issued_by, self.admin)

    def test_grant_edit_revokes_and_rotation_keeps_identity(self) -> None:
        row = self.create(operations=["mmr:read"], inbound_enabled=True, enabled=True)
        url = f"{self.url}{row['id']}/"
        first = self.client.post(f"{url}issue-key/", {}, format="json").data
        raw = first["credential"]["token"]
        self.assertEqual(self.bearer(raw).get(self.sync_url()).status_code, 200)
        changed = self.client.patch(
            url,
            {
                "config_version": first["connection"]["config_version"],
                "operations": ["mmr:read", "mmr:write"],
            },
            format="json",
        )
        self.assertEqual(changed.status_code, 200, changed.data)
        self.assertEqual(self.bearer(raw).get(self.sync_url()).status_code, 401)
        second = self.client.post(f"{url}issue-key/", {}, format="json").data
        rotated = self.client.post(f"{url}rotate-key/", {}, format="json")
        self.assertEqual(rotated.status_code, 201, rotated.data)
        self.assertEqual(rotated.data["connection"]["id"], row["id"])
        self.assertEqual(
            self.bearer(second["credential"]["token"]).get(self.sync_url()).status_code,
            401,
        )
        self.assertEqual(
            self.bearer(rotated.data["credential"]["token"])
            .get(self.sync_url())
            .status_code,
            200,
        )

    def test_revoke_does_not_disable_outbound(self) -> None:
        issued = issue_token(self.org, self.admin, "Old")
        connection = issued.token.connection
        OrgApiConnection.objects.filter(pk=connection.pk).update(mmr_push_enabled=True)
        response = self.client.post(
            f"{self.url}{connection.pk}/revoke-key/", {}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        connection.refresh_from_db()
        self.assertTrue(connection.mmr_push_enabled)
        self.assertEqual(self.bearer(issued.raw).get(self.sync_url()).status_code, 401)

    @override_settings(ORG_API_CREDENTIAL_KEYS=json.dumps([OLD_KEY]))
    def test_cas_409_and_secret_free_read_admin_audit(self) -> None:
        row = self.create(
            outbound_base_url="https://ratings.example",
            outbound_auth="bearer",
            outbound_credential="synthetic-write-only-secret",
        )
        self.assertTrue(row["credential_present"])
        connection = OrgApiConnection.objects.get(pk=row["id"])
        self.assertNotIn(
            "synthetic-write-only-secret", connection.outbound_credential_ciphertext
        )
        url = f"{self.url}{row['id']}/"
        changed = self.client.patch(
            url, {"config_version": 1, "name": "Changed"}, format="json"
        )
        self.assertEqual(changed.status_code, 200, changed.data)
        stale = self.client.patch(
            url, {"config_version": 1, "name": "Stale"}, format="json"
        )
        self.assertEqual(stale.status_code, 409)
        self.assertEqual(stale.data["code"], "configuration_changed")
        for field in (
            "outbound_credential_owner",
            "outbound_authorizer",
            "issued_by",
            "created_by",
            "last_run_summary",
        ):
            rejected = self.client.patch(
                url, {"config_version": 2, field: self.admin.pk}, format="json"
            )
            self.assertEqual(rejected.status_code, 400)
        content = self.client.get(url).content.decode()
        self.assertNotIn("ciphertext", content)
        self.assertNotIn("secret_hash", content)
        self.assertNotIn("synthetic-write-only-secret", content)
        self.assertNotIn(connection.outbound_credential_ciphertext, content)
        self.assertNotIn(
            "synthetic-write-only-secret",
            json.dumps(list(OrgLog.objects.values_list("details", flat=True))),
        )
        self.assertTrue(OrgLog.objects.filter(action="edit_api_connection").exists())
        request = RequestFactory().get("/admin/")
        request.user = self.site_admin
        for model in (OrgApiConnection, OrgApiToken):
            fields = admin.site._registry[model].get_fields(request)
            self.assertNotIn("outbound_credential_ciphertext", fields)
            self.assertNotIn("secret_hash", fields)

    def test_locked_features_allow_read_disable_revoke_not_add_issue_enable(
        self,
    ) -> None:
        issued = issue_token(self.org, self.admin, "Old")
        connection = issued.token.connection
        url = f"{self.url}{connection.pk}/"
        set_org_feature(self.org, FeatureKey.MMR_SYNC, enabled=False, actor=None)
        self.assertEqual(self.client.get(url).status_code, 200)
        self.assertEqual(
            self.client.post(f"{url}rotate-key/", {}, format="json").status_code, 403
        )
        self.assertEqual(
            self.client.patch(
                url, {"config_version": 1, "enabled": False}, format="json"
            ).status_code,
            200,
        )
        self.assertEqual(
            self.client.patch(
                url, {"config_version": 2, "enabled": True}, format="json"
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.post(f"{url}revoke-key/", {}, format="json").status_code, 200
        )
        self.assertEqual(self.client.delete(url).status_code, 200)

    def test_session_csrf_and_role_required(self) -> None:
        csrf = APIClient(enforce_csrf_checks=True)
        csrf.force_login(self.admin)
        self.assertEqual(
            csrf.post(self.url, {"name": "Blocked"}, format="json").status_code, 403
        )
        for user in (self.staff, self.member):
            self.client.force_authenticate(user)
            self.assertEqual(self.client.get(self.url).status_code, 403)
            self.assertEqual(
                self.client.post(
                    self.url, {"name": "Blocked"}, format="json"
                ).status_code,
                403,
            )

    def test_unimplemented_directions_and_routes_fail_closed(self) -> None:
        for direction in (
            "mmr_pull_enabled",
            "promotion_push_enabled",
        ):
            self.assertEqual(
                self.client.post(
                    self.url, {"name": "Blocked", direction: True}, format="json"
                ).status_code,
                400,
            )
        row = self.create()
        for action in ("test", "pull", "promotion/resume"):
            self.assertEqual(
                self.client.post(
                    f"{self.url}{row['id']}/{action}/", {}, format="json"
                ).status_code,
                404,
            )

    def test_owner_destroy_org_with_migrated_keys(self) -> None:
        self.org.owner = self.admin
        self.org.save(update_fields=["owner"])
        issued = issue_token(self.org, self.admin, "Migrated")
        connection = issued.token.connection
        OrgApiConnection.objects.filter(pk=connection.pk).update(
            legacy_backfilled=True, legacy_multi_credential=True
        )
        OrgApiToken.objects.filter(pk=issued.token.pk).update(legacy_credential=True)
        OrgApiToken.objects.create(
            organization=self.org,
            user=self.admin,
            connection=connection,
            legacy_credential=True,
            prefix="revoked",
            secret_hash="0" * 64,
            revoked_at=connection.created_at,
        )
        self.client.delete(f"{self.url}{connection.pk}/")
        response = self.client.delete(f"/api/organizations/{self.org.pk}/")
        self.assertEqual(response.status_code, 204, response.data)
        self.assertFalse(
            OrgApiToken.objects.filter(organization_id=self.org.pk).exists()
        )

    def test_malformed_patch_is_400_not_server_error(self) -> None:
        row = self.create()
        for body in ([1], "text", None):
            response = self.client.patch(
                f"{self.url}{row['id']}/", body, content_type="application/json"
            )
            self.assertEqual(response.status_code, 400)

    def test_connection_usage_is_opt_in_and_aggregates_rotated_keys(self) -> None:
        issued = issue_token(self.org, self.admin, "Usage")
        self.bearer(issued.raw).get(self.sync_url())
        url = f"/api/organizations/{self.org.pk}/api-tokens/usage/"
        self.assertNotIn("connections", self.client.get(url).data)
        response = self.client.get(url, {"by_connection": "true"})
        self.assertEqual(
            response.data["connections"][0]["connection_id"], issued.token.connection_id
        )
        self.assertEqual(response.data["connections"][0]["requests"], 1)

    def test_manual_and_test_share_minute_budget_and_daily_test_cap(self) -> None:
        now = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
        with patch("org.api_connections.views.timezone.now", return_value=now) as clock:
            for _ in range(4):
                check_action_budget(self.org.pk, self.admin.pk, kind="manual")
            check_action_budget(self.org.pk, self.admin2.pk, kind="test")
            with self.assertRaises(ConnectionRateLimited):
                check_action_budget(self.org.pk, self.admin2.pk, kind="test")
            for minute in range(1, 100):
                clock.return_value = now + timedelta(minutes=minute)
                check_action_budget(self.org.pk, self.admin.pk, kind="test")
            clock.return_value = now + timedelta(minutes=101)
            with self.assertRaises(ConnectionRateLimited):
                check_action_budget(self.org.pk, self.admin.pk, kind="test")

    def test_enabled_flag_audits_authority_change(self) -> None:
        row = self.create()
        url = f"{self.url}{row['id']}/"
        for version, enabled in ((1, True), (2, False)):
            response = self.client.patch(
                url, {"config_version": version, "enabled": enabled}, format="json"
            )
            self.assertEqual(response.status_code, 200, response.data)
        actions = set(
            OrgLog.objects.filter(organization=self.org).values_list(
                "action", flat=True
            )
        )
        self.assertIn("enable_api_connection", actions)
        self.assertIn("disable_api_connection", actions)

    def test_administrative_budget_is_org_scoped(self) -> None:
        for index in range(30):
            self.create(name=f"Connection {index}")
        self.client.force_authenticate(self.admin2)
        response = self.client.post(self.url, {"name": "Limited"}, format="json")
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.data["code"], "rate_limited")

    def test_exhausted_budget_allows_only_fail_safe_actions(self) -> None:
        issued = issue_token(self.org, self.admin, "Emergency")
        url = f"{self.url}{issued.token.connection_id}/"
        for _ in range(30):
            check_action_budget(self.org.pk, self.admin.pk)
        self.client.force_authenticate(self.admin2)
        for action in ("issue-key", "rotate-key"):
            self.assertEqual(
                self.client.post(f"{url}{action}/", {}, format="json").status_code, 429
            )
        self.assertEqual(
            self.client.patch(
                url, {"config_version": 1, "enabled": True}, format="json"
            ).status_code,
            429,
        )
        self.assertEqual(
            self.client.patch(
                url,
                {"config_version": 1, "enabled": False, "name": "Other"},
                format="json",
            ).status_code,
            429,
        )
        response = self.client.patch(
            url,
            {"config_version": 1, "enabled": False, "inbound_enabled": False},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(
            self.client.post(f"{url}revoke-key/", {}, format="json").status_code, 200
        )
        self.assertEqual(self.client.delete(url).status_code, 200)

    def test_list_credentials_query_count_is_constant(self) -> None:
        issue_token(self.org, self.admin, "First")
        with self.assertNumQueries(4):
            response = self.client.get(self.url)
        for i in range(4):
            issue_token(self.org, self.admin, f"Other {i}")
        with self.assertNumQueries(4):
            response = self.client.get(self.url)
        self.assertEqual(len(response.data), 5)
        self.assertEqual(len(response.data[0]["inbound_credentials"]), 1)

    def test_legacy_multi_key_http_confirmation_names_exact_new_grants(self) -> None:
        for action in ("issue", "rotate"):
            with self.subTest(action=action):
                issued = issue_token(
                    self.org, self.admin, action, operations=["mmr:read"]
                )
                current = issued.token.connection
                OrgApiConnection.objects.filter(pk=current.pk).update(
                    legacy_multi_credential=True,
                    operations=["mmr:read", "mmr:write"],
                )
                OrgApiToken.objects.filter(pk=issued.token.pk).update(
                    legacy_credential=True
                )
                other = OrgApiToken.objects.create(
                    organization=self.org,
                    connection=current,
                    user=self.admin2,
                    legacy_credential=True,
                    prefix=f"legacy-{action}",
                    secret_hash="0" * 64,
                    operations=["mmr:write"],
                )
                url = f"{self.url}{current.pk}/{action}-key/"
                for body in ({}, {"confirmed_operations": ["mmr:read"]}):
                    denied = self.client.post(url, body, format="json")
                    self.assertEqual(denied.status_code, 409, denied.data)
                    self.assertEqual(denied.data["code"], "grant_confirmation_required")
                    self.assertEqual(
                        denied.data["operations"], ["mmr:read", "mmr:write"]
                    )
                    self.assertEqual(
                        current.tokens.filter(revoked_at__isnull=True).count(), 2
                    )
                response = self.client.post(
                    url,
                    {"confirmed_operations": ["mmr:read", "mmr:write"]},
                    format="json",
                )
                self.assertEqual(response.status_code, 201, response.data)
                self.assertEqual(response["Cache-Control"], "no-store")
                token = OrgApiToken.objects.get(pk=response.data["credential"]["id"])
                self.assertEqual(token.operations, ["mmr:read", "mmr:write"])
                self.assertEqual(
                    current.tokens.filter(revoked_at__isnull=True).count(), 1
                )
                other.refresh_from_db()
                self.assertIsNotNone(other.revoked_at)

    def test_credential_order_is_stable_on_list_and_detail(self) -> None:
        issued = issue_token(self.org, self.admin, "Order")
        current = issued.token.connection
        rotated, _ = issue_connection_key(current, actor=self.admin2, rotate=True)
        expected = [issued.token.pk, rotated.pk]
        detail = self.client.get(f"{self.url}{current.pk}/")
        listed = self.client.get(self.url)
        self.assertEqual(
            [row["id"] for row in detail.data["inbound_credentials"]], expected
        )
        self.assertEqual(
            [row["id"] for row in listed.data[0]["inbound_credentials"]], expected
        )
