from datetime import date, timedelta

from django.contrib import admin
from django.db import IntegrityError, models, transaction
from django.test import RequestFactory, TestCase
from django.utils import timezone

from app.models import CustomUser
from discordbot.admin import DiscordDMAdmin, StuckSendingFilter
from discordbot.models import (
    DiscordDM,
    DiscordEvent,
    DiscordEventDM,
    DiscordTournamentLog,
    DMKind,
    DMStatus,
    DMType,
    LedgerImmutableError,
)
from events.models import Event
from org.models import Organization, OrgUser
from tournament.models import Tournament


def _row(key: str, **extra: object) -> DiscordDM:
    return DiscordDM.objects.create(
        kind=DMKind.SIGNUP_REMINDER,
        idempotency_key=key,
        discord_user_id="1001",
        claimed_at=timezone.now(),
        **extra,
    )


class DiscordDMModelTests(TestCase):
    def test_queryset_delete_raises(self) -> None:
        _row("k1")
        with self.assertRaises(LedgerImmutableError):
            DiscordDM.objects.all().delete()
        self.assertEqual(DiscordDM.objects.count(), 1)

    def test_instance_delete_raises(self) -> None:
        row = _row("k1")
        with self.assertRaises(LedgerImmutableError):
            row.delete()
        self.assertTrue(DiscordDM.objects.filter(pk=row.pk).exists())

    def test_idempotency_key_unique(self) -> None:
        _row("k1")
        with self.assertRaises(IntegrityError), transaction.atomic():
            _row("k1")

    def test_message_id_unique_when_set_only(self) -> None:
        _row("k1", discord_message_id=None)
        _row("k2", discord_message_id=None)
        _row("k3", discord_message_id="123")
        with self.assertRaises(IntegrityError), transaction.atomic():
            _row("k4", discord_message_id="123")

    def test_created_at_preserved_on_bulk_create(self) -> None:
        t0 = timezone.now() - timedelta(days=30)
        DiscordDM.objects.bulk_create(
            [
                DiscordDM(
                    kind=DMKind.SIGNUP_REMINDER,
                    idempotency_key="legacy:1",
                    created_at=t0,
                    claimed_at=t0,
                )
            ]
        )
        row = DiscordDM.objects.get(idempotency_key="legacy:1")
        self.assertEqual(row.created_at, t0)
        self.assertEqual(row.claimed_at, t0)

    def test_deleting_user_org_log_nulls_fks(self) -> None:
        owner = CustomUser.objects.create_user(username="owner", password="pw")
        recipient = CustomUser.objects.create_user(username="rcpt", password="pw")
        org = Organization.objects.create(name="Org", owner=owner)
        tournament = Tournament.objects.create(name="T", date_played=date.today())
        log = DiscordTournamentLog.objects.create(
            tournament=tournament,
            notification_type=DiscordTournamentLog.NotificationType.DRAFT_LINK,
            message="m",
        )
        row = _row("k1", recipient=recipient, organization=org, tournament_log=log)
        self.assertEqual(list(log.dms.all()), [row])

        recipient.delete()
        org.delete()
        log.delete()

        row.refresh_from_db()
        self.assertIsNone(row.recipient_id)
        self.assertIsNone(row.organization_id)
        self.assertIsNone(row.tournament_log_id)

    def test_event_dm_ledger_entry_protect(self) -> None:
        user = CustomUser.objects.create_user(username="u", password="pw")
        org = Organization.objects.create(name="Org", owner=user)
        org_user = OrgUser.objects.create(user=user, organization=org)
        event = Event.objects.create(
            organization=org,
            name="E",
            scheduled_at=timezone.now(),
            created_by=user,
        )
        discord_event = DiscordEvent.objects.create(event=event, guild_id="1")
        row = _row("k1")
        event_dm = DiscordEventDM.objects.create(
            discord_event=discord_event,
            org_user=org_user,
            dm_type=DMType.SIGNUP_REMINDER,
            ledger_entry=row,
        )
        row.refresh_from_db()
        self.assertEqual(row.event_dm, event_dm)
        field = DiscordEventDM._meta.get_field("ledger_entry")
        self.assertIs(field.remote_field.on_delete, models.PROTECT)
        with self.assertRaises(IntegrityError), transaction.atomic():
            DiscordEventDM.objects.create(
                discord_event=discord_event,
                org_user=org_user,
                dm_type=DMType.PROFILE_UPDATE,
                ledger_entry=row,
            )
        event_dm.delete()
        self.assertTrue(DiscordDM.objects.filter(pk=row.pk).exists())


class DiscordDMAdminTests(TestCase):
    def setUp(self) -> None:
        self.request = RequestFactory().get("/")
        self.model_admin = DiscordDMAdmin(DiscordDM, admin.site)

    def test_admin_is_read_only(self) -> None:
        row = _row("k1")
        self.assertFalse(self.model_admin.has_add_permission(self.request))
        self.assertFalse(self.model_admin.has_change_permission(self.request, row))
        self.assertFalse(self.model_admin.has_delete_permission(self.request, row))

    def test_stuck_sending_filter(self) -> None:
        now = timezone.now()
        stuck = _row(
            "stuck",
            status=DMStatus.PENDING,
            send_started_at=now - timedelta(minutes=16),
        )
        _row(
            "fresh", status=DMStatus.PENDING, send_started_at=now - timedelta(minutes=5)
        )
        _row("claimed", status=DMStatus.PENDING)
        _row(
            "sent",
            status=DMStatus.SENT,
            send_started_at=now - timedelta(minutes=30),
        )
        flt = StuckSendingFilter(
            self.request, {"stuck_sending": ["yes"]}, DiscordDM, self.model_admin
        )
        self.assertEqual(
            list(flt.queryset(self.request, DiscordDM.objects.all())), [stuck]
        )
        unfiltered = StuckSendingFilter(self.request, {}, DiscordDM, self.model_admin)
        self.assertEqual(
            unfiltered.queryset(self.request, DiscordDM.objects.all()).count(), 4
        )
