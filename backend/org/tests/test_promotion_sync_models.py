"""Durable models behind the promotion contact sync.

``ExternalPromotionReceipt`` keeps immutable source facts apart from the
mutable DraftForge association; ``PromotionContactOutbox`` keeps one row per
recorded DM that outlives the ``PromoSend`` it came from. The hashing tests
pin the same digests as the adaptor's Go golden fixtures.
"""

import json
from datetime import UTC, date, datetime
from pathlib import Path

from django.db import IntegrityError, transaction
from django.utils import timezone
from django_test_migrations.contrib.unittest_case import MigratorTestCase

from events.models import Event
from org.contributions.kinds import ContributionKind
from org.integration.receipts import (
    ImmutableFieldError,
    canonical_receipt_hash,
    canonical_receipt_json,
    import_source_hash,
)
from org.models import ContributionEntry, OrgLog, OrgUser, PromoSend
from org.models_promotion_sync import (
    AssociationReason,
    AssociationState,
    ContactMethod,
    ContactReason,
    ExternalPromotionReceipt,
    OutboxState,
    PointReason,
    PointStatus,
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

    def test_import_source_hash_excludes_discord_ids(self) -> None:
        golden = _golden("import_source_hash.json")
        base = golden["cases"][0]["entry"]
        digest = import_source_hash(base, source=golden["source"])
        self.assertEqual(digest, golden["cases"][0]["hash"])
        for field, value in (
            ("target_discord_id", "123456789012345679"),
            ("promoter_discord_id", None),
        ):
            with self.subTest(field=field):
                self.assertEqual(
                    import_source_hash({**base, field: value}, source="contact_log"),
                    digest,
                )

    def test_import_source_hash_changes_with_source_facts(self) -> None:
        base = _golden("import_source_hash.json")["cases"][0]["entry"]
        digest = import_source_hash(base, source="contact_log")
        for field, value in (
            ("source_contact_id", "1999"),
            ("recorded_at", "2026-11-24T18:30:01Z"),
            ("contact_date_ny", "2026-11-25"),
            ("contact_method", "OTHER"),
            ("contact_reason", "FOLLOW_UP"),
            ("occasion_id", "78"),
            ("forced", True),
        ):
            with self.subTest(field=field):
                self.assertNotEqual(
                    import_source_hash({**base, field: value}, source="contact_log"),
                    digest,
                )


class ExternalPromotionReceiptModelTest(_SendFixture):
    def setUp(self) -> None:
        super().setUp()
        self.other_event = Event.objects.create(
            organization=self.org,
            name="Receipt Other Event",
            scheduled_at=timezone.now(),
            created_by=self.owner,
        )

    def _receipt(self, **overrides: object) -> ExternalPromotionReceipt:
        fields: dict[str, object] = {
            "organization": self.org,
            "source": ReceiptSource.CONTACT_LOG,
            "source_contact_id": 8021,
            "event": self.event,
            "discord_id": "123456789012345678",
            "recorded_at": datetime(2026, 11, 24, 11, 30, tzinfo=UTC),
            "contact_date_ny": date(2026, 11, 24),
            "contact_method": ContactMethod.DISCORD_DM,
            "contact_reason": ContactReason.EVENT_INVITE,
            "occasion_id": 88,
            "forced": False,
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

    def test_source_facts_immutable_outside_bypass(self) -> None:
        receipt = self._receipt()
        changes: dict[str, object] = {
            "recorded_at": datetime(2026, 11, 24, 12, 0, tzinfo=UTC),
            "contact_date_ny": date(2026, 11, 25),
            "contact_method": ContactMethod.OTHER,
            "contact_reason": ContactReason.FOLLOW_UP,
            "occasion_id": 89,
            "forced": True,
            "source_hash": "b" * 64,
            "discord_id": "123456789012345679",
            "promoter_discord_id": "223456789012345678",
            "event": self.other_event,
        }
        for field, value in changes.items():
            with self.subTest(field=field):
                setattr(receipt, field, value)
                with self.assertRaises(ImmutableFieldError):
                    receipt.save(update_fields=[field])
                with self.assertRaises(ImmutableFieldError):
                    ExternalPromotionReceipt.objects.filter(pk=receipt.pk).update(
                        **{field: value}
                    )
                with self.assertRaises(ImmutableFieldError):
                    ExternalPromotionReceipt.objects.bulk_update([receipt], [field])
                receipt.refresh_from_db()
        with self.assertRaises(ImmutableFieldError):
            receipt.save()
        self.assertEqual(receipt.source_hash, "a" * 64)
        self.assertEqual(receipt.event_id, self.event.pk)

    def test_identity_fields_immutable_even_in_bypass(self) -> None:
        receipt = self._receipt()
        with ExternalPromotionReceipt.source_update():
            for field, value in (
                ("source_contact_id", 9999),
                ("organization", self.other_org),
                ("first_imported_at", timezone.now()),
            ):
                with self.subTest(field=field):
                    setattr(receipt, field, value)
                    with self.assertRaises(ImmutableFieldError):
                        receipt.save(update_fields=[field])
                    receipt.refresh_from_db()

    def test_source_update_bypass_allows_supersede_fields(self) -> None:
        receipt = self._receipt()
        fields = [
            "recorded_at",
            "contact_date_ny",
            "contact_reason",
            "occasion_id",
            "source_hash",
            "discord_id",
            "promoter_discord_id",
            "event",
            "source_revision",
            "source_updated_at",
        ]
        with ExternalPromotionReceipt.source_update():
            receipt.recorded_at = datetime(2026, 11, 24, 12, 0, tzinfo=UTC)
            receipt.contact_date_ny = date(2026, 11, 25)
            receipt.contact_reason = ContactReason.GENERAL
            receipt.occasion_id = 89
            receipt.source_hash = "b" * 64
            receipt.discord_id = "123456789012345679"
            receipt.promoter_discord_id = "223456789012345678"
            receipt.event = self.other_event
            receipt.source_revision = 1
            receipt.source_updated_at = timezone.now()
            receipt.save(update_fields=fields)
            ExternalPromotionReceipt.objects.filter(pk=receipt.pk).update(forced=True)
        receipt.refresh_from_db()
        self.assertEqual(receipt.source_hash, "b" * 64)
        self.assertEqual(receipt.event_id, self.other_event.pk)
        self.assertEqual(receipt.promoter_discord_id, "223456789012345678")
        self.assertTrue(receipt.forced)
        self.assertEqual(receipt.source_revision, 1)
        receipt.source_hash = "c" * 64
        with self.assertRaises(ImmutableFieldError):
            receipt.save(update_fields=["source_hash"])

    def test_source_update_bypass_resets_after_error(self) -> None:
        receipt = self._receipt()
        with self.assertRaises(RuntimeError):
            with ExternalPromotionReceipt.source_update():
                raise RuntimeError("boom")
        receipt.source_hash = "b" * 64
        with self.assertRaises(ImmutableFieldError):
            receipt.save(update_fields=["source_hash"])

    def test_new_field_defaults(self) -> None:
        receipt = self._receipt()
        receipt.refresh_from_db()
        self.assertEqual(receipt.point_status, PointStatus.NOT_APPLICABLE)
        self.assertEqual(receipt.point_reason, PointReason.NONE)
        self.assertFalse(receipt.holds_point)
        self.assertIsNone(receipt.origin_send_id)
        self.assertEqual(receipt.promoter_discord_id, "")
        self.assertEqual(receipt.source_revision, 0)
        self.assertIsNone(receipt.source_updated_at)
        self.assertIsNone(receipt.retracted_at)
        self.assertIsNone(receipt.event_date)
        self.assertFalse(hasattr(receipt, "linkage"))

    def _assert_check(self, name: str, **overrides: object) -> None:
        with self.assertRaisesMessage(IntegrityError, name), transaction.atomic():
            self._receipt(**overrides)

    def test_point_unique_per_event_and_player(self) -> None:
        held = {"holds_point": True, "point_status": PointStatus.CREDITED}
        self._receipt(**held)
        with self.assertRaises(IntegrityError), transaction.atomic():
            self._receipt(source_contact_id=8022, **held)
        self._receipt(
            source_contact_id=8023,
            holds_point=False,
            point_status=PointStatus.DUPLICATE,
        )
        self._receipt(source_contact_id=8024, event=self.other_event, **held)
        names = {c.name for c in ExternalPromotionReceipt._meta.constraints}
        self.assertIn("uniq_external_promo_point", names)

    def test_occasion_xor_date_constraint(self) -> None:
        self._assert_check(
            "ck_ext_promo_rcpt_occasion_xor_date", occasion_id=None, event_date=None
        )
        self._assert_check(
            "ck_ext_promo_rcpt_occasion_xor_date",
            event_date=datetime(2026, 11, 30, tzinfo=UTC),
        )
        self._receipt(occasion_id=None, event_date=datetime(2026, 11, 30, tzinfo=UTC))

    def test_forced_needs_occasion_constraint(self) -> None:
        self._assert_check(
            "ck_ext_promo_rcpt_forced_occasion",
            forced=True,
            occasion_id=None,
            event_date=datetime(2026, 11, 30, tzinfo=UTC),
        )
        self._receipt(forced=True)

    def test_point_has_event_constraint(self) -> None:
        self._assert_check(
            "ck_ext_promo_rcpt_point_has_event",
            event=None,
            holds_point=True,
            point_status=PointStatus.UNCREDITED,
            point_reason=PointReason.SELF_CONTACT,
        )

    def test_point_status_constraint(self) -> None:
        self._assert_check(
            "ck_ext_promo_rcpt_point_status",
            holds_point=True,
            point_status=PointStatus.DUPLICATE,
        )
        self._assert_check(
            "ck_ext_promo_rcpt_point_status",
            holds_point=False,
            point_status=PointStatus.CREDITED,
        )

    def test_retracted_constraint(self) -> None:
        self._assert_check("ck_ext_promo_rcpt_retracted", retracted_at=timezone.now())
        self._assert_check(
            "ck_ext_promo_rcpt_retracted", point_status=PointStatus.RETRACTED
        )
        self._receipt(point_status=PointStatus.RETRACTED, retracted_at=timezone.now())

    def test_phase_b_indexes_exist(self) -> None:
        names = {index.name for index in ExternalPromotionReceipt._meta.indexes}
        self.assertTrue(
            {
                "ext_promo_rcpt_event_discord",
                "ext_promo_rcpt_org_discord_at",
                "ext_promo_rcpt_org_date",
            }
            <= names
        )

    def test_event_deletion_keeps_contact(self) -> None:
        receipt = self._receipt()
        self.event.delete()
        receipt.refresh_from_db()
        self.assertIsNone(receipt.event_id)
        self.assertEqual(receipt.source_contact_id, 8021)

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


class LedgerReversalModelTest(_SendFixture):
    """``ContributionEntry`` fields that link credits, voids and restores."""

    def setUp(self) -> None:
        super().setUp()
        self.org_user, _ = OrgUser.objects.get_or_create(
            user=self.promoter, organization=self.org
        )
        self.receipt = ExternalPromotionReceipt.objects.create(
            organization=self.org,
            source=ReceiptSource.CONTACT_LOG,
            source_contact_id=8021,
            event=self.event,
            discord_id="123456789012345678",
            recorded_at=datetime(2026, 11, 24, 11, 30, tzinfo=UTC),
            contact_date_ny=date(2026, 11, 24),
            contact_method=ContactMethod.DISCORD_DM,
            contact_reason=ContactReason.EVENT_INVITE,
            occasion_id=88,
            forced=False,
            source_hash="a" * 64,
        )

    def _entry(self, **overrides: object) -> ContributionEntry:
        fields: dict[str, object] = {
            "organization": self.org,
            "org_user": self.org_user,
            "kind": ContributionKind.PROMO_MESSAGE,
            "points": 1,
            "event": self.event,
            "occurred_at": datetime(2026, 11, 24, 11, 30, tzinfo=UTC),
        }
        fields.update(overrides)
        return ContributionEntry.objects.create(**fields)

    def test_uniq_external_promo_credit(self) -> None:
        first = self._entry(external_contact=self.receipt)
        with self.assertRaises(IntegrityError), transaction.atomic():
            self._entry(external_contact=self.receipt)
        ContributionEntry.objects.filter(pk=first.pk).update(voided=True)
        second = self._entry(external_contact=self.receipt)
        self.assertEqual(
            set(self.receipt.ledger_entries.values_list("pk", flat=True)),
            {first.pk, second.pk},
        )

    def test_reversal_link_constraint(self) -> None:
        credit = self._entry()
        for kind in (ContributionKind.PROMO_VOID, ContributionKind.PROMO_RESTORE):
            with self.subTest(kind=kind):
                with (
                    self.assertRaisesMessage(IntegrityError, "ck_promo_reversal_link"),
                    transaction.atomic(),
                ):
                    self._entry(kind=kind, points=-1)
        with (
            self.assertRaisesMessage(IntegrityError, "ck_promo_reversal_link"),
            transaction.atomic(),
        ):
            self._entry(kind=ContributionKind.MANUAL, reversal_of=credit, event=None)
        void = self._entry(
            kind=ContributionKind.PROMO_VOID, points=-1, reversal_of=credit
        )
        self.assertEqual(list(credit.reversals.all()), [void])

    def test_reversal_not_voided_constraint(self) -> None:
        credit = self._entry()
        with (
            self.assertRaisesMessage(IntegrityError, "ck_promo_reversal_not_voided"),
            transaction.atomic(),
        ):
            self._entry(
                kind=ContributionKind.PROMO_VOID,
                points=-1,
                reversal_of=credit,
                voided=True,
            )

    def test_reversal_cascade_on_entry_delete(self) -> None:
        credit = self._entry()
        void = self._entry(
            kind=ContributionKind.PROMO_VOID, points=-1, reversal_of=credit
        )
        restore = self._entry(
            kind=ContributionKind.PROMO_RESTORE, points=1, reversal_of=credit
        )
        credit.delete()
        self.assertFalse(
            ContributionEntry.objects.filter(pk__in=[void.pk, restore.pk]).exists()
        )

    def test_external_contact_deletion_keeps_entry(self) -> None:
        credit = self._entry(external_contact=self.receipt)
        self.receipt.delete()
        credit.refresh_from_db()
        self.assertIsNone(credit.external_contact_id)
        self.assertFalse(credit.voided)

    def test_ledger_audit_actions(self) -> None:
        actions = dict(OrgLog.ACTION_CHOICES)
        self.assertEqual(actions["void_promo_point"], "Void Promotion Point")
        self.assertEqual(actions["restore_promo_point"], "Restore Promotion Point")
        self.assertEqual(actions["update_external_contact"], "Update External Contact")


class PromoSendSnapshotTest(_SendFixture):
    def test_recipient_discord_id_set_at_send_and_immutable(self) -> None:
        discord_id = self.recipient.discordId
        send = self._send(self.promoter)
        send.refresh_from_db()
        self.assertEqual(send.recipient_discord_id, discord_id)
        self.recipient.discordId = "999000000000000001"
        self.recipient.save()
        send.refresh_from_db()
        self.assertEqual(send.recipient_discord_id, discord_id)
        send.recipient_discord_id = "999000000000000001"
        with self.assertRaises(ImmutableFieldError):
            send.save(update_fields=["recipient_discord_id"])
        with self.assertRaises(ImmutableFieldError):
            send.save()
        send.refresh_from_db()
        self.assertEqual(send.recipient_discord_id, discord_id)
        send.earns_points = False
        send.save(update_fields=["earns_points"])
        send.save()

    def test_recipient_without_discord_snapshots_blank(self) -> None:
        send = PromoSend.objects.create(
            organization=self.org,
            event=self.event,
            recipient=self.no_discord,
            sender=self.promoter,
            text="hi",
        )
        self.assertEqual(send.recipient_discord_id, "")


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
    migrate_from = ("org", "0026_api_token_operations")
    migrate_to = ("org", "0027_promotion_sync_receipts")

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
