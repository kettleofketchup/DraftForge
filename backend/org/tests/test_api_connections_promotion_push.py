import json
from datetime import timedelta
from typing import Any
from unittest.mock import patch

from django.test import override_settings
from django.utils import timezone
from rest_framework.response import Response
from rest_framework.test import APIClient

from app.models import CustomUser
from org.api_connections import tls_adapter
from org.api_connections.promotion_config import adopt_legacy_promotion
from org.api_connections.tls_adapter import SafeHttpError
from org.api_connections.types import SafeHttpRawResponse, SafeHttpRequest
from org.contributions.queries import member_totals
from org.integration import points
from org.integration.dispatch import DispatchReport, dispatch_due
from org.integration.receipts import canonical_receipt_hash, canonical_receipt_json
from org.models import (
    ContributionEntry,
    OrgApiConnection,
    OrgApiPromotionEventBinding,
    OrgUser,
    PromoSend,
)
from org.models_promotion_sync import (
    OutboxState,
    PointStatus,
    PromotionContactOutbox,
)
from org.tests.test_api_connections_crypto import OLD_KEY
from org.tests.test_integration_contacts import age_import
from org.tests.test_promotion_dispatch import FakeClient, _config, applied
from org.tests.test_promotion_ledger import _LedgerBase
from tournament.models import Tournament

PUBLIC = "93.184.216.34"
BASE_URL = "https://adaptor.example"
PER_ORG_KEY = "per-org-adaptor-key"
CONTACT_LOG_ID = 8021
PATH = "/api/v1/organizations/{org_id}/promotion/contact-receipts"


def applied_body(request: SafeHttpRequest) -> dict[str, Any]:
    assert request.body is not None
    return {
        "delivery_id": request.body["delivery_id"],
        "status": "applied",
        "applied": True,
        "durable": True,
        "contact_log_id": str(CONTACT_LOG_ID),
    }


def not_applied_body(request: SafeHttpRequest) -> dict[str, Any]:
    assert request.body is not None
    return {
        "delivery_id": request.body["delivery_id"],
        "status": "not_applied",
        "reason": "writeback_disabled",
        "applied": False,
        "durable": False,
    }


class FakeAdaptorTransport:
    """Stands in for ``request_bytes`` and answers each request in order."""

    def __init__(self, responses: list[Any]) -> None:
        self.responses = list(responses)
        self.requests: list[SafeHttpRequest] = []

    def __call__(
        self, request: SafeHttpRequest, *, deadline: float, max_bytes: int
    ) -> SafeHttpRawResponse:
        self.requests.append(request)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        status, body = response
        if callable(body):
            body = body(request)
        return SafeHttpRawResponse(
            status=status, body=json.dumps(body).encode(), retry_after=None
        )


@override_settings(
    ORG_API_CREDENTIAL_KEYS=json.dumps([OLD_KEY]), PROMOTION_ADAPTOR=_config()
)
class _PushBase(_LedgerBase):
    def setUp(self) -> None:
        super().setUp()
        self.operator = CustomUser.objects.create_superuser(
            username="push-operator", password="x"
        )
        resolve = patch.object(tls_adapter, "_resolve", return_value=(PUBLIC,))
        resolve.start()
        self.addCleanup(resolve.stop)
        self.session = APIClient()
        self.session.force_authenticate(self.admin)

    def adopt(self, *, enable: bool = True) -> OrgApiConnection:
        connection = adopt_legacy_promotion(
            org_id=self.org.pk,
            actor=self.operator,
            credential=PER_ORG_KEY,
            base_url=BASE_URL,
            dry_run=False,
        )
        if enable:
            OrgApiConnection.objects.filter(pk=connection.pk).update(
                enabled=True, promotion_push_enabled=True
            )
        connection.refresh_from_db()
        return connection

    def player(self, name: str) -> CustomUser:
        user = self._user(name)
        Tournament.objects.get(name="Promotion API Past").users.add(user)
        return user

    def row(self, send: PromoSend) -> PromotionContactOutbox:
        return PromotionContactOutbox.objects.get(
            organization=self.org, local_send_id=send.pk
        )

    def dispatch(
        self,
        transport: FakeAdaptorTransport | None = None,
        env: FakeClient | None = None,
        **kwargs: Any,
    ) -> DispatchReport:
        transport = transport or FakeAdaptorTransport([])
        with patch(
            "org.integration.adaptor_client.request_bytes", side_effect=transport
        ):
            return dispatch_due(client=env or FakeClient(applied), **kwargs)

    def url(self, connection: OrgApiConnection, action: str) -> str:
        return (
            f"/api/organizations/{self.org.pk}/api-connections/"
            f"{connection.pk}/promotion/{action}/"
        )

    def outbox(self, connection: OrgApiConnection) -> Response:
        return self.session.get(self.url(connection, "outbox"))

    def ledger_rows(self) -> int:
        return ContributionEntry.objects.nocache().count()

    def totals(self, user: CustomUser) -> int:
        member = OrgUser.objects.get(user=user, organization=self.org)
        return member_totals(member)["all_time"]


class EchoReconciliationTests(_PushBase):
    def assertSettledOnce(self, send: PromoSend) -> None:
        receipt = self.receipt(CONTACT_LOG_ID)
        self.assertEqual(receipt.point_status, PointStatus.ECHO)
        self.assertFalse(receipt.holds_point)
        self.assertEqual(receipt.origin_send_id, send.pk)
        send.refresh_from_db()
        self.assertTrue(send.earns_points)
        entry = self.entry_for(send)
        self.assertFalse(entry.voided)
        self.assertEqual(self.totals(self.promoter), entry.points)
        self.assertEqual(self.totals(self.member), 0)
        self.assertFalse(self.ticked(self.recipient.discordId, self.recipient))

    def test_echo_before_ack_settles_once(self) -> None:
        send = self.send()
        self.imported(
            [self.entry(CONTACT_LOG_ID, self.recipient, promoter=self.member)]
        )
        self.assertEqual(
            self.receipt(CONTACT_LOG_ID).point_status, PointStatus.CREDITED
        )
        self.assertTrue(self.entry_for(send).voided)
        report = self.dispatch()
        self.assertEqual(report.counts["applied"], 1)
        row = self.row(send)
        self.assertEqual(row.state, OutboxState.APPLIED)
        self.assertEqual(row.applied_contact_log_id, CONTACT_LOG_ID)
        self.assertSettledOnce(send)
        [credit] = self.credits(self.receipt(CONTACT_LOG_ID))
        self.assertTrue(credit.voided)
        settled = self.ledger_rows()
        body = self.imported(
            [self.entry(CONTACT_LOG_ID, self.recipient, promoter=self.member)]
        )
        self.assertEqual(self.point(body), PointStatus.ECHO)
        self.assertEqual(self.ledger_rows(), settled)
        self.assertSettledOnce(send)

    def test_ack_before_echo_settles_once(self) -> None:
        send = self.send()
        self.dispatch()
        self.assertEqual(self.row(send).state, OutboxState.APPLIED)
        before = self.ledger_rows()
        for _ in range(2):
            body = self.imported(
                [self.entry(CONTACT_LOG_ID, self.recipient, promoter=self.member)]
            )
            self.assertEqual(self.point(body), PointStatus.ECHO)
            self.assertFalse(body["results"][0]["voided_local"])
        self.assertEqual(self.ledger_rows(), before)
        self.assertSettledOnce(send)

    def test_ack_atomically_reclassifies_imported_echo(self) -> None:
        send = self.send()
        self.imported(
            [self.entry(CONTACT_LOG_ID, self.recipient, promoter=self.member)]
        )
        before = self.ledger_rows()
        with (
            patch.object(points, "reclassify_echo", side_effect=RuntimeError("boom")),
            self.assertRaises(RuntimeError),
        ):
            self.dispatch()
        row = self.row(send)
        self.assertEqual(row.state, OutboxState.IN_FLIGHT)
        self.assertIsNone(row.applied_contact_log_id)
        self.assertEqual(
            self.receipt(CONTACT_LOG_ID).point_status, PointStatus.CREDITED
        )
        self.assertEqual(self.ledger_rows(), before)
        env = FakeClient(applied)
        self.dispatch(env=env, now=row.lease_expires_at + timedelta(seconds=1))
        self.assertEqual(env.calls, [row.payload])
        self.assertEqual(self.row(send).state, OutboxState.APPLIED)
        self.assertSettledOnce(send)

    def test_duplicate_echo_releases_nothing(self) -> None:
        send = self.send()
        self.imported(
            [
                self.entry(8001, self.recipient, promoter=self.member),
                self.entry(CONTACT_LOG_ID, self.recipient, promoter=self.member),
            ]
        )
        self.assertEqual(
            self.receipt(CONTACT_LOG_ID).point_status, PointStatus.DUPLICATE
        )
        before = self.ledger_rows()
        self.dispatch()
        receipt = self.receipt(CONTACT_LOG_ID)
        self.assertEqual(receipt.point_status, PointStatus.ECHO)
        self.assertEqual(receipt.origin_send_id, send.pk)
        self.assertEqual(self.receipt(8001).point_status, PointStatus.CREDITED)
        self.assertTrue(self.entry_for(send).voided)
        self.assertEqual(self.ledger_rows(), before)

    def test_retracted_echo_keeps_local_point(self) -> None:
        send = self.send()
        self.dispatch()
        self.imported(
            [self.entry(CONTACT_LOG_ID, self.recipient, promoter=self.member)]
        )
        age_import(self.receipt(CONTACT_LOG_ID).pk)
        body = self.imported([], after=CONTACT_LOG_ID - 1, through=CONTACT_LOG_ID)
        self.assertEqual(body["retracted"], 1)
        self.assertEqual(body["restored_local"], 0)
        self.assertEqual(
            self.receipt(CONTACT_LOG_ID).point_status, PointStatus.RETRACTED
        )
        send.refresh_from_db()
        self.assertTrue(send.earns_points)
        self.assertFalse(self.entry_for(send).voided)


class ConnectionTransportTests(_PushBase):
    def test_pending_null_connection_uses_adopted_resolver(self) -> None:
        send = self.send()
        row = self.row(send)
        self.assertIsNone(row.connection_id)
        connection = self.adopt()
        env = FakeClient(applied)
        transport = FakeAdaptorTransport([(200, applied_body)])
        report = self.dispatch(transport, env)
        self.assertEqual(env.calls, [])
        [request] = transport.requests
        self.assertEqual(
            request.url,
            connection.outbound_base_url.rstrip("/") + PATH.format(org_id=self.org.pk),
        )
        self.assertEqual(request.method, "POST")
        self.assertEqual((request.auth, request.credential), ("bearer", PER_ORG_KEY))
        self.assertEqual(request.credential_origin, "https://adaptor.example:443")
        self.assertEqual(request.body, row.payload)
        self.assertEqual(request.body_encoding, "canonical")
        self.assertEqual(
            canonical_receipt_json(request.body), canonical_receipt_json(row.payload)
        )
        after = self.row(send)
        self.assertEqual(after.state, OutboxState.APPLIED)
        self.assertEqual(after.connection_id, connection.pk)
        self.assertEqual(after.delivery_id, row.delivery_id)
        self.assertEqual(after.payload_hash, canonical_receipt_hash(row.payload))
        self.assertEqual(report.counts["applied"], 1)

    def test_echo_before_connection_ack_settles_once(self) -> None:
        send = self.send()
        self.adopt()
        self.imported(
            [self.entry(CONTACT_LOG_ID, self.recipient, promoter=self.member)]
        )
        self.dispatch(FakeAdaptorTransport([(200, applied_body)]))
        receipt = self.receipt(CONTACT_LOG_ID)
        self.assertEqual(receipt.point_status, PointStatus.ECHO)
        self.assertEqual(receipt.origin_send_id, send.pk)
        self.assertFalse(self.entry_for(send).voided)
        self.assertEqual(self.totals(self.member), 0)

    def test_disabled_adopted_holds_without_env_send(self) -> None:
        send = self.send()
        connection = self.adopt(enable=False)
        env = FakeClient(applied)
        transport = FakeAdaptorTransport([])
        report = self.dispatch(transport, env)
        self.assertEqual((env.calls, transport.requests), ([], []))
        self.assertEqual(report.held, 1)
        row = self.row(send)
        self.assertEqual((row.state, row.attempts), (OutboxState.PENDING, 0))
        self.assertIsNone(row.connection_id)
        OrgApiConnection.objects.filter(pk=connection.pk).update(enabled=True)
        self.dispatch(transport, env)
        self.assertEqual(self.row(send).state, OutboxState.PENDING)
        self.assertEqual(env.calls, [])

    def test_adoption_mid_run_holds_remaining_env_rows(self) -> None:
        first = self.send()
        second = self.send(self.player("push_second"))
        adopted: list[OrgApiConnection] = []

        def respond(payload: dict[str, Any]) -> Any:
            if not adopted:
                adopted.append(self.adopt(enable=False))
            return applied(payload)

        env = FakeClient(respond)
        report = self.dispatch(env=env)
        self.assertEqual([call["local_send_id"] for call in env.calls], [str(first.pk)])
        self.assertEqual(self.row(first).state, OutboxState.APPLIED)
        held = self.row(second)
        self.assertEqual((held.state, held.attempts), (OutboxState.PENDING, 0))
        self.assertEqual(report.held, 1)

    def test_pre_effective_send_is_backlog_held(self) -> None:
        early = self.send()
        connection = self.adopt()
        OrgApiPromotionEventBinding.objects.filter(event=self.event).update(
            effective_at=timezone.now()
        )
        late = self.send(self.player("push_late"))
        transport = FakeAdaptorTransport([(200, applied_body)])
        self.dispatch(transport)
        self.assertEqual(
            [request.body["local_send_id"] for request in transport.requests],
            [str(late.pk)],
        )
        held = self.row(early)
        self.assertEqual(held.state, OutboxState.BACKLOG_HELD)
        self.assertEqual(held.attempts, 0)
        self.assertIsNone(held.connection_id)
        self.dispatch(FakeAdaptorTransport([]))
        self.assertEqual(self.row(early).state, OutboxState.BACKLOG_HELD)
        resp = self.outbox(connection)
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertEqual(resp.data["counts"]["backlog_held"], 1)
        self.assertEqual(resp.data["counts"]["applied"], 1)
        self.assertNotIn("payload", json.dumps(resp.data))

    def test_confirmed_backlog_release_and_org_resume_keep_id_hash(self) -> None:
        early = self.send()
        connection = self.adopt()
        OrgApiPromotionEventBinding.objects.filter(event=self.event).update(
            effective_at=timezone.now()
        )
        paused = self.send(self.player("push_paused"))
        self.dispatch(FakeAdaptorTransport([(409, not_applied_body)]))
        self.assertEqual(self.row(paused).state, OutboxState.PAUSED)
        self.assertEqual(self.row(early).state, OutboxState.BACKLOG_HELD)
        stuck = self.send(self.player("push_stuck"))
        PromotionContactOutbox.objects.filter(local_send_id=stuck.pk).update(
            state=OutboxState.RECONCILIATION_REQUIRED, last_reason="already_contacted"
        )
        frozen = {
            send.pk: (self.row(send).delivery_id, self.row(send).payload_hash)
            for send in (early, paused)
        }

        stale = self.session.post(
            self.url(connection, "send-backlog"), {"confirmed_count": 2}, format="json"
        )
        self.assertEqual(stale.status_code, 409, stale.data)
        self.assertEqual(stale.data["code"], "backlog_changed")
        self.assertEqual(self.row(early).state, OutboxState.BACKLOG_HELD)
        released = self.session.post(
            self.url(connection, "send-backlog"), {"confirmed_count": 1}, format="json"
        )
        self.assertEqual(released.status_code, 200, released.data)
        self.assertEqual(released.data, {"released": 1})
        resumed = self.session.post(self.url(connection, "resume"), {}, format="json")
        self.assertEqual(resumed.status_code, 200, resumed.data)
        self.assertEqual(resumed.data, {"resumed": 1})
        self.assertEqual(self.row(stuck).state, OutboxState.RECONCILIATION_REQUIRED)

        transport = FakeAdaptorTransport([(200, applied_body), (200, applied_body)])
        self.dispatch(transport)
        sent = {request.body["local_send_id"] for request in transport.requests}
        self.assertEqual(sent, {str(early.pk), str(paused.pk)})
        for send in (early, paused):
            row = self.row(send)
            self.assertEqual(row.state, OutboxState.APPLIED)
            self.assertEqual((row.delivery_id, row.payload_hash), frozen[send.pk])
            self.assertEqual(row.connection_id, connection.pk)
        for request in transport.requests:
            self.assertEqual(
                canonical_receipt_hash(request.body),
                frozen[int(request.body["local_send_id"])][1],
            )
        self.assertEqual(self.row(stuck).state, OutboxState.RECONCILIATION_REQUIRED)

    def test_recovery_routes_scoped_to_stream_and_admins(self) -> None:
        connection = self.adopt()
        other = OrgApiConnection.objects.create(organization=self.org, name="MMR")
        for action in ("resume", "send-backlog"):
            body = {} if action == "resume" else {"confirmed_count": 0}
            resp = self.session.post(self.url(other, action), body, format="json")
            self.assertEqual(resp.status_code, 400, resp.data)
            self.assertEqual(resp.data["code"], "not_promotion_stream")
        bad = self.session.post(
            self.url(connection, "send-backlog"),
            {"confirmed_count": "1"},
            format="json",
        )
        self.assertEqual(bad.status_code, 400)
        extra = self.session.post(
            self.url(connection, "resume"), {"force": True}, format="json"
        )
        self.assertEqual(extra.status_code, 400)
        member = APIClient()
        member.force_authenticate(self.member)
        self.assertEqual(member.get(self.url(connection, "outbox")).status_code, 403)
        foreign = (
            f"/api/organizations/{self.other_org.pk}/api-connections/"
            f"{connection.pk}/promotion/outbox/"
        )
        owner = APIClient()
        owner.force_authenticate(self.users["owner"])
        self.assertEqual(owner.get(foreign).status_code, 404)

    def test_authority_loss_at_send_pauses_and_disables_push(self) -> None:
        send = self.send()
        connection = self.adopt()
        CustomUser.objects.filter(pk=self.operator.pk).update(is_active=False)
        transport = FakeAdaptorTransport([])
        self.dispatch(transport)
        self.assertEqual(transport.requests, [])
        row = self.row(send)
        self.assertEqual(
            (row.state, row.last_reason), (OutboxState.PAUSED, "authority_lost")
        )
        connection.refresh_from_db()
        self.assertFalse(connection.promotion_push_enabled)
        self.assertEqual(connection.outbound_credential_ciphertext, "")

    def test_unsupported_auth_and_unsafe_destination_pause_visibly(self) -> None:
        send = self.send()
        connection = self.adopt()
        OrgApiConnection.objects.filter(pk=connection.pk).update(
            outbound_auth="api_key_field"
        )
        self.dispatch()
        row = self.row(send)
        self.assertEqual(
            (row.state, row.last_reason), (OutboxState.PAUSED, "unsupported_auth")
        )
        OrgApiConnection.objects.filter(pk=connection.pk).update(outbound_auth="bearer")
        self.session.post(self.url(connection, "resume"), {}, format="json")
        self.dispatch(FakeAdaptorTransport([SafeHttpError("unsafe_address")]))
        row = self.row(send)
        self.assertEqual(
            (row.state, row.last_reason), (OutboxState.PAUSED, "unsafe_destination")
        )
        self.session.post(self.url(connection, "resume"), {}, format="json")
        self.dispatch(FakeAdaptorTransport([SafeHttpError("deadline_exceeded")]))
        row = self.row(send)
        self.assertEqual((row.state, row.last_reason), (OutboxState.RETRY, "timeout"))


class PromotionPushEnableTests(_PushBase):
    def patch(self, connection: OrgApiConnection, body: dict[str, Any]) -> Response:
        connection.refresh_from_db()
        return self.session.patch(
            f"/api/organizations/{self.org.pk}/api-connections/{connection.pk}/",
            {"config_version": connection.config_version, **body},
            format="json",
        )

    def test_push_enables_only_on_adopted_bearer_stream(self) -> None:
        other = OrgApiConnection.objects.create(
            organization=self.org,
            name="Other",
            outbound_base_url=BASE_URL,
            outbound_auth="bearer",
        )
        resp = self.patch(other, {"promotion_push_enabled": True})
        self.assertEqual(resp.status_code, 400, resp.data)
        self.assertEqual(resp.data["code"], "not_promotion_stream")
        connection = self.adopt(enable=False)
        OrgApiConnection.objects.filter(pk=connection.pk).update(
            outbound_credential_owner=self.admin
        )
        resp = self.patch(connection, {"enabled": True, "promotion_push_enabled": True})
        self.assertEqual(resp.status_code, 200, resp.data)
        connection.refresh_from_db()
        self.assertTrue(connection.promotion_push_enabled)

    def test_enable_does_not_resume_paused_rows(self) -> None:
        send = self.send()
        connection = self.adopt()
        PromotionContactOutbox.objects.filter(local_send_id=send.pk).update(
            state=OutboxState.PAUSED, due_at=None, last_reason="writeback_disabled"
        )
        OrgApiConnection.objects.filter(pk=connection.pk).update(
            promotion_push_enabled=False, outbound_credential_owner=self.admin
        )
        self.assertEqual(
            self.patch(connection, {"promotion_push_enabled": True}).status_code, 200
        )
        self.dispatch()
        self.assertEqual(self.row(send).state, OutboxState.PAUSED)
