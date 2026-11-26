from datetime import timedelta
from unittest.mock import MagicMock, patch

from django.core.management import call_command
from django.db.models import Sum
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from app.models import CustomUser
from events.constants import EventState
from events.models import Event
from org.contributions.kinds import ContributionKind
from org.contributions.services import award_entry
from org.integration import points
from org.models import (
    ContributionEntry,
    Organization,
    OrgUser,
    PromoSend,
    PromoTemplate,
)
from org.models_promotion_sync import ExternalPromotionReceipt
from org.promotion.services import demote_colliding_earning_sends
from org.tests.test_integration_contacts import age_import
from org.tests.test_promotion_ledger import _LedgerBase
from user.discord_accounts import merge_discord_accounts
from user.models import ProfileClaimRequest


class _PromoMergeFixture(TestCase):
    def setUp(self) -> None:
        self.owner = CustomUser.objects.create_user(username="pm_owner", password="x")
        self.org = Organization.objects.create(name="Promo Merge Org", owner=self.owner)
        self.promoter_a = CustomUser.objects.create_user(
            username="pm_promoter_a", password="x"
        )
        self.promoter_b = CustomUser.objects.create_user(
            username="pm_promoter_b", password="x"
        )
        self.org.promoters.add(self.promoter_a, self.promoter_b)
        self.event = self._event("Promo Merge Event")
        self.other_event = self._event("Promo Merge Event 2")

    def _event(self, name: str) -> Event:
        return Event.objects.create(
            organization=self.org,
            name=name,
            scheduled_at=timezone.now() + timedelta(days=2),
            created_by=self.owner,
            state=EventState.UPCOMING,
        )

    def _send(
        self,
        sender: CustomUser,
        recipient: CustomUser,
        *,
        event: Event | None = None,
        earning: bool = True,
    ) -> PromoSend:
        event = event or self.event
        send = PromoSend.objects.create(
            organization=self.org,
            event=event,
            recipient=recipient,
            sender=sender,
            text="Hi",
            earns_points=earning,
        )
        if earning:
            award_entry(
                org=self.org,
                user=sender,
                kind=ContributionKind.PROMO_MESSAGE,
                occurred_at=send.sent_at,
                event=event,
                promo_send=send,
            )
        return send

    def _points(self, user: CustomUser) -> int:
        return (
            ContributionEntry.objects.nocache()
            .filter(org_user__user=user, organization=self.org)
            .aggregate(total=Sum("points"))["total"]
            or 0
        )

    def _assert_recipient_collision_resolved(
        self, kept: CustomUser, first: PromoSend, second: PromoSend
    ) -> None:
        sends = PromoSend.objects.filter(pk__in=[first.pk, second.pk])
        self.assertEqual(sends.count(), 2)
        self.assertEqual(set(sends.values_list("recipient_id", flat=True)), {kept.pk})
        self.assertEqual(
            PromoSend.objects.filter(
                event=self.event, recipient=kept, earns_points=True
            ).count(),
            1,
        )
        entries = ContributionEntry.objects.nocache().filter(
            promo_send__in=[first.pk, second.pk]
        )
        self.assertEqual(entries.count(), 2)
        self.assertEqual(self._points(self.promoter_a), 1)
        self.assertEqual(self._points(self.promoter_b), 1)


class DemoteCollidingEarningSendsTest(_PromoMergeFixture):
    def test_demotes_only_drop_sends_colliding_with_keep(self) -> None:
        keep = CustomUser.objects.create_user(username="pm_keep", password="x")
        drop = CustomUser.objects.create_user(username="pm_drop", password="x")
        keep_send = self._send(self.promoter_a, keep)
        drop_send = self._send(self.promoter_b, drop)
        drop_other = self._send(self.promoter_b, drop, event=self.other_event)

        demoted = demote_colliding_earning_sends(keep, drop)

        self.assertEqual(demoted, 1)
        keep_send.refresh_from_db()
        drop_send.refresh_from_db()
        drop_other.refresh_from_db()
        self.assertTrue(keep_send.earns_points)
        self.assertFalse(drop_send.earns_points)
        self.assertTrue(drop_other.earns_points)
        self.assertTrue(
            ContributionEntry.objects.nocache().filter(promo_send=drop_send).exists()
        )


class ClaimMergePromotionTest(_PromoMergeFixture):
    def setUp(self) -> None:
        super().setUp()
        self.admin = CustomUser.objects.create_superuser(
            username="pm_claim_admin", password="x"
        )
        self.target = CustomUser.objects.create_user(
            username="pm_claim_target", password="x"
        )
        self.claimer = CustomUser.objects.create_user(
            username="pm_claim_claimer", password="x", discordId="777222333"
        )
        OrgUser.objects.create(user=self.target, organization=self.org)
        OrgUser.objects.create(user=self.claimer, organization=self.org)
        self.claim = ProfileClaimRequest.objects.create(
            claimer=self.claimer,
            target_user=self.target,
            organization=self.org,
            status=ProfileClaimRequest.Status.PENDING,
        )
        self.client = APIClient()
        self.client.force_authenticate(self.admin)

    def _approve(self) -> None:
        response = self.client.post(f"/api/claim-requests/{self.claim.pk}/approve/")
        self.assertEqual(response.status_code, 200, response.content)

    def test_target_sends_keep_sender_points(self) -> None:
        self.org.promoters.add(self.target)
        recipient = CustomUser.objects.create_user(username="pm_r", password="x")
        send = self._send(self.target, recipient)

        self._approve()

        send.refresh_from_db()
        self.assertEqual(send.sender_id, self.claimer.pk)
        self.assertTrue(send.earns_points)
        self.assertEqual(self._points(self.claimer), 1)
        self.assertTrue(
            ContributionEntry.objects.nocache().filter(promo_send=send).exists()
        )

    def test_recipient_collision_keeps_one_earning_send(self) -> None:
        to_target = self._send(self.promoter_a, self.target)
        to_claimer = self._send(self.promoter_b, self.claimer)

        self._approve()

        self.assertFalse(CustomUser.objects.filter(pk=self.target.pk).exists())
        self._assert_recipient_collision_resolved(self.claimer, to_target, to_claimer)
        to_claimer.refresh_from_db()
        self.assertTrue(to_claimer.earns_points)


class DiscordReclaimPromotionTest(_PromoMergeFixture):
    def setUp(self) -> None:
        super().setUp()
        self.keep = CustomUser.objects.create(username="pm_dc_keep", discordId="999111")
        self.drop = CustomUser.objects.create(username="pm_dc_drop")

    def test_drop_sends_keep_sender_points(self) -> None:
        self.org.promoters.add(self.drop)
        recipient = CustomUser.objects.create_user(username="pm_dc_r", password="x")
        send = self._send(self.drop, recipient)

        merge_discord_accounts(keep=self.keep, drop=self.drop)

        send.refresh_from_db()
        self.assertEqual(send.sender_id, self.keep.pk)
        self.assertEqual(self._points(self.keep), 1)

    def test_recipient_collision_keeps_one_earning_send(self) -> None:
        to_keep = self._send(self.promoter_a, self.keep)
        to_drop = self._send(self.promoter_b, self.drop)

        merge_discord_accounts(keep=self.keep, drop=self.drop)

        self.assertFalse(CustomUser.objects.filter(pk=self.drop.pk).exists())
        self._assert_recipient_collision_resolved(self.keep, to_keep, to_drop)
        to_keep.refresh_from_db()
        self.assertTrue(to_keep.earns_points)

    def test_drop_template_created_by_moves_to_keep(self) -> None:
        template = PromoTemplate.objects.create(
            organization=self.org, name="Drop T", body="Hi", created_by=self.drop
        )

        merge_discord_accounts(keep=self.keep, drop=self.drop)

        template.refresh_from_db()
        self.assertEqual(template.created_by_id, self.keep.pk)


class SyncProdUsersPromotionTest(_PromoMergeFixture):
    def test_sync_prod_users_deletes_promo_sends(self) -> None:
        recipient = CustomUser.objects.create_user(username="pm_sync_r", password="x")
        self._send(self.promoter_a, recipient)
        self._send(self.promoter_b, recipient, earning=False)
        Organization.objects.update(owner=None)
        response = MagicMock()
        response.json.return_value = []

        with patch(
            "user.management.commands.sync_prod_users.requests.get",
            return_value=response,
        ):
            call_command("sync_prod_users")

        self.assertFalse(PromoSend.objects.exists())
        self.assertFalse(CustomUser.objects.exists())


class ExternalHolderMergeTest(_LedgerBase):
    """A merge that brings an external point holder and an earning local send
    for the same event together leaves one live point: the external one."""

    def _assert_one_live_point(self, send: PromoSend) -> None:
        send.refresh_from_db()
        self.assertFalse(send.earns_points)
        entry = self.entry_for(send)
        self.assertTrue(entry.voided)
        [void] = self.reversals(entry, ContributionKind.PROMO_VOID)
        self.assertEqual(void.points, -entry.points)
        self.assertTrue(
            ExternalPromotionReceipt.objects.filter(
                source_contact_id=8021, holds_point=True
            ).exists()
        )
        live = (
            ContributionEntry.objects.nocache()
            .filter(organization=self.org, event=self.event)
            .aggregate(total=Sum("points"))["total"]
        )
        self.assertEqual(live, 0)

    def test_merge_drop_holder_keep_earning_send_one_live_point(self) -> None:
        drop = self.non_member_player("ext_drop")
        keep = self.non_member_player("ext_keep")
        self.imported([self.entry(8021, drop)])
        send = self.send(keep)
        self.assertTrue(send.earns_points)

        merge_discord_accounts(keep=keep, drop=drop)

        self._assert_one_live_point(send)

    def test_claim_request_holder_and_earning_send_one_live_point(self) -> None:
        claimer = self.non_member_player("ext_claimer")
        OrgUser.objects.create(user=claimer, organization=self.org)
        target = CustomUser.objects.create_user(username="ext_target", password="x")
        OrgUser.objects.create(user=target, organization=self.org)
        self.imported([self.entry(8021, claimer)])
        send = self.raw_send(target)
        self.assertEqual(send.recipient_discord_id, "")
        claim = ProfileClaimRequest.objects.create(
            claimer=claimer,
            target_user=target,
            organization=self.org,
            status=ProfileClaimRequest.Status.PENDING,
        )
        admin = CustomUser.objects.create_superuser(
            username="ext_claim_admin", password="x"
        )
        client = APIClient()
        client.force_authenticate(admin)

        response = client.post(f"/api/claim-requests/{claim.pk}/approve/")

        self.assertEqual(response.status_code, 200, response.content)
        send.refresh_from_db()
        self.assertEqual(send.recipient_id, claimer.pk)
        self._assert_one_live_point(send)

    def _merged_holder(self, *, duplicate: bool = False):
        drop = self.non_member_player("release_drop")
        keep = self.non_member_player("release_keep")
        discord_id = drop.discordId
        entries = [self.entry(8021, drop)]
        if duplicate:
            entries.append(self.entry(8022, drop))
        self.imported(entries)
        send = self.send(keep)
        merge_discord_accounts(keep=keep, drop=drop)
        self._assert_one_live_point(send)
        age_import(self.receipt(8021).pk)
        if duplicate:
            age_import(self.receipt(8022).pk)
        return keep, send, discord_id

    def _assert_restored(self, send):
        send.refresh_from_db()
        self.assertTrue(send.earns_points)
        entry = self.entry_for(send)
        self.assertFalse(entry.voided)
        self.assertEqual(len(self.reversals(entry, ContributionKind.PROMO_RESTORE)), 1)
        self.assertFalse(points.external_point_held(self.event, send.recipient))

    def test_retraction_restores_send_voided_during_merge(self):
        keep, send, _ = self._merged_holder()
        body = self.imported([], after=8020, through=8021)
        self.assertEqual(body["retracted"], 1)
        self.assertEqual(body["restored_local"], 1)
        self._assert_restored(send)

    def test_source_target_change_restores_merged_send(self):
        keep, send, _ = self._merged_holder()
        other = self.non_member_player("release_other")
        body = self.imported([self.entry(8021, other)])
        self.assertEqual(body["restored_local"], 1)
        self._assert_restored(send)
        self.assertTrue(points.external_point_held(self.event, other))

    def test_duplicate_takes_over_then_releases_merged_point(self):
        keep, send, _ = self._merged_holder(duplicate=True)
        body = self.imported([], after=8020, through=8021)
        self.assertEqual(body["restored_local"], 0)
        self.assertTrue(points.external_point_held(self.event, keep))
        self.assertTrue(self.entry_for(send).voided)
        self.assertTrue(self.receipt(8022).holds_point)
        # Changing the original source key must not lose the link between
        # the replacement holder and the merged recipient's voided send.
        other = self.non_member_player("replacement_other")
        self.imported([self.entry(8021, other)])
        self.assertTrue(self.entry_for(send).voided)
        self.assertTrue(points.external_point_held(self.event, keep))
        body = self.imported([], after=8021, through=8022)
        self.assertEqual(body["restored_local"], 1)
        self._assert_restored(send)

    def test_remaining_holder_for_survivor_blocks_restoration(self):
        keep, send, _ = self._merged_holder()
        self.imported([self.entry(8022, keep)])
        body = self.imported([], after=8020, through=8021)
        self.assertEqual(body["restored_local"], 0)
        self.assertTrue(self.entry_for(send).voided)
        self.assertTrue(points.external_point_held(self.event, keep))
        age_import(self.receipt(8022).pk)
        body = self.imported([], after=8021, through=8022)
        self.assertEqual(body["restored_local"], 1)
        self._assert_restored(send)
