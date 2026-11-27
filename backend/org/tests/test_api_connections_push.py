import json
from datetime import timedelta
from typing import Any
from unittest.mock import patch

from django.test import override_settings
from django.utils import timezone
from structlog.testing import capture_logs

from common.game import GameType
from org.api_connections import recovery
from org.api_connections.config import apply_config_patch
from org.api_connections.crypto import seal_credential
from org.api_connections.mutations import MmrMutationContext
from org.api_connections.push import (
    BACKOFF_BASE_SECONDS,
    BACKOFF_CAP_SECONDS,
    acquire_delivery_lease,
    retry_delay,
    step_mmr_delivery,
)
from org.api_connections.recovery import (
    resume_mmr_deliveries,
    resync_mmr_deliveries,
)
from org.api_connections.schemas import ConnectionConfigError
from org.api_connections.tls_adapter import SafeHttpError
from org.api_connections.types import SafeHttpRequest, SafeHttpResponse, StepResult
from org.api_tokens.tokens import issue_token
from org.features import FeatureKey, set_org_feature
from org.mmr import set_org_mmr
from org.models import (
    OrgApiConnection,
    OrgApiMmrDelivery,
    OrgApiToken,
    OrgMmrSyncState,
    OrgUser,
    OrgUserGameMmr,
)
from org.tests.test_api_connections_crypto import OLD_KEY
from org.tests.test_api_tokens import ApiTokenBase

GAME = GameType.DOTA2
SECRET = "push-secret-abc"
ORIGIN = "https://ratings.example.test"


def ack(delivery: OrgApiMmrDelivery, status: str = "applied") -> dict[str, str]:
    return {"delivery_id": str(delivery.delivery_id), "status": status}


class FakeRemote:
    def __init__(self, responses: list[Any]) -> None:
        self.responses = list(responses)
        self.requests: list[SafeHttpRequest] = []

    def __call__(
        self, request: SafeHttpRequest, *, deadline: float, max_bytes: int
    ) -> SafeHttpResponse:
        self.requests.append(request)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        status, data = response
        if callable(data):
            data = data(request)
        return SafeHttpResponse(
            status=status, data=data, bytes_received=len(json.dumps(data))
        )


def echo_ack(status: str = "applied") -> Any:
    return lambda request: {
        "delivery_id": request.body["delivery_id"],
        "status": status,
    }


@override_settings(ORG_API_CREDENTIAL_KEYS=json.dumps([OLD_KEY]))
class PushBase(ApiTokenBase):
    def setUp(self) -> None:
        super().setUp()
        self.connection = OrgApiConnection.objects.create(
            organization=self.org,
            name="Ratings",
            enabled=True,
            mmr_push_enabled=True,
            outbound_base_url=ORIGIN,
            outbound_auth="bearer",
            outbound_credential_owner=self.admin,
            game_type=int(GAME),
        )
        self.seal(self.connection, SECRET, ORIGIN)

    def seal(self, connection: OrgApiConnection, secret: str, origin: str) -> None:
        OrgApiConnection.objects.filter(pk=connection.pk).update(
            outbound_credential_ciphertext=seal_credential(
                secret,
                org_id=connection.organization_id,
                connection_id=connection.pk,
                origin=origin,
            ),
            outbound_credential_key_id="old",
        )
        connection.refresh_from_db()

    def write(self, value: int, member: OrgUser | None = None, **kwargs: Any) -> None:
        set_org_mmr(member or self.ou_alice, GAME, value, mark_verified=False, **kwargs)

    def latest(self, connection: OrgApiConnection | None = None) -> OrgApiMmrDelivery:
        return OrgApiMmrDelivery.objects.filter(
            connection=connection or self.connection
        ).latest("revision")

    def step(
        self, delivery: OrgApiMmrDelivery, remote: FakeRemote
    ) -> tuple[StepResult, OrgApiMmrDelivery]:
        fence = acquire_delivery_lease(delivery.delivery_id)
        self.assertIsNotNone(fence, delivery.state)
        assert fence is not None
        with patch("org.api_connections.push.request_json", side_effect=remote):
            result = step_mmr_delivery(delivery.delivery_id, fence=fence)
        delivery.refresh_from_db()
        return result, delivery

    def make_due(self, delivery: OrgApiMmrDelivery) -> None:
        OrgApiMmrDelivery.objects.filter(pk=delivery.pk).update(
            due_at=timezone.now() - timedelta(seconds=1)
        )


class PushDeliveryTests(PushBase):
    def test_payload_idempotency_ack_and_zero_clear(self) -> None:
        self.write(4500)
        first = self.latest()
        remote = FakeRemote([(200, echo_ack())])
        result, first = self.step(first, remote)
        self.assertEqual(result.state, "applied")
        self.assertEqual(first.state, "applied")
        request = remote.requests[0]
        self.assertEqual(
            request.url, f"{ORIGIN}/api/v1/organizations/{self.org.pk}/mmr"
        )
        self.assertEqual(request.method, "POST")
        self.assertEqual(request.auth, "bearer")
        self.assertEqual(request.credential, SECRET)
        self.assertEqual(request.credential_origin, f"{ORIGIN}:443")
        self.assertEqual(request.idempotency_key, str(first.delivery_id))
        state = OrgMmrSyncState.objects.get(org_user=self.ou_alice, game_type=GAME)
        self.assertEqual(
            request.body,
            {
                "schema_version": 1,
                "delivery_id": str(first.delivery_id),
                "org_id": self.org.pk,
                "game_type": int(GAME),
                "entries": [
                    {
                        "org_user_id": self.ou_alice.pk,
                        "steam_id": "1001",
                        "discord_id": "d-alice",
                        "mmr": 4500,
                        "revision": state.revision,
                    }
                ],
            },
        )
        self.write(0)
        cleared = self.latest()
        self.assertEqual(cleared.payload["entries"][0]["mmr"], 0)
        remote = FakeRemote([(200, echo_ack("unchanged"))])
        _, cleared = self.step(cleared, remote)
        self.assertEqual(cleared.state, "applied")
        self.assertEqual(cleared.last_reason, "unchanged")
        self.assertEqual(remote.requests[0].body["entries"][0]["mmr"], 0)

    def test_invalid_acknowledgements_pause(self) -> None:
        cases: list[Any] = [
            (200, {"delivery_id": "00000000-0000-0000-0000-000000000000"}),
            (200, lambda request: {"delivery_id": request.body["delivery_id"]}),
            (204, None),
            (200, ["applied"]),
            SafeHttpError("invalid_json"),
        ]
        for index, case in enumerate(cases):
            with self.subTest(index=index):
                self.write(4000 + index)
                delivery = self.latest()
                _, delivery = self.step(delivery, FakeRemote([case]))
                self.assertEqual(delivery.state, "paused")
                self.assertEqual(delivery.last_reason, "invalid_acknowledgement")

    def test_timeout_retries_same_id_but_never_older_after_newer(self) -> None:
        self.write(4500)
        older = self.latest()
        remote = FakeRemote(
            [SafeHttpError("deadline_exceeded"), SafeHttpError("network_failed")]
        )
        _, older = self.step(older, remote)
        self.assertEqual(older.state, "retry")
        self.assertEqual(older.attempts, 1)
        self.assertGreater(older.due_at, timezone.now())
        self.assertIsNone(acquire_delivery_lease(older.delivery_id))
        self.make_due(older)
        _, older = self.step(older, remote)
        self.assertEqual(older.state, "retry")
        self.assertEqual(
            [r.idempotency_key for r in remote.requests],
            [str(older.delivery_id)] * 2,
        )
        self.make_due(older)
        fence = acquire_delivery_lease(older.delivery_id)
        assert fence is not None
        self.write(4700)
        newer = self.latest()
        self.assertGreater(newer.revision, older.revision)
        self.assertIsNone(acquire_delivery_lease(newer.delivery_id))
        remote = FakeRemote([SafeHttpError("deadline_exceeded"), (200, echo_ack())])
        with patch("org.api_connections.push.request_json", side_effect=remote):
            step_mmr_delivery(older.delivery_id, fence=fence)
        older.refresh_from_db()
        self.assertEqual(older.state, "superseded")
        _, newer = self.step(newer, remote)
        self.assertEqual(newer.state, "applied")
        self.assertIsNone(acquire_delivery_lease(older.delivery_id))
        self.assertEqual(
            [r.body["entries"][0]["mmr"] for r in remote.requests], [4500, 4700]
        )

    def test_unsent_older_revisions_coalesce(self) -> None:
        self.write(4500)
        first = self.latest()
        self.write(4600)
        self.assertEqual(OrgApiMmrDelivery.objects.get(pk=first.pk).state, "superseded")
        self.assertIsNone(acquire_delivery_lease(first.delivery_id))
        remote = FakeRemote([(200, echo_ack())])
        self.step(self.latest(), remote)
        self.assertEqual(len(remote.requests), 1)

    def test_auth_schema_pause_and_five_attempt_backoff(self) -> None:
        for status, reason in (
            (401, "auth_failed"),
            (403, "auth_failed"),
            (422, "schema_rejected"),
            (400, "schema_rejected"),
        ):
            with self.subTest(status=status):
                self.write(3000 + status)
                _, delivery = self.step(
                    self.latest(), FakeRemote([(status, {"error": "x"})])
                )
                self.assertEqual(delivery.state, "paused")
                self.assertEqual(delivery.last_reason, reason)
        self.write(4999)
        delivery = self.latest()
        responses: list[Any] = [(500, None), (429, None), (503, None), (502, None)]
        for attempt, response in enumerate(responses, start=1):
            before = timezone.now()
            _, delivery = self.step(delivery, FakeRemote([response]))
            self.assertEqual(delivery.state, "retry")
            self.assertEqual(delivery.attempts, attempt)
            delay = min(BACKOFF_CAP_SECONDS, BACKOFF_BASE_SECONDS * 2 ** (attempt - 1))
            self.assertGreaterEqual(
                delivery.due_at, before + timedelta(seconds=delay / 2)
            )
            self.assertLessEqual(
                delivery.due_at, timezone.now() + timedelta(seconds=delay)
            )
            self.make_due(delivery)
        _, delivery = self.step(delivery, FakeRemote([(500, None)]))
        self.assertEqual(delivery.attempts, 5)
        self.assertEqual(delivery.state, "paused")
        self.assertEqual(delivery.last_reason, "retries_exhausted")

    def test_backoff_is_capped(self) -> None:
        for attempts in range(1, 20):
            delay = retry_delay(attempts).total_seconds()
            self.assertLessEqual(delay, BACKOFF_CAP_SECONDS)
            self.assertGreaterEqual(
                delay,
                min(BACKOFF_CAP_SECONDS, BACKOFF_BASE_SECONDS * 2 ** (attempts - 1))
                / 2,
            )

    def test_expired_in_flight_lease_is_reclaimed_and_stale_fence_refused(
        self,
    ) -> None:
        self.write(4500)
        delivery = self.latest()
        stale = acquire_delivery_lease(delivery.delivery_id)
        assert stale is not None
        self.assertIsNone(acquire_delivery_lease(delivery.delivery_id))
        later = timezone.now() + timedelta(minutes=5)
        fresh = acquire_delivery_lease(delivery.delivery_id, now=later)
        self.assertIsNotNone(fresh)
        remote = FakeRemote([(200, echo_ack())])
        with patch("org.api_connections.push.request_json", side_effect=remote):
            result = step_mmr_delivery(delivery.delivery_id, fence=stale)
        self.assertEqual(result.error_code, "stale_fence")
        self.assertEqual(remote.requests, [])
        delivery.refresh_from_db()
        self.assertEqual(delivery.state, "in_flight")
        self.assertEqual(delivery.attempts, 2)

    def test_lease_lost_during_request_refuses_finalize(self) -> None:
        self.write(4500)
        delivery = self.latest()
        fence = acquire_delivery_lease(delivery.delivery_id)
        assert fence is not None

        def expire(request: SafeHttpRequest) -> dict[str, str]:
            OrgApiMmrDelivery.objects.filter(pk=delivery.pk).update(
                lease_expires_at=timezone.now() - timedelta(seconds=1)
            )
            return {"delivery_id": request.body["delivery_id"], "status": "applied"}

        with patch(
            "org.api_connections.push.request_json",
            side_effect=FakeRemote([(200, expire)]),
        ):
            result = step_mmr_delivery(delivery.delivery_id, fence=fence)
        self.assertEqual(result.error_code, "stale_fence")
        delivery.refresh_from_db()
        self.assertEqual(delivery.state, "in_flight")

    def test_removed_member_cancels(self) -> None:
        self.write(4500)
        delivery = self.latest()
        self.ou_alice.delete()
        delivery.refresh_from_db()
        self.assertEqual(delivery.state, "canceled")
        self.assertEqual(delivery.last_reason, "membership_removed")
        self.assertIsNone(acquire_delivery_lease(delivery.delivery_id))

    def test_enqueue_while_role_lost_or_feature_locked_does_not_export(self) -> None:
        self.org.admins.remove(self.admin)
        self.write(4500)
        self.assertFalse(OrgApiMmrDelivery.objects.exists())
        self.org.admins.add(self.admin)
        set_org_feature(self.org, FeatureKey.MMR_SYNC, enabled=False, actor=None)
        self.write(4600)
        self.assertFalse(OrgApiMmrDelivery.objects.exists())

    def test_authority_lost_before_send_pauses_and_cleans_up(self) -> None:
        self.write(4500)
        delivery = self.latest()
        self.org.admins.remove(self.admin)
        remote = FakeRemote([(200, echo_ack())])
        result, delivery = self.step(delivery, remote)
        self.assertEqual(result.error_code, "authority_lost")
        self.assertEqual(delivery.state, "paused")
        self.assertEqual(remote.requests, [])
        self.connection.refresh_from_db()
        self.assertFalse(self.connection.mmr_push_enabled)
        self.assertEqual(self.connection.outbound_credential_ciphertext, "")

    def test_feature_locked_before_send_pauses(self) -> None:
        self.write(4500)
        delivery = self.latest()
        set_org_feature(self.org, FeatureKey.MMR_SYNC, enabled=False, actor=None)
        remote = FakeRemote([(200, echo_ack())])
        _, delivery = self.step(delivery, remote)
        self.assertEqual(delivery.state, "paused")
        self.assertEqual(delivery.last_reason, "feature_locked")
        self.assertEqual(remote.requests, [])

    def test_revoked_inbound_token_does_not_stop_push(self) -> None:
        issued = issue_token(self.org, self.admin, "Inbound")
        OrgApiToken.objects.filter(pk=issued.token.pk).update(
            connection=self.connection
        )
        OrgApiToken.objects.filter(pk=issued.token.pk).update(revoked_at=timezone.now())
        self.write(4500)
        _, delivery = self.step(self.latest(), FakeRemote([(200, echo_ack())]))
        self.assertEqual(delivery.state, "applied")

    def test_secret_absent_from_delivery_and_logs(self) -> None:
        self.write(4500)
        with capture_logs() as logs:
            _, delivery = self.step(self.latest(), FakeRemote([(401, None)]))
        dumped = json.dumps([logs, delivery.payload, delivery.last_reason], default=str)
        self.assertNotIn(SECRET, dumped)
        self.assertTrue(
            any(entry.get("event") == "api_connection_delivery" for entry in logs)
        )


class PushOrderingTests(PushBase):
    def test_newer_waits_while_older_in_flight(self) -> None:
        self.write(4500)
        older = self.latest()
        fence = acquire_delivery_lease(older.delivery_id)
        assert fence is not None
        self.write(4600)
        newer = self.latest()
        self.assertIsNone(acquire_delivery_lease(newer.delivery_id))
        remote = FakeRemote([(200, echo_ack())])
        with patch("org.api_connections.push.request_json", side_effect=remote):
            step_mmr_delivery(older.delivery_id, fence=fence)
        older.refresh_from_db()
        self.assertEqual(older.state, "applied")
        self.assertIsNotNone(acquire_delivery_lease(newer.delivery_id))

    def test_per_org_two_request_semaphore(self) -> None:
        others = [
            OrgApiConnection.objects.create(
                organization=self.org,
                name=f"Ratings {index}",
                enabled=True,
                mmr_push_enabled=True,
                outbound_base_url=ORIGIN,
                outbound_auth="none",
                outbound_authorizer=self.admin,
                game_type=int(GAME),
            )
            for index in range(2)
        ]
        self.write(4500)
        deliveries = [self.latest(c) for c in (self.connection, *others)]
        fences = [acquire_delivery_lease(d.delivery_id) for d in deliveries]
        self.assertIsNotNone(fences[0])
        self.assertIsNotNone(fences[1])
        self.assertIsNone(fences[2])
        later = timezone.now() + timedelta(minutes=5)
        self.assertIsNotNone(
            acquire_delivery_lease(deliveries[2].delivery_id, now=later)
        )
        other_org_connection = OrgApiConnection.objects.create(
            organization=self.other_org,
            name="Other",
            enabled=True,
            mmr_push_enabled=True,
            outbound_base_url=ORIGIN,
            outbound_authorizer=self.admin,
        )
        self.other_org.admins.add(self.admin)
        set_org_feature(self.other_org, FeatureKey.MMR_SYNC, enabled=True, actor=None)
        member = OrgUser.objects.create(user=self.bob, organization=self.other_org)
        self.write(4100, member)
        self.assertIsNotNone(
            acquire_delivery_lease(self.latest(other_org_connection).delivery_id)
        )


class PushRecoveryTests(PushBase):
    def pause(self, status: int = 401) -> OrgApiMmrDelivery:
        self.write(4500)
        _, delivery = self.step(self.latest(), FakeRemote([(status, None)]))
        self.assertEqual(delivery.state, "paused")
        return delivery

    def patch_config(self, **patch_fields: Any) -> None:
        self.connection = apply_config_patch(
            self.connection,
            actor=self.admin,
            patch=patch_fields,
            expected_version=self.connection.config_version,
        )

    def resume(self) -> int:
        self.connection.refresh_from_db()
        return resume_mmr_deliveries(
            self.connection,
            actor=self.admin,
            expected_version=self.connection.config_version,
        )

    def test_auth_replace_resume_delivers_frozen_payload(self) -> None:
        delivery = self.pause(401)
        frozen = dict(delivery.payload)
        self.assertEqual(self.resume(), 0)
        self.patch_config(outbound_credential="replaced-secret")
        self.assertEqual(self.resume(), 1)
        delivery.refresh_from_db()
        self.assertEqual(delivery.state, "retry")
        self.assertEqual(delivery.attempts, 0)
        remote = FakeRemote([(200, echo_ack())])
        _, delivery = self.step(delivery, remote)
        self.assertEqual(delivery.state, "applied")
        self.assertEqual(remote.requests[0].body, frozen)
        self.assertEqual(remote.requests[0].credential, "replaced-secret")
        self.assertEqual(remote.requests[0].idempotency_key, frozen["delivery_id"])

    def test_resume_rejects_stale_version(self) -> None:
        self.pause(422)
        with self.assertRaises(ConnectionConfigError) as caught:
            resume_mmr_deliveries(
                self.connection,
                actor=self.admin,
                expected_version=self.connection.config_version + 1,
            )
        self.assertEqual(caught.exception.code, "configuration_changed")

    def test_origin_change_requires_resync(self) -> None:
        self.write(4500)
        delivery = self.latest()
        self.patch_config(
            outbound_base_url="https://new.example.test",
            outbound_credential="new-secret",
        )
        remote = FakeRemote([(200, echo_ack())])
        _, delivery = self.step(delivery, remote)
        self.assertEqual(delivery.state, "paused")
        self.assertEqual(delivery.last_reason, "origin_changed")
        self.assertEqual(remote.requests, [])
        self.assertEqual(self.resume(), 0)
        with self.assertRaises(ConnectionConfigError) as caught:
            resync_mmr_deliveries(
                self.connection,
                actor=self.admin,
                expected_version=self.connection.config_version,
                confirmed=False,
            )
        self.assertEqual(caught.exception.code, "confirmation_required")
        before = OrgMmrSyncState.objects.get(org_user=self.ou_alice, game_type=GAME)
        self.write(3000, self.ou_bob)
        OrgApiMmrDelivery.objects.filter(connection=self.connection).exclude(
            pk=delivery.pk
        ).update(state="pending")
        created = resync_mmr_deliveries(
            self.connection,
            actor=self.admin,
            expected_version=self.connection.config_version,
            confirmed=True,
        )
        self.assertEqual(created, 2)
        delivery.refresh_from_db()
        self.assertEqual(delivery.state, "canceled")
        self.assertEqual(delivery.last_reason, "resynced")
        fresh = OrgApiMmrDelivery.objects.get(
            connection=self.connection, org_user=self.ou_alice, state="pending"
        )
        self.assertGreater(fresh.revision, before.revision)
        self.assertEqual(fresh.payload["entries"][0]["mmr"], 4500)
        self.assertEqual(fresh.destination_origin, "https://new.example.test:443")
        self.assertEqual(
            OrgUserGameMmr.objects.get(org_user=self.ou_alice, game_type=GAME).mmr,
            4500,
        )
        remote = FakeRemote([(200, echo_ack())])
        _, fresh = self.step(fresh, remote)
        self.assertEqual(fresh.state, "applied")
        self.assertTrue(remote.requests[0].url.startswith("https://new.example.test/"))
        self.assertEqual(remote.requests[0].credential, "new-secret")

    def test_same_origin_configuration_change_pauses_until_resume(self) -> None:
        self.write(4500)
        delivery = self.latest()
        self.patch_config(name="Renamed")
        remote = FakeRemote([(200, echo_ack())])
        _, delivery = self.step(delivery, remote)
        self.assertEqual(delivery.last_reason, "configuration_changed")
        self.assertEqual(self.resume(), 1)
        _, delivery = self.step(delivery, remote)
        self.assertEqual(delivery.state, "applied")

    def test_pause_does_not_auto_resume(self) -> None:
        paused = self.pause(401)
        self.write(3000, self.ou_bob)
        pending = self.latest()
        self.patch_config(mmr_push_enabled=False)
        remote = FakeRemote([(200, echo_ack())])
        _, pending = self.step(pending, remote)
        self.assertEqual(pending.state, "paused")
        self.assertEqual(remote.requests, [])
        self.patch_config(mmr_push_enabled=True)
        for delivery in (paused, pending):
            delivery.refresh_from_db()
            self.assertEqual(delivery.state, "paused")
            self.assertIsNone(acquire_delivery_lease(delivery.delivery_id))
        self.assertEqual(self.resume(), 1)
        pending.refresh_from_db()
        self.assertEqual(pending.state, "retry")

    def test_resume_is_bounded(self) -> None:
        self.pause(422)
        self.write(3000, self.ou_bob)
        _, second = self.step(self.latest(), FakeRemote([(422, None)]))
        self.patch_config(name="Edited")
        with patch.object(recovery, "RESUME_LIMIT", 1):
            self.assertEqual(self.resume(), 1)
            self.assertEqual(self.resume(), 1)
            self.assertEqual(self.resume(), 0)

    def test_oscillation_guard_pauses_eleventh_distinct_change(self) -> None:
        source = OrgApiConnection.objects.create(
            organization=self.org,
            name="Source",
            enabled=True,
            outbound_authorizer=self.admin,
        )
        context = MmrMutationContext(origin_connection_id=source.pk)
        for value in range(4000, 4010):
            self.write(value, sync_context=context)
            self.write(value, sync_context=context)
        rows = OrgApiMmrDelivery.objects.filter(connection=self.connection)
        self.assertEqual(rows.count(), 10)
        self.assertFalse(rows.filter(state="paused").exists())
        self.write(1234)
        self.assertEqual(self.latest().state, "pending")
        self.write(4010, sync_context=context)
        guarded = self.latest()
        self.assertEqual(guarded.state, "paused")
        self.assertEqual(guarded.last_reason, "sync_loop_suspected")
        self.assertFalse(OrgApiMmrDelivery.objects.filter(connection=source).exists())
        self.assertEqual(self.resume(), 1)
        guarded.refresh_from_db()
        self.assertEqual(guarded.state, "retry")


class PushApiTests(PushBase):
    def setUp(self) -> None:
        super().setUp()
        self.client.force_authenticate(self.admin)
        self.base = (
            f"/api/organizations/{self.org.pk}/api-connections/{self.connection.pk}/"
        )

    def test_push_enablement_passes_validation(self) -> None:
        response = self.client.post(
            f"/api/organizations/{self.org.pk}/api-connections/",
            {
                "name": "Push",
                "outbound_base_url": ORIGIN,
                "mmr_push_enabled": True,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertTrue(response.data["mmr_push_enabled"])
        self.assertEqual(response.data["outbound_authorizer"], self.admin.pk)

    def test_deliveries_list_resume_resync_routes(self) -> None:
        self.write(4500)
        _, delivery = self.step(self.latest(), FakeRemote([(401, None)]))
        listed = self.client.get(f"{self.base}deliveries/", {"state": "paused"})
        self.assertEqual(listed.status_code, 200, listed.data)
        self.assertEqual(listed.data["counts"]["paused"], 1)
        item = listed.data["items"][0]
        self.assertEqual(item["delivery_id"], str(delivery.delivery_id))
        self.assertEqual(item["last_reason"], "auth_failed")
        self.assertEqual(item["mmr"], 4500)
        self.assertNotIn("payload", item)
        self.assertNotIn(SECRET, json.dumps(listed.data, default=str))
        self.assertEqual(
            self.client.get(f"{self.base}deliveries/", {"state": "bogus"}).status_code,
            400,
        )
        version = self.connection.config_version
        stale = self.client.post(
            f"{self.base}deliveries/resume/",
            {"config_version": version + 5},
            format="json",
        )
        self.assertEqual(stale.status_code, 409)
        resumed = self.client.post(
            f"{self.base}deliveries/resume/",
            {"config_version": version},
            format="json",
        )
        self.assertEqual(resumed.status_code, 200, resumed.data)
        self.assertEqual(resumed.data["resumed"], 0)
        unconfirmed = self.client.post(
            f"{self.base}deliveries/resync/",
            {"config_version": version},
            format="json",
        )
        self.assertEqual(unconfirmed.status_code, 400)
        resynced = self.client.post(
            f"{self.base}deliveries/resync/",
            {"config_version": version, "confirm": True},
            format="json",
        )
        self.assertEqual(resynced.status_code, 200, resynced.data)
        self.assertEqual(resynced.data["enqueued"], 1)

    def test_delivery_routes_are_org_scoped_and_paginated(self) -> None:
        self.other_org.admins.add(self.admin)
        foreign = f"/api/organizations/{self.other_org.pk}/api-connections/{self.connection.pk}/deliveries/"
        self.assertEqual(self.client.get(foreign).status_code, 404)
        self.client.force_authenticate(self.staff)
        self.assertEqual(self.client.get(f"{self.base}deliveries/").status_code, 403)
        self.client.force_authenticate(self.admin)
        for value in range(3):
            member = OrgUser.objects.create(
                user=type(self.alice).objects.create_user(
                    username=f"p{value}", steam_account_id=2000 + value
                ),
                organization=self.org,
            )
            self.write(3000 + value, member)
        with patch("org.api_connections.views.DELIVERY_PAGE_SIZE", 2):
            first = self.client.get(f"{self.base}deliveries/")
            self.assertEqual(len(first.data["items"]), 2)
            self.assertIsNotNone(first.data["next_cursor"])
            second = self.client.get(
                f"{self.base}deliveries/", {"cursor": first.data["next_cursor"]}
            )
            self.assertEqual(len(second.data["items"]), 1)
            self.assertIsNone(second.data["next_cursor"])
        other = f"/api/organizations/{self.org.pk}/api-connections/{OrgApiConnection.objects.create(organization=self.org, name='x').pk}/deliveries/"
        self.assertEqual(
            self.client.get(other, {"cursor": first.data["next_cursor"]}).status_code,
            400,
        )
