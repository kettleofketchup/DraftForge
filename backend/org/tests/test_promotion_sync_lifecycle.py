"""Account merge, relink and deletion against imported SFG receipts.

A merge into the account that owns the receipt's Discord ID keeps the tick.
A merge or relink that would hand the receipt to a different Discord owner
quarantines it instead: the evidence stays, the tick goes. A merge also
moves the dropped account's open outbox rows to the kept account, so the
dropped account's delete cannot cancel a DM still owed to SFG. Deleting an
account quarantines its receipts and cancels its unsent outbox rows, and a
later replay of the same SFG contact cannot recreate the account or its
membership.
"""

from __future__ import annotations

import uuid
from datetime import timedelta

from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from app.models import CustomUser
from org.integration.lifecycle import (
    cancel_or_redact_promotion_identity,
    reconcile_promotion_identity,
)
from org.models import OrgUser, PromoSend
from org.models_promotion_sync import (
    AssociationReason,
    AssociationState,
    ImmutableFieldError,
    OutboxState,
    PromotionContactOutbox,
)
from org.promotion.services import record_promo_send
from org.tests.test_integration_contacts import GUILD_ONLY_ID, _ImportBase
from user.discord_accounts import merge_discord_accounts


class MergeTests(_ImportBase):
    def test_merge_into_verified_owner_keeps_tick(self) -> None:
        drop = self.non_member_player("m_drop")
        discord_id = drop.discordId
        self.imported([self.entry(8021, drop)])
        keep = self._user("m_keep")
        keep_ou = OrgUser.objects.create(user=keep, organization=self.org)
        CustomUser.objects.filter(pk=drop.pk).update(discordId=None)
        CustomUser.objects.filter(pk=keep.pk).update(discordId=discord_id)
        keep.refresh_from_db()
        drop.refresh_from_db()

        merge_discord_accounts(keep, drop)

        stored = self.receipt(8021)
        self.assertEqual(stored.user_id, keep.pk)
        self.assertEqual(stored.org_user_id, keep_ou.pk)
        self.assertEqual(stored.association_state, AssociationState.LINKED)
        self.assertTrue(self.ticked(discord_id, keep))

    def test_merge_into_other_discord_owner_quarantines(self) -> None:
        drop = self.non_member_player("q_drop")
        discord_id = drop.discordId
        self.imported([self.entry(8021, drop)])
        keep = self._user("q_keep")

        merge_discord_accounts(keep, drop)

        stored = self.receipt(8021)
        self.assertEqual(stored.association_state, AssociationState.QUARANTINED)
        self.assertEqual(
            stored.association_reason, AssociationReason.DISCORD_OWNER_CHANGED
        )
        self.assertIsNone(stored.user_id)
        self.assertEqual(stored.discord_id, discord_id)
        self.assertFalse(self.ticked(keep.discordId, keep))
        self.assertFalse(self.ticked(discord_id, None))

    def test_reconcile_leaves_other_users_receipts_alone(self) -> None:
        self.imported(
            [self.entry(8021, self.recipient), self.entry(8022, GUILD_ONLY_ID)]
        )
        keep = self._user("noop_keep")
        drop = self._user("noop_drop")
        reconcile_promotion_identity(keep, drop)
        self.assertEqual(self.receipt(8021).user_id, self.recipient.pk)
        self.assertEqual(self.receipt(8021).association_state, AssociationState.LINKED)
        self.assertIsNone(self.receipt(8022).user_id)

    def _take_over_discord(self, drop: CustomUser, name: str) -> CustomUser:
        """A fresh ``keep`` that now owns ``drop``'s Discord ID, as a merge expects."""
        keep = self._user(name)
        discord_id = drop.discordId
        CustomUser.objects.filter(pk=drop.pk).update(discordId=None)
        CustomUser.objects.filter(pk=keep.pk).update(discordId=discord_id)
        keep.refresh_from_db()
        drop.refresh_from_db()
        return keep

    def _send(self, sender: CustomUser, recipient: CustomUser) -> PromoSend:
        return record_promo_send(
            sender=sender,
            event=self.event,
            recipient=recipient,
            template=None,
            text="Hi",
        )

    @override_settings(DISCORD_BOT_TOKEN="test-bot-token")
    def test_merging_the_recipient_keeps_the_outbox_row_pending(self) -> None:
        drop = self.non_member_player("ob_rcpt_drop")
        send = self._send(self.users["promoter"], drop)
        before = PromotionContactOutbox.objects.get(local_send_id=send.pk)
        self.assertEqual(before.state, OutboxState.PENDING)
        keep = self._take_over_discord(drop, "ob_rcpt_keep")

        merge_discord_accounts(keep, drop)

        row = PromotionContactOutbox.objects.get(local_send_id=send.pk)
        self.assertEqual(PromoSend.objects.get(pk=send.pk).recipient_id, keep.pk)
        self.assertEqual(row.state, OutboxState.PENDING)
        self.assertEqual(row.last_reason, "")
        self.assertEqual(row.recipient_user_id, keep.pk)
        self.assertEqual(row.payload, before.payload)
        self.assertEqual(row.payload_hash, before.payload_hash)

    @override_settings(DISCORD_BOT_TOKEN="test-bot-token")
    def test_merging_the_sender_keeps_the_outbox_row_pending(self) -> None:
        drop = self.users["promoter"]
        send = self._send(drop, self.recipient)
        before = PromotionContactOutbox.objects.get(local_send_id=send.pk)
        self.assertEqual(before.state, OutboxState.PENDING)
        keep = self._take_over_discord(drop, "ob_sender_keep")

        merge_discord_accounts(keep, drop)

        row = PromotionContactOutbox.objects.get(local_send_id=send.pk)
        self.assertEqual(PromoSend.objects.get(pk=send.pk).sender_id, keep.pk)
        self.assertEqual(row.state, OutboxState.PENDING)
        self.assertEqual(row.sender_user_id, keep.pk)
        self.assertEqual(row.payload, before.payload)

    @override_settings(DISCORD_BOT_TOKEN="test-bot-token")
    def test_deleting_the_kept_account_after_a_merge_cancels_and_redacts(
        self,
    ) -> None:
        """The merge deletes ``drop`` but leaves the row owed to SFG; its
        payload still names ``drop``'s user ID, as recorded at send time.
        Deleting ``keep`` later must still find, cancel and redact that row,
        though no payload field names ``keep``.
        """
        drop = self.non_member_player("ob_md_drop")
        send = self._send(self.users["promoter"], drop)
        before = PromotionContactOutbox.objects.get(local_send_id=send.pk)
        keep = self._take_over_discord(drop, "ob_md_keep")
        drop_pk = drop.pk

        merge_discord_accounts(keep, drop)

        self.assertFalse(CustomUser.objects.filter(pk=drop_pk).exists())
        row = PromotionContactOutbox.objects.get(local_send_id=send.pk)
        self.assertEqual(row.state, OutboxState.PENDING)
        self.assertEqual(row.payload["recipient"]["user_id"], str(drop_pk))
        self.assertEqual(row.payload["recipient"]["discord_id"], keep.discordId)

        CustomUser.objects.get(pk=keep.pk).delete()

        row = PromotionContactOutbox.objects.get(local_send_id=send.pk)
        self.assertEqual(row.state, OutboxState.CANCELED)
        self.assertEqual(row.last_reason, "account_deleted")
        self.assertIsNone(row.payload)
        self.assertEqual(row.payload_hash, before.payload_hash)

    @override_settings(DISCORD_BOT_TOKEN="test-bot-token")
    def test_reconcile_leaves_terminal_outbox_rows_alone(self) -> None:
        drop = self.non_member_player("ob_term_drop")
        send = self._send(self.users["promoter"], drop)
        PromotionContactOutbox.objects.filter(local_send_id=send.pk).update(
            state=OutboxState.APPLIED
        )
        keep = self._user("ob_term_keep")
        reconcile_promotion_identity(keep, drop)
        row = PromotionContactOutbox.objects.get(local_send_id=send.pk)
        self.assertEqual(row.recipient_user_id, drop.pk)
        self.assertEqual(row.state, OutboxState.APPLIED)

    def test_relink_to_new_owner_does_not_transfer_tick(self) -> None:
        old_owner = self.non_member_player("relink_old")
        discord_id = old_owner.discordId
        self.imported([self.entry(8021, old_owner)])
        CustomUser.objects.filter(pk=old_owner.pk).update(
            discordId="880000000000000777"
        )
        new_owner = CustomUser.objects.create_user(
            username="relink_new", password="x", discordId=discord_id
        )
        self.assertFalse(self.ticked(discord_id, new_owner))
        body = self.imported([self.entry(8021, new_owner)])
        self.assertEqual(self.statuses(body), ["quarantined"])
        stored = self.receipt(8021)
        self.assertEqual(stored.user_id, old_owner.pk)
        self.assertEqual(stored.discord_id, discord_id)


class DeletionTests(_ImportBase):
    def _delete_via_api(self, user: CustomUser) -> None:
        client = APIClient()
        site_admin = self.users["site_admin"]
        client.force_authenticate(user=site_admin)
        resp = client.delete(f"/api/users/{user.pk}/")
        self.assertIn(resp.status_code, (200, 204), resp.content)
        self.assertFalse(CustomUser.objects.filter(pk=user.pk).exists())

    def test_deleted_account_quarantines_and_replay_cannot_recreate(self) -> None:
        player = self.non_member_player("deleted_player")
        OrgUser.objects.create(user=player, organization=self.org)
        discord_id = player.discordId
        self.imported([self.entry(8021, player)])

        self._delete_via_api(player)

        stored = self.receipt(8021)
        self.assertEqual(stored.association_state, AssociationState.QUARANTINED)
        self.assertEqual(stored.association_reason, AssociationReason.ACCOUNT_DELETED)
        self.assertIsNone(stored.user_id)
        self.assertIsNone(stored.org_user_id)
        self.assertFalse(self.ticked(discord_id, None))

        users, org_users = CustomUser.objects.count(), OrgUser.objects.count()
        body = self.imported([self.entry(8021, discord_id)])
        self.assertEqual(self.statuses(body), ["quarantined"])
        self.assertEqual(CustomUser.objects.count(), users)
        self.assertEqual(OrgUser.objects.count(), org_users)
        self.assertEqual(self.receipt(8021).source_hash, stored.source_hash)

    def test_admin_delete_runs_the_same_hook(self) -> None:
        from django.contrib.admin.sites import site

        from app.admin import CustomUserAdmin

        player = self.non_member_player("admin_deleted")
        self.imported([self.entry(8021, player)])
        admin = CustomUserAdmin(CustomUser, site)
        request = type("R", (), {"user": self.users["site_admin"]})()
        admin.delete_model(request, player)
        self.assertEqual(
            self.receipt(8021).association_reason, AssociationReason.ACCOUNT_DELETED
        )

    def test_direct_model_delete_runs_the_same_hook(self) -> None:
        player = self.non_member_player("model_deleted")
        discord_id = player.discordId
        self.imported([self.entry(8021, player)])
        CustomUser.objects.get(pk=player.pk).delete()
        stored = self.receipt(8021)
        self.assertEqual(stored.association_state, AssociationState.QUARANTINED)
        self.assertEqual(stored.association_reason, AssociationReason.ACCOUNT_DELETED)
        self.assertIsNone(stored.user_id)

        # A later account that owns the same Discord ID gets no tick, and a
        # replay naming it cannot turn the receipt back into a link.
        heir = self._user("model_heir")
        heir.discordId = discord_id
        heir.save()
        self.assertFalse(self.ticked(discord_id, heir))
        body = self.imported([self.entry(8021, heir)])
        self.assertEqual(self.statuses(body), ["quarantined"])

    def test_queryset_delete_runs_the_same_hook(self) -> None:
        player = self.non_member_player("bulk_deleted")
        self.imported([self.entry(8021, player)])
        CustomUser.objects.filter(pk=player.pk).delete()
        self.assertEqual(
            self.receipt(8021).association_reason, AssociationReason.ACCOUNT_DELETED
        )

    @override_settings(DISCORD_BOT_TOKEN="test-bot-token")
    def test_deletion_cancels_unsent_outbox_rows_only(self) -> None:
        send = record_promo_send(
            sender=self.users["promoter"],
            event=self.event,
            recipient=self.recipient,
            template=None,
            text="Hi",
        )
        applied = record_promo_send(
            sender=self.users["promoter"],
            event=self.event,
            recipient=self.non_member_player("outbox_other"),
            template=None,
            text="Hi",
        )
        in_flight = record_promo_send(
            sender=self.users["promoter"],
            event=self.event,
            recipient=self.recipient,
            template=None,
            text="Again",
        )
        PromotionContactOutbox.objects.filter(local_send_id=applied.pk).update(
            state=OutboxState.APPLIED
        )
        PromotionContactOutbox.objects.filter(local_send_id=in_flight.pk).update(
            state=OutboxState.IN_FLIGHT,
            lease_token=uuid.uuid4(),
            lease_expires_at=timezone.now() + timedelta(minutes=1),
        )
        applied_hash = PromotionContactOutbox.objects.get(
            local_send_id=applied.pk
        ).payload_hash
        cancel_or_redact_promotion_identity(self.recipient)
        row = PromotionContactOutbox.objects.get(local_send_id=send.pk)
        self.assertEqual(row.state, OutboxState.CANCELED)
        self.assertEqual(row.last_reason, "account_deleted")
        self.assertIsNone(row.payload)
        self.assertTrue(row.payload_hash)
        flying = PromotionContactOutbox.objects.get(local_send_id=in_flight.pk)
        self.assertEqual(flying.state, OutboxState.CANCELED)
        self.assertIsNone(flying.lease_token)
        self.assertIsNone(flying.lease_expires_at)
        self.assertIsNone(flying.payload)
        # Another account's applied row keeps its state and payload.
        other = PromotionContactOutbox.objects.get(local_send_id=applied.pk)
        self.assertEqual(other.state, OutboxState.APPLIED)
        self.assertIsNotNone(other.payload)
        self.assertEqual(other.payload_hash, applied_hash)
        self.assertTrue(PromoSend.objects.filter(pk=send.pk).exists())

    @override_settings(DISCORD_BOT_TOKEN="test-bot-token")
    def test_redacted_payload_cannot_be_materialised_again(self) -> None:
        send = record_promo_send(
            sender=self.users["promoter"],
            event=self.event,
            recipient=self.recipient,
            template=None,
            text="Hi",
        )
        cancel_or_redact_promotion_identity(self.recipient)
        row = PromotionContactOutbox.objects.get(local_send_id=send.pk)
        row.payload = {"schema_version": 1}
        with self.assertRaises(ImmutableFieldError):
            row.save(update_fields=["payload"])

    def test_quarantined_evidence_stays_in_universe(self) -> None:
        player = self.non_member_player("evidence_player")
        discord_id = player.discordId
        self.imported([self.entry(8021, player)])
        cancel_or_redact_promotion_identity(player)
        player.delete()
        universe = self.version()
        self.assertTrue(universe)
        from org.integration.subjects import authorized_event_subjects

        subjects = authorized_event_subjects(self.org, self.event)
        self.assertIsNotNone(subjects.by_discord_id(discord_id))
        self.assertEqual(self.receipt(8021).discord_id, discord_id)
