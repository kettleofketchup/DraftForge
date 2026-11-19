import unittest
from datetime import UTC, datetime, timedelta
from typing import Any

from events.line_backfill import backfill_signup_line

# django-test-migrations is a dev dep; a stale CI image may lack it.
try:
    from django_test_migrations.contrib.unittest_case import MigratorTestCase
except ImportError as _import_error:  # pragma: no cover
    raise unittest.SkipTest(
        "django-test-migrations not installed — rebuild backend-dev image "
        "to pick up the new dev dep from pyproject.toml."
    ) from _import_error

REMOVED = {"cancelled", "rejected"}
MAIN = {"rsvp", "pending_approval", "approved", "confirmed"}
BASE = datetime(2026, 10, 1, 18, 0, tzinfo=UTC)


def _created_order(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(rows, key=lambda r: (r["created_at"], r["id"]))


def _today_waitlist(rows: list[dict[str, Any]]) -> list[int]:
    waitlisted = [r for r in _created_order(rows) if r["status"] == "waitlisted"]
    return [
        r["id"] for r in sorted(waitlisted, key=lambda r: r["waitlist_position"] or 999)
    ]


def _ids(rows: list[dict[str, Any]], statuses: set[str]) -> list[int]:
    return [r["id"] for r in rows if r["status"] in statuses]


class BackfillSignupLineMigrationTest(MigratorTestCase):
    migrate_from = [
        ("events", "0025_eventsignup_unmet_requirements"),
        ("user", "0004_backfill_game_profiles"),
    ]
    migrate_to = ("events", "0027_backfill_signup_line")

    def prepare(self) -> None:
        apps = self.old_state.apps
        Organization = apps.get_model("app", "Organization")
        User = apps.get_model("app", "CustomUser")
        BaseUserProfile = apps.get_model("user", "BaseUserProfile")
        Event = apps.get_model("events", "Event")
        EventSignup = apps.get_model("events", "EventSignup")

        org = Organization.objects.create(name="Backfill Org")
        self.org_id = org.pk
        self.event = Event.objects.create(
            organization=org, name="Main", scheduled_at=BASE + timedelta(days=30)
        )
        self.other = Event.objects.create(
            organization=org, name="Other", scheduled_at=BASE + timedelta(days=31)
        )
        users = [
            User.objects.create(username=f"bf{i}", discordId=f"9000{i}")
            for i in range(12)
        ]
        BaseUserProfile.objects.create(user=users[0], nickname="Nick Zero")
        self.nicknamed_user_id = users[0].pk

        # (user index, status, waitlist_position, minutes after BASE)
        spec: list[tuple[int, str, int | None, int]] = [
            (0, "confirmed", None, 0),
            (1, "waitlisted", 3, 1),  # demoted: early created_at, max position
            (2, "rsvp", None, 2),
            (3, "tentative", None, 2),  # tie with the row above
            (4, "cancelled", None, 3),
            (5, "waitlisted", 2, 4),
            (6, "approved", None, 5),
            (7, "waitlisted", None, 6),
            (8, "waitlisted", 1, 6),  # tie with the row above
            (9, "rejected", None, 7),
            (10, "pending_approval", None, 8),
        ]
        for index, status, position, minutes in spec:
            s = EventSignup.objects.create(
                event=self.event,
                user=users[index],
                status=status,
                waitlist_position=position,
            )
            EventSignup.objects.filter(pk=s.pk).update(
                created_at=BASE + timedelta(minutes=minutes)
            )
        for index, status, minutes in [(0, "rsvp", 5), (11, "waitlisted", 1)]:
            s = EventSignup.objects.create(
                event=self.other,
                user=users[index],
                status=status,
                waitlist_position=1 if status == "waitlisted" else None,
            )
            EventSignup.objects.filter(pk=s.pk).update(
                created_at=BASE + timedelta(minutes=minutes)
            )

        self.before = {
            event_id: list(
                EventSignup.objects.filter(event_id=event_id).values(
                    "id", "status", "waitlist_position", "created_at", "user_id"
                )
            )
            for event_id in (self.event.pk, self.other.pk)
        }

    def _after(self, event_id: int) -> list[Any]:
        EventSignup = self.new_state.apps.get_model("events", "EventSignup")
        return list(EventSignup.objects.filter(event_id=event_id))

    def test_seqs_are_a_permutation_per_event(self) -> None:
        for event_id, before in self.before.items():
            seqs = sorted(s.line_seq for s in self._after(event_id))
            self.assertEqual(seqs, list(range(1, len(before) + 1)))

    def test_per_consumer_order(self) -> None:
        for event_id, before in self.before.items():
            today = _created_order(before)
            after = [{"id": s.pk, "status": s.status} for s in self._after(event_id)]
            self.assertEqual(_ids(after, MAIN), _ids(today, MAIN))
            self.assertEqual(_ids(after, {"tentative"}), _ids(today, {"tentative"}))
            self.assertEqual(_ids(after, REMOVED), _ids(today, REMOVED))
            for status in MAIN | REMOVED | {"tentative"}:
                self.assertEqual(_ids(after, {status}), _ids(today, {status}))
            self.assertEqual(_ids(after, {"waitlisted"}), _today_waitlist(before))

            other_after = [r["id"] for r in after]
            waitlist = iter(_today_waitlist(before))
            expected = [
                next(waitlist) if r["status"] == "waitlisted" else r["id"]
                for r in today
            ]
            self.assertEqual(other_after, expected)

    def test_demoted_row_moves_in_waitlist(self) -> None:
        waitlist = _ids(
            [{"id": s.pk, "status": s.status} for s in self._after(self.event.pk)],
            {"waitlisted"},
        )
        demoted = next(
            r["id"] for r in self.before[self.event.pk] if r["waitlist_position"] == 3
        )
        self.assertEqual(waitlist[-2], demoted)

    def test_line_fields(self) -> None:
        for event_id, before in self.before.items():
            created = {r["id"]: r["created_at"] for r in before}
            rows = self._after(event_id)
            stamps = [s.signed_up_at for s in rows]
            self.assertEqual(stamps, sorted(stamps))
            for s in rows:
                self.assertEqual(s.first_signed_up_at, created[s.pk])
                expected = "maybe" if s.status == "tentative" else "main"
                self.assertEqual(s.commitment, expected)
                self.assertEqual(s.first_commitment, s.commitment)
                self.assertEqual(s.rsvp_class, "standard")
                self.assertEqual(s.first_rsvp_class, s.rsvp_class)
                if s.status != "waitlisted":
                    self.assertEqual(s.signed_up_at, created[s.pk])

    def test_one_backfilled_entry_per_row(self) -> None:
        Entry = self.new_state.apps.get_model("events", "SignupLedgerEntry")
        signups = {s.pk: s for event_id in self.before for s in self._after(event_id)}
        entries = list(Entry.objects.filter(action="backfilled"))
        self.assertEqual(sorted(e.signup_id for e in entries), sorted(signups))
        self.assertEqual(len({e.correlation_id for e in entries}), 1)
        self.assertTrue(entries[0].correlation_id.startswith("backfill-"))
        for e in entries:
            s = signups[e.signup_id]
            self.assertEqual(e.actor_role, "system")
            self.assertEqual(e.means, "system")
            self.assertIsNone(e.actor_user_id)
            self.assertFalse(e.on_behalf)
            self.assertIsNone(e.before)
            self.assertEqual(e.after["line_seq"], s.line_seq)
            self.assertEqual(e.after["status"], s.status)
            self.assertEqual(e.event_id, s.event_id)
            self.assertEqual(e.organization_id, self.org_id)
            self.assertEqual(e.subject_user_id, s.user_id)
            self.assertEqual(e.subject_snapshot["user_id"], s.user_id)
            self.assertEqual(e.event_snapshot["id"], s.event_id)
            self.assertIn("discord_id", e.subject_snapshot)
        nicknamed = next(
            e for e in entries if e.subject_user_id == self.nicknamed_user_id
        )
        self.assertEqual(nicknamed.subject_snapshot["nickname"], "Nick Zero")
        self.assertEqual(nicknamed.subject_snapshot["discord_id"], "90000")
        self.assertEqual(nicknamed.subject_snapshot["username"], "bf0")


class BackfillSignupLineReverseTest(MigratorTestCase):
    migrate_from = ("events", "0027_backfill_signup_line")
    migrate_to = ("events", "0026_signup_ledger")

    def prepare(self) -> None:
        apps = self.old_state.apps
        Organization = apps.get_model("app", "Organization")
        User = apps.get_model("app", "CustomUser")
        Event = apps.get_model("events", "Event")
        EventSignup = apps.get_model("events", "EventSignup")
        Entry = apps.get_model("events", "SignupLedgerEntry")

        org = Organization.objects.create(name="Reverse Org")
        event = Event.objects.create(
            organization=org, name="Reverse", scheduled_at=BASE
        )
        for i, status in enumerate(["rsvp", "tentative", "waitlisted"]):
            EventSignup.objects.create(
                event=event,
                user=User.objects.create(username=f"rv{i}"),
                status=status,
                waitlist_position=1 if status == "waitlisted" else None,
            )
        self.assertEqual(EventSignup.objects.filter(line_seq=None).count(), 3)
        backfill_signup_line(apps)
        self.assertFalse(EventSignup.objects.filter(line_seq=None).exists())
        self.assertEqual(
            sorted(Entry.objects.values_list("signup_id", flat=True)),
            sorted(EventSignup.objects.values_list("pk", flat=True)),
        )
        self.signup_ids = sorted(EventSignup.objects.values_list("pk", flat=True))

    def test_reverse_then_reapply(self) -> None:
        apps = self.new_state.apps
        EventSignup = apps.get_model("events", "EventSignup")
        Entry = apps.get_model("events", "SignupLedgerEntry")
        self.assertFalse(Entry.objects.filter(action="backfilled").exists())
        self.assertEqual(EventSignup.objects.filter(line_seq=None).count(), 3)

        state = self._migrator.apply_tested_migration(
            ("events", "0027_backfill_signup_line")
        )
        Entry = state.apps.get_model("events", "SignupLedgerEntry")
        EventSignup = state.apps.get_model("events", "EventSignup")
        self.assertEqual(
            sorted(Entry.objects.values_list("signup_id", flat=True)),
            self.signup_ids,
        )
        self.assertEqual(
            sorted(EventSignup.objects.values_list("line_seq", flat=True)),
            [1, 2, 3],
        )
