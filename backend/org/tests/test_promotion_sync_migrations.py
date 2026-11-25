"""Upgrade and rollback compatibility for the promotion contact sync migrations.

``0026_api_token_operations`` and ``0027_promotion_sync_receipts`` are
additive. Upgrading must leave every pre-feature token MMR-only and every
send, award and leadership row untouched, and must not backfill receipts or
outbox rows. Rolling back is possible on a disposable database, but it drops
the retained receipts and outbox, so the operator docs tell people to turn
the integration off instead of migrating back over retained data.
"""

from datetime import UTC, datetime

from django_test_migrations.contrib.unittest_case import MigratorTestCase

AT = datetime(2026, 11, 20, 12, 0, tzinfo=UTC)
BEFORE = ("org", "0025_mmrchangerequest")
OPERATIONS = ("org", "0026_api_token_operations")
RECEIPTS = ("org", "0027_promotion_sync_receipts")
MMR_PAIR = ["mmr:read", "mmr:write"]


def _seed_pre_feature(apps) -> dict[str, list[int] | int]:
    """Tokens, sends (one earning, one repeat), an award and leadership."""
    CustomUser = apps.get_model("app", "CustomUser")
    Organization = apps.get_model("org", "Organization")
    OrgUser = apps.get_model("org", "OrgUser")
    Event = apps.get_model("events", "Event")
    PromoSend = apps.get_model("org", "PromoSend")
    Entry = apps.get_model("org", "ContributionEntry")
    Token = apps.get_model("org", "OrgApiToken")

    owner = CustomUser.objects.create(username="compat_owner", discordId="11")
    other = CustomUser.objects.create(username="compat_other", discordId="12")
    recipient = CustomUser.objects.create(username="compat_rcpt", discordId="13")
    org = Organization.objects.create(name="Compat Org", owner=owner)
    owner_ou = OrgUser.objects.create(user=owner, organization=org)
    other_ou = OrgUser.objects.create(user=other, organization=org)
    event = Event.objects.create(
        organization=org, name="Compat Event", scheduled_at=AT, created_by=owner
    )
    earning = PromoSend.objects.create(
        organization=org,
        event=event,
        recipient=recipient,
        sender=owner,
        text="first",
        earns_points=True,
    )
    repeat = PromoSend.objects.create(
        organization=org,
        event=event,
        recipient=recipient,
        sender=other,
        text="repeat",
        earns_points=False,
    )
    entries = [
        Entry.objects.create(
            organization=org,
            org_user=owner_ou,
            kind="promo_message",
            points=1,
            event=event,
            promo_send=earning,
            occurred_at=AT,
        ).pk,
        Entry.objects.create(
            organization=org,
            org_user=other_ou,
            track="leadership",
            kind="captained",
            points=5,
            event=event,
            occurred_at=AT,
        ).pk,
        Entry.objects.create(
            organization=org,
            org_user=other_ou,
            kind="manual",
            points=-2,
            reason="correction",
            occurred_at=AT,
        ).pk,
    ]
    tokens = [
        Token.objects.create(
            organization=org,
            user=owner,
            name=f"legacy {i}",
            prefix=f"compat{i:06d}",
            secret_hash=f"{i}" * 64,
        ).pk
        for i in range(2)
    ]
    return {
        "org": org.pk,
        "event": event.pk,
        "sends": [earning.pk, repeat.pk],
        "entries": entries,
        "tokens": tokens,
    }


def _ledger(apps, pks) -> list[tuple]:
    Entry = apps.get_model("org", "ContributionEntry")
    return list(
        Entry.objects.filter(pk__in=pks)
        .order_by("pk")
        .values_list("track", "kind", "points", "promo_send_id", "org_user_id")
    )


def _sends(apps, pks) -> list[tuple]:
    PromoSend = apps.get_model("org", "PromoSend")
    return list(
        PromoSend.objects.filter(pk__in=pks)
        .order_by("pk")
        .values_list("sender_id", "recipient_id", "text", "earns_points")
    )


class UpgradeFromBeforeTheFeatureTest(MigratorTestCase):
    migrate_from = BEFORE
    migrate_to = RECEIPTS

    def prepare(self) -> None:
        apps = self.old_state.apps
        self.seed = _seed_pre_feature(apps)
        self.ledger_before = _ledger(apps, self.seed["entries"])
        self.sends_before = _sends(apps, self.seed["sends"])

    def test_pre_feature_tokens_get_only_the_mmr_pair(self) -> None:
        Token = self.new_state.apps.get_model("org", "OrgApiToken")
        self.assertEqual(
            [t.operations for t in Token.objects.filter(pk__in=self.seed["tokens"])],
            [MMR_PAIR, MMR_PAIR],
        )

    def test_sends_and_ledger_rows_are_unchanged(self) -> None:
        apps = self.new_state.apps
        self.assertEqual(_sends(apps, self.seed["sends"]), self.sends_before)
        self.assertEqual(_ledger(apps, self.seed["entries"]), self.ledger_before)

    def test_nothing_is_backfilled(self) -> None:
        apps = self.new_state.apps
        for model in ("PromotionContactOutbox", "ExternalPromotionReceipt"):
            with self.subTest(model=model):
                self.assertFalse(apps.get_model("org", model).objects.exists())


class RollbackOnDisposableDatabaseTest(MigratorTestCase):
    """Down to 0023 and back up again, with feature data present."""

    migrate_from = RECEIPTS
    migrate_to = BEFORE

    def prepare(self) -> None:
        apps = self.old_state.apps
        self.seed = _seed_pre_feature(apps)
        self.ledger_before = _ledger(apps, self.seed["entries"])
        self.sends_before = _sends(apps, self.seed["sends"])
        Token = apps.get_model("org", "OrgApiToken")
        Token.objects.filter(pk=self.seed["tokens"][0]).update(
            operations=["contributions:read", "promotion:import", "promotion:read"]
        )
        Organization = apps.get_model("org", "Organization")
        org = Organization.objects.get(pk=self.seed["org"])
        Receipt = apps.get_model("org", "ExternalPromotionReceipt")
        Receipt.objects.create(
            organization=org,
            source="contact_log",
            source_contact_id="8001",
            event_id=self.seed["event"],
            discord_id="13",
            recorded_at=AT,
            contact_method="DISCORD_DM",
            linkage="occasion",
            source_hash="a" * 64,
        )
        Outbox = apps.get_model("org", "PromotionContactOutbox")
        Outbox.objects.create(
            organization=org,
            local_send_id=self.seed["sends"][1],
            event_id=self.seed["event"],
            sender_user_id=1,
            recipient_user_id=2,
            sent_at=AT,
            state="paused",
        )

    def test_rollback_keeps_legacy_rows_and_drops_feature_tables(self) -> None:
        apps = self.new_state.apps
        self.assertEqual(_sends(apps, self.seed["sends"]), self.sends_before)
        self.assertEqual(_ledger(apps, self.seed["entries"]), self.ledger_before)
        model_names = {m.__name__ for m in apps.get_app_config("org").get_models()}
        # Retained evidence does not survive a migration rollback; the docs
        # therefore advise disabling the integration instead.
        self.assertNotIn("ExternalPromotionReceipt", model_names)
        self.assertNotIn("PromotionContactOutbox", model_names)

    def test_upgrading_again_never_widens_a_grant(self) -> None:
        new = self._migrator.apply_tested_migration(RECEIPTS)
        Token = new.apps.get_model("org", "OrgApiToken")
        self.assertEqual(
            [
                t.operations
                for t in Token.objects.filter(pk__in=self.seed["tokens"]).order_by("pk")
            ],
            [MMR_PAIR, MMR_PAIR],
        )
        self.assertFalse(
            new.apps.get_model("org", "ExternalPromotionReceipt").objects.exists()
        )
        self.assertFalse(
            new.apps.get_model("org", "PromotionContactOutbox").objects.exists()
        )
        self.assertEqual(_sends(new.apps, self.seed["sends"]), self.sends_before)
