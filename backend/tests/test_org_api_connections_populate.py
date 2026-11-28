"""Regression tests for the org API connections E2E data, fake transport and test endpoints."""

import time
from typing import Any

from django.contrib.sessions.backends.db import SessionStore
from django.test import TestCase, override_settings
from rest_framework.test import APIClient, APIRequestFactory

from app.models import CustomUser
from common.game import GameType
from org.api_connections import orchestration, pull, push
from org.api_connections.runs import COUNTERS
from org.api_connections.tls_adapter import SafeHttpError
from org.api_connections.types import SafeHttpRequest
from org.mmr import set_org_mmr
from org.models import (
    OrgApiConnection,
    OrgApiLimits,
    OrgApiMmrDelivery,
    OrgApiPromotionAdoption,
    OrgApiSyncRun,
    OrgApiToken,
    OrgApiTokenUsage,
    OrgMmrSyncState,
    OrgUser,
    OrgUserGameMmr,
)
from org.models_promotion_sync import PromotionContactOutbox
from tests.data.org_api_connections import (
    AC_ADMIN,
    AC_PLAYER_ONE,
    AC_PLAYER_TWO,
    API_CONNECTIONS_ORG,
    API_CONNECTIONS_ROLE_USERS,
    API_CONNECTIONS_SECOND_ORG,
    FAKE_BAD_CREDENTIAL,
    FAKE_GOOD_CREDENTIAL,
    FAKE_ORIGIN,
    FAKE_PULL_PATH,
    SEEDED_CONNECTION_NAME,
)
from tests.helpers.org_api_connections_transport import (
    FakeTransportUnavailable,
    drive_connection_work,
    fake_calls,
    fake_transport_installed,
    install_fake_transport,
    uninstall_fake_transport,
)
from tests.populate.org_api_connections import (
    populate_org_api_connections_data,
    reset_org_api_connections_data,
    seed_promotion_backlog,
)
from tests.test_org_api_connections import (
    drive_org_api_connections,
    login_org_api_connections,
    org_api_connections_state,
    reset_org_api_connections,
    seed_org_api_promotion_backlog,
)

MAIN = API_CONNECTIONS_ORG.pk
SECOND = API_CONNECTIONS_SECOND_ORG.pk
PULL_CONFIG: dict[str, Any] = {
    "path": FAKE_PULL_PATH,
    "mapping": {
        "list_path": "players",
        "player_id_path": "steam_id",
        "mmr_path": "mmr",
    },
}


def _mmr(user_pk: int) -> int:
    return (
        OrgUserGameMmr.objects.nocache()
        .filter(
            org_user__organization_id=MAIN,
            org_user__user_id=user_pk,
            game_type=GameType.DOTA2,
        )
        .values_list("mmr", flat=True)
        .first()
        or 0
    )


@override_settings(DEBUG=True, ORG_API_CREDENTIAL_KEYS="")
class OrgApiConnectionsDataTest(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        populate_org_api_connections_data(force=True)

    def setUp(self) -> None:
        install_fake_transport()
        self.addCleanup(uninstall_fake_transport)
        self.admin = CustomUser.objects.get(pk=AC_ADMIN.pk)
        self.client = APIClient()
        self.client.force_authenticate(self.admin)
        self.url = f"/api/organizations/{MAIN}/api-connections/"

    def create(self, **fields: Any) -> dict[str, Any]:
        response = self.client.post(self.url, fields, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        return response.data

    def patch(self, row: dict[str, Any], **fields: Any) -> dict[str, Any]:
        response = self.client.patch(
            f"{self.url}{row['id']}/",
            {"config_version": row["config_version"], **fields},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        return response.data

    def _populate_every_ledger(self) -> None:
        inbound = self.create(
            name="Inbound", enabled=True, inbound_enabled=True, operations=["mmr:write"]
        )
        url = f"{self.url}{inbound['id']}/"
        self.assertEqual(
            self.client.post(f"{url}issue-key/", {}, format="json").status_code, 201
        )
        rotated = self.client.post(f"{url}rotate-key/", {}, format="json")
        self.assertEqual(rotated.status_code, 201)
        token = OrgApiToken.objects.get(pk=rotated.data["credential"]["id"])
        OrgApiTokenUsage.objects.create(
            token=token,
            organization_id=MAIN,
            user=self.admin,
            date=token.created_at.date(),
            request_count=3,
        )
        OrgApiLimits.objects.create(organization_id=MAIN, per_minute=5, per_day=10)
        self.assertEqual(
            OrgApiToken.objects.filter(connection_id=inbound["id"]).count(), 2
        )
        self.assertTrue(
            OrgApiToken.objects.filter(
                connection_id=inbound["id"], revoked_at__isnull=False
            ).exists()
        )

        outbound = self.create(
            name="Outbound",
            enabled=True,
            mmr_pull_enabled=True,
            mmr_push_enabled=True,
            outbound_base_url=FAKE_ORIGIN,
            outbound_auth="bearer",
            outbound_credential=FAKE_GOOD_CREDENTIAL,
            overwrite_policy="replace",
            mmr_pull_config=PULL_CONFIG,
        )
        pulled = self.client.post(
            f"{self.url}{outbound['id']}/pull/", {}, format="json"
        )
        self.assertEqual(pulled.status_code, 202, pulled.data)
        driven = drive_connection_work(
            [MAIN], edit_after_stage=(AC_PLAYER_ONE.pk, 3333)
        )
        run = OrgApiSyncRun.objects.get(pk=pulled.data["id"])
        self.assertEqual(run.state, "succeeded", driven)
        self.assertEqual(
            (run.updated_count, run.unmatched_count, run.conflict_count), (1, 1, 1)
        )
        self.assertEqual(_mmr(AC_PLAYER_ONE.pk), 3333)
        self.assertEqual(_mmr(AC_PLAYER_TWO.pk), 2500)
        # The conflicting edit is pushed; the pulled value is not echoed back.
        self.assertEqual(
            list(
                OrgApiMmrDelivery.objects.filter(
                    connection_id=outbound["id"]
                ).values_list("state", flat=True)
            ),
            ["applied"],
        )
        pushes = [c for c in fake_calls() if c["method"] == "POST"]
        self.assertEqual([c["mmrs"] for c in pushes], [[3333]])
        seed_promotion_backlog(self.admin)
        self.assertTrue(
            OrgMmrSyncState.objects.filter(org_user__organization_id=MAIN).exists()
        )

    def test_populate_reset_twice_is_idempotent_and_fk_safe(self) -> None:
        self._populate_every_ledger()
        for _ in range(2):
            reset_org_api_connections_data()
            # Every reset keeps the Steam links; none flips to unlinked.
            self.assertEqual(
                dict(
                    CustomUser.objects.filter(
                        pk__in=[AC_PLAYER_ONE.pk, AC_PLAYER_TWO.pk]
                    ).values_list("pk", "steam_account_id")
                ),
                {AC_PLAYER_ONE.pk: 830_304, AC_PLAYER_TWO.pk: 830_305},
            )

        self.assertFalse(OrgApiConnection.objects.filter(organization_id=MAIN).exists())
        for model in (OrgApiToken, OrgApiTokenUsage, OrgApiLimits):
            self.assertFalse(
                model.objects.filter(organization_id__in=[MAIN, SECOND]).exists(), model
            )
        self.assertFalse(OrgApiSyncRun.objects.filter(organization_id=MAIN).exists())
        self.assertFalse(
            OrgApiMmrDelivery.objects.filter(connection__organization_id=MAIN).exists()
        )
        self.assertFalse(
            PromotionContactOutbox.objects.filter(organization_id=MAIN).exists()
        )
        self.assertFalse(
            OrgApiPromotionAdoption.objects.filter(organization_id=MAIN).exists()
        )
        self.assertEqual(_mmr(AC_PLAYER_ONE.pk), 3000)
        self.assertEqual(_mmr(AC_PLAYER_TWO.pk), 0)
        self.assertEqual(
            set(
                OrgUser.objects.nocache()
                .filter(organization_id=MAIN)
                .values_list("user_id", flat=True)
            ),
            set(range(8300, 8307)),
        )
        seeded = OrgApiConnection.objects.get(organization_id=SECOND)
        self.assertEqual(seeded.name, SEEDED_CONNECTION_NAME)
        self.assertFalse(seeded.enabled or seeded.inbound_enabled)
        self.assertEqual(seeded.runs.get().unmatched_count, 1)
        self.assertEqual(seeded.last_run_summary["state"], "succeeded")
        self.assertEqual(
            set(seeded.last_run_summary),
            {"run_id", "kind", "state", "error_code", *COUNTERS},
        )

    def test_fake_rejects_wrong_credential_and_pauses_push(self) -> None:
        outbound = self.create(
            name="Outbound",
            enabled=True,
            mmr_push_enabled=True,
            outbound_base_url=FAKE_ORIGIN,
            outbound_auth="bearer",
            outbound_credential=FAKE_BAD_CREDENTIAL,
        )
        player = OrgUser.objects.nocache().get(
            organization_id=MAIN, user_id=AC_PLAYER_TWO.pk
        )
        set_org_mmr(player, GameType.DOTA2, 2100, mark_verified=False)
        drive_connection_work([MAIN])
        delivery = OrgApiMmrDelivery.objects.get(connection_id=outbound["id"])
        self.assertEqual(
            (delivery.state, delivery.last_reason), ("paused", "auth_failed")
        )
        self.assertEqual(fake_calls()[-1]["status"], 401)

    def test_other_origins_still_use_the_safe_transport(self) -> None:
        request = SafeHttpRequest(url="https://127.0.0.1/mmr")
        with self.assertRaises(SafeHttpError):
            pull.request_json(request, deadline=time.monotonic() + 1)
        self.assertEqual(fake_calls(), [])

    def test_every_role_logs_in(self) -> None:
        factory = APIRequestFactory()
        for role in [*API_CONNECTIONS_ROLE_USERS, "nobody"]:
            request = factory.post(f"/api/tests/login-org-api-connections/{role}/")
            request.session = SessionStore()
            expected = 400 if role == "nobody" else 200
            self.assertEqual(
                login_org_api_connections(request, role).status_code, expected, role
            )


@override_settings(DEBUG=True)
class FakeTransportGateTest(TestCase):
    def test_fake_transport_and_helpers_unavailable_outside_test(self) -> None:
        originals = (
            pull.request_json,
            push.request_json,
            orchestration.request_json,
            orchestration.request_bytes,
        )
        factory = APIRequestFactory()
        for overrides in ({"TEST": False}, {"RELEASE": True}, {"DEBUG": False}):
            with self.subTest(overrides=overrides), override_settings(**overrides):
                with self.assertRaises(FakeTransportUnavailable):
                    install_fake_transport()
                with self.assertRaises(FakeTransportUnavailable):
                    drive_connection_work([MAIN])
                with self.assertRaises(FakeTransportUnavailable):
                    fake_calls()
                self.assertFalse(fake_transport_installed())
                for view, path in (
                    (reset_org_api_connections, "org-api-connections/reset/"),
                    (drive_org_api_connections, "org-api-connections/drive/"),
                    (
                        seed_org_api_promotion_backlog,
                        "org-api-connections/promotion-backlog/",
                    ),
                ):
                    response = view(factory.post(f"/api/tests/{path}"))
                    self.assertEqual(response.status_code, 404, path)
                state = org_api_connections_state(
                    factory.get("/api/tests/org-api-connections/state/")
                )
                self.assertEqual(state.status_code, 404)
                login = login_org_api_connections(
                    factory.post("/api/tests/login-org-api-connections/admin/"),
                    "admin",
                )
                self.assertEqual(login.status_code, 404)
        self.assertEqual(
            originals,
            (
                pull.request_json,
                push.request_json,
                orchestration.request_json,
                orchestration.request_bytes,
            ),
        )
        self.assertFalse(OrgApiConnection.objects.filter(organization_id=MAIN).exists())
