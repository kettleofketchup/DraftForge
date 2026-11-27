import json

from django.contrib import admin
from django.test import RequestFactory, override_settings
from rest_framework.exceptions import PermissionDenied

from app.models import CustomUser
from events.tests.actors import SYSTEM
from org.api_connections.authority import assert_connection_authority
from org.api_connections.config import apply_config_patch
from org.api_connections.lifecycle import (
    handle_credential_owner_loss,
    issue_connection_key,
)
from org.api_connections.schemas import ConnectionConfigError
from org.api_tokens.tokens import issue_token
from org.models import OrgApiConnection, OrgApiSyncRun, OrgApiToken, OrgLog
from org.tests.test_api_connections_crypto import OLD_KEY
from org.tests.test_api_tokens import ApiTokenBase
from org.views import ClaimRequestViewSet
from user.discord_accounts import merge_discord_accounts


class ConnectionLifecycleTests(ApiTokenBase):
    def test_legacy_multi_key_rotation_revokes_all(self) -> None:
        old = issue_token(self.org, self.admin, "Legacy")
        connection = old.token.connection
        OrgApiConnection.objects.filter(pk=connection.pk).update(
            legacy_multi_credential=True
        )
        OrgApiToken.objects.filter(pk=old.token.pk).update(legacy_credential=True)
        other = OrgApiToken.objects.create(
            organization=self.org,
            connection=connection,
            user=self.admin2,
            legacy_credential=True,
            prefix="other",
            secret_hash="0" * 64,
            operations=["mmr:read"],
        )
        connection.refresh_from_db()
        token, raw = issue_connection_key(connection, actor=self.admin2, rotate=True)
        self.assertEqual(token.connection_id, connection.pk)
        self.assertEqual(token.user, self.admin2)
        self.assertEqual(self.bearer(old.raw).get(self.sync_url()).status_code, 401)
        other.refresh_from_db()
        self.assertIsNotNone(other.revoked_at)
        self.assertEqual(self.bearer(raw).get(self.sync_url()).status_code, 200)
        connection.refresh_from_db()
        self.assertFalse(connection.legacy_multi_credential)

    def test_delete_and_merge_scrub_authority(self) -> None:
        for mode in ("delete", "merge"):
            with self.subTest(mode=mode):
                owner = CustomUser.objects.create_user(username=f"owner-{mode}")
                keeper = CustomUser.objects.create_user(username=f"keeper-{mode}")
                self.org.admins.add(owner, keeper)
                issued = issue_token(self.org, owner, mode)
                connection = issued.token.connection
                OrgApiConnection.objects.filter(pk=connection.pk).update(
                    outbound_auth="bearer",
                    outbound_credential_ciphertext="synthetic-ciphertext",
                    outbound_credential_owner=owner,
                    mmr_push_enabled=True,
                )
                if mode == "merge":
                    merge_discord_accounts(keeper, owner)
                else:
                    request = RequestFactory().delete("/admin/")
                    request.user = self.site_admin
                    admin.site._registry[CustomUser].delete_model(request, owner)
                connection.refresh_from_db()
                self.assertEqual(connection.outbound_credential_ciphertext, "")
                self.assertIsNone(connection.outbound_credential_owner_id)
                self.assertFalse(connection.mmr_push_enabled)
                self.assertEqual(
                    self.bearer(issued.raw).get(self.sync_url()).status_code, 401
                )
                self.assertTrue(
                    OrgLog.objects.filter(
                        action="api_connection_owner_lost",
                        details__connection_id=connection.pk,
                    ).exists()
                )

    def test_auth_none_authorizer_lifecycle(self) -> None:
        connection = OrgApiConnection.objects.create(
            organization=self.org, name="No auth"
        )
        connection = apply_config_patch(
            connection,
            actor=self.admin,
            patch={
                "outbound_base_url": "https://ratings.example",
                "mmr_push_enabled": True,
            },
            expected_version=1,
        )
        self.assertEqual(connection.outbound_authorizer, self.admin)
        self.assertEqual(connection.outbound_credential_ciphertext, "")
        assert_connection_authority(
            connection, direction="mmr_push", testing=True, requester=self.admin
        )
        self.org.admins.remove(self.admin)
        with self.assertRaises(PermissionDenied):
            assert_connection_authority(
                connection, direction="mmr_push", testing=True, requester=self.admin2
            )
        connection.refresh_from_db()
        self.assertIsNone(connection.outbound_authorizer_id)
        self.assertFalse(connection.mmr_push_enabled)

    def test_owner_loss_does_not_transfer_auth_none_authorizer(self) -> None:
        connection = OrgApiConnection.objects.create(
            organization=self.org,
            name="No auth",
            outbound_authorizer=self.admin,
            mmr_pull_enabled=True,
        )
        handle_credential_owner_loss(self.admin)
        connection.refresh_from_db()
        self.assertIsNone(connection.outbound_authorizer_id)
        self.assertFalse(connection.mmr_pull_enabled)
        self.assertEqual(connection.last_error_code, "authority_lost")

    def test_role_loss_does_not_scrub_other_org_authority(self) -> None:
        self.other_org.admins.add(self.admin)
        other = OrgApiConnection.objects.create(
            organization=self.other_org,
            name="Other",
            outbound_authorizer=self.admin,
            mmr_pull_enabled=True,
        )
        connection = OrgApiConnection.objects.create(
            organization=self.org,
            name="Lost",
            outbound_authorizer=self.admin,
            mmr_pull_enabled=True,
        )
        self.org.admins.remove(self.admin)
        with self.assertRaises(PermissionDenied):
            assert_connection_authority(
                connection, direction="mmr_pull", testing=True, requester=self.admin2
            )
        other.refresh_from_db()
        self.assertEqual(other.outbound_authorizer_id, self.admin.pk)
        self.assertTrue(other.mmr_pull_enabled)

    @override_settings(ORG_API_CREDENTIAL_KEYS=json.dumps([OLD_KEY]))
    def test_auth_mode_switch_requires_new_credential_and_never_retains_authorizer(
        self,
    ) -> None:
        connection = OrgApiConnection.objects.create(
            organization=self.org,
            name="No auth",
            outbound_base_url="https://ratings.example",
            outbound_authorizer=self.admin,
            mmr_pull_enabled=True,
        )
        with self.assertRaises(ConnectionConfigError):
            apply_config_patch(
                connection,
                actor=self.admin2,
                patch={"outbound_auth": "bearer"},
                expected_version=1,
            )
        connection = apply_config_patch(
            connection,
            actor=self.admin2,
            patch={
                "outbound_auth": "bearer",
                "outbound_credential": "synthetic-secret",
            },
            expected_version=1,
        )
        self.assertIsNone(connection.outbound_authorizer_id)
        self.assertEqual(connection.outbound_credential_owner_id, self.admin2.pk)
        connection = apply_config_patch(
            connection,
            actor=self.admin,
            patch={"outbound_auth": "none"},
            expected_version=2,
        )
        self.assertEqual(connection.outbound_authorizer_id, self.admin.pk)
        self.assertIsNone(connection.outbound_credential_owner_id)
        self.assertEqual(connection.outbound_credential_ciphertext, "")

    def test_claim_repoint_and_auth_none_merge_leave_no_live_authority(self) -> None:
        for mode in ("claim", "discord"):
            with self.subTest(mode=mode):
                owner = CustomUser.objects.create_user(username=f"dropped-{mode}")
                keeper = CustomUser.objects.create_user(username=f"kept-{mode}")
                self.org.admins.add(owner, keeper)
                issued = issue_token(self.org, owner, "Dropped")
                connection = issued.token.connection
                OrgApiConnection.objects.filter(pk=connection.pk).update(
                    outbound_authorizer=owner, mmr_pull_enabled=True
                )
                if mode == "claim":
                    ClaimRequestViewSet()._merge_profiles(keeper, owner, actor=SYSTEM)
                else:
                    merge_discord_accounts(keeper, owner)
                connection.refresh_from_db()
                self.assertIsNone(connection.outbound_authorizer_id)
                self.assertFalse(connection.mmr_pull_enabled)
                self.assertEqual(
                    self.bearer(issued.raw).get(self.sync_url()).status_code, 401
                )

    def test_api_delete_and_admin_bulk_delete_scrub_outbound(self) -> None:
        for mode in ("api", "admin_bulk"):
            with self.subTest(mode=mode):
                owner = CustomUser.objects.create_user(username=f"delete-{mode}")
                self.org.admins.add(owner)
                connection = OrgApiConnection.objects.create(
                    organization=self.org,
                    name="Delete",
                    outbound_authorizer=owner,
                    mmr_pull_enabled=True,
                )
                if mode == "api":
                    self.client.force_authenticate(self.site_admin)
                    response = self.client.delete(f"/api/users/{owner.pk}/")
                    self.assertEqual(response.status_code, 204, response.data)
                else:
                    request = RequestFactory().delete("/admin/")
                    request.user = self.site_admin
                    admin.site._registry[CustomUser].delete_queryset(
                        request, CustomUser.objects.filter(pk=owner.pk)
                    )
                connection.refresh_from_db()
                self.assertFalse(connection.mmr_pull_enabled)
                self.assertIsNone(connection.outbound_authorizer_id)
                self.assertTrue(
                    OrgLog.objects.filter(
                        action="api_connection_owner_lost",
                        details__connection_id=connection.pk,
                    ).exists()
                )

    def test_owner_loss_revokes_nullable_legacy_credentials_before_repoint(
        self,
    ) -> None:
        issued = issue_token(self.org, self.admin, "Nullable legacy")
        OrgApiToken.objects.filter(pk=issued.token.pk).update(connection=None)
        handle_credential_owner_loss(self.admin)
        OrgApiToken.objects.filter(pk=issued.token.pk).update(user=self.admin2)
        self.assertEqual(self.bearer(issued.raw).get(self.sync_url()).status_code, 401)

    def test_inbound_lifecycle_does_not_fence_independent_outbound_work(self) -> None:
        for action in ("rotate", "revoke", "owner_loss"):
            with self.subTest(action=action):
                issued = issue_token(self.org, self.admin, action)
                connection = issued.token.connection
                OrgApiConnection.objects.filter(pk=connection.pk).update(
                    outbound_authorizer=self.admin2, mmr_pull_enabled=True
                )
                run = OrgApiSyncRun.objects.create(
                    organization=self.org,
                    connection=connection,
                    kind="mmr_pull",
                    config_version=connection.config_version,
                )
                if action == "rotate":
                    issue_connection_key(connection, actor=self.admin2, rotate=True)
                elif action == "revoke":
                    self.client.force_authenticate(self.admin2)
                    response = self.client.post(
                        f"/api/organizations/{self.org.pk}/api-connections/{connection.pk}/revoke-key/",
                        {},
                        format="json",
                    )
                    self.assertEqual(response.status_code, 200, response.data)
                else:
                    handle_credential_owner_loss(self.admin)
                connection.refresh_from_db()
                run.refresh_from_db()
                self.assertEqual(run.state, "queued")
                self.assertEqual(connection.config_version, run.config_version)
                self.assertEqual(connection.outbound_authorizer_id, self.admin2.pk)
                self.assertTrue(connection.mmr_pull_enabled)

    def test_repeated_owner_loss_is_idempotent(self) -> None:
        issued = issue_token(self.org, self.admin, "Key")
        handle_credential_owner_loss(self.admin)
        count = OrgLog.objects.filter(action="api_connection_owner_lost").count()
        handle_credential_owner_loss(self.admin)
        self.assertEqual(
            OrgLog.objects.filter(action="api_connection_owner_lost").count(), count
        )
        issued.token.refresh_from_db()
        self.assertIsNotNone(issued.token.revoked_at)
