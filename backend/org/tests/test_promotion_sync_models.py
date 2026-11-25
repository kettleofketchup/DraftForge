"""Durable models behind the promotion contact sync.

``ExternalPromotionReceipt`` keeps immutable source facts apart from the
mutable DraftForge association; ``PromotionContactOutbox`` keeps one row per
recorded DM that outlives the ``PromoSend`` it came from. The hashing tests
pin the same digests as the adaptor's Go golden fixtures.
"""

import json
from datetime import UTC, datetime
from pathlib import Path

from django.db import IntegrityError, transaction
from django.utils import timezone
from django_test_migrations.contrib.unittest_case import MigratorTestCase

from events.models import Event
from org.integration.receipts import (
    ImmutableFieldError,
    canonical_receipt_hash,
    canonical_receipt_json,
    import_source_hash,
)
from org.models import OrgUser, PromoSend
from org.models_promotion_sync import (
    AssociationReason,
    AssociationState,
    ContactLinkage,
    ContactMethod,
    ExternalPromotionReceipt,
    OutboxState,
    PromotionContactOutbox,
    ReceiptSource,
)
from org.tests.test_promotion_sends import _SendFixture

GOLDEN = Path(__file__).parent / "golden"


def _golden(name: str) -> dict:
    return json.loads((GOLDEN / name).read_text(encoding="utf-8"))


class CanonicalHashGoldenTest(_SendFixture):
    def test_receipt_hash_matches_go_golden(self) -> None:
        golden = _golden("receipt_hash.json")
        self.assertEqual(canonical_receipt_json(golden["receipt"]), golden["canonical"])
        self.assertEqual(canonical_receipt_hash(golden["receipt"]), golden["sha256"])

    def test_import_source_hash_excludes_associations(self) -> None:
        golden = _golden("import_source_hash.json")
        users = {entry["user_id"] for entry in golden["entries"]}
        org_users = {entry["org_user_id"] for entry in golden["entries"]}
        self.assertEqual(users, {None, "9001"})
        self.assertEqual(org_users, {None, "9100"})
        for index, entry in enumerate(golden["entries"]):
            with self.subTest(index=index):
                self.assertEqual(
                    import_source_hash(entry, source=golden["source"]),
                    golden["sha256"],
                )

    def test_import_source_hash_changes_with_source_facts(self) -> None:
        base = _golden("import_source_hash.json")["entries"][0]
        digest = import_source_hash(base, source="contact_log")
        for field, value in (
            ("source_contact_id", "8022"),
            ("event_id", "721"),
            ("discord_id", "123456789012345679"),
            ("recorded_at", "2026-11-24T11:30:01Z"),
            ("contact_method", "OTHER"),
            ("linkage", "event_date"),
        ):
            with self.subTest(field=field):
                self.assertNotEqual(
                    import_source_hash({**base, field: value}, source="contact_log"),
                    digest,
                )


class ExternalPromotionReceiptModelTest(_SendFixture):
    def _receipt(self, **overrides: object) -> ExternalPromotionReceipt:
        fields: dict[str, object] = {
            "organization": self.org,
            "source": ReceiptSource.CONTACT_LOG,
            "source_contact_id": 8021,
            "event": self.event,
            "discord_id": "123456789012345678",
            "recorded_at": datetime(2026, 11, 24, 11, 30, tzinfo=UTC),
            "contact_method": ContactMethod.DISCORD_DM,
            "linkage": ContactLinkage.OCCASION,
            "source_hash": "a" * 64,
        }
        fields.update(overrides)
        return ExternalPromotionReceipt.objects.create(**fields)

    def test_null_user_receipt_defaults_to_unresolved(self) -> None:
        receipt = self._receipt()
        receipt.refresh_from_db()
        self.assertIsNone(receipt.user_id)
        self.assertIsNone(receipt.org_user_id)
        self.assertEqual(receipt.association_state, AssociationState.UNRESOLVED)
        self.assertEqual(receipt.association_reason, AssociationReason.NONE)
        self.assertIsNotNone(receipt.first_imported_at)

    def test_source_contact_id_unique_per_org_and_source(self) -> None:
        self._receipt()
        with self.assertRaises(IntegrityError), transaction.atomic():
            self._receipt(discord_id="123456789012345679")
        self._receipt(organization=self.other_org)

    def test_event_discord_index_exists(self) -> None:
        indexed = [
            tuple(index.fields) for index in ExternalPromotionReceipt._meta.indexes
        ]
        self.assertIn(("event", "discord_id"), indexed)

    def test_association_fields_are_updatable(self) -> None:
        receipt = self._receipt()
        org_user, _ = OrgUser.objects.get_or_create(
            user=self.recipient, organization=self.org
        )
        receipt.user = self.recipient
        receipt.org_user = org_user
        receipt.association_state = AssociationState.LINKED
        receipt.association_updated_at = timezone.now()
        receipt.save(
            update_fields=[
                "user",
                "org_user",
                "association_state",
                "association_updated_at",
            ]
        )
        receipt.refresh_from_db()
        self.assertEqual(receipt.user_id, self.recipient.pk)
        self.assertEqual(receipt.org_user_id, org_user.pk)
        self.assertEqual(receipt.association_state, AssociationState.LINKED)
        self.assertEqual(receipt.source_hash, "a" * 64)

    def test_source_facts_are_immutable(self) -> None:
        receipt = self._receipt()
        receipt.source_hash = "b" * 64
        with self.assertRaises(ImmutableFieldError):
            receipt.save(update_fields=["source_hash"])
        with self.assertRaises(ImmutableFieldError):
            receipt.save()
        with self.assertRaises(ImmutableFieldError):
            ExternalPromotionReceipt.objects.filter(pk=receipt.pk).update(
                recorded_at=timezone.now()
            )
        with self.assertRaises(ImmutableFieldError):
            ExternalPromotionReceipt.objects.bulk_update([receipt], ["source_hash"])
        receipt.refresh_from_db()
        self.assertEqual(receipt.source_hash, "a" * 64)

    def test_queryset_update_of_association_is_allowed(self) -> None:
        receipt = self._receipt()
        ExternalPromotionReceipt.objects.filter(pk=receipt.pk).update(
            association_state=AssociationState.QUARANTINED,
            association_reason=AssociationReason.DISCORD_OWNER_CHANGED,
        )
        receipt.refresh_from_db()
        self.assertEqual(receipt.association_state, AssociationState.QUARANTINED)

    def test_user_deletion_keeps_source_evidence(self) -> None:
        receipt = self._receipt(user=self.recipient)
        self.recipient.delete()
        receipt.refresh_from_db()
        self.assertIsNone(receipt.user_id)
        self.assertEqual(receipt.source_contact_id, 8021)


class PromotionContactOutboxModelTest(_SendFixture):
    def test_no_promo_send_foreign_keys(self) -> None:
        related = {
            field.related_model
            for field in PromotionContactOutbox._meta.get_fields()
            if field.is_relation
        }
        self.assertNotIn(PromoSend, related)
        self.assertNotIn(Event, related)

    def test_deleting_event_keeps_pending_outbox_row(self) -> None:
        send = self._send(self.promoter)
        row = PromotionContactOutbox.objects.get(local_send_id=send.pk)
        self.event.delete()
        row.refresh_from_db()
        self.assertEqual(row.state, OutboxState.PENDING)
        self.assertEqual(row.payload_hash, canonical_receipt_hash(row.payload))

    def test_deleting_send_keeps_outbox_row(self) -> None:
        send = self._send(self.promoter)
        send_id = send.pk
        row = PromotionContactOutbox.objects.get(local_send_id=send_id)
        send.delete()
        self.assertFalse(PromoSend.objects.filter(pk=send_id).exists())
        row.refresh_from_db()
        self.assertEqual(row.local_send_id, send_id)
        self.assertEqual(row.state, OutboxState.PENDING)

    def test_unique_local_send_per_org(self) -> None:
        send = self._send(self.promoter)
        row = PromotionContactOutbox.objects.get(local_send_id=send.pk)
        with self.assertRaises(IntegrityError), transaction.atomic():
            PromotionContactOutbox.objects.create(
                organization=self.org,
                local_send_id=send.pk,
                event_id=row.event_id,
                sent_at=row.sent_at,
            )

    def test_materialized_payload_is_frozen(self) -> None:
        send = self._send(self.promoter)
        row = PromotionContactOutbox.objects.get(local_send_id=send.pk)
        row.payload = {**row.payload, "sent_at": "2020-01-01T00:00:00Z"}
        with self.assertRaises(ImmutableFieldError):
            row.save(update_fields=["payload"])
        with self.assertRaises(ImmutableFieldError):
            PromotionContactOutbox.objects.filter(pk=row.pk).update(payload_hash="")
        row.refresh_from_db()
        self.assertEqual(row.payload_hash, canonical_receipt_hash(row.payload))


class PromotionSyncMigrationTest(MigratorTestCase):
    migrate_from = ("org", "0024_api_token_operations")
    migrate_to = ("org", "0025_promotion_sync_receipts")

    def prepare(self) -> None:
        apps = self.old_state.apps
        CustomUser = apps.get_model("app", "CustomUser")
        Organization = apps.get_model("org", "Organization")
        Event = apps.get_model("events", "Event")
        PromoSend = apps.get_model("org", "PromoSend")
        ContributionEntry = apps.get_model("org", "ContributionEntry")
        Token = apps.get_model("org", "OrgApiToken")
        owner = CustomUser.objects.create(username="mig_owner", discordId="1")
        recipient = CustomUser.objects.create(username="mig_rcpt", discordId="2")
        org = Organization.objects.create(name="Migration Org", owner=owner)
        event = Event.objects.create(
            organization=org,
            name="Old Event",
            scheduled_at=timezone.now(),
            created_by=owner,
        )
        send = PromoSend.objects.create(
            organization=org,
            event=event,
            recipient=recipient,
            sender=owner,
            text="old",
            earns_points=True,
        )
        self.send_pk = send.pk
        self.entry_pk = ContributionEntry.objects.create(
            organization=org,
            org_user=apps.get_model("org", "OrgUser").objects.create(
                user=owner, organization=org
            ),
            kind="promo_message",
            points=1,
            event=event,
            promo_send=send,
            occurred_at=timezone.now(),
        ).pk
        self.token_pk = Token.objects.create(
            organization=org,
            user=owner,
            name="legacy",
            prefix="mig123def456",
            secret_hash="0" * 64,
            operations=["mmr:read", "mmr:write"],
        ).pk

    def test_existing_data_kept_and_no_outbox_backfill(self) -> None:
        apps = self.new_state.apps
        send = apps.get_model("org", "PromoSend").objects.get(pk=self.send_pk)
        self.assertTrue(send.earns_points)
        entry = apps.get_model("org", "ContributionEntry").objects.get(pk=self.entry_pk)
        self.assertEqual(entry.promo_send_id, self.send_pk)
        self.assertFalse(
            apps.get_model("org", "PromotionContactOutbox").objects.exists()
        )
        self.assertFalse(
            apps.get_model("org", "ExternalPromotionReceipt").objects.exists()
        )
        token = apps.get_model("org", "OrgApiToken").objects.get(pk=self.token_pk)
        self.assertEqual(token.operations, ["mmr:read", "mmr:write"])
