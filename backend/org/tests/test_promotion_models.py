from datetime import UTC, datetime, timedelta

from django.db import IntegrityError, transaction
from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from app.models import CustomUser, League, Organization
from common.discord_format import discord_timestamp
from events.models import Event
from org.contributions.kinds import ContributionKind
from org.contributions.services import repoint_user_attribution
from org.feature_keys import FeatureKey
from org.features import set_org_feature
from org.models import ContributionEntry, OrgUser, PromoSend, PromoTemplate
from org.promotion.starter import (
    STARTER_TEMPLATE_BODY,
    STARTER_TEMPLATE_NAME,
    seed_starter_template,
)


class DiscordTimestampTest(SimpleTestCase):
    def test_relative_style(self) -> None:
        dt = datetime(2026, 11, 15, 1, 0, tzinfo=UTC)
        self.assertEqual(discord_timestamp(dt, "R"), "<t:1794704400:R>")

    def test_default_style_is_full(self) -> None:
        dt = datetime(2026, 11, 15, 1, 0, tzinfo=UTC)
        self.assertEqual(discord_timestamp(dt), "<t:1794704400:F>")


class _PromoFixture(TestCase):
    def setUp(self) -> None:
        self.admin = CustomUser.objects.create_user(
            username="promo_admin", password="x"
        )
        self.sender = CustomUser.objects.create_user(
            username="promo_sender", password="x"
        )
        self.recipient = CustomUser.objects.create_user(
            username="promo_recipient", password="x"
        )
        self.org = Organization.objects.create(name="Promo Org", owner=self.admin)
        self.league = League.objects.create(
            name="Promo League", organization=self.org, steam_league_id=99771
        )
        self.event = Event.objects.create(
            organization=self.org,
            name="Promo Event",
            scheduled_at=timezone.now() + timedelta(days=2),
            created_by=self.admin,
            tournament_league=self.league,
        )

    def _send(self, *, earns_points: bool) -> PromoSend:
        return PromoSend.objects.create(
            organization=self.org,
            event=self.event,
            recipient=self.recipient,
            sender=self.sender,
            text="hi",
            earns_points=earns_points,
        )


class PromoSendModelTest(_PromoFixture):
    def test_two_earning_sends_for_same_recipient_rejected(self) -> None:
        self._send(earns_points=True)
        with self.assertRaises(IntegrityError), transaction.atomic():
            self._send(earns_points=True)

    def test_non_earning_sends_allowed(self) -> None:
        self._send(earns_points=True)
        self._send(earns_points=False)
        self._send(earns_points=False)
        self.assertEqual(PromoSend.objects.filter(event=self.event).count(), 3)

    def test_event_delete_cascades_sends_and_keeps_entry(self) -> None:
        send = self._send(earns_points=True)
        org_user = OrgUser.objects.create(user=self.sender, organization=self.org)
        entry = ContributionEntry.objects.create(
            org_user=org_user,
            organization=self.org,
            kind=ContributionKind.PROMO_MESSAGE,
            points=1,
            event=self.event,
            event_name=self.event.name,
            promo_send=send,
            occurred_at=send.sent_at,
        )

        self.event.delete()

        self.assertFalse(PromoSend.objects.filter(pk=send.pk).exists())
        entry.refresh_from_db()
        self.assertIsNone(entry.promo_send_id)
        self.assertIsNone(entry.event_id)
        self.assertEqual(entry.event_name, "Promo Event")

    def test_one_entry_per_promo_send(self) -> None:
        send = self._send(earns_points=True)
        org_user = OrgUser.objects.create(user=self.sender, organization=self.org)
        fields: dict[str, object] = {
            "org_user": org_user,
            "organization": self.org,
            "kind": ContributionKind.PROMO_MESSAGE,
            "points": 1,
            "event": self.event,
            "promo_send": send,
            "occurred_at": send.sent_at,
        }
        ContributionEntry.objects.create(**fields)
        with self.assertRaises(IntegrityError), transaction.atomic():
            ContributionEntry.objects.create(**fields)


class StarterTemplateTest(_PromoFixture):
    def test_starter_body_uses_required_placeholders(self) -> None:
        for token in (
            "{player}",
            "{event}",
            "{event_time}",
            "{event_time_relative}",
            "{event_link}",
            "{promoter}",
            "{org}",
        ):
            self.assertIn(token, STARTER_TEMPLATE_BODY)
        self.assertLessEqual(len(STARTER_TEMPLATE_BODY), 2000)

    def test_unlock_promotion_seeds_one_template(self) -> None:
        set_org_feature(self.org, FeatureKey.PROMOTION, enabled=True, actor=self.admin)

        templates = list(PromoTemplate.objects.filter(organization=self.org))
        self.assertEqual(len(templates), 1)
        self.assertEqual(templates[0].name, STARTER_TEMPLATE_NAME)
        self.assertEqual(templates[0].body, STARTER_TEMPLATE_BODY)
        self.assertEqual(templates[0].created_by_id, self.admin.pk)

    def test_relock_and_reunlock_does_not_seed_again(self) -> None:
        set_org_feature(self.org, FeatureKey.PROMOTION, enabled=True, actor=self.admin)
        set_org_feature(self.org, FeatureKey.PROMOTION, enabled=False, actor=self.admin)
        set_org_feature(self.org, FeatureKey.PROMOTION, enabled=True, actor=self.admin)

        self.assertEqual(PromoTemplate.objects.filter(organization=self.org).count(), 1)

    def test_reunlock_after_templates_deleted_seeds_again(self) -> None:
        set_org_feature(self.org, FeatureKey.PROMOTION, enabled=True, actor=self.admin)
        set_org_feature(self.org, FeatureKey.PROMOTION, enabled=False, actor=self.admin)
        PromoTemplate.objects.filter(organization=self.org).delete()
        set_org_feature(self.org, FeatureKey.PROMOTION, enabled=True, actor=self.admin)

        self.assertEqual(PromoTemplate.objects.filter(organization=self.org).count(), 1)

    def test_locked_or_contributions_does_not_seed(self) -> None:
        set_org_feature(self.org, FeatureKey.PROMOTION, enabled=False, actor=self.admin)
        set_org_feature(
            self.org, FeatureKey.CONTRIBUTIONS, enabled=True, actor=self.admin
        )

        self.assertFalse(PromoTemplate.objects.filter(organization=self.org).exists())

    def test_seed_skips_org_with_templates(self) -> None:
        PromoTemplate.objects.create(organization=self.org, name="Mine", body="x")

        self.assertIsNone(seed_starter_template(self.org, self.admin))
        self.assertEqual(PromoTemplate.objects.filter(organization=self.org).count(), 1)

    def test_repoint_user_attribution_moves_template_author(self) -> None:
        template = PromoTemplate.objects.create(
            organization=self.org, name="Mine", body="x", created_by=self.sender
        )

        changed = repoint_user_attribution(self.sender, self.recipient)

        self.assertEqual(changed, 1)
        template.refresh_from_db()
        self.assertEqual(template.created_by_id, self.recipient.pk)
