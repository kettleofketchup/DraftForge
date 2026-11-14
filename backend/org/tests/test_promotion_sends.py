from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from app.models import CustomUser, League, Organization, Tournament
from events.constants import EventState
from events.models import Event
from org.contributions.kinds import ContributionKind
from org.feature_keys import FeatureKey
from org.features import org_has_feature, set_org_feature
from org.models import ContributionEntry, OrgUser, PromoSend, PromoTemplate
from org.promotion.services import (
    MAX_SEND_TEXT,
    PromoSendError,
    can_undo,
    record_promo_send,
    undo_promo_send,
    will_earn,
)


class _SendFixture(TestCase):
    def setUp(self) -> None:
        now = timezone.now()
        self.owner = CustomUser.objects.create_user(username="ps_owner", password="x")
        self.org = Organization.objects.create(name="Send Org", owner=self.owner)
        self.other_org = Organization.objects.create(
            name="Other Send Org", owner=self.owner
        )
        set_org_feature(self.org, FeatureKey.PROMOTION, enabled=True, actor=None)
        self.promoter = self._user("ps_promoter")
        self.promoter_b = self._user("ps_promoter_b")
        self.staff = self._user("ps_staff")
        self.site_admin = self._user("ps_site_admin")
        self.site_admin.is_staff = True
        self.site_admin.save()
        self.org.promoters.add(self.promoter, self.promoter_b)
        self.org.staff.add(self.staff)
        self.recipient = self._user("ps_recipient")
        self.outsider = self._user("ps_outsider")
        self.no_discord = self._user("ps_no_discord", discord=False)
        self.league = League.objects.create(
            name="Send League", organization=self.org, steam_league_id=88301
        )
        tournament = Tournament.objects.create(
            name="Send Past T",
            date_played=now - timedelta(days=5),
            league=self.league,
        )
        tournament.users.add(self.recipient, self.no_discord, self.promoter)
        self.event = Event.objects.create(
            organization=self.org,
            name="Send Event",
            scheduled_at=now + timedelta(days=3),
            created_by=self.owner,
            state=EventState.UPCOMING,
        )
        self.template = PromoTemplate.objects.create(
            organization=self.org, name="T", body="Hi {player}"
        )

    def _user(self, username: str, *, discord: bool = True) -> CustomUser:
        user = CustomUser.objects.create_user(username=username, password="x")
        if discord:
            user.discordId = str(883000000000000000 + user.pk)
            user.discordUsername = f"{username}_dc"
            user.save()
        return user

    def _send(
        self,
        sender: CustomUser,
        *,
        recipient: CustomUser | None = None,
        event: Event | None = None,
        template: PromoTemplate | None = None,
        text: str = "Hi there",
    ) -> PromoSend:
        return record_promo_send(
            sender=sender,
            event=event or self.event,
            recipient=recipient or self.recipient,
            template=template,
            text=text,
        )

    def _entries(self, send: PromoSend) -> list[ContributionEntry]:
        return list(ContributionEntry.objects.nocache().filter(promo_send=send))


class RecordPromoSendValidationTest(_SendFixture):
    def _assert_field(self, field: str, **kwargs: object) -> None:
        with self.assertRaises(PromoSendError) as ctx:
            self._send(self.promoter, **kwargs)  # type: ignore[arg-type]
        self.assertEqual(ctx.exception.field, field)
        self.assertFalse(PromoSend.objects.exists())

    def test_rejects_wrong_state_event(self) -> None:
        for state in (
            EventState.ROLL_CALL,
            EventState.IN_PROGRESS,
            EventState.COMPLETED,
            EventState.CANCELLED,
        ):
            with self.subTest(state=state):
                Event.objects.filter(pk=self.event.pk).update(state=state)
                self.event.refresh_from_db()
                self._assert_field("event")

    def test_signups_open_event_accepted(self) -> None:
        Event.objects.filter(pk=self.event.pk).update(state=EventState.SIGNUPS_OPEN)
        self.event.refresh_from_db()
        self.assertIsNotNone(self._send(self.promoter).pk)

    def test_rejects_foreign_template(self) -> None:
        foreign = PromoTemplate.objects.create(
            organization=self.other_org, name="F", body="x"
        )
        self._assert_field("template_id", template=foreign)

    def test_rejects_recipient_not_in_pool(self) -> None:
        self._assert_field("recipient_id", recipient=self.outsider)

    def test_rejects_self(self) -> None:
        self._assert_field("recipient_id", recipient=self.promoter)

    def test_rejects_recipient_without_discord(self) -> None:
        self._assert_field("recipient_id", recipient=self.no_discord)

    def test_rejects_text_over_limit(self) -> None:
        self.assertEqual(MAX_SEND_TEXT, 4000)
        self._assert_field("text", text="x" * 4001)

    def test_accepts_text_at_limit(self) -> None:
        send = self._send(self.promoter, text="x" * 4000, template=self.template)
        self.assertEqual(send.template, self.template)
        self.assertEqual(len(send.text), 4000)


class RecordPromoSendEarningTest(_SendFixture):
    def test_first_send_earns_default_point_with_contributions_locked(self) -> None:
        self.assertFalse(org_has_feature(self.org, FeatureKey.CONTRIBUTIONS))
        self.assertTrue(will_earn(self.promoter, self.event, self.recipient))

        send = self._send(self.promoter)

        self.assertTrue(send.earns_points)
        self.assertEqual(send.organization, self.org)
        self.assertEqual(send.sender, self.promoter)
        entries = self._entries(send)
        self.assertEqual(len(entries), 1)
        entry = entries[0]
        self.assertEqual(entry.kind, ContributionKind.PROMO_MESSAGE)
        self.assertEqual(entry.points, 1)
        self.assertEqual(entry.org_user.user, self.promoter)
        self.assertEqual(entry.event, self.event)
        self.assertEqual(entry.occurred_at, send.sent_at)

    def test_second_send_by_other_promoter_does_not_earn(self) -> None:
        self._send(self.promoter)
        self.assertFalse(will_earn(self.promoter_b, self.event, self.recipient))

        second = self._send(self.promoter_b)

        self.assertFalse(second.earns_points)
        self.assertEqual(self._entries(second), [])
        self.assertEqual(ContributionEntry.objects.nocache().count(), 1)

    def test_undo_first_promotes_second(self) -> None:
        first = self._send(self.promoter)
        second = self._send(self.promoter_b)

        undo_promo_send(first, actor=self.promoter)

        self.assertFalse(PromoSend.objects.filter(pk=first.pk).exists())
        second.refresh_from_db()
        self.assertTrue(second.earns_points)
        entries = self._entries(second)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].org_user.user, self.promoter_b)
        self.assertEqual(entries[0].occurred_at, second.sent_at)
        self.assertEqual(ContributionEntry.objects.nocache().count(), 1)

    def test_undo_non_earning_send_leaves_earning_send(self) -> None:
        first = self._send(self.promoter)
        second = self._send(self.promoter_b)

        undo_promo_send(second, actor=self.promoter_b)

        first.refresh_from_db()
        self.assertTrue(first.earns_points)
        self.assertEqual(len(self._entries(first)), 1)
        self.assertEqual(ContributionEntry.objects.nocache().count(), 1)

    def test_site_admin_without_role_does_not_earn(self) -> None:
        self.assertFalse(will_earn(self.site_admin, self.event, self.recipient))

        send = self._send(self.site_admin)

        self.assertFalse(send.earns_points)
        self.assertEqual(self._entries(send), [])
        self.assertFalse(
            OrgUser.objects.filter(user=self.site_admin, organization=self.org).exists()
        )

    def test_site_admin_send_does_not_block_promoter(self) -> None:
        self._send(self.site_admin)
        self.assertTrue(will_earn(self.promoter, self.event, self.recipient))

        promo = self._send(self.promoter)

        self.assertTrue(promo.earns_points)
        self.assertEqual(len(self._entries(promo)), 1)

    def test_undo_with_only_site_admin_send_remaining_promotes_nothing(self) -> None:
        earning = self._send(self.promoter)
        admin_send = self._send(self.site_admin)

        undo_promo_send(earning, actor=self.promoter)

        admin_send.refresh_from_db()
        self.assertFalse(admin_send.earns_points)
        self.assertFalse(ContributionEntry.objects.nocache().exists())

    def test_undo_skips_revoked_sender_for_later_role_holder(self) -> None:
        earning = self._send(self.promoter)
        revoked = self._send(self.promoter_b)
        later = self._send(self.staff)
        self.org.promoters.remove(self.promoter_b)

        undo_promo_send(earning, actor=self.staff)

        revoked.refresh_from_db()
        later.refresh_from_db()
        self.assertFalse(revoked.earns_points)
        self.assertTrue(later.earns_points)
        self.assertEqual(len(self._entries(later)), 1)

    def test_owner_without_org_user_gets_one(self) -> None:
        self.assertFalse(
            OrgUser.objects.filter(user=self.owner, organization=self.org).exists()
        )

        send = self._send(self.owner)

        self.assertTrue(send.earns_points)
        org_user = OrgUser.objects.get(user=self.owner, organization=self.org)
        self.assertEqual(self._entries(send)[0].org_user, org_user)

    def test_send_does_not_touch_recipient_membership(self) -> None:
        OrgUser.objects.filter(user=self.recipient).delete()

        self._send(self.promoter)

        self.assertFalse(OrgUser.objects.filter(user=self.recipient).exists())


class CanUndoTest(_SendFixture):
    def test_staff_can_undo_another_send(self) -> None:
        send = self._send(self.promoter)
        self.assertTrue(can_undo(self.staff, send))
        self.assertTrue(can_undo(self.owner, send))
        self.assertTrue(can_undo(self.site_admin, send))

    def test_sender_can_undo_own_send(self) -> None:
        send = self._send(self.promoter)
        self.assertTrue(can_undo(self.promoter, send))

    def test_other_promoter_cannot_undo(self) -> None:
        send = self._send(self.promoter)
        self.assertFalse(can_undo(self.promoter_b, send))

    def test_revoked_sender_cannot_undo(self) -> None:
        send = self._send(self.promoter)
        self.org.promoters.remove(self.promoter)
        self.assertFalse(can_undo(self.promoter, send))

    def test_sender_cannot_undo_when_promotion_locked(self) -> None:
        send = self._send(self.promoter)
        set_org_feature(self.org, FeatureKey.PROMOTION, enabled=False, actor=None)
        self.assertFalse(can_undo(self.promoter, send))
