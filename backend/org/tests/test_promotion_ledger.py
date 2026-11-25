"""The promotion ledger that imported external contacts settle.

An imported invitation for a bound event holds the (event, player) point.
It credits the external promoter when the promoter's Discord ID matches a
member of the org, and otherwise records why nobody was credited. A second
contact for the same point is a duplicate, and a contact the external log
recorded on DraftForge's behalf is an echo of the local send. A local send
that earned the same point is voided by a ``promo_void`` ledger reversal:
the send, its outbox row and its tick stay. A contact that is superseded or
retracted gives its point to the next duplicate, or, with none left,
restores the voided local point with a ``promo_restore``. Nothing is ever
deleted.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

from django.test import override_settings

from app.models import CustomUser
from events.models import Event
from org.contributions.kinds import ContributionKind
from org.contributions.queries import leaderboard, member_totals, own_totals
from org.contributions.services import award_entry, set_point_value
from org.integration import points
from org.models import (
    ContributionEntry,
    ContributionPointValue,
    OrgLog,
    OrgUser,
    PromoSend,
)
from org.models_promotion_sync import (
    AssociationState,
    ExternalPromotionReceipt,
    OutboxState,
    PointReason,
    PointStatus,
    PromotionContactOutbox,
)
from org.promotion import services
from org.promotion.services import (
    ContactAlreadyRecorded,
    record_promo_send,
    undo_promo_send,
    will_earn,
)
from org.standing.periods import parse_period
from org.tests.test_integration_contacts import (
    COMPLETED_OCCASION,
    GUILD_ONLY_ID,
    OCCASION,
    UNKNOWN_ID,
    _ImportBase,
    age_import,
    guild_member,
)

CREDIT_REASON = "Recorded in the external contact log"


@override_settings(DISCORD_BOT_TOKEN="test-bot-token")
class _LedgerBase(_ImportBase):
    def setUp(self) -> None:
        super().setUp()
        self.promoter = self.users["promoter"]
        self.member = self.users["member"]
        assert self.promoter is not None and self.member is not None

    def send(
        self,
        recipient: CustomUser | None = None,
        *,
        sender: CustomUser | None = None,
        event: Event | None = None,
    ) -> PromoSend:
        return record_promo_send(
            sender=sender or self.promoter,
            event=event or self.event,
            recipient=recipient or self.recipient,
            template=None,
            text="Hi",
        )

    def raw_send(
        self, recipient: CustomUser, *, sender: CustomUser | None = None
    ) -> PromoSend:
        """An earning send written past the send guards, as one recorded
        before the external point existed would be."""
        sender = sender or self.promoter
        send = PromoSend.objects.create(
            organization=self.org,
            event=self.event,
            recipient=recipient,
            recipient_discord_id=recipient.discordId or "",
            sender=sender,
            text="Hi",
            earns_points=True,
        )
        award_entry(
            org=self.org,
            user=sender,
            kind=ContributionKind.PROMO_MESSAGE,
            occurred_at=send.sent_at,
            event=self.event,
            promo_send=send,
        )
        return send

    def quarantined_holder(self, name: str) -> tuple[str, CustomUser]:
        """A holding receipt quarantined because its Discord ID moved to a
        new account; returns the Discord ID and the new owner."""
        first_owner = self.non_member_player(f"{name}_first")
        discord_id = first_owner.discordId
        self.imported([self.entry(8021, first_owner)])
        CustomUser.objects.filter(pk=first_owner.pk).update(
            discordId=f"88000000000000{first_owner.pk:04d}"
        )
        new_owner = CustomUser.objects.create_user(
            username=f"{name}_new", password="x", discordId=discord_id
        )
        self.imported([self.entry(8021, discord_id)])
        receipt = self.receipt(8021)
        self.assertEqual(receipt.association_state, AssociationState.QUARANTINED)
        self.assertTrue(receipt.holds_point)
        return discord_id, new_owner

    def entry_for(self, send: PromoSend) -> ContributionEntry:
        return ContributionEntry.objects.nocache().get(promo_send=send)

    def reversals(self, entry: ContributionEntry, kind: str) -> list[ContributionEntry]:
        return list(
            ContributionEntry.objects.nocache()
            .filter(reversal_of=entry, kind=kind)
            .order_by("pk")
        )

    def credits(self, receipt: ExternalPromotionReceipt) -> list[ContributionEntry]:
        return list(
            ContributionEntry.objects.nocache()
            .filter(external_contact=receipt, kind=ContributionKind.PROMO_MESSAGE)
            .order_by("pk")
        )

    def point(self, body: dict[str, Any], index: int = 0) -> str:
        return body["results"][index]["point"]


class SettleTests(_LedgerBase):
    def test_credit_matched_member_with_org_point_value(self) -> None:
        ContributionPointValue.objects.create(
            organization=self.org, kind=ContributionKind.PROMO_MESSAGE, points=4
        )
        body = self.imported([self.entry(8021, GUILD_ONLY_ID, promoter=self.member)])
        self.assertEqual(self.point(body), "credited")
        self.assertEqual(body["credited"], 1)
        receipt = self.receipt(8021)
        self.assertTrue(receipt.holds_point)
        self.assertEqual(receipt.point_reason, PointReason.NONE)
        [credit] = self.credits(receipt)
        self.assertEqual(credit.points, 4)
        self.assertEqual(
            credit.org_user,
            OrgUser.objects.get(user=self.member, organization=self.org),
        )
        self.assertEqual(credit.occurred_at, receipt.recorded_at)
        self.assertEqual(credit.event_id, self.event.pk)
        self.assertEqual(credit.reason, CREDIT_REASON)
        self.assertIsNone(credit.awarded_by_id)
        self.assertIsNone(credit.promo_send_id)
        self.assertFalse(credit.voided)

    def _uncredited(self, promoter: CustomUser | str | None, reason: str) -> None:
        body = self.imported([self.entry(8021, GUILD_ONLY_ID, promoter=promoter)])
        self.assertEqual(self.point(body), "uncredited")
        receipt = self.receipt(8021)
        self.assertTrue(receipt.holds_point)
        self.assertEqual(receipt.point_status, PointStatus.UNCREDITED)
        self.assertEqual(receipt.point_reason, reason)
        self.assertFalse(ContributionEntry.objects.nocache().exists())

    def test_uncredited_promoter_unresolved(self) -> None:
        self._uncredited(None, PointReason.PROMOTER_UNRESOLVED)

    def test_uncredited_self_contact(self) -> None:
        self._uncredited(GUILD_ONLY_ID, PointReason.SELF_CONTACT)

    def test_uncredited_promoter_unmatched(self) -> None:
        self._uncredited(UNKNOWN_ID, PointReason.PROMOTER_UNMATCHED)

    def test_uncredited_promoter_not_member(self) -> None:
        outsider = self.non_member_player("outsider_promoter")
        users = OrgUser.objects.count()
        self._uncredited(outsider, PointReason.PROMOTER_NOT_MEMBER)
        self.assertEqual(OrgUser.objects.count(), users)

    def test_uncredited_is_settled_again_on_replay(self) -> None:
        outsider = self.non_member_player("later_member")
        self.imported([self.entry(8021, GUILD_ONLY_ID, promoter=outsider)])
        OrgUser.objects.create(user=outsider, organization=self.org)
        body = self.imported([self.entry(8021, GUILD_ONLY_ID, promoter=outsider)])
        self.assertEqual(body["results"][0]["status"], "unchanged")
        self.assertEqual(self.point(body), "credited")
        self.assertEqual(len(self.credits(self.receipt(8021))), 1)

    def test_duplicate_second_receipt(self) -> None:
        body = self.imported(
            [
                self.entry(8021, GUILD_ONLY_ID, promoter=self.member),
                self.entry(8022, GUILD_ONLY_ID, promoter=self.member),
            ]
        )
        self.assertEqual(
            [r["point"] for r in body["results"]], ["credited", "duplicate"]
        )
        self.assertEqual(body["duplicate"], 1)
        self.assertFalse(self.receipt(8022).holds_point)
        self.assertEqual(ContributionEntry.objects.nocache().count(), 1)

    def test_same_player_other_event_is_its_own_point(self) -> None:
        body = self.imported(
            [
                self.entry(8021, GUILD_ONLY_ID),
                self.entry(8022, GUILD_ONLY_ID, event=self.completed_event),
            ]
        )
        self.assertEqual(
            [r["point"] for r in body["results"]], ["uncredited", "uncredited"]
        )

    def test_echo_from_applied_outbox_row(self) -> None:
        send = self.send()
        PromotionContactOutbox.objects.filter(local_send_id=send.pk).update(
            state=OutboxState.APPLIED, applied_contact_log_id=8021
        )
        body = self.imported([self.entry(8021, self.recipient, promoter=self.member)])
        self.assertEqual(self.point(body), "echo")
        self.assertEqual(body["echo"], 1)
        self.assertFalse(body["results"][0]["voided_local"])
        receipt = self.receipt(8021)
        self.assertFalse(receipt.holds_point)
        self.assertEqual(receipt.origin_send_id, send.pk)
        send.refresh_from_db()
        self.assertTrue(send.earns_points)
        self.assertFalse(self.entry_for(send).voided)
        self.assertEqual(ContributionEntry.objects.nocache().count(), 1)
        self.assertFalse(self.ticked(self.recipient.discordId, self.recipient))


class VoidTests(_LedgerBase):
    def test_void_local_point(self) -> None:
        send = self.send()
        entry = self.entry_for(send)
        body = self.imported([self.entry(8021, self.recipient)])
        self.assertTrue(body["results"][0]["voided_local"])
        self.assertEqual(body["voided_local"], 1)
        send.refresh_from_db()
        self.assertFalse(send.earns_points)
        entry.refresh_from_db()
        self.assertTrue(entry.voided)
        [void] = self.reversals(entry, ContributionKind.PROMO_VOID)
        self.assertEqual(void.points, -entry.points)
        self.assertEqual(void.occurred_at, entry.occurred_at)
        self.assertEqual(void.org_user_id, entry.org_user_id)
        self.assertEqual(void.event_id, entry.event_id)
        self.assertEqual(void.external_contact, self.receipt(8021))
        self.assertFalse(void.voided)
        log = OrgLog.objects.get(action="void_promo_point")
        self.assertIsNone(log.actor_id)
        self.assertEqual(log.target_user, self.promoter)
        self.assertEqual(
            log.details,
            {
                "entry_pk": entry.pk,
                "void_pk": void.pk,
                "send_id": send.pk,
                "event_id": self.event.pk,
                "source_contact_id": 8021,
            },
        )
        self.assertTrue(PromoSend.objects.filter(pk=send.pk).exists())
        self.assertTrue(
            PromotionContactOutbox.objects.filter(local_send_id=send.pk).exists()
        )
        self.assertTrue(self.ticked(self.recipient.discordId, self.recipient))

    def test_replay_does_not_void_twice(self) -> None:
        send = self.send()
        self.imported([self.entry(8021, self.recipient)])
        body = self.imported([self.entry(8021, self.recipient)])
        self.assertFalse(body["results"][0]["voided_local"])
        entry = self.entry_for(send)
        self.assertEqual(len(self.reversals(entry, ContributionKind.PROMO_VOID)), 1)

    def test_void_totals_net_zero_same_month(self) -> None:
        promoter_ou = OrgUser.objects.create(user=self.promoter, organization=self.org)
        self.send()
        other = self.non_member_player("other_recipient")
        self.send(other)
        before = member_totals(promoter_ou)
        self.assertEqual((before["all_time"], before["this_month"]), (2, 2))
        self.imported([self.entry(8021, self.recipient)])
        after = member_totals(promoter_ou)
        self.assertEqual((after["all_time"], after["this_month"]), (1, 1))
        period = parse_period(self.org, None)
        self.assertEqual(own_totals(promoter_ou, period), (1, 1))
        rows = leaderboard(self.org, period, sort="entries")
        self.assertEqual([(r["points"], r["entries"]) for r in rows], [(1, 1)])

    def test_quarantined_holder_still_voids(self) -> None:
        discord_id, new_owner = self.quarantined_holder("q")
        send = self.raw_send(new_owner)
        body = self.imported([self.entry(8021, discord_id)])
        self.assertTrue(body["results"][0]["voided_local"])
        send.refresh_from_db()
        self.assertFalse(send.earns_points)

    def test_void_via_snapshot_after_recipient_deleted(self) -> None:
        recipient = self.non_member_player("gone_recipient")
        discord_id = recipient.discordId
        send = self.send(recipient)
        recipient.delete()
        send.refresh_from_db()
        self.assertIsNone(send.recipient_id)
        body = self.imported([self.entry(8021, discord_id)])
        self.assertTrue(body["results"][0]["voided_local"])
        send.refresh_from_db()
        self.assertFalse(send.earns_points)
        self.assertTrue(self.entry_for(send).voided)

    def test_void_after_recipient_relinked(self) -> None:
        recipient = self.non_member_player("relinked_recipient")
        old_discord = recipient.discordId
        send = self.send(recipient)
        CustomUser.objects.filter(pk=recipient.pk).update(
            discordId="880000000000000557"
        )
        body = self.imported([self.entry(8021, old_discord)])
        self.assertTrue(body["results"][0]["voided_local"])
        self.assertTrue(self.entry_for(send).voided)

    def test_send_without_snapshot_voids_by_current_discord(self) -> None:
        send = self.send()
        PromoSend.objects.filter(pk=send.pk).update(recipient_discord_id="")
        body = self.imported([self.entry(8021, self.recipient)])
        self.assertTrue(body["results"][0]["voided_local"])

    def test_other_event_send_is_not_voided(self) -> None:
        other = Event.objects.create(
            organization=self.org,
            name="Second Promo Night",
            scheduled_at=self.event.scheduled_at,
            created_by=self.users["owner"],
            state=self.event.state,
        )
        send = self.send(event=other)
        body = self.imported([self.entry(8021, self.recipient)])
        self.assertFalse(body["results"][0]["voided_local"])
        self.assertFalse(self.entry_for(send).voided)


class SupersedeAndRetractTests(_LedgerBase):
    def test_primary_flip_moves_point_and_resettles_old_key(self) -> None:
        old = self.send()
        new_target = self.non_member_player("flip_target")
        new = self.send(new_target)
        self.imported([self.entry(8021, self.recipient)])
        self.assertTrue(self.entry_for(old).voided)

        body = self.imported([self.entry(8021, new_target)])
        self.assertEqual(body["results"][0]["status"], "updated")
        self.assertTrue(body["results"][0]["voided_local"])
        self.assertEqual(body["restored_local"], 1)
        receipt = self.receipt(8021)
        self.assertEqual(receipt.discord_id, new_target.discordId)
        self.assertTrue(receipt.holds_point)
        old.refresh_from_db()
        self.assertTrue(old.earns_points)
        old_entry = self.entry_for(old)
        self.assertFalse(old_entry.voided)
        [restore] = self.reversals(old_entry, ContributionKind.PROMO_RESTORE)
        self.assertEqual(restore.points, old_entry.points)
        self.assertEqual(restore.external_contact, receipt)
        self.assertTrue(OrgLog.objects.filter(action="restore_promo_point").exists())
        self.assertTrue(self.entry_for(new).voided)
        self.assertTrue(self.ticked(new_target.discordId, new_target))
        self.assertFalse(self.ticked(self.recipient.discordId, self.recipient))

    def test_promoter_change_voids_old_credit_and_credits_new(self) -> None:
        OrgUser.objects.create(user=self.users["staff"], organization=self.org)
        self.imported([self.entry(8021, GUILD_ONLY_ID, promoter=self.member)])
        body = self.imported(
            [self.entry(8021, GUILD_ONLY_ID, promoter=self.users["staff"])]
        )
        self.assertEqual(self.point(body), "credited")
        receipt = self.receipt(8021)
        old, new = self.credits(receipt)
        self.assertTrue(old.voided)
        self.assertEqual(old.org_user.user, self.member)
        self.assertFalse(new.voided)
        self.assertEqual(new.org_user.user, self.users["staff"])
        [void] = self.reversals(old, ContributionKind.PROMO_VOID)
        self.assertEqual(void.points, -old.points)
        self.assertEqual(
            void.reason, "Voided: the external contact changed or was removed"
        )

    def test_promoter_change_to_unmatched_records_uncredited(self) -> None:
        self.imported([self.entry(8021, GUILD_ONLY_ID, promoter=self.member)])
        body = self.imported([self.entry(8021, GUILD_ONLY_ID, promoter=UNKNOWN_ID)])
        self.assertEqual(self.point(body), "uncredited")
        [old] = self.credits(self.receipt(8021))
        self.assertTrue(old.voided)

    def test_retract_without_duplicate_restores_local(self) -> None:
        send = self.send()
        self.imported([self.entry(8021, self.recipient, promoter=self.member)])
        age_import(self.receipt(8021).pk)
        body = self.imported([], after=8020, through=8021)
        self.assertEqual(body["retracted"], 1)
        self.assertEqual(body["restored_local"], 1)
        send.refresh_from_db()
        self.assertTrue(send.earns_points)
        entry = self.entry_for(send)
        self.assertFalse(entry.voided)
        self.assertEqual(len(self.reversals(entry, ContributionKind.PROMO_VOID)), 1)
        self.assertEqual(len(self.reversals(entry, ContributionKind.PROMO_RESTORE)), 1)
        [credit] = self.credits(self.receipt(8021))
        self.assertTrue(credit.voided)
        promoter_ou = OrgUser.objects.get(user=self.promoter, organization=self.org)
        self.assertEqual(member_totals(promoter_ou)["all_time"], entry.points)
        member_ou = OrgUser.objects.get(user=self.member, organization=self.org)
        self.assertEqual(member_totals(member_ou)["all_time"], 0)

    def test_retract_with_duplicate_promotes_duplicate(self) -> None:
        send = self.send()
        self.imported(
            [
                self.entry(8021, self.recipient),
                self.entry(8030, self.recipient, promoter=self.member),
            ]
        )
        self.assertEqual(self.receipt(8030).point_status, PointStatus.DUPLICATE)
        age_import(self.receipt(8021).pk)
        body = self.imported([], after=8020, through=8021)
        self.assertEqual(body["retracted"], 1)
        self.assertEqual(body["restored_local"], 0)
        promoted = self.receipt(8030)
        self.assertEqual(promoted.point_status, PointStatus.CREDITED)
        self.assertTrue(promoted.holds_point)
        self.assertTrue(self.entry_for(send).voided)
        send.refresh_from_db()
        self.assertFalse(send.earns_points)

    def test_binding_change_full_replay_moves_point(self) -> None:
        self.imported([self.entry(8021, GUILD_ONLY_ID, promoter=self.member)])
        self.bind({self.completed_event: OCCASION, self.event: COMPLETED_OCCASION})
        body = self.imported([self.entry(8021, GUILD_ONLY_ID, promoter=self.member)])
        self.assertEqual(body["results"][0]["status"], "updated")
        receipt = self.receipt(8021)
        self.assertEqual(receipt.event_id, self.completed_event.pk)
        self.assertTrue(receipt.holds_point)
        old, new = self.credits(receipt)
        self.assertEqual((old.event_id, old.voided), (self.event.pk, True))
        self.assertEqual((new.event_id, new.voided), (self.completed_event.pk, False))


class ExternalPointHeldTests(_LedgerBase):
    def test_held_by_receipt_or_snapshot(self) -> None:
        self.assertFalse(points.external_point_held(self.event, self.recipient))
        recipient = self.non_member_player("held_recipient")
        old_discord = recipient.discordId
        self.send(recipient)
        self.imported([self.entry(8021, old_discord)])
        self.assertTrue(points.external_point_held(self.event, recipient))
        CustomUser.objects.filter(pk=recipient.pk).update(
            discordId="880000000000000558"
        )
        recipient.refresh_from_db()
        self.assertTrue(points.external_point_held(self.event, recipient))
        self.assertFalse(points.external_point_held(self.completed_event, recipient))

    def test_not_held_after_retraction(self) -> None:
        self.imported([self.entry(8021, self.recipient)])
        age_import(self.receipt(8021).pk)
        self.imported([], after=8020, through=8021)
        self.assertFalse(points.external_point_held(self.event, self.recipient))


class LocalGuardTests(_LedgerBase):
    def test_will_earn_promote_next_and_409_agree_with_external_holder(
        self,
    ) -> None:
        self.assertTrue(will_earn(self.promoter, self.event, self.recipient))
        waiting = PromoSend.objects.create(
            organization=self.org,
            event=self.event,
            recipient=self.recipient,
            recipient_discord_id=self.recipient.discordId,
            sender=self.promoter_b,
            text="Hi",
            earns_points=False,
        )
        self.imported([self.entry(8021, self.recipient)])
        self.assertFalse(will_earn(self.promoter, self.event, self.recipient))
        self.assertIsNone(services._promote_next_send(self.event, self.recipient.pk))
        waiting.refresh_from_db()
        self.assertFalse(waiting.earns_points)
        self.assertTrue(self.ticked(self.recipient.discordId, self.recipient))
        with self.assertRaises(ContactAlreadyRecorded):
            self.send()

    def test_quarantined_holder_blocks_send_409_and_ticks(self) -> None:
        discord_id, new_owner = self.quarantined_holder("qb")
        self.assertTrue(points.external_point_held(self.event, new_owner))
        self.assertTrue(self.ticked(discord_id, new_owner))
        self.assertFalse(will_earn(self.promoter, self.event, new_owner))
        with self.assertRaises(ContactAlreadyRecorded):
            self.send(new_owner)
        self.assertFalse(PromoSend.objects.filter(recipient=new_owner).exists())

    def test_quarantined_before_settlement(self) -> None:
        send = self.send()
        self.imported(
            [self.entry(8021, self.recipient), self.entry(8030, self.recipient)]
        )
        self.assertEqual(self.receipt(8030).point_status, PointStatus.DUPLICATE)
        ExternalPromotionReceipt.objects.filter(source_contact_id=8030).update(
            association_state=AssociationState.QUARANTINED,
            association_reason="discord_owner_changed",
            user=None,
            org_user=None,
        )
        age_import(self.receipt(8021).pk)
        body = self.imported([], after=8020, through=8021)
        self.assertEqual(body["restored_local"], 0)
        promoted = self.receipt(8030)
        self.assertTrue(promoted.holds_point)
        self.assertEqual(promoted.association_state, AssociationState.QUARANTINED)
        self.assertTrue(self.entry_for(send).voided)
        self.assertTrue(self.ticked(self.recipient.discordId, self.recipient))
        with self.assertRaises(ContactAlreadyRecorded):
            self.send(sender=self.promoter_b)

    def test_no_new_earning_send_after_relink(self) -> None:
        recipient = self.non_member_player("relink_guard")
        send = self.send(recipient)
        self.imported([self.entry(8021, recipient)])
        self.assertTrue(self.entry_for(send).voided)
        CustomUser.objects.filter(pk=recipient.pk).update(
            discordId="880000000000000559"
        )
        self.members = [*self.members, guild_member("880000000000000559", days_ago=3)]
        recipient.refresh_from_db()
        self.assertFalse(self.ticked(recipient.discordId, recipient))
        self.assertTrue(points.external_point_held(self.event, recipient))
        self.assertFalse(will_earn(self.promoter_b, self.event, recipient))
        with self.assertRaises(ContactAlreadyRecorded):
            self.send(recipient, sender=self.promoter_b)
        self.assertEqual(PromoSend.objects.filter(recipient=recipient).count(), 1)

    def test_undo_after_void_deletes_entry_and_reversals(self) -> None:
        send = self.send()
        waiting = PromoSend.objects.create(
            organization=self.org,
            event=self.event,
            recipient=self.recipient,
            recipient_discord_id=self.recipient.discordId,
            sender=self.promoter_b,
            text="Hi",
            earns_points=False,
        )
        self.imported([self.entry(8021, self.recipient)])
        entry = self.entry_for(send)
        self.assertTrue(entry.voided)
        with patch.object(services, "lock_event", wraps=services.lock_event) as locked:
            undo_promo_send(send, actor=self.promoter)
        locked.assert_called_once_with(self.event.pk)
        self.assertFalse(
            ContributionEntry.objects.nocache().filter(pk=entry.pk).exists()
        )
        self.assertFalse(
            ContributionEntry.objects.nocache().filter(reversal_of_id=entry.pk).exists()
        )
        waiting.refresh_from_db()
        self.assertFalse(waiting.earns_points)
        self.assertFalse(
            ContributionEntry.objects.nocache().filter(promo_send=waiting).exists()
        )
        self.assertTrue(self.receipt(8021).holds_point)


class RescoreTests(_LedgerBase):
    def test_rescore_updates_credits_voids_and_restores(self) -> None:
        restored_send = self.send()
        other = self.non_member_player("rescore_other")
        voided_send = self.send(other)
        self.imported(
            [
                self.entry(8021, self.recipient),
                self.entry(8022, GUILD_ONLY_ID, promoter=self.member),
                self.entry(8023, other),
            ]
        )
        age_import(self.receipt(8021).pk)
        body = self.imported(
            [self.entry(8022, GUILD_ONLY_ID, promoter=self.member)],
            after=8020,
            through=8022,
        )
        self.assertEqual(body["restored_local"], 1)

        set_point_value(
            self.org,
            ContributionKind.PROMO_MESSAGE,
            3,
            actor=self.users["admin"],
            apply_to_past=True,
        )

        [credit] = self.credits(self.receipt(8022))
        self.assertEqual(credit.points, 3)
        restored = self.entry_for(restored_send)
        self.assertEqual(restored.points, 3)
        [void] = self.reversals(restored, ContributionKind.PROMO_VOID)
        [restore] = self.reversals(restored, ContributionKind.PROMO_RESTORE)
        self.assertEqual((void.points, restore.points), (-3, 3))
        voided = self.entry_for(voided_send)
        self.assertEqual(voided.points, 3)
        [other_void] = self.reversals(voided, ContributionKind.PROMO_VOID)
        self.assertEqual(other_void.points, -3)
        promoter_ou = OrgUser.objects.get(user=self.promoter, organization=self.org)
        member_ou = OrgUser.objects.get(user=self.member, organization=self.org)
        self.assertEqual(member_totals(promoter_ou)["all_time"], 3)
        self.assertEqual(member_totals(member_ou)["all_time"], 3)


class EventLifecycleTests(_LedgerBase):
    def test_event_delete_releases_holder(self) -> None:
        self.imported([self.entry(8021, GUILD_ONLY_ID, promoter=self.member)])
        [credit] = self.credits(self.receipt(8021))
        Event.objects.filter(pk=self.event.pk).delete()
        receipt = self.receipt(8021)
        self.assertIsNone(receipt.event_id)
        self.assertFalse(receipt.holds_point)
        self.assertEqual(receipt.point_status, PointStatus.NOT_APPLICABLE)
        credit.refresh_from_db()
        self.assertIsNone(credit.event_id)
        self.assertEqual(credit.points, 1)

    def test_event_instance_delete_releases_holder(self) -> None:
        self.imported([self.entry(8021, self.recipient)])
        Event.objects.get(pk=self.event.pk).delete()
        receipt = self.receipt(8021)
        self.assertEqual(
            (receipt.event_id, receipt.holds_point, receipt.point_status),
            (None, False, PointStatus.NOT_APPLICABLE),
        )

    def test_account_deletion_keeps_holds_point(self) -> None:
        player = self.non_member_player("deleted_holder")
        discord_id = player.discordId
        self.imported([self.entry(8021, player)])
        player.delete()
        receipt = self.receipt(8021)
        self.assertEqual(receipt.association_state, AssociationState.QUARANTINED)
        self.assertTrue(receipt.holds_point)
        self.assertTrue(self.ticked(discord_id, None))
