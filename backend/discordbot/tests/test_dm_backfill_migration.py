import importlib
import unittest
from datetime import UTC, datetime
from types import ModuleType
from typing import Any

# django-test-migrations is a dev dep; a stale CI image may lack it.
try:
    from django_test_migrations.contrib.unittest_case import MigratorTestCase
except ImportError as _import_error:  # pragma: no cover
    raise unittest.SkipTest(
        "django-test-migrations not installed — rebuild backend-dev image "
        "to pick up the new dev dep from pyproject.toml."
    ) from _import_error

CREATED = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)
SENT = datetime(2026, 10, 1, 12, 5, tzinfo=UTC)
LOG_CREATED = datetime(2026, 10, 2, 9, 0, tzinfo=UTC)

EVENT_DM_FIELDS = (
    "id",
    "discord_event_id",
    "org_user_id",
    "dm_type",
    "message_id",
    "sent_at",
    "delivered",
    "responded",
    "response_text",
    "responded_at",
    "created_at",
)
MESSAGE_LOG_FIELDS = (
    "id",
    "channel_id",
    "embed_data",
    "discord_message_id",
    "status_code",
    "response_data",
    "success",
    "claimed_at",
    "source",
    "source_id",
    "tournament_log_id",
    "fired_by_id",
    "created_at",
)


def _migration_module() -> ModuleType:
    return importlib.import_module(
        "discordbot.migrations.0018_backfill_discord_dm_ledger"
    )


class DiscordDMBackfillMigrationTest(MigratorTestCase):
    migrate_from = ("discordbot", "0017_discord_dm_ledger")
    migrate_to = ("discordbot", "0018_backfill_discord_dm_ledger")

    def prepare(self) -> None:
        apps = self.old_state.apps
        CustomUser = apps.get_model("app", "CustomUser")
        Organization = apps.get_model("org", "Organization")
        OrgUser = apps.get_model("org", "OrgUser")
        Event = apps.get_model("events", "Event")
        League = apps.get_model("league", "League")
        Tournament = apps.get_model("tournament", "Tournament")
        DiscordEvent = apps.get_model("discordbot", "DiscordEvent")
        DiscordEventDM = apps.get_model("discordbot", "DiscordEventDM")
        TournamentLog = apps.get_model("discordbot", "DiscordTournamentLog")
        MessageLog = apps.get_model("discordbot", "DiscordMessageLog")

        org = Organization.objects.create(name="Backfill Org")
        self.org_id = org.pk
        with_discord = CustomUser.objects.create(username="bf_dm", discordId="9001")
        without_discord = CustomUser.objects.create(username="bf_nodiscord")
        self.user_id = with_discord.pk
        member = OrgUser.objects.create(user=with_discord, organization=org)
        other = OrgUser.objects.create(user=without_discord, organization=org)
        event = Event.objects.create(
            organization=org, name="Backfill Event", scheduled_at=CREATED
        )
        self.event_id = event.pk
        discord_event = DiscordEvent.objects.create(event=event, guild_id="g1")

        def event_dm(org_user: Any, **fields: Any) -> int:
            dm = DiscordEventDM.objects.create(
                discord_event=discord_event, org_user=org_user, dm_type=1, **fields
            )
            DiscordEventDM.objects.filter(pk=dm.pk).update(created_at=CREATED)
            return dm.pk

        self.delivered = event_dm(
            member, delivered=True, message_id="555", sent_at=SENT
        )
        self.fake = event_dm(
            other, delivered=True, message_id="test-fake-message-id", sent_at=SENT
        )
        self.fake_two = event_dm(
            member, delivered=True, message_id="test-fake-message-id"
        )
        self.undelivered = event_dm(other, delivered=False)

        league = League.objects.create(name="Backfill League", organization=org)
        tournament = Tournament.objects.create(
            name="Backfill T", date_played=CREATED, league=league
        )
        leagueless = Tournament.objects.create(name="No League", date_played=CREATED)
        Event.objects.create(
            organization=org,
            name="Leagueless Event",
            scheduled_at=CREATED,
            tournament=leagueless,
        )
        draft_log = TournamentLog.objects.create(
            tournament=tournament, notification_type="draft_link", message="m"
        )
        hero_log = TournamentLog.objects.create(
            tournament=tournament, notification_type="herodraft_link", message="m"
        )
        fallback_log = TournamentLog.objects.create(
            tournament=leagueless, notification_type="draft_link", message="m"
        )
        self.draft_log_id = draft_log.pk

        def message_log(**fields: Any) -> int:
            row = MessageLog.objects.create(
                channel_id="dmchan",
                embed_data={"title": "Draft link", "url": "https://secret"},
                source=fields.pop("source", "tournament_dm"),
                **fields,
            )
            MessageLog.objects.filter(pk=row.pk).update(created_at=LOG_CREATED)
            return row.pk

        self.log_draft = message_log(
            success=True,
            status_code=200,
            discord_message_id="777",
            response_data={"id": "777", "content": "body"},
            tournament_log=draft_log,
        )
        self.log_hero_failed = message_log(success=False, tournament_log=hero_log)
        self.log_no_tlog = message_log(success=True, discord_message_id="778")
        self.log_fallback = message_log(
            success=True, discord_message_id="779", tournament_log=fallback_log
        )
        self.log_channel = message_log(
            source="event_announcement", source_id=event.pk, success=True
        )

        self.before_event_dms = list(
            DiscordEventDM.objects.order_by("pk").values(*EVENT_DM_FIELDS)
        )
        self.before_logs = list(
            MessageLog.objects.order_by("pk").values(*MESSAGE_LOG_FIELDS)
        )

    def _ledger(self) -> Any:
        return self.new_state.apps.get_model("discordbot", "DiscordDM")

    def _event_row(self, pk: int) -> Any:
        return self._ledger().objects.get(idempotency_key=f"legacy:discordeventdm:{pk}")

    def _log_row(self, pk: int) -> Any:
        return self._ledger().objects.get(
            idempotency_key=f"legacy:discordmessagelog:{pk}"
        )

    def test_delivered_event_dm_becomes_sent(self) -> None:
        row = self._event_row(self.delivered)
        self.assertEqual(row.kind, "signup_reminder")
        self.assertEqual(row.status, "sent")
        self.assertEqual(row.discord_message_id, "555")
        self.assertEqual(row.sent_at, SENT)
        self.assertEqual(row.backfilled_from, "discordeventdm")
        self.assertEqual(row.recipient_id, self.user_id)
        self.assertEqual(row.discord_user_id, "9001")
        self.assertEqual(row.organization_id, self.org_id)
        self.assertEqual((row.subject_type, row.subject_id), ("event", self.event_id))
        self.assertFalse(row.retryable)
        self.assertIsNotNone(row.finished_at)

    def test_fake_message_id_becomes_skipped_test_mode(self) -> None:
        for pk in (self.fake, self.fake_two):
            row = self._event_row(pk)
            self.assertEqual(row.status, "skipped_test_mode")
            self.assertIsNone(row.discord_message_id)
        self.assertEqual(self._event_row(self.fake).discord_user_id, "")

    def test_undelivered_becomes_failed_not_retryable(self) -> None:
        row = self._event_row(self.undelivered)
        self.assertEqual(row.status, "failed")
        self.assertEqual(row.error, "legacy: not delivered")
        self.assertFalse(row.retryable)
        self.assertIsNone(row.sent_at)

    def test_created_at_copied(self) -> None:
        event_row = self._event_row(self.delivered)
        self.assertEqual(event_row.created_at, CREATED)
        self.assertEqual(event_row.claimed_at, CREATED)
        log_row = self._log_row(self.log_draft)
        self.assertEqual(log_row.created_at, LOG_CREATED)
        self.assertEqual(log_row.claimed_at, LOG_CREATED)

    def test_event_dm_linked_to_ledger_entry(self) -> None:
        DiscordEventDM = self.new_state.apps.get_model("discordbot", "DiscordEventDM")
        for pk in (self.delivered, self.fake, self.fake_two, self.undelivered):
            dm = DiscordEventDM.objects.get(pk=pk)
            self.assertEqual(dm.ledger_entry_id, self._event_row(pk).pk)

    def test_tournament_dm_log_draft_vs_herodraft_kind(self) -> None:
        draft = self._log_row(self.log_draft)
        self.assertEqual(draft.kind, "tournament_draft_link")
        self.assertEqual(draft.status, "sent")
        self.assertEqual(draft.discord_message_id, "777")
        self.assertEqual(draft.discord_channel_id, "dmchan")
        self.assertEqual(draft.http_status, 200)
        self.assertEqual(draft.tournament_log_id, self.draft_log_id)
        self.assertEqual(draft.organization_id, self.org_id)
        self.assertEqual(draft.discord_user_id, "")
        self.assertEqual(draft.backfilled_from, "discordmessagelog")
        self.assertEqual(draft.context, {})
        hero = self._log_row(self.log_hero_failed)
        self.assertEqual(hero.kind, "tournament_herodraft_link")
        self.assertEqual(hero.status, "failed")
        self.assertFalse(hero.retryable)
        self.assertIsNone(hero.sent_at)

    def test_tournament_log_org_falls_back_to_source_event(self) -> None:
        self.assertEqual(self._log_row(self.log_fallback).organization_id, self.org_id)

    def test_tournament_dm_log_without_tournament_log_flagged_legacy(self) -> None:
        row = self._log_row(self.log_no_tlog)
        self.assertEqual(row.kind, "tournament_draft_link")
        self.assertEqual(row.context, {"legacy_kind_unknown": True})
        self.assertIsNone(row.organization_id)
        self.assertIsNone(row.tournament_log_id)

    def test_embed_data_not_copied(self) -> None:
        for row in self._ledger().objects.all():
            serialized = repr(
                {f.attname: getattr(row, f.attname) for f in row._meta.concrete_fields}
            )
            self.assertNotIn("secret", serialized)
            self.assertNotIn("Draft link", serialized)
            self.assertNotIn("body", serialized)

    def test_source_rows_untouched(self) -> None:
        DiscordEventDM = self.new_state.apps.get_model("discordbot", "DiscordEventDM")
        MessageLog = self.new_state.apps.get_model("discordbot", "DiscordMessageLog")
        self.assertEqual(
            list(DiscordEventDM.objects.order_by("pk").values(*EVENT_DM_FIELDS)),
            self.before_event_dms,
        )
        self.assertEqual(
            list(MessageLog.objects.order_by("pk").values(*MESSAGE_LOG_FIELDS)),
            self.before_logs,
        )

    def test_non_dm_message_logs_ignored(self) -> None:
        self.assertFalse(
            self._ledger()
            .objects.filter(
                idempotency_key=f"legacy:discordmessagelog:{self.log_channel}"
            )
            .exists()
        )
        self.assertEqual(self._ledger().objects.count(), 8)

    def test_rerun_is_idempotent(self) -> None:
        _migration_module().backfill(self.new_state.apps, None)
        self.assertEqual(self._ledger().objects.count(), 8)

    def test_unexpected_dm_type_asserts(self) -> None:
        apps = self.new_state.apps
        DiscordEventDM = apps.get_model("discordbot", "DiscordEventDM")
        source = DiscordEventDM.objects.get(pk=self.delivered)
        DiscordEventDM.objects.create(
            discord_event_id=source.discord_event_id,
            org_user_id=source.org_user_id,
            dm_type=2,
        )
        with self.assertRaises(AssertionError):
            _migration_module().backfill(apps, None)
