"""The opt-in synthetic external contact fixtures for the promotion E2E specs."""

from unittest.mock import patch

from django.conf import settings
from django.test import TestCase
from rest_framework.test import APIRequestFactory

from app.models import CustomUser
from events.models import Event
from org.integration.contacts import contact_sync_status
from org.models import ContributionEntry, Organization, OrgUser, PromoSend
from org.models_promotion_sync import (
    ExternalPromotionReceipt,
    PromotionContactOutbox,
)
from org.promotion.recipients import CandidateSource, candidates
from tests.data.org_features import FEATURES_ORG, OF_PROMOTER
from tests.populate.org_features import (
    populate_org_features_data,
    reset_org_features_data,
)
from tests.test_org_features import reset_org_features


class PromotionIntegrationFixtureTests(TestCase):
    def setUp(self) -> None:
        self.original_sync = settings.PROMOTION_SYNC
        self.addCleanup(reset_org_features_data)
        populate_org_features_data()

    def _rows(self, event: Event, source: CandidateSource) -> dict[str, dict]:
        rows = candidates(
            Organization.objects.get(pk=FEATURES_ORG.pk),
            event,
            n=3,
            sender=CustomUser.objects.get(pk=OF_PROMOTER.pk),
            source=source,
            days=30,
            hide_signed_up=False,
            hide_messaged=False,
        )
        return {r["discordId"]: r for r in rows}

    def test_seeds_bound_event_receipts_without_sends_awards_or_accounts(
        self,
    ) -> None:
        with patch("discordbot.services.discord_members.requests.get") as fetch:
            before_users = CustomUser.objects.count()
            data = reset_org_features_data(external_contacts=True)
            refs = data["external_contacts"]
            event = Event.objects.get(pk=data["events"]["upcoming"]["pk"])
            org = Organization.objects.get(pk=FEATURES_ORG.pk)

            binding = settings.PROMOTION_SYNC.for_org(org.pk)
            self.assertIsNotNone(binding)
            self.assertIn(event.pk, binding.events)
            sync = contact_sync_status(org, event)
            self.assertTrue(sync["configured"])
            self.assertIsNotNone(sync["last_receipt_imported_at"])

            self.assertEqual(
                set(refs),
                {"external", "local_and_external", "discord_only", "non_member"},
            )
            self.assertEqual(
                ExternalPromotionReceipt.objects.filter(event=event).count(), 4
            )
            self.assertEqual(
                PromoSend.objects.filter(event=event).count(), 1
            )  # the audience fixture's seeded local send only
            self.assertFalse(
                ContributionEntry.objects.filter(promo_send__event=event).exists()
            )
            self.assertFalse(
                OrgUser.objects.filter(
                    organization=org, user_id=refs["non_member"]["pk"]
                ).exists()
            )
            # Seeding audiences adds its own linked accounts; receipts add none.
            self.assertEqual(
                CustomUser.objects.count() - before_users,
                CustomUser.objects.filter(username__startswith="audience_").count(),
            )

            recent = self._rows(event, CandidateSource.RECENT)
            self.assertIsNotNone(
                recent[refs["non_member"]["discord_id"]]["external_contact"]
            )
            active = self._rows(event, CandidateSource.ACTIVE)
            external = active[refs["external"]["discord_id"]]
            self.assertTrue(external["contact_recorded"])
            self.assertIsNone(external["last_messaged"])
            both = active[refs["local_and_external"]["discord_id"]]
            self.assertIsNotNone(both["last_messaged"])
            self.assertIsNotNone(both["external_contact"])
            discord = self._rows(event, CandidateSource.DISCORD)
            only = discord[refs["discord_only"]["discord_id"]]
            self.assertIsNone(only["user_pk"])
            self.assertIsNotNone(only["external_contact"])
            fetch.assert_not_called()

    def test_ordinary_reset_restores_bindings_and_clears_evidence(self) -> None:
        with patch("discordbot.services.discord_members.requests.get"):
            reset_org_features_data(external_contacts=True)
            reset_org_features_data()
        self.assertIs(settings.PROMOTION_SYNC, self.original_sync)
        self.assertFalse(
            ExternalPromotionReceipt.objects.filter(
                organization_id=FEATURES_ORG.pk
            ).exists()
        )
        self.assertFalse(
            PromotionContactOutbox.objects.filter(
                organization_id=FEATURES_ORG.pk
            ).exists()
        )

    def test_reset_rejects_non_boolean_external_contacts_option(self) -> None:
        request = APIRequestFactory().post(
            "/", {"external_contacts": "true"}, format="json"
        )
        with patch("tests.test_org_features.isTestEnvironment", return_value=True):
            response = reset_org_features(request)
        self.assertEqual(response.status_code, 400)
        self.assertIs(settings.PROMOTION_SYNC, self.original_sync)
