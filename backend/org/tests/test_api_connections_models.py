from django.db import IntegrityError, transaction
from django.db.models.deletion import RestrictedError
from django.test import TestCase
from django.utils import timezone

from app.models import CustomUser
from events.models import Event
from org import models_api_connections as connections
from org.models import Organization, OrgApiToken, OrgUser
from org.models_promotion_sync import (
    ExternalPromotionReceipt,
    PromotionContactOutbox,
    PromotionImportObservation,
)


class ConnectionModelsTests(TestCase):
    def setUp(self) -> None:
        self.org = Organization.objects.create(name="Connection schema")
        self.user = CustomUser.objects.create(username="connection_owner")
        self.member = OrgUser.objects.create(organization=self.org, user=self.user)
        self.connection = connections.OrgApiConnection.objects.create(
            organization=self.org, name="Ratings"
        )

    def token(self, suffix: str, **kwargs: object) -> OrgApiToken:
        return OrgApiToken.objects.create(
            organization=self.org,
            user=self.user,
            connection=self.connection,
            name=suffix,
            prefix=f"schema_{suffix}",
            secret_hash="a" * 64,
            **kwargs,
        )

    def test_new_connection_is_disabled_and_keyless(self) -> None:
        for flag in (
            "enabled",
            "inbound_enabled",
            "mmr_push_enabled",
            "mmr_pull_enabled",
            "promotion_push_enabled",
        ):
            self.assertIs(getattr(self.connection, flag), False)
        self.assertEqual(self.connection.operations, [])
        self.assertEqual(self.connection.config_version, 1)
        self.assertIsNone(self.connection.outbound_authorizer)
        self.assertFalse(self.connection.tokens.exists())
        self.assertFalse(connections.OrgApiPromotionAdoption.objects.exists())

    def test_constraints_allow_legacy_but_only_one_new_active_credential(self) -> None:
        self.token("legacy1", legacy_credential=True)
        self.token("legacy2", legacy_credential=True)
        self.token("revoked", revoked_at=timezone.now())
        self.token("current")
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.token("duplicate")

    def test_connection_delete_restricted_by_token(self) -> None:
        token = self.token("restricted")
        for revoked in (None, timezone.now()):
            token.revoked_at = revoked
            token.save(update_fields=["revoked_at"])
            with self.assertRaises(RestrictedError), transaction.atomic():
                self.connection.delete()

    def test_only_one_active_pull_per_connection(self) -> None:
        connections.OrgApiSyncRun.objects.create(
            organization=self.org, connection=self.connection, kind="mmr_pull"
        )
        with self.assertRaises(IntegrityError), transaction.atomic():
            connections.OrgApiSyncRun.objects.create(
                organization=self.org,
                connection=self.connection,
                kind="mmr_pull",
                state="partial",
            )
        connections.OrgApiSyncRun.objects.create(
            organization=self.org,
            connection=self.connection,
            kind="mmr_pull",
            state="succeeded",
        )

    def test_only_one_promotion_stream_and_unique_event_occasion(self) -> None:
        binding = connections.OrgApiPromotionBinding.objects.create(
            organization=self.org, connection=self.connection, guild_id="123"
        )
        other = connections.OrgApiConnection.objects.create(
            organization=self.org, name="Other"
        )
        with self.assertRaises(IntegrityError), transaction.atomic():
            connections.OrgApiPromotionBinding.objects.create(
                organization=self.org, connection=other, guild_id="123"
            )
        event = Event.objects.create(
            organization=self.org, name="Bound", scheduled_at=timezone.now()
        )
        connections.OrgApiPromotionEventBinding.objects.create(
            binding=binding, event=event, occasion_id=123, effective_at=timezone.now()
        )
        with self.assertRaises(IntegrityError), transaction.atomic():
            connections.OrgApiPromotionEventBinding.objects.create(
                binding=binding,
                event=event,
                occasion_id=456,
                effective_at=timezone.now(),
            )
        event2 = Event.objects.create(
            organization=self.org, name="Second", scheduled_at=timezone.now()
        )
        with self.assertRaises(IntegrityError), transaction.atomic():
            connections.OrgApiPromotionEventBinding.objects.create(
                binding=binding,
                event=event2,
                occasion_id=123,
                effective_at=timezone.now(),
            )

    def test_membership_delete_removes_staging_and_cancels_delivery(self) -> None:
        run = connections.OrgApiSyncRun.objects.create(
            organization=self.org, connection=self.connection, kind="mmr_pull"
        )
        connections.OrgApiRunCheckpoint.objects.create(run=run)
        connections.OrgApiMmrPullTarget.objects.create(
            run=run, org_user=self.member, game_type=1, proposed_value=4000
        )
        connections.OrgMmrSyncState.objects.create(org_user=self.member, game_type=1)
        delivery = connections.OrgApiMmrDelivery.objects.create(
            connection=self.connection,
            org_user=self.member,
            game_type=1,
            revision=1,
            payload={"mmr": 4000},
        )
        self.member.delete()
        delivery.refresh_from_db()
        self.assertEqual(delivery.state, "canceled")
        self.assertIsNone(delivery.org_user_id)
        self.assertEqual(delivery.payload, {"mmr": 4000})
        self.assertFalse(connections.OrgApiMmrPullTarget.objects.exists())
        self.assertFalse(connections.OrgMmrSyncState.objects.exists())

    def test_org_delete_cascades_connections_tokens_and_ledgers(self) -> None:
        self.connection.legacy_multi_credential = True
        self.connection.save(update_fields=["legacy_multi_credential"])
        self.token("active", legacy_credential=True, operations=["promotion:import"])
        self.token("old", legacy_credential=True, revoked_at=timezone.now())
        run = connections.OrgApiSyncRun.objects.create(
            organization=self.org, connection=self.connection, kind="mmr_pull"
        )
        connections.OrgApiRunCheckpoint.objects.create(run=run)
        connections.OrgApiMmrPullTarget.objects.create(
            run=run, org_user=self.member, game_type=1, proposed_value=10
        )
        connections.OrgApiMmrDelivery.objects.create(
            connection=self.connection, org_user=self.member, game_type=1, revision=1
        )
        connections.OrgMmrSyncState.objects.create(org_user=self.member, game_type=1)
        connections.OrgMmrRevisionCounter.objects.create(
            organization=self.org, game_type=1
        )
        connections.OrgApiPromotionBinding.objects.create(
            organization=self.org, connection=self.connection, guild_id="123"
        )
        connections.OrgApiPromotionAdoption.objects.create(
            organization=self.org, connection=self.connection
        )
        now = timezone.now()
        outside = Organization.objects.create(name="Unrelated")
        receipt_kwargs = {
            "source": "contact_log",
            "source_contact_id": 123,
            "recorded_at": now,
            "contact_date_ny": now.date(),
            "contact_method": "DISCORD_DM",
            "contact_reason": "EVENT_INVITE",
            "discord_id": "123",
            "source_hash": "a" * 64,
            "occasion_id": 88,
        }
        ExternalPromotionReceipt.objects.create(
            organization=self.org, connection=self.connection, **receipt_kwargs
        )
        survivor = ExternalPromotionReceipt.objects.create(
            organization=outside, **receipt_kwargs
        )
        PromotionImportObservation.objects.create(
            organization=self.org,
            connection=self.connection,
            after=0,
            through=1,
            observed_at=now,
        )
        PromotionContactOutbox.objects.create(
            organization=self.org,
            connection=self.connection,
            local_send_id=123,
            event_id=123,
            sent_at=now,
        )
        self.org.delete()
        self.assertTrue(
            ExternalPromotionReceipt.objects.filter(pk=survivor.pk).exists()
        )
        for model in (
            connections.OrgApiConnection,
            connections.OrgApiSyncRun,
            connections.OrgApiRunCheckpoint,
            connections.OrgApiMmrPullTarget,
            connections.OrgApiMmrDelivery,
            connections.OrgMmrSyncState,
            connections.OrgMmrRevisionCounter,
            connections.OrgApiPromotionBinding,
            connections.OrgApiPromotionAdoption,
            OrgApiToken,
            PromotionImportObservation,
            PromotionContactOutbox,
        ):
            self.assertFalse(model.objects.exists(), model.__name__)

    def test_connection_delete_preserves_provenance_rows(self) -> None:
        now = timezone.now()
        observation = PromotionImportObservation.objects.create(
            organization=self.org,
            connection=self.connection,
            after=0,
            through=1,
            observed_at=now,
        )
        connections.OrgApiPromotionAdoption.objects.create(
            organization=self.org, connection=self.connection
        )
        self.connection.delete()
        observation.refresh_from_db()
        self.assertIsNone(observation.connection_id)
