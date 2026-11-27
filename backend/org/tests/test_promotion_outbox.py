"""Every recorded promotion DM gets its own outbox row in the same transaction.

The row is local-only: nothing here talks to the adaptor. It freezes the
contracted receipt payload when the identities are complete and keeps a
non-dispatchable reconciliation row when they are not.
"""

import socket
import uuid
from datetime import UTC, datetime
from unittest.mock import patch

from org.integration.outbox import enqueue_send, outbox_summary
from org.integration.receipts import canonical_receipt_hash
from org.models import ContributionEntry, OrgUser, PromoSend
from org.models_promotion_sync import OutboxState, PromotionContactOutbox
from org.promotion.services import undo_promo_send
from org.tests.test_promotion_sends import _SendFixture

_PAYLOAD_KEYS = {
    "schema_version",
    "delivery_id",
    "org_id",
    "event_id",
    "local_send_id",
    "sender",
    "recipient",
    "sent_at",
}


class _OutboxFixture(_SendFixture):
    def _row(self, send: PromoSend) -> PromotionContactOutbox:
        return PromotionContactOutbox.objects.get(
            organization=self.org, local_send_id=send.pk
        )


class EnqueueEverySendTest(_OutboxFixture):
    def test_every_send_has_distinct_outbox_even_without_award(self) -> None:
        first = self._send(self.promoter)
        repeat = self._send(self.promoter, text="Second nudge")
        other = self._send(self.promoter_b, text="From B")
        self.assertEqual(
            [first.earns_points, repeat.earns_points, other.earns_points],
            [True, False, False],
        )
        rows = [self._row(send) for send in (first, repeat, other)]
        self.assertEqual(len({row.pk for row in rows}), 3)
        self.assertEqual(len({row.delivery_id for row in rows}), 3)
        self.assertEqual(
            [row.local_send_id for row in rows], [first.pk, repeat.pk, other.pk]
        )
        for row in rows:
            self.assertEqual(row.state, OutboxState.PENDING)
            self.assertEqual(row.attempts, 0)
            self.assertIsNotNone(row.due_at)
            self.assertIsNone(row.lease_token)
            self.assertIsNone(row.applied_contact_log_id)

    def test_payload_matches_contract_and_actual_sender(self) -> None:
        org_user, _ = OrgUser.objects.get_or_create(
            user=self.recipient, organization=self.org
        )
        send = self._send(self.promoter_b)
        row = self._row(send)
        self.assertEqual(set(row.payload), _PAYLOAD_KEYS)
        self.assertEqual(row.payload["schema_version"], 1)
        self.assertEqual(row.payload["delivery_id"], str(row.delivery_id))
        self.assertEqual(
            str(uuid.UUID(row.payload["delivery_id"])), str(row.delivery_id)
        )
        self.assertEqual(row.payload["org_id"], str(self.org.pk))
        self.assertEqual(row.payload["event_id"], str(self.event.pk))
        self.assertEqual(row.payload["local_send_id"], str(send.pk))
        self.assertEqual(
            row.payload["sender"],
            {
                "user_id": str(self.promoter_b.pk),
                "discord_id": self.promoter_b.discordId,
            },
        )
        self.assertEqual(
            row.payload["recipient"],
            {
                "user_id": str(self.recipient.pk),
                "org_user_id": str(org_user.pk),
                "discord_id": self.recipient.discordId,
            },
        )
        sent_at = datetime.strptime(row.payload["sent_at"], "%Y-%m-%dT%H:%M:%S.%fZ")
        self.assertEqual(sent_at.replace(tzinfo=UTC), send.sent_at)
        self.assertEqual(row.payload_hash, canonical_receipt_hash(row.payload))
        self.assertEqual(row.sender_user_id, self.promoter_b.pk)
        self.assertEqual(row.recipient_user_id, self.recipient.pk)
        self.assertEqual(row.event_id, self.event.pk)

    def test_recipient_without_membership_has_null_org_user(self) -> None:
        OrgUser.objects.filter(user=self.recipient, organization=self.org).delete()
        row = self._row(self._send(self.promoter))
        self.assertIsNone(row.payload["recipient"]["org_user_id"])
        self.assertFalse(
            OrgUser.objects.filter(user=self.recipient, organization=self.org).exists()
        )

    def test_outbox_never_contains_text_template_or_names(self) -> None:
        send = self._send(
            self.promoter, template=self.template, text="Secret pitch for ps_recipient"
        )
        row = self._row(send)
        stored = repr(
            {
                field.attname: getattr(row, field.attname)
                for field in PromotionContactOutbox._meta.concrete_fields
            }
        )
        for forbidden in (
            "Secret pitch",
            self.recipient.username,
            self.promoter.username,
            self.recipient.discordUsername,
            "template",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, stored)

    def test_enqueue_is_idempotent_for_the_same_send(self) -> None:
        send = self._send(self.promoter)
        row = self._row(send)
        again = enqueue_send(send)
        self.assertEqual(again.pk, row.pk)
        self.assertEqual(again.delivery_id, row.delivery_id)
        self.assertEqual(
            PromotionContactOutbox.objects.filter(local_send_id=send.pk).count(), 1
        )

    def test_sender_missing_discord_retains_reconciliation_without_breaking_legacy_send(
        self,
    ) -> None:
        self.promoter.discordId = None
        self.promoter.save()
        send = self._send(self.promoter)
        self.assertTrue(PromoSend.objects.filter(pk=send.pk).exists())
        self.assertTrue(send.earns_points)
        self.assertEqual(
            ContributionEntry.objects.nocache().filter(promo_send=send).count(), 1
        )
        row = self._row(send)
        self.assertEqual(row.state, OutboxState.RECONCILIATION_REQUIRED)
        self.assertEqual(row.last_reason, "sender_discord_missing")
        self.assertIsNone(row.payload)
        self.assertEqual(row.payload_hash, "")
        self.assertIsNone(row.due_at)
        self.assertEqual(row.sender_user_id, self.promoter.pk)
        self.assertEqual(row.recipient_user_id, self.recipient.pk)

    def test_no_automatic_backfill_for_old_sends(self) -> None:
        legacy = PromoSend.objects.create(
            organization=self.org,
            event=self.event,
            recipient=self.recipient,
            sender=self.promoter,
            text="legacy",
        )
        self.assertFalse(
            PromotionContactOutbox.objects.filter(local_send_id=legacy.pk).exists()
        )


class UndoAndSummaryTest(_OutboxFixture):
    def test_undo_preserves_original_payload_key_and_delivery(self) -> None:
        send = self._send(self.promoter)
        before = self._row(send)
        undo_promo_send(send, actor=self.promoter)
        self.assertFalse(PromoSend.objects.filter(pk=before.local_send_id).exists())
        after = PromotionContactOutbox.objects.get(pk=before.pk)
        self.assertEqual(after.delivery_id, before.delivery_id)
        self.assertEqual(after.local_send_id, before.local_send_id)
        self.assertEqual(after.payload, before.payload)
        self.assertEqual(after.payload_hash, before.payload_hash)
        self.assertEqual(after.state, OutboxState.PENDING)

    def test_outbox_summary_reports_state_without_claiming_success(self) -> None:
        send = self._send(self.promoter)
        row = self._row(send)
        self.assertEqual(
            outbox_summary(send.pk, self.org.pk),
            {
                "state": "pending",
                "reason": None,
                "delivery_id": str(row.delivery_id),
            },
        )

    def test_outbox_summary_is_org_scoped(self) -> None:
        send = self._send(self.promoter)
        self.assertEqual(
            outbox_summary(send.pk, self.other_org.pk),
            {"state": None, "reason": None, "delivery_id": None},
        )


class NoNetworkInSendTransactionTest(_OutboxFixture):
    def test_no_network_in_send_transaction(self) -> None:
        def refuse(*args: object, **kwargs: object) -> None:
            raise AssertionError("network used while recording a send")

        with (
            patch.object(socket.socket, "connect", refuse),
            patch.object(socket, "create_connection", refuse),
            patch("urllib.request.urlopen", refuse),
            patch("requests.sessions.Session.request", refuse),
        ):
            send = self._send(self.promoter)
        self.assertEqual(self._row(send).state, OutboxState.PENDING)


class SendAwardOutboxAtomicityTest(_SendFixture):
    def test_send_award_outbox_rollback_together(self) -> None:
        with (
            patch(
                "org.promotion.services.enqueue_send",
                side_effect=RuntimeError("outbox down"),
            ),
            self.assertRaises(RuntimeError),
        ):
            self._send(self.promoter)
        self.assertFalse(PromoSend.objects.exists())
        self.assertFalse(ContributionEntry.objects.nocache().exists())
        self.assertFalse(PromotionContactOutbox.objects.exists())

    def test_award_failure_rolls_back_outbox(self) -> None:
        with (
            patch(
                "org.promotion.services.award_entry",
                side_effect=RuntimeError("ledger down"),
            ),
            self.assertRaises(RuntimeError),
        ):
            self._send(self.promoter)
        self.assertFalse(PromoSend.objects.exists())
        self.assertFalse(PromotionContactOutbox.objects.exists())
