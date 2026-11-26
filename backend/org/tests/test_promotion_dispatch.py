"""Dispatching retained promotion receipts to the adaptor.

One outbox row is one recorded DM. The dispatcher leases due rows in a short
transaction, sends each frozen payload with no transaction open, and then
finalizes only the lease it still holds. Only a fully validated ``applied``
answer counts as written to the external contact log. Everything else is an
honest state: retry
with backoff, paused until an operator resumes, or reconciliation required.
"""

from __future__ import annotations

import io
import json
import threading
import time
from collections.abc import Callable
from datetime import timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from unittest.mock import patch

from django.core.exceptions import ImproperlyConfigured
from django.core.management import call_command
from django.db import connection, models
from django.test import SimpleTestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient
from structlog.testing import capture_logs

from app.models import CustomUser
from config.promotion_sync import (
    OrgPromotionBinding,
    PromotionAdaptorConfig,
    PromotionSyncConfig,
)
from org.integration.adaptor_client import (
    OutcomeKind,
    PromotionAdaptorClient,
    ReceiptOutcome,
)
from org.integration.dispatch import (
    DispatchReport,
    claim,
    dispatch_due,
    finalize,
    preview_due,
)
from org.integration.receipts import canonical_receipt_json
from org.models import PromoSend
from org.models_promotion_sync import OutboxState, PromotionContactOutbox
from org.promotion.services import undo_promo_send
from org.tests.test_promotion_sends import _SendFixture

KEY = "adaptor-key-test-dispatch-000000000000"
CONTACT_LOG_ID = "8021"


def _config(**overrides: Any) -> PromotionAdaptorConfig:
    values: dict[str, Any] = {
        "enabled": True,
        "base_url": "http://127.0.0.1:9",
        "api_key": KEY,
        "timeout": 5.0,
        "max_attempts": 5,
        "retry_cap": 120.0,
    }
    values.update(overrides)
    return PromotionAdaptorConfig(**values)


def applied(payload: dict[str, Any]) -> ReceiptOutcome:
    return ReceiptOutcome(
        kind=OutcomeKind.APPLIED,
        reason="",
        http_status=200,
        contact_log_id=int(CONTACT_LOG_ID),
    )


def outcome(kind: OutcomeKind, reason: str, **kw: Any) -> Callable[..., ReceiptOutcome]:
    def make(payload: dict[str, Any]) -> ReceiptOutcome:
        return ReceiptOutcome(kind=kind, reason=reason, **kw)

    return make


class FakeClient:
    """Records each payload it is given and answers with ``respond``."""

    def __init__(self, respond: Callable[[dict[str, Any]], ReceiptOutcome]) -> None:
        self.respond = respond
        self.calls: list[dict[str, Any]] = []

    def record(self, payload: dict[str, Any]) -> ReceiptOutcome:
        self.calls.append(payload)
        return self.respond(payload)


class _DispatchFixture(_SendFixture):
    def setUp(self) -> None:
        super().setUp()
        self.bindings = PromotionSyncConfig(
            bindings=(
                OrgPromotionBinding(
                    org_id=self.org.pk,
                    guild_id=555000000000000001,
                    events={self.event.pk: 88},
                ),
            )
        )
        patcher = override_settings(
            PROMOTION_SYNC=self.bindings, PROMOTION_ADAPTOR=_config()
        )
        patcher.enable()
        self.addCleanup(patcher.disable)

    def row(self, send: PromoSend | int) -> PromotionContactOutbox:
        send_id = send if isinstance(send, int) else send.pk
        return PromotionContactOutbox.objects.get(
            organization=self.org, local_send_id=send_id
        )

    def dispatch(
        self, client: FakeClient, *, at: Any = None, **kw: Any
    ) -> DispatchReport:
        return dispatch_due(client=client, now=at, **kw)


class AppliedTests(_DispatchFixture):
    def test_applied_outcome_is_terminal_and_records_contact_log(self) -> None:
        send = self._send(self.promoter)
        frozen = self.row(send).payload
        client = FakeClient(applied)
        report = self.dispatch(client)
        self.assertEqual(client.calls, [frozen])
        row = self.row(send)
        self.assertEqual(row.state, OutboxState.APPLIED)
        self.assertEqual(row.applied_contact_log_id, int(CONTACT_LOG_ID))
        self.assertIsNone(row.lease_token)
        self.assertIsNone(row.lease_expires_at)
        self.assertIsNone(row.due_at)
        self.assertEqual(row.attempts, 1)
        self.assertEqual(report.counts["applied"], 1)
        # Applied rows are never sent again.
        self.dispatch(client, at=timezone.now() + timedelta(days=1))
        self.assertEqual(len(client.calls), 1)

    def test_every_send_is_dispatched_separately(self) -> None:
        sends = [
            self._send(self.promoter),
            self._send(self.promoter, text="again"),
            self._send(self.promoter_b, text="other"),
        ]
        client = FakeClient(applied)
        self.dispatch(client)
        self.assertEqual(
            sorted(call["local_send_id"] for call in client.calls),
            sorted(str(send.pk) for send in sends),
        )
        self.assertEqual(len({call["delivery_id"] for call in client.calls}), 3)

    def test_already_contacted_goes_to_reconciliation_not_applied(self) -> None:
        send = self._send(self.promoter)
        client = FakeClient(
            outcome(
                OutcomeKind.ALREADY_CONTACTED,
                "already_contacted",
                http_status=200,
                contact_log_id=8000,
            )
        )
        self.dispatch(client)
        row = self.row(send)
        self.assertEqual(row.state, OutboxState.RECONCILIATION_REQUIRED)
        self.assertEqual(row.last_reason, "already_contacted")
        self.assertIsNone(row.applied_contact_log_id)
        self.assertIsNotNone(row.payload)
        self.dispatch(client, at=timezone.now() + timedelta(days=1))
        self.assertEqual(len(client.calls), 1)

    def test_invalid_response_cannot_apply(self) -> None:
        send = self._send(self.promoter)
        client = FakeClient(
            outcome(OutcomeKind.INVALID_RESPONSE, "invalid_response", http_status=200)
        )
        self.dispatch(client)
        row = self.row(send)
        self.assertEqual(row.state, OutboxState.RECONCILIATION_REQUIRED)
        self.assertEqual(row.last_reason, "invalid_response")
        self.assertIsNone(row.applied_contact_log_id)


class PauseAndReconcileTests(_DispatchFixture):
    def test_disabled_pauses_until_explicit_resume(self) -> None:
        send = self._send(self.promoter)
        client = FakeClient(
            outcome(OutcomeKind.NOT_APPLIED, "writeback_disabled", http_status=409)
        )
        self.dispatch(client)
        row = self.row(send)
        self.assertEqual(row.state, OutboxState.PAUSED)
        self.assertEqual(row.last_reason, "writeback_disabled")
        self.assertIsNone(row.due_at)
        self.assertIsNotNone(row.payload)

        later = timezone.now() + timedelta(days=30)
        self.dispatch(client, at=later)
        self.assertEqual(len(client.calls), 1)

        client.respond = applied
        report = self.dispatch(client, at=later, resume_paused=True)
        self.assertEqual(report.resumed, 1)
        self.assertEqual(len(client.calls), 2)
        self.assertEqual(client.calls[0], client.calls[1])
        self.assertEqual(self.row(send).state, OutboxState.APPLIED)

    def test_dry_run_answer_also_pauses(self) -> None:
        send = self._send(self.promoter)
        self.dispatch(
            FakeClient(outcome(OutcomeKind.NOT_APPLIED, "dry_run", http_status=409))
        )
        self.assertEqual(self.row(send).state, OutboxState.PAUSED)
        self.assertEqual(self.row(send).last_reason, "dry_run")

    def test_resume_touches_only_paused_rows(self) -> None:
        paused = self._send(self.promoter)
        reconcile = self._send(self.promoter, text="again")
        PromotionContactOutbox.objects.filter(local_send_id=paused.pk).update(
            state=OutboxState.PAUSED, due_at=None, last_reason="writeback_disabled"
        )
        PromotionContactOutbox.objects.filter(local_send_id=reconcile.pk).update(
            state=OutboxState.RECONCILIATION_REQUIRED,
            due_at=None,
            last_reason="already_contacted",
        )
        client = FakeClient(applied)
        self.dispatch(client, resume_paused=True)
        self.assertEqual([c["local_send_id"] for c in client.calls], [str(paused.pk)])
        self.assertEqual(self.row(reconcile).state, OutboxState.RECONCILIATION_REQUIRED)

    def test_mapping_and_idempotency_conflicts_need_reconciliation(self) -> None:
        for kind, reason in (
            (OutcomeKind.MAPPING_REQUIRED, "mapping_required"),
            (OutcomeKind.IDEMPOTENCY_CONFLICT, "idempotency_conflict"),
            (OutcomeKind.REJECTED, "adaptor_rejected"),
        ):
            with self.subTest(kind=kind):
                send = self._send(self.promoter, text=f"m {kind}")
                client = FakeClient(outcome(kind, reason, http_status=409))
                self.dispatch(client)
                row = self.row(send)
                self.assertEqual(row.state, OutboxState.RECONCILIATION_REQUIRED)
                self.assertEqual(row.last_reason, reason)
                self.dispatch(client, at=timezone.now() + timedelta(days=1))
                self.assertEqual(len(client.calls), 1)

    def test_credential_failures_pause_instead_of_retrying(self) -> None:
        for kind, reason, status in (
            (OutcomeKind.UNAUTHORIZED, "adaptor_unauthorized", 401),
            (OutcomeKind.FORBIDDEN, "adaptor_forbidden", 403),
        ):
            with self.subTest(kind=kind):
                send = self._send(self.promoter, text=f"c {kind}")
                client = FakeClient(outcome(kind, reason, http_status=status))
                for days in range(3):
                    self.dispatch(client, at=timezone.now() + timedelta(days=days))
                self.assertEqual(len(client.calls), 1)
                row = self.row(send)
                self.assertEqual(row.state, OutboxState.PAUSED)
                self.assertEqual(row.last_reason, reason)

    def test_incomplete_identity_rows_are_never_dispatched(self) -> None:
        sender = self._user("ps_promoter_no_discord", discord=False)
        self.org.promoters.add(sender)
        send = self._send(sender)
        self.assertEqual(self.row(send).state, OutboxState.RECONCILIATION_REQUIRED)
        client = FakeClient(applied)
        self.dispatch(client, resume_paused=True)
        self.assertEqual(client.calls, [])

    def test_payload_that_no_longer_matches_its_hash_is_not_sent(self) -> None:
        send = self._send(self.promoter)
        tampered = {**self.row(send).payload, "event_id": "999"}
        models.QuerySet.update(
            PromotionContactOutbox.objects.filter(local_send_id=send.pk),
            payload=tampered,
        )
        client = FakeClient(applied)
        self.dispatch(client)
        self.assertEqual(client.calls, [])
        row = self.row(send)
        self.assertEqual(row.state, OutboxState.RECONCILIATION_REQUIRED)
        self.assertEqual(row.last_reason, "payload_integrity")


class RetryTests(_DispatchFixture):
    def test_retryable_failure_respects_retry_after(self) -> None:
        send = self._send(self.promoter)
        start = timezone.now()
        client = FakeClient(
            outcome(
                OutcomeKind.RETRYABLE,
                "rate_limited",
                http_status=429,
                retry_after=90.0,
            )
        )
        self.dispatch(client, at=start)
        row = self.row(send)
        self.assertEqual(row.state, OutboxState.RETRY)
        self.assertEqual(row.last_reason, "rate_limited")
        self.assertEqual(row.attempts, 1)
        self.assertGreaterEqual(row.due_at, start + timedelta(seconds=90))
        self.assertIsNone(row.lease_token)

        self.dispatch(client, at=start + timedelta(seconds=60))
        self.assertEqual(len(client.calls), 1)
        self.dispatch(client, at=start + timedelta(seconds=91))
        self.assertEqual(len(client.calls), 2)

    def test_backoff_is_capped(self) -> None:
        send = self._send(self.promoter)
        client = FakeClient(
            outcome(OutcomeKind.RETRYABLE, "adaptor_unavailable", http_status=503)
        )
        at = timezone.now()
        for _ in range(4):
            self.dispatch(client, at=at)
            row = self.row(send)
            self.assertLessEqual(row.due_at - at, timedelta(seconds=120))
            at = row.due_at
        self.assertEqual(len(client.calls), 4)

    def test_fifth_failure_requires_reconciliation(self) -> None:
        send = self._send(self.promoter)
        client = FakeClient(outcome(OutcomeKind.RETRYABLE, "timeout", http_status=None))
        at = timezone.now()
        for _ in range(8):
            self.dispatch(client, at=at)
            at = at + timedelta(hours=1)
        self.assertEqual(len(client.calls), 5)
        row = self.row(send)
        self.assertEqual(row.state, OutboxState.RECONCILIATION_REQUIRED)
        self.assertEqual(row.last_reason, "retries_exhausted")
        self.assertEqual(row.attempts, 5)
        self.assertEqual(len({json.dumps(c, sort_keys=True) for c in client.calls}), 1)

    def test_timeout_then_success_resends_identical_receipt(self) -> None:
        send = self._send(self.promoter)
        answers = iter(
            [
                ReceiptOutcome(OutcomeKind.RETRYABLE, "timeout", None),
                ReceiptOutcome(OutcomeKind.APPLIED, "", 200, contact_log_id=8021),
            ]
        )
        client = FakeClient(lambda payload: next(answers))
        at = timezone.now()
        self.dispatch(client, at=at)
        self.dispatch(client, at=at + timedelta(minutes=5))
        self.assertEqual(len(client.calls), 2)
        self.assertEqual(
            canonical_receipt_json(client.calls[0]),
            canonical_receipt_json(client.calls[1]),
        )
        self.assertEqual(self.row(send).state, OutboxState.APPLIED)

    def test_limit_bounds_one_run(self) -> None:
        for i in range(3):
            self._send(self.promoter, text=f"n{i}")
        client = FakeClient(applied)
        report = self.dispatch(client, limit=2)
        self.assertEqual(len(client.calls), 2)
        self.assertEqual(report.leased, 2)


class ConfigGateTests(_DispatchFixture):
    def test_disabled_config_sends_nothing_and_keeps_rows(self) -> None:
        send = self._send(self.promoter)
        client = FakeClient(applied)
        with override_settings(PROMOTION_ADAPTOR=PromotionAdaptorConfig()):
            report = dispatch_due(client=client)
        self.assertFalse(report.enabled)
        self.assertEqual(client.calls, [])
        row = self.row(send)
        self.assertEqual(row.state, OutboxState.PENDING)
        self.assertEqual(row.attempts, 0)
        self.assertIsNone(row.lease_token)

    def test_unbound_org_or_event_stays_pending(self) -> None:
        send = self._send(self.promoter)
        client = FakeClient(applied)
        with override_settings(PROMOTION_SYNC=PromotionSyncConfig()):
            report = dispatch_due(client=client)
        self.assertEqual(client.calls, [])
        self.assertEqual(report.skipped_unbound, 1)
        unbound_event = PromotionSyncConfig(
            bindings=(
                OrgPromotionBinding(
                    org_id=self.org.pk, guild_id=555000000000000001, events={}
                ),
            )
        )
        with override_settings(PROMOTION_SYNC=unbound_event):
            dispatch_due(client=client)
        self.assertEqual(client.calls, [])
        self.assertEqual(self.row(send).state, OutboxState.PENDING)


class LeaseTests(_DispatchFixture):
    def test_concurrent_dispatchers_lease_once(self) -> None:
        send = self._send(self.promoter)
        inner = FakeClient(applied)

        def respond(payload: dict[str, Any]) -> ReceiptOutcome:
            dispatch_due(client=inner)
            return applied(payload)

        outer = FakeClient(respond)
        dispatch_due(client=outer)
        self.assertEqual(len(outer.calls), 1)
        self.assertEqual(inner.calls, [])
        self.assertEqual(self.row(send).state, OutboxState.APPLIED)

    def test_slow_adaptor_cannot_expire_later_leases_or_backdate_retries(
        self,
    ) -> None:
        """Each row is leased and rescheduled from the clock at that moment.

        Every request takes longer than a whole lease. Were the run's start
        time used for every row, later rows would be leased already expired
        and a second dispatcher would resend them, and Retry-After would be
        measured from a moment long past.
        """
        sends = [self._send(self.promoter, text=f"slow {i}") for i in range(3)]
        lease = timedelta(seconds=65)  # max(2 * 5s timeout, 5s + 60s)
        retry_after = timedelta(seconds=600)
        clock = [timezone.now() + timedelta(seconds=1)]
        answered_at: dict[str, Any] = {}
        expired: list[str] = []
        resent: list[str] = []

        def tick() -> Any:
            return clock[0]

        def respond(payload: dict[str, Any]) -> ReceiptOutcome:
            # dispatch_due turns a client exception into a retry, so problems
            # are collected here and asserted after the run.
            row = self.row(int(payload["local_send_id"]))
            if row.state != OutboxState.IN_FLIGHT or (
                row.lease_expires_at < clock[0] + lease
            ):
                expired.append(payload["local_send_id"])
            # A second dispatcher at this moment must not take the row.
            if claim(row, now=clock[0], config=_config()) is not None:
                resent.append(payload["delivery_id"])
            clock[0] += lease + timedelta(seconds=5)
            answered_at[payload["local_send_id"]] = clock[0]
            return ReceiptOutcome(
                OutcomeKind.RETRYABLE,
                "rate_limited",
                http_status=429,
                retry_after=retry_after.total_seconds(),
            )

        client = FakeClient(respond)
        dispatch_due(client=client, clock=tick)
        self.assertEqual(len(client.calls), 3)
        self.assertEqual(expired, [])
        self.assertEqual(resent, [])
        for send in sends:
            row = self.row(send)
            self.assertEqual(row.state, OutboxState.RETRY)
            self.assertEqual(row.attempts, 1)
            self.assertGreaterEqual(row.due_at, answered_at[str(send.pk)] + retry_after)
            self.assertEqual(row.updated_at, answered_at[str(send.pk)])

    def test_claim_is_compare_and_set(self) -> None:
        send = self._send(self.promoter)
        row = self.row(send)
        now = timezone.now()
        first = claim(row, now=now, config=_config())
        second = claim(row, now=now, config=_config())
        self.assertIsNotNone(first)
        self.assertIsNone(second)
        self.assertEqual(self.row(send).attempts, 1)

    def test_abandoned_lease_retries_same_delivery_after_expiry(self) -> None:
        send = self._send(self.promoter)
        row = self.row(send)
        now = timezone.now()
        lease = claim(row, now=now, config=_config())
        assert lease is not None
        # The worker died: the row stays in flight until its lease expires.
        client = FakeClient(applied)
        self.dispatch(client, at=now + timedelta(seconds=1))
        self.assertEqual(client.calls, [])
        self.dispatch(client, at=self.row(send).lease_expires_at + timedelta(seconds=1))
        self.assertEqual(len(client.calls), 1)
        self.assertEqual(client.calls[0]["delivery_id"], str(row.delivery_id))
        self.assertEqual(client.calls[0], lease.payload)
        self.assertEqual(self.row(send).state, OutboxState.APPLIED)
        self.assertEqual(self.row(send).attempts, 2)

    def test_late_response_cannot_reset_applied(self) -> None:
        send = self._send(self.promoter)
        now = timezone.now()
        stale = claim(self.row(send), now=now, config=_config())
        assert stale is not None
        expired = self.row(send).lease_expires_at + timedelta(seconds=1)
        self.dispatch(FakeClient(applied), at=expired)
        self.assertEqual(self.row(send).state, OutboxState.APPLIED)
        changed = finalize(
            stale,
            ReceiptOutcome(OutcomeKind.RETRYABLE, "timeout", None),
            now=expired,
            config=_config(),
        )
        self.assertFalse(changed)
        row = self.row(send)
        self.assertEqual(row.state, OutboxState.APPLIED)
        self.assertEqual(row.applied_contact_log_id, int(CONTACT_LOG_ID))

    def test_no_transaction_is_open_during_the_request(self) -> None:
        self._send(self.promoter)
        seen: list[bool] = []

        def respond(payload: dict[str, Any]) -> ReceiptOutcome:
            # Django's TestCase wraps each test in its own atomic blocks.
            seen.append(
                all(
                    getattr(block, "_from_testcase", False)
                    for block in connection.atomic_blocks
                )
            )
            return applied(payload)

        dispatch_due(client=FakeClient(respond))
        self.assertEqual(seen, [True])


class UndoAndPrivacyTests(_DispatchFixture):
    def test_undo_leaves_the_queued_send_dispatchable(self) -> None:
        send = self._send(self.promoter)
        frozen = self.row(send).payload
        undo_promo_send(send, actor=self.promoter)
        client = FakeClient(applied)
        self.dispatch(client)
        self.assertEqual(client.calls, [frozen])
        self.assertEqual(self.row(int(frozen["local_send_id"])).state, "applied")

    def test_deleted_account_before_dispatch_is_canceled_and_redacted(self) -> None:
        send = self._send(self.promoter)
        send_id = send.pk
        stored_hash = self.row(send).payload_hash
        CustomUser.objects.get(pk=self.recipient.pk).delete()
        row = self.row(send_id)
        self.assertEqual(row.state, OutboxState.CANCELED)
        self.assertEqual(row.last_reason, "account_deleted")
        self.assertIsNone(row.payload)
        self.assertEqual(row.payload_hash, stored_hash)
        client = FakeClient(applied)
        self.dispatch(client, resume_paused=True)
        self.assertEqual(client.calls, [])

    def test_deletion_redacts_applied_rows_without_reopening_them(self) -> None:
        send = self._send(self.promoter)
        self.dispatch(FakeClient(applied))
        CustomUser.objects.get(pk=self.recipient.pk).delete()
        row = self.row(send.pk)
        self.assertEqual(row.state, OutboxState.APPLIED)
        self.assertIsNone(row.payload)
        self.assertEqual(row.applied_contact_log_id, int(CONTACT_LOG_ID))

    def test_deletion_during_flight_prevents_late_state_resurrection(self) -> None:
        send = self._send(self.promoter)
        send_id = send.pk
        recipient_pk = self.recipient.pk

        def respond(payload: dict[str, Any]) -> ReceiptOutcome:
            CustomUser.objects.get(pk=recipient_pk).delete()
            return applied(payload)

        client = FakeClient(respond)
        report = self.dispatch(client)
        self.assertEqual(len(client.calls), 1)
        row = self.row(send_id)
        self.assertEqual(row.state, OutboxState.CANCELED)
        self.assertEqual(row.last_reason, "account_deleted")
        self.assertIsNone(row.payload)
        self.assertIsNone(row.applied_contact_log_id)
        self.assertIsNone(row.lease_token)
        self.assertEqual(report.discarded, 1)


class WritebackSummaryApiTests(_DispatchFixture):
    def _client(self, user: CustomUser) -> APIClient:
        client = APIClient()
        client.force_authenticate(user=user)
        return client

    def test_send_and_undo_report_writeback_state_never_applied(self) -> None:
        client = self._client(self.promoter)
        url = (
            f"/api/organizations/{self.org.pk}/promotion/events/{self.event.pk}/sends/"
        )
        resp = client.post(
            url, {"recipient_id": self.recipient.pk, "text": "Hi"}, format="json"
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        body = resp.json()
        row = self.row(body["id"])
        self.assertEqual(
            body["writeback"],
            {"state": "pending", "reason": None, "delivery_id": str(row.delivery_id)},
        )

        self.dispatch(
            FakeClient(
                outcome(OutcomeKind.NOT_APPLIED, "writeback_disabled", http_status=409)
            )
        )
        resp = client.delete(
            f"/api/organizations/{self.org.pk}/promotion/sends/{body['id']}/"
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(
            resp.json(),
            {
                "writeback": {
                    "state": "paused",
                    "reason": "writeback_disabled",
                    "delivery_id": str(row.delivery_id),
                }
            },
        )


class CommandTests(_DispatchFixture):
    def test_dry_run_neither_leases_nor_sends(self) -> None:
        send = self._send(self.promoter)
        out = io.StringIO()
        with patch(
            "org.integration.adaptor_client.PromotionAdaptorClient.record",
            side_effect=AssertionError("dry run sent a receipt"),
        ):
            call_command(
                "dispatch_promotion_contacts", "--dry-run", "--limit", "1", stdout=out
            )
        report = json.loads(out.getvalue())
        self.assertTrue(report["dry_run"])
        self.assertEqual(report["due"], 1)
        row = self.row(send)
        self.assertEqual(row.state, OutboxState.PENDING)
        self.assertEqual(row.attempts, 0)
        self.assertIsNone(row.lease_token)

    def test_preview_counts_paused_rows_only_when_resuming(self) -> None:
        send = self._send(self.promoter)
        PromotionContactOutbox.objects.filter(local_send_id=send.pk).update(
            state=OutboxState.PAUSED, due_at=None
        )
        self.assertEqual(preview_due().due, 0)
        self.assertEqual(preview_due(resume_paused=True).due, 1)
        self.assertEqual(self.row(send).state, OutboxState.PAUSED)

    def test_command_dispatches_through_a_local_fake_adaptor(self) -> None:
        send = self._send(self.promoter)
        delivery = str(self.row(send).delivery_id)
        with FakeAdaptor(
            [
                (
                    200,
                    {
                        "delivery_id": delivery,
                        "status": "applied",
                        "applied": True,
                        "durable": True,
                        "contact_log_id": "8021",
                    },
                    {},
                )
            ]
        ) as server:
            out = io.StringIO()
            with override_settings(PROMOTION_ADAPTOR=_config(base_url=server.url)):
                call_command("dispatch_promotion_contacts", "--limit", "5", stdout=out)
        report = json.loads(out.getvalue())
        self.assertEqual(report["counts"], {"applied": 1})
        self.assertEqual(self.row(send).state, OutboxState.APPLIED)
        self.assertEqual(len(server.requests), 1)

    def test_command_reports_disabled_without_sending(self) -> None:
        self._send(self.promoter)
        out = io.StringIO()
        with override_settings(PROMOTION_ADAPTOR=PromotionAdaptorConfig()):
            call_command("dispatch_promotion_contacts", stdout=out)
        report = json.loads(out.getvalue())
        self.assertFalse(report["enabled"])
        self.assertEqual(report["leased"], 0)


# --- HTTP client against a real local server --------------------------------


Script = list[tuple[int, Any, dict[str, str]]]


class FakeAdaptor:
    """A threaded local HTTP server answering scripted responses in order.

    A response body of ``bytes`` is sent raw; anything else as JSON. A
    header ``X-Test-Sleep`` delays the answer, for timeouts.
    """

    def __init__(self, script: Script) -> None:
        self.script = list(script)
        self.requests: list[dict[str, Any]] = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:  # noqa: N802
                length = int(self.headers.get("Content-Length", "0"))
                outer.requests.append(
                    {
                        "path": self.path,
                        "headers": dict(self.headers),
                        "body": self.rfile.read(length),
                    }
                )
                status, body, headers = outer.script.pop(0)
                sleep = float(headers.pop("X-Test-Sleep", "0"))
                if sleep:
                    time.sleep(sleep)
                raw = body if isinstance(body, bytes) else json.dumps(body).encode()
                try:
                    self.send_response(status)
                    for name, value in headers.items():
                        self.send_header(name, value)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(raw)))
                    self.end_headers()
                    self.wfile.write(raw)
                except (BrokenPipeError, ConnectionResetError):
                    pass

            def log_message(self, *args: Any) -> None:
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self) -> FakeAdaptor:
        self.thread.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self.server.shutdown()
        self.server.server_close()


DELIVERY = "b53fd0d1-480c-424b-b8bb-49cb10509b13"
PAYLOAD: dict[str, Any] = {
    "schema_version": 1,
    "delivery_id": DELIVERY,
    "org_id": "41",
    "event_id": "720",
    "local_send_id": "1102",
    "sender": {"user_id": "9000", "discord_id": "123456789012345677"},
    "recipient": {
        "user_id": "9001",
        "org_user_id": None,
        "discord_id": "123456789012345678",
    },
    "sent_at": "2026-11-24T12:00:00.000000Z",
}
APPLIED = {
    "delivery_id": DELIVERY,
    "status": "applied",
    "applied": True,
    "durable": True,
    "contact_log_id": "8021",
}


class AdaptorClientTests(SimpleTestCase):
    def record(
        self, script: Script, payload: dict[str, Any] | None = None, **cfg: Any
    ) -> tuple[ReceiptOutcome, FakeAdaptor]:
        with FakeAdaptor(script) as server:
            client = PromotionAdaptorClient(_config(base_url=server.url, **cfg))
            result = client.record(payload or PAYLOAD)
        return result, server

    def test_applied_request_shape(self) -> None:
        result, server = self.record([(200, APPLIED, {})])
        self.assertEqual(result.kind, OutcomeKind.APPLIED)
        self.assertEqual(result.contact_log_id, 8021)
        (request,) = server.requests
        self.assertEqual(
            request["path"], "/api/v1/organizations/41/promotion/contact-receipts"
        )
        self.assertEqual(request["headers"]["Authorization"], f"Bearer {KEY}")
        self.assertEqual(
            request["headers"]["Content-Type"], "application/json; charset=utf-8"
        )
        self.assertEqual(request["body"], canonical_receipt_json(PAYLOAD).encode())

    def test_timeout_after_commit_retries_byte_identical_body(self) -> None:
        with FakeAdaptor(
            [(200, APPLIED, {"X-Test-Sleep": "1.0"}), (200, APPLIED, {})]
        ) as server:
            client = PromotionAdaptorClient(_config(base_url=server.url, timeout=0.2))
            first = client.record(PAYLOAD)
            second = client.record(PAYLOAD)
        self.assertEqual(first.kind, OutcomeKind.RETRYABLE)
        self.assertEqual(first.reason, "timeout")
        self.assertEqual(second.kind, OutcomeKind.APPLIED)
        self.assertEqual(server.requests[0]["body"], server.requests[1]["body"])

    def test_applied_requires_every_field_to_agree(self) -> None:
        bad_bodies = {
            "not_durable": {**APPLIED, "durable": False},
            "not_applied_flag": {**APPLIED, "applied": False},
            "missing_contact": {
                k: v for k, v in APPLIED.items() if k != "contact_log_id"
            },
            "numeric_contact": {**APPLIED, "contact_log_id": 8021},
            "zero_contact": {**APPLIED, "contact_log_id": "0"},
            "other_delivery": {
                **APPLIED,
                "delivery_id": "00000000-0000-4000-8000-000000000000",
            },
            "extra_field": {**APPLIED, "note": "x"},
            "reason_on_applied": {**APPLIED, "reason": "dry_run"},
            "unknown_status": {**APPLIED, "status": "synced"},
            "not_object": [APPLIED],
        }
        for name, body in bad_bodies.items():
            with self.subTest(name=name):
                result, _ = self.record([(200, body, {})])
                self.assertEqual(result.kind, OutcomeKind.INVALID_RESPONSE)
                self.assertIsNone(result.contact_log_id)

    def test_malformed_and_duplicate_key_bodies_are_invalid(self) -> None:
        dup = (
            b'{"delivery_id":"' + DELIVERY.encode() + b'","status":"applied",'
            b'"applied":true,"durable":true,"contact_log_id":"8021",'
            b'"applied":true}'
        )
        for body in (b"{", b"", dup, b'{"a":1} {"b":2}'):
            with self.subTest(body=body):
                result, _ = self.record([(200, body, {})])
                self.assertEqual(result.kind, OutcomeKind.INVALID_RESPONSE)

    def test_non_200_success_status_is_not_applied(self) -> None:
        for status in (201, 202, 204):
            with self.subTest(status=status):
                body: Any = b"" if status == 204 else APPLIED
                result, _ = self.record([(status, body, {})])
                self.assertEqual(result.kind, OutcomeKind.INVALID_RESPONSE)

    def test_already_contacted_is_its_own_outcome(self) -> None:
        body = {
            "delivery_id": DELIVERY,
            "status": "already_contacted",
            "applied": False,
            "durable": False,
            "contact_log_id": "8000",
        }
        result, _ = self.record([(200, body, {})])
        self.assertEqual(result.kind, OutcomeKind.ALREADY_CONTACTED)
        self.assertEqual(result.contact_log_id, 8000)
        contradictory = {**body, "applied": True}
        result, _ = self.record([(200, contradictory, {})])
        self.assertEqual(result.kind, OutcomeKind.INVALID_RESPONSE)

    def test_not_applied_answers(self) -> None:
        for reason in ("writeback_disabled", "dry_run"):
            body = {
                "delivery_id": DELIVERY,
                "status": "not_applied",
                "reason": reason,
                "applied": False,
                "durable": False,
            }
            with self.subTest(reason=reason):
                result, _ = self.record([(409, body, {})])
                self.assertEqual(result.kind, OutcomeKind.NOT_APPLIED)
                self.assertEqual(result.reason, reason)
        # A not_applied body on 200 is contradictory.
        result, _ = self.record([(200, {**body, "reason": "dry_run"}, {})])
        self.assertEqual(result.kind, OutcomeKind.INVALID_RESPONSE)
        unknown = {**body, "reason": "something_else"}
        result, _ = self.record([(409, unknown, {})])
        self.assertEqual(result.kind, OutcomeKind.INVALID_RESPONSE)

    def test_error_envelopes(self) -> None:
        def envelope(code: str, **extra: Any) -> dict[str, Any]:
            return {
                "error": {"code": code, "message": "m", "request_id": "r1"},
                **extra,
            }

        cases = [
            (
                409,
                envelope(
                    "mapping_required",
                    mapping={"party": "sender", "reason": "identity_unknown"},
                ),
                OutcomeKind.MAPPING_REQUIRED,
                "mapping_required",
            ),
            (
                409,
                envelope("idempotency_conflict"),
                OutcomeKind.IDEMPOTENCY_CONFLICT,
                "idempotency_conflict",
            ),
            (
                409,
                envelope("conflict"),
                OutcomeKind.INVALID_RESPONSE,
                "invalid_response",
            ),
            (
                401,
                envelope("unauthorized"),
                OutcomeKind.UNAUTHORIZED,
                "adaptor_unauthorized",
            ),
            (403, envelope("forbidden"), OutcomeKind.FORBIDDEN, "adaptor_forbidden"),
            (400, envelope("bad_request"), OutcomeKind.REJECTED, "adaptor_rejected"),
            (404, envelope("not_found"), OutcomeKind.REJECTED, "adaptor_rejected"),
            (
                413,
                envelope("payload_too_large"),
                OutcomeKind.REJECTED,
                "adaptor_rejected",
            ),
            (
                503,
                envelope("unavailable"),
                OutcomeKind.RETRYABLE,
                "adaptor_unavailable",
            ),
            (500, envelope("internal"), OutcomeKind.RETRYABLE, "server_error"),
            (502, b"<html>bad gateway</html>", OutcomeKind.RETRYABLE, "server_error"),
            (302, b"", OutcomeKind.REJECTED, "adaptor_rejected"),
        ]
        for status, body, kind, reason in cases:
            with self.subTest(status=status, reason=reason):
                headers = (
                    {"Location": "http://127.0.0.1:1/elsewhere"}
                    if status == 302
                    else {}
                )
                result, server = self.record([(status, body, headers)])
                self.assertEqual(result.kind, kind)
                self.assertEqual(result.reason, reason)
                self.assertEqual(result.http_status, status)
                self.assertEqual(len(server.requests), 1)

    def test_rate_limit_reads_retry_after(self) -> None:
        body = {"error": {"code": "rate_limited", "message": "m", "request_id": "r"}}
        result, _ = self.record([(429, body, {"Retry-After": "45"})])
        self.assertEqual(result.kind, OutcomeKind.RETRYABLE)
        self.assertEqual(result.reason, "rate_limited")
        self.assertEqual(result.retry_after, 45.0)
        result, _ = self.record([(503, body, {"Retry-After": "soon"})])
        self.assertIsNone(result.retry_after)

    def test_connection_refused_is_retryable(self) -> None:
        with FakeAdaptor([]) as server:
            url = server.url
        result = PromotionAdaptorClient(_config(base_url=url)).record(PAYLOAD)
        self.assertEqual(result.kind, OutcomeKind.RETRYABLE)
        self.assertEqual(result.reason, "connection_error")

    def test_logs_never_carry_identities_or_the_key(self) -> None:
        with capture_logs() as logs:
            self.record(
                [
                    (
                        500,
                        {
                            "error": {
                                "code": "internal",
                                "message": PAYLOAD["sender"]["discord_id"],
                                "request_id": "r",
                            }
                        },
                        {},
                    )
                ]
            )
        self.assertTrue(logs)
        text = json.dumps(logs, default=str)
        for secret in (KEY, "123456789012345677", "123456789012345678", "9001"):
            self.assertNotIn(secret, text)

    def test_disabled_client_refuses_to_send(self) -> None:
        with self.assertRaises(ImproperlyConfigured):
            PromotionAdaptorClient(PromotionAdaptorConfig())


class AdaptorConfigTests(SimpleTestCase):
    def env(self, **values: str) -> dict[str, str]:
        return {f"PROMOTION_ADAPTOR_{k}": v for k, v in values.items()}

    def test_defaults_are_off(self) -> None:
        cfg = PromotionAdaptorConfig.from_env(environ={})
        self.assertFalse(cfg.enabled)
        self.assertEqual(cfg.base_url, "")
        self.assertEqual(cfg.api_key, "")
        self.assertEqual(cfg.timeout, 30.0)
        self.assertEqual(cfg.max_attempts, 5)
        self.assertEqual(cfg.retry_cap, 120.0)

    def test_enabled_https_with_key(self) -> None:
        cfg = PromotionAdaptorConfig.from_env(
            environ=self.env(
                ENABLED="true",
                BASE_URL="https://adaptor.example:8443/",
                API_KEY=KEY,
            )
        )
        self.assertTrue(cfg.enabled)
        self.assertEqual(cfg.base_url, "https://adaptor.example:8443")
        self.assertNotIn(KEY, repr(cfg))

    def test_key_file(self) -> None:
        import tempfile

        with tempfile.NamedTemporaryFile("w", suffix=".key") as fh:
            fh.write(KEY + "\n")
            fh.flush()
            cfg = PromotionAdaptorConfig.from_env(
                environ=self.env(
                    ENABLED="1", BASE_URL="http://127.0.0.1:8080", API_KEY_FILE=fh.name
                )
            )
        self.assertEqual(cfg.api_key, KEY)

    def test_rejections_never_echo_values(self) -> None:
        secret_host = "secret-host.internal"
        cases = {
            "http_non_loopback": self.env(
                ENABLED="1", BASE_URL=f"http://{secret_host}", API_KEY=KEY
            ),
            "missing_url": self.env(ENABLED="1", API_KEY=KEY),
            "path": self.env(
                ENABLED="1", BASE_URL=f"https://{secret_host}/x", API_KEY=KEY
            ),
            "query": self.env(
                ENABLED="1", BASE_URL=f"https://{secret_host}?a=1", API_KEY=KEY
            ),
            "userinfo": self.env(
                ENABLED="1", BASE_URL=f"https://u:p@{secret_host}", API_KEY=KEY
            ),
            "ftp": self.env(ENABLED="1", BASE_URL=f"ftp://{secret_host}", API_KEY=KEY),
            "missing_key": self.env(ENABLED="1", BASE_URL=f"https://{secret_host}"),
            "draftforge_token": self.env(
                ENABLED="1",
                BASE_URL=f"https://{secret_host}",
                API_KEY="dfk_" + secret_host,
            ),
            "both_keys": self.env(
                ENABLED="1",
                BASE_URL=f"https://{secret_host}",
                API_KEY=KEY,
                API_KEY_FILE="/nonexistent/" + secret_host,
            ),
            "missing_file": self.env(
                ENABLED="1",
                BASE_URL=f"https://{secret_host}",
                API_KEY_FILE="/nonexistent/" + secret_host,
            ),
            "timeout": self.env(TIMEOUT="0"),
            "timeout_text": self.env(TIMEOUT=secret_host),
            "attempts": self.env(MAX_ATTEMPTS="0"),
            "cap": self.env(RETRY_CAP="-1"),
        }
        for name, environ in cases.items():
            with self.subTest(name=name):
                with self.assertRaises(ImproperlyConfigured) as ctx:
                    PromotionAdaptorConfig.from_env(environ=environ)
                self.assertNotIn(secret_host, str(ctx.exception))
                self.assertNotIn(KEY, str(ctx.exception))

    def test_disabled_does_not_read_credentials(self) -> None:
        cfg = PromotionAdaptorConfig.from_env(
            environ=self.env(API_KEY_FILE="/nonexistent/key", BASE_URL="http://x")
        )
        self.assertFalse(cfg.enabled)
        self.assertEqual(cfg.api_key, "")
