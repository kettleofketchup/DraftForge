import uuid
from datetime import timedelta
from typing import Any

from django.conf import settings
from django.contrib import admin
from django.test import RequestFactory
from django.urls import reverse
from django.utils import timezone as tz
from structlog.testing import capture_logs

from app.models import CustomUser
from events.admin import SignupLedgerEntryAdmin
from events.constants import (
    ActorRole,
    EventState,
    SignupAction,
    SignupMeans,
    SignupStatus,
)
from events.exceptions import LedgerAppendOnlyError
from events.models import Event, EventSignup, SignupLedgerEntry
from events.services import SignupRecordsConflict, teardown_event
from events.tests.base import EventTestCase
from user.discord_accounts import merge_discord_accounts


class SignupLedgerModelTestCase(EventTestCase):
    def setUp(self) -> None:
        self.signup = EventSignup.objects.create(event=self.event, user=self.user)

    def _entry(self, **kw: Any) -> SignupLedgerEntry:
        fields: dict[str, Any] = {
            "event": self.event,
            "organization": self.org,
            "signup": self.signup,
            "event_snapshot": {"id": self.event.pk},
            "subject_user": self.user,
            "subject_snapshot": {
                "user_id": self.user.pk,
                "username": self.user.username,
                "nickname": None,
                "discord_id": self.user.discordId,
            },
            "actor_role": ActorRole.SYSTEM,
            "means": SignupMeans.SYSTEM,
            "action": SignupAction.SIGNED_UP,
            "correlation_id": uuid.uuid4().hex,
        }
        fields.update(kw)
        return SignupLedgerEntry.objects.create(**fields)

    def _blocked(self, logs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [e for e in logs if e["event"] == "signup_ledger_mutation_blocked"]

    def _assert_blocked_log(
        self, logs: list[dict[str, Any]], operation: str, entry_id: int | None
    ) -> dict[str, Any]:
        blocked = self._blocked(logs)
        self.assertEqual(len(blocked), 1, logs)
        record = blocked[0]
        self.assertEqual(record["system"], "events")
        self.assertEqual(record["subsystem"], "ledger")
        self.assertEqual(record["log_level"], "warning")
        self.assertEqual(record["operation"], operation)
        self.assertEqual(record["entry_id"], entry_id)
        self.assertIn("fields", record)
        return record


class AppendOnlyTest(SignupLedgerModelTestCase):
    def test_full_save_on_existing_raises(self) -> None:
        entry = self._entry()
        entry.reason = "edited"
        with capture_logs() as logs, self.assertRaises(LedgerAppendOnlyError):
            entry.save()
        self._assert_blocked_log(logs, "save", entry.pk)
        entry.refresh_from_db()
        self.assertEqual(entry.reason, "")

    def test_repoint_update_fields_allowed(self) -> None:
        entry = self._entry()
        other = CustomUser.objects.create(username="ledger_other")
        for update_fields in (["subject_user"], ["actor_user"], ["subject_user_id"]):
            with self.subTest(update_fields=update_fields):
                entry.subject_user = other
                entry.actor_user = other
                with capture_logs() as logs:
                    entry.save(update_fields=update_fields)
                self.assertEqual(self._blocked(logs), [])
        entry.refresh_from_db()
        self.assertEqual(entry.subject_user_id, other.pk)
        self.assertEqual(entry.actor_user_id, other.pk)

    def test_other_update_fields_raise(self) -> None:
        entry = self._entry()
        entry.reason = "edited"
        for update_fields in (["reason"], ["subject_user", "reason"], []):
            with self.subTest(update_fields=update_fields):
                with capture_logs() as logs, self.assertRaises(LedgerAppendOnlyError):
                    entry.save(update_fields=update_fields)
                record = self._assert_blocked_log(logs, "save", entry.pk)
                self.assertEqual(record["fields"], update_fields)
        entry.refresh_from_db()
        self.assertEqual(entry.reason, "")

    def test_instance_delete_raises(self) -> None:
        entry = self._entry()
        with capture_logs() as logs, self.assertRaises(LedgerAppendOnlyError):
            entry.delete()
        self._assert_blocked_log(logs, "delete", entry.pk)
        self.assertTrue(SignupLedgerEntry.objects.filter(pk=entry.pk).exists())

    def test_queryset_delete_raises(self) -> None:
        entry = self._entry()
        with capture_logs() as logs, self.assertRaises(LedgerAppendOnlyError):
            SignupLedgerEntry.objects.filter(pk=entry.pk).delete()
        self._assert_blocked_log(logs, "queryset_delete", None)
        self.assertTrue(SignupLedgerEntry.objects.filter(pk=entry.pk).exists())

    def test_queryset_update_other_field_raises(self) -> None:
        self._entry()
        with capture_logs() as logs, self.assertRaises(LedgerAppendOnlyError):
            SignupLedgerEntry.objects.update(reason="x")
        record = self._assert_blocked_log(logs, "queryset_update", None)
        self.assertEqual(record["fields"], ["reason"])
        self.assertFalse(SignupLedgerEntry.objects.filter(reason="x").exists())

    def test_queryset_update_repoint_returns_count(self) -> None:
        self._entry()
        self._entry()
        other = CustomUser.objects.create(username="ledger_other")
        self.assertEqual(SignupLedgerEntry.objects.update(subject_user=other), 2)
        self.assertEqual(
            SignupLedgerEntry.objects.filter(subject_user=other).count(), 2
        )

    def test_purge_deletes_and_logs(self) -> None:
        keep = self._entry()
        a = self._entry()
        b = self._entry()
        with capture_logs() as logs:
            outcome = SignupLedgerEntry.objects.filter(pk__in=[a.pk, b.pk]).purge()
        self.assertEqual(outcome.count, 2)
        self.assertEqual(
            list(SignupLedgerEntry.objects.values_list("pk", flat=True)), [keep.pk]
        )
        purged = [e for e in logs if e["event"] == "signup_records_purged"]
        self.assertEqual(len(purged), 1, logs)
        self.assertEqual(purged[0]["system"], "events")
        self.assertEqual(purged[0]["subsystem"], "ledger")
        self.assertEqual(purged[0]["log_level"], "info")
        self.assertEqual(purged[0]["count"], 2)

    def test_not_in_cacheops(self) -> None:
        self.assertNotIn("events.signupledgerentry", settings.CACHEOPS)
        self.assertNotIn("events.*", settings.CACHEOPS)
        self.assertNotIn("*.*", settings.CACHEOPS)


class LedgerAdminTest(SignupLedgerModelTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.superuser = CustomUser.objects.create_superuser(
            username="ledger_su", password="pw", email="su@example.com"
        )

    def test_permissions_denied(self) -> None:
        request = RequestFactory().get("/")
        request.user = self.superuser
        model_admin = SignupLedgerEntryAdmin(SignupLedgerEntry, admin.site)
        entry = self._entry()
        self.assertFalse(model_admin.has_add_permission(request))
        self.assertFalse(model_admin.has_change_permission(request))
        self.assertFalse(model_admin.has_change_permission(request, entry))
        self.assertFalse(model_admin.has_delete_permission(request))
        self.assertFalse(model_admin.has_delete_permission(request, entry))
        self.assertEqual(
            model_admin.list_select_related, ("subject_user", "actor_user")
        )

    def test_eventsignup_admin_add_and_change(self) -> None:
        self.client.force_login(self.superuser)
        add = self.client.get(reverse("admin:events_eventsignup_add"))
        self.assertEqual(add.status_code, 403)
        change_url = reverse("admin:events_eventsignup_change", args=[self.signup.pk])
        change = self.client.get(change_url)
        self.assertEqual(change.status_code, 200)
        form_fields = set(change.context["adminform"].form.fields)
        for name in (
            "signed_up_at",
            "line_seq",
            "commitment",
            "rsvp_class",
            "first_signed_up_at",
            "first_commitment",
            "first_rsvp_class",
        ):
            self.assertNotIn(name, form_fields)

        before = EventSignup.objects.values(
            "status",
            "first_signed_up_at",
            "first_commitment",
            "first_rsvp_class",
            "line_seq",
        ).get(pk=self.signup.pk)
        data = {
            "event": self.event.pk,
            "user": self.user.pk,
            "event_team": "",
            "signup_type": self.signup.signup_type,
            "status": SignupStatus.APPROVED,
            "waitlist_position": "",
        }
        for name in form_fields - set(data):
            value = change.context["adminform"].form.initial.get(name)
            data[name] = "" if value is None else value
        response = self.client.post(change_url, data)
        self.assertEqual(response.status_code, 302, getattr(response, "context", None))
        after = EventSignup.objects.values(
            "status",
            "first_signed_up_at",
            "first_commitment",
            "first_rsvp_class",
            "line_seq",
        ).get(pk=self.signup.pk)
        self.assertNotEqual(before["status"], SignupStatus.APPROVED)
        self.assertEqual(after, before)


class LedgerSurvivalTest(SignupLedgerModelTestCase):
    def test_event_teardown_leaves_entry(self) -> None:
        event = Event.objects.create(
            organization=self.org,
            name="Doomed Event",
            scheduled_at=tz.now() + timedelta(days=2),
            state=EventState.SIGNUPS_OPEN,
            created_by=self.admin,
        )
        signup = EventSignup.objects.create(event=event, user=self.user)
        entry = self._entry(
            event=event,
            signup=signup,
            event_snapshot={"id": event.pk, "name": event.name},
        )
        event_id = event.pk

        with self.assertRaises(SignupRecordsConflict):
            teardown_event(event, actor=self.admin)
        teardown_event(event, actor=self.admin, confirm_signup_records=True)

        self.assertFalse(Event.objects.filter(pk=event_id).exists())
        self.assertFalse(EventSignup.objects.filter(pk=signup.pk).exists())
        self.assertIn(entry.pk, SignupLedgerEntry.objects.values_list("pk", flat=True))
        fetched = SignupLedgerEntry.objects.select_related("subject_user").get(
            pk=entry.pk
        )
        self.assertEqual(fetched.event_id, event_id)
        self.assertEqual(fetched.subject_user, self.user)
        self.assertEqual(
            fetched.event_snapshot, {"id": event_id, "name": "Doomed Event"}
        )

        superuser = CustomUser.objects.create_superuser(
            username="ledger_su", password="pw", email="su@example.com"
        )
        self.client.force_login(superuser)
        response = self.client.get(reverse("admin:events_signupledgerentry_changelist"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, entry.correlation_id)

    def test_signup_delete_leaves_entry(self) -> None:
        entry = self._entry()
        signup_id = self.signup.pk
        self.signup.delete()
        fetched = SignupLedgerEntry.objects.select_related("subject_user").get(
            pk=entry.pk
        )
        self.assertEqual(fetched.signup_id, signup_id)
        self.assertEqual(fetched.subject_user, self.user)
        self.assertIn(entry.pk, SignupLedgerEntry.objects.values_list("pk", flat=True))

    def test_user_delete_nulls_subject_keeps_snapshot(self) -> None:
        doomed = CustomUser.objects.create(username="ledger_doomed")
        snapshot = {
            "user_id": doomed.pk,
            "username": "ledger_doomed",
            "nickname": None,
            "discord_id": None,
        }
        entry = self._entry(signup=None, subject_user=doomed, subject_snapshot=snapshot)
        doomed.delete()
        entry.refresh_from_db()
        self.assertIsNone(entry.subject_user_id)
        self.assertEqual(entry.subject_snapshot, snapshot)

    def test_merge_discord_accounts_repoints_entries(self) -> None:
        keep = CustomUser.objects.create(username="ledger_keep")
        drop = CustomUser.objects.create(username="ledger_drop")
        as_subject = self._entry(signup=None, subject_user=drop)
        as_actor = self._entry(
            signup=None,
            actor_user=drop,
            actor_role=ActorRole.STAFF,
            actor_snapshot={"user_id": drop.pk},
            on_behalf=True,
        )
        count = SignupLedgerEntry.objects.count()

        merge_discord_accounts(keep=keep, drop=drop)

        as_subject.refresh_from_db()
        as_actor.refresh_from_db()
        self.assertEqual(as_subject.subject_user_id, keep.pk)
        self.assertEqual(as_actor.actor_user_id, keep.pk)
        self.assertEqual(SignupLedgerEntry.objects.count(), count)
