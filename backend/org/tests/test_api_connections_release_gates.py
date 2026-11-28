import json
import unittest
from datetime import timedelta
from pathlib import Path
from typing import Any
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from org.api_connections.orchestration import claim_work
from org.api_connections.push import step_mmr_delivery
from org.models import (
    OrgApiConnection,
    OrgApiMmrDelivery,
    OrgApiSyncRun,
    OrgApiToken,
    OrgLog,
    OrgMmrSyncState,
)
from org.tests.test_api_connections_crypto import OLD_KEY
from org.tests.test_api_connections_push import (
    ORIGIN,
    SECRET,
    FakeRemote,
    PushBase,
    echo_ack,
)
from org.tests.test_api_connections_wire import WIRE_FIXTURE

BACKEND_DIR = Path(__file__).resolve().parents[2]
REPO_DIR = BACKEND_DIR.parent
TOKEN = "release-gate-internal-token"
KEY_RING_SETTING = "ORG_API_CREDENTIAL_KEYS"

# Evidence owned by earlier tasks; release verification selects these modules.
EVIDENCE_TESTS: tuple[str, ...] = (
    "org.tests.test_api_connections_safe_http.SafeHttpTests."
    "test_rebinding_never_redials_hostname",
    "org.tests.test_api_connections_safe_http.SafeHttpTests."
    "test_real_tcp_socket_retains_numeric_dial_and_original_tls_name",
    "org.tests.test_api_connections_safe_http.SafeHttpTests."
    "test_tls_sni_host_and_certificate_use_original_hostname",
    "org.tests.test_api_connections_safe_http.SafeHttpTests."
    "test_connected_peer_must_match_validated_set",
    "org.tests.test_api_connections_safe_http.SafeHttpTests."
    "test_redirect_proxy_cookie_netrc_forbidden",
    "org.tests.test_api_connections_safe_http.SafeHttpTests."
    "test_decompression_bomb_stops_at_cap",
    "org.tests.test_api_connections_safe_http.SafeHttpTests."
    "test_dns_and_slow_stream_share_absolute_deadline",
    "org.tests.test_api_connections_promotion_push.EchoReconciliationTests."
    "test_echo_before_ack_settles_once",
    "org.tests.test_api_connections_promotion_push.EchoReconciliationTests."
    "test_ack_before_echo_settles_once",
    "org.tests.test_promotion_sync_races.EchoAckRaceTests."
    "test_import_holding_locks_then_ack_reclassifies",
    "org.tests.test_promotion_sync_races.EchoAckRaceTests."
    "test_ack_holding_locks_then_import_sees_echo",
    "org.tests.test_api_connections_races.ConnectionKeyRaceTests."
    "test_concurrent_issue_rotate_single_usable_credential",
    "org.tests.test_api_connections_races.PullRunRaceTests."
    "test_concurrent_create_pull_run_returns_same_active_run",
    "org.tests.test_api_connections_races.PromotionStreamRaceTests."
    "test_concurrent_promotion_stream_adoption_single_authority",
)


def _keys(value: Any) -> set[str]:
    if isinstance(value, dict):
        return set(value) | {key for child in value.values() for key in _keys(child)}
    if isinstance(value, list):
        return {key for child in value for key in _keys(child)}
    return set()


class ReleaseGateTests(PushBase):
    def setUp(self) -> None:
        super().setUp()
        self.session = APIClient()
        self.session.force_authenticate(self.admin)
        self.base = f"/api/organizations/{self.org.pk}/api-connections/"

    def test_outbound_disabled_without_encryption_and_legacy_auth_still_works(
        self,
    ) -> None:
        self.write(4100)
        delivery = self.latest()
        with override_settings(ORG_API_CREDENTIAL_KEYS=""):
            created = self.session.post(
                self.base,
                {
                    "name": "No ring",
                    "outbound_base_url": ORIGIN,
                    "outbound_auth": "bearer",
                    "outbound_credential": "replacement-secret",
                },
                format="json",
            )
            self.assertEqual(created.status_code, 400, created.data)
            self.assertEqual(created.data["code"], "credential_keys_unavailable")
            self.assertFalse(OrgApiConnection.objects.filter(name="No ring").exists())

            remote = FakeRemote([(200, echo_ack())])
            _, delivery = self.step(delivery, remote)
            self.assertEqual(delivery.state, "paused")
            self.assertEqual(delivery.last_reason, "credential_keys_unavailable")
            self.assertEqual(remote.requests, [])

            legacy = self.session.post(
                f"/api/organizations/{self.org.pk}/api-tokens/",
                {"name": "Legacy"},
                format="json",
            )
            self.assertEqual(legacy.status_code, 201, legacy.data)
            raw = legacy.data["token"]
            read = self.bearer(raw).get(self.sync_url(), {"game_type": 1})
            self.assertEqual(read.status_code, 200, read.data)
            pushed = self.bearer(raw).post(
                self.sync_url(),
                {
                    "game_type": 1,
                    "mark_verified": False,
                    "entries": [{"steam_id": 1002, "mmr": 3300}],
                },
                format="json",
            )
            self.assertEqual(pushed.status_code, 200, pushed.data)
            self.assertEqual(pushed.data["updated"], 1)

    def test_public_redacted_contract_matches_frontend_fixture(self) -> None:
        ciphertext = self.connection.outbound_credential_ciphertext
        self.assertTrue(ciphertext)
        granted = self.session.patch(
            f"{self.base}{self.connection.pk}/",
            {
                "operations": ["mmr:read"],
                "inbound_enabled": True,
                "config_version": self.connection.config_version,
            },
            format="json",
        )
        self.assertEqual(granted.status_code, 200, granted.data)
        issued = self.session.post(
            f"{self.base}{self.connection.pk}/issue-key/", {}, format="json"
        )
        self.assertEqual(issued.status_code, 201, issued.data)
        self.assertEqual(issued["Cache-Control"], "no-store")
        raw = issued.json()["credential"]["token"]
        token = OrgApiToken.objects.get(connection=self.connection)
        listed = self.session.get(self.base)
        self.assertEqual(listed.status_code, 200)
        detail = self.session.get(f"{self.base}{self.connection.pk}/")
        wire = json.loads(WIRE_FIXTURE.read_text(encoding="utf-8"))
        [row] = listed.json()
        self.assertTrue(row["credential_present"])
        self.assertEqual(set(row), set(wire["connections"][0]))
        self.assertEqual(set(detail.json()), set(row))
        forbidden = {
            "outbound_credential",
            "outbound_credential_ciphertext",
            "outbound_credential_key_id",
            "secret_hash",
            "secret",
        }
        for label, body in (("list", listed.json()), ("detail", detail.json())):
            with self.subTest(label=label):
                text = json.dumps(body)
                self.assertFalse(_keys(body) & forbidden)
                self.assertNotIn(SECRET, text)
                self.assertNotIn(ciphertext, text)
                self.assertNotIn(raw, text)
                self.assertNotIn(token.secret_hash, text)
        self.assertEqual(set(issued.json()), set(wire["issue_key_response"]))
        self.assertFalse(_keys(wire) & forbidden)

    @override_settings(INTERNAL_SERVICE_TOKEN=TOKEN)
    def test_light_worker_modules_and_task_payloads_never_carry_key_ring(
        self,
    ) -> None:
        celery_settings = (BACKEND_DIR / "config" / "settings_celery.py").read_text()
        self.assertNotIn(KEY_RING_SETTING, celery_settings)
        for relative in (
            "config/tasks_org_api_sync.py",
            "app/internal_client/org_api_sync.py",
        ):
            with self.subTest(module=relative):
                source = (BACKEND_DIR / relative).read_text()
                for needle in (KEY_RING_SETTING, "api_connections.crypto", "secret"):
                    self.assertNotIn(needle, source)
        self.write(4300)
        claimed = APIClient().post(
            "/api/internal/org-api-sync/claim/",
            {"limit": 5},
            format="json",
            HTTP_X_INTERNAL_TOKEN=TOKEN,
        )
        self.assertEqual(claimed.status_code, 200, claimed.data)
        self.assertEqual(set(claimed.data), {"claims", "promotion_due"})
        [claim] = claimed.data["claims"]
        self.assertEqual(set(claim), {"kind", "id", "fence"})
        remote = FakeRemote([(200, echo_ack())])
        with patch("org.api_connections.push.request_json", side_effect=remote):
            stepped = APIClient().post(
                f"/api/internal/org-api-sync/deliveries/{claim['id']}/step/",
                {"fence": claim["fence"]},
                format="json",
                HTTP_X_INTERNAL_TOKEN=TOKEN,
            )
        self.assertEqual(stepped.status_code, 200, stepped.data)
        self.assertEqual(stepped.data["state"], "applied")
        self.assertEqual(remote.requests[0].credential, SECRET)
        key = OLD_KEY["key"]
        for response in (claimed, stepped):
            text = json.dumps(response.data)
            self.assertNotIn(SECRET, text)
            self.assertNotIn(key, text)
            self.assertNotIn(self.connection.outbound_credential_ciphertext, text)

    def test_rollback_disables_new_work_without_erasing_history(self) -> None:
        past = timezone.now() - timedelta(minutes=1)
        OrgApiConnection.objects.filter(pk=self.connection.pk).update(
            mmr_pull_enabled=True, interval_minutes=15, next_due_at=past
        )
        control = OrgApiConnection.objects.create(
            organization=self.org,
            name="Control",
            enabled=True,
            mmr_pull_enabled=True,
            outbound_base_url=ORIGIN,
            outbound_auth="bearer",
            outbound_credential_owner=self.admin,
            game_type=self.connection.game_type,
            interval_minutes=15,
            next_due_at=past,
        )
        self.seal(control, "control-secret", ORIGIN)
        self.write(4500)
        sent = self.latest()
        self.step(sent, FakeRemote([(200, echo_ack())]))
        self.write(4600)
        pending = self.latest()
        history = OrgApiSyncRun.objects.create(
            organization=self.org,
            connection=self.connection,
            kind=OrgApiSyncRun.Kind.MMR_PULL,
            state=OrgApiSyncRun.State.SUCCEEDED,
            updated_count=3,
            finished_at=timezone.now(),
        )
        self.connection.refresh_from_db()
        ciphertext = self.connection.outbound_credential_ciphertext

        with override_settings(ORG_API_SCHEDULED_PULLS=False):
            claims = claim_work(now=timezone.now())
        [leased] = [c for c in claims if c.run_id == pending.delivery_id]
        self.assertFalse(
            OrgApiSyncRun.objects.exclude(pk=history.pk)
            .filter(kind=OrgApiSyncRun.Kind.MMR_PULL)
            .exists()
        )

        disabled = self.session.patch(
            f"{self.base}{self.connection.pk}/",
            {"enabled": False, "config_version": self.connection.config_version},
            format="json",
        )
        self.assertEqual(disabled.status_code, 200, disabled.data)
        self.assertTrue(disabled.data["credential_present"])
        self.assertNotIn(ciphertext, json.dumps(disabled.json()))

        with override_settings(ORG_API_SCHEDULED_PULLS=True):
            claim_work(now=timezone.now())
        pulls = OrgApiSyncRun.objects.exclude(pk=history.pk).filter(
            kind=OrgApiSyncRun.Kind.MMR_PULL
        )
        self.assertEqual(
            list(pulls.values_list("connection_id", flat=True)), [control.pk]
        )

        remote = FakeRemote([(200, echo_ack())])
        with patch("org.api_connections.push.request_json", side_effect=remote):
            step_mmr_delivery(pending.delivery_id, fence=leased.fence)
        pending.refresh_from_db()
        self.assertEqual(remote.requests, [])
        self.assertEqual(pending.state, "paused")
        self.assertEqual(pending.last_reason, "configuration_changed")

        self.connection.refresh_from_db()
        self.assertFalse(self.connection.enabled)
        self.assertTrue(self.connection.mmr_push_enabled)
        self.assertEqual(self.connection.outbound_credential_ciphertext, ciphertext)
        self.assertEqual(self.connection.outbound_credential_owner, self.admin)
        history.refresh_from_db()
        self.assertEqual(history.state, OrgApiSyncRun.State.SUCCEEDED)
        sent.refresh_from_db()
        self.assertEqual(sent.state, OrgApiMmrDelivery.State.APPLIED)
        self.assertTrue(OrgMmrSyncState.objects.filter(org_user=self.ou_alice).exists())
        self.assertTrue(
            OrgLog.objects.filter(
                organization=self.org,
                action="disable_api_connection",
                details__connection_id=self.connection.pk,
            ).exists()
        )


class ReleaseEvidenceTests(SimpleTestCase):
    def test_release_evidence_tests_exist(self) -> None:
        loader = unittest.TestLoader()
        for name in EVIDENCE_TESTS:
            with self.subTest(test=name):
                suite = loader.loadTestsFromName(name)
                [case] = list(suite)
                self.assertEqual(case.id(), name)
