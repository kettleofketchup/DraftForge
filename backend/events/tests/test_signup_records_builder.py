import uuid
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import patch

from django.test import override_settings
from structlog.testing import capture_logs

from app.models import CustomUser
from events.constants import (
    ActorRole,
    EventState,
    SignupAction,
    SignupMeans,
    SignupStatus,
)
from events.ledger import RecordsWindow, event_snapshot, user_snapshot
from events.models import Event, SignupLedgerEntry
from events.records import (
    RECORD_COLUMNS,
    RecordsFilter,
    SignupRecord,
    TooManyRecords,
    build_signup_records,
    flatten_record,
    guard_csv_cell,
    record_to_json,
)
from events.tests.base import EventTestCase
from org.models import Organization

T0 = datetime(2026, 3, 1, 18, 0, tzinfo=UTC)
ALL = RecordsFilter(window=RecordsWindow())


def _after(
    status: str = SignupStatus.CONFIRMED,
    commitment: str = "main",
    *,
    signed_up_at: datetime | None = T0,
    line_seq: int | None = 1,
) -> dict[str, Any]:
    return {
        "status": status,
        "commitment": commitment,
        "rsvp_class": "standard",
        "signed_up_at": signed_up_at.isoformat() if signed_up_at else None,
        "line_seq": line_seq,
        "waitlist_position": None,
        "event_team_id": None,
        "extra": {},
    }


class SignupRecordsBuilderTest(EventTestCase):
    def _row(
        self,
        event: Event,
        user: CustomUser | None,
        at: datetime,
        *,
        after: dict[str, Any] | None,
        before: dict[str, Any] | None = None,
        action: str = SignupAction.SIGNED_UP,
        means: str = SignupMeans.DISCORD_BUTTON,
        subject_snapshot: dict[str, Any] | None = None,
        snapshot: dict[str, Any] | None = None,
        organization: Organization | None = None,
    ) -> SignupLedgerEntry:
        return SignupLedgerEntry.objects.create(
            event_id=event.pk,
            organization=organization or self.org,
            event_snapshot=snapshot if snapshot is not None else event_snapshot(event),
            subject_user=user,
            subject_snapshot=(
                subject_snapshot
                if subject_snapshot is not None
                else user_snapshot(user) or {}
            ),
            actor_user=self.admin,
            actor_snapshot=user_snapshot(self.admin),
            actor_role=ActorRole.STAFF,
            means=means,
            action=action,
            before=before,
            after=after,
            correlation_id=uuid.uuid4().hex,
            occurred_at=at,
        )

    def _one(self, **kwargs: Any) -> SignupRecord:
        records = build_signup_records(self.org.pk, ALL, **kwargs)
        self.assertEqual(len(records), 1)
        return records[0]

    def test_one_row_per_event_and_subject(self) -> None:
        event = self.make_event(scheduled_at=T0)
        self._row(event, self.user, T0 - timedelta(days=3), after=_after())
        self._row(
            event, self.user, T0 - timedelta(days=2), after=_after(commitment="sub")
        )
        self._row(
            event,
            self.user,
            T0 - timedelta(days=1),
            after=_after(SignupStatus.CANCELLED),
        )
        self._row(event, self.admin, T0 - timedelta(days=2), after=_after())

        records = build_signup_records(self.org.pk, ALL)

        self.assertEqual(
            sorted((r.event_id, r.user_id) for r in records),
            sorted([(event.pk, self.user.pk), (event.pk, self.admin.pk)]),
        )

    def test_original_and_final(self) -> None:
        event = self.make_event(scheduled_at=T0)
        signed = T0 - timedelta(days=5)
        cancel_at = T0 - timedelta(days=1)
        self._row(
            event,
            self.user,
            signed,
            after=_after(signed_up_at=signed),
            means=SignupMeans.WEB,
        )
        self._row(
            event,
            self.user,
            T0 - timedelta(days=3),
            after=_after(commitment="sub", signed_up_at=signed, line_seq=2),
            action=SignupAction.SWITCHED_COMMITMENT,
        )
        self._row(
            event,
            self.user,
            cancel_at,
            after=_after(
                SignupStatus.CANCELLED, "sub", signed_up_at=signed, line_seq=3
            ),
            action=SignupAction.WITHDREW,
        )

        record = self._one()

        self.assertEqual(
            record.original,
            {
                "signed_up_at": signed,
                "commitment": "main",
                "rsvp_class": "standard",
                "means": SignupMeans.WEB,
            },
        )
        self.assertEqual(
            record.final,
            {
                "status": SignupStatus.CANCELLED,
                "commitment": "sub",
                "rsvp_class": "standard",
                "signed_up_at": signed,
                "line_seq": 3,
            },
        )
        self.assertEqual(record.change_count, 2)
        self.assertEqual(record.last_changed_at, cancel_at)
        self.assertEqual(record.withdrawn_at, cancel_at)

    def test_original_signed_up_at_falls_back_to_occurred_at(self) -> None:
        event = self.make_event(scheduled_at=T0)
        at = T0 - timedelta(days=2)
        self._row(event, self.user, at, after=_after(signed_up_at=None))

        record = self._one()

        assert record.original is not None
        self.assertEqual(record.original["signed_up_at"], at)
        self.assertEqual(record.change_count, 0)

    def test_withdrawn_at_trailing_run(self) -> None:
        event = self.make_event(scheduled_at=T0)
        t1 = T0 - timedelta(days=2)
        t2 = T0 - timedelta(days=1)
        self._row(event, self.user, T0 - timedelta(days=3), after=_after())
        self._row(event, self.user, t1, after=_after(SignupStatus.CANCELLED))
        self._row(event, self.user, t2, after=_after(SignupStatus.DROPPED))

        self.assertEqual(self._one().withdrawn_at, t1)

    def test_withdrawn_at_cleared_by_resignup(self) -> None:
        event = self.make_event(scheduled_at=T0)
        self._row(event, self.user, T0 - timedelta(days=3), after=_after())
        self._row(
            event,
            self.user,
            T0 - timedelta(days=2),
            after=_after(SignupStatus.CANCELLED),
        )
        self._row(
            event,
            self.user,
            T0 - timedelta(days=1),
            after=_after(),
            action=SignupAction.RESIGNED_UP,
        )

        record = self._one()

        self.assertIsNone(record.withdrawn_at)
        assert record.final is not None
        self.assertEqual(record.final["status"], SignupStatus.CONFIRMED)

    def test_deleted_event_row(self) -> None:
        event = self.make_event(scheduled_at=T0, name="Gone Inhouse")
        self._row(event, self.user, T0 - timedelta(days=1), after=_after())
        pk = event.pk
        Event.objects.filter(pk=pk).delete()

        record = self._one()

        self.assertEqual(record.event_id, pk)
        self.assertEqual(record.event_state, "deleted")
        self.assertEqual(record.event_name, "Gone Inhouse")
        self.assertEqual(record.scheduled_at, T0)

    def test_cancelled_event_row(self) -> None:
        event = self.make_event(scheduled_at=T0, state=EventState.CANCELLED)
        self._row(event, self.user, T0 - timedelta(days=1), after=_after())

        self.assertEqual(self._one().event_state, EventState.CANCELLED)

    def test_deleted_user_uses_snapshot(self) -> None:
        event = self.make_event(scheduled_at=T0)
        gone = CustomUser.objects.create_user(username="gone_user", password="x")
        gone.discordId = "555000111"
        gone.save()
        gone_pk = gone.pk
        self._row(event, gone, T0 - timedelta(days=2), after=_after())
        self._row(
            event, gone, T0 - timedelta(days=1), after=_after(SignupStatus.CANCELLED)
        )
        gone.delete()

        record = self._one()

        self.assertEqual(record.user_id, gone_pk)
        self.assertEqual(record.discord_id, "555000111")
        self.assertEqual(record.change_count, 1)

    def test_live_user_discord_id(self) -> None:
        event = self.make_event(scheduled_at=T0)
        self._row(event, self.user, T0 - timedelta(days=1), after=_after())

        record = self._one()

        self.assertEqual(record.user_id, self.user.pk)
        self.assertEqual(record.discord_id, self.user.discordId)

    def test_ready_check_rows_excluded(self) -> None:
        event = self.make_event(scheduled_at=T0)
        self._row(
            event,
            None,
            T0 - timedelta(days=1),
            after={"extra": {"step": "asked"}},
            action=SignupAction.READY_CHECK_ASKED,
            subject_snapshot={},
        )

        self.assertEqual(build_signup_records(self.org.pk, ALL), [])

    def test_group_without_valid_after(self) -> None:
        event = self.make_event(scheduled_at=T0)
        other = self.make_event(scheduled_at=T0 + timedelta(days=1))
        self._row(
            event,
            self.user,
            T0 - timedelta(days=1),
            after=None,
            action=SignupAction.EVENT_CANCELLED,
        )
        self._row(other, self.user, T0, after={"status": "confirmed"})
        self._row(other, self.user, T0 + timedelta(hours=1), after={"bogus": 1})

        with capture_logs() as logs:
            records = build_signup_records(self.org.pk, ALL)

        self.assertEqual(len(records), 2)
        for record in records:
            self.assertIsNone(record.original)
            self.assertIsNone(record.final)
            self.assertIsNone(record.withdrawn_at)
        invalid = [e for e in logs if e["event"] == "signup_records_snapshot_invalid"]
        self.assertEqual(len(invalid), 1)
        self.assertEqual(invalid[0]["count"], 2)
        self.assertEqual(invalid[0]["system"], "events")
        self.assertEqual(invalid[0]["subsystem"], "ledger")

    def test_group_without_valid_after_counts_every_entry(self) -> None:
        event = self.make_event(scheduled_at=T0)
        self._row(event, self.user, T0 - timedelta(days=2), after=None)
        self._row(event, self.user, T0 - timedelta(days=1), after={"bogus": 1})
        self._row(event, self.user, T0, after=None)

        record = self._one()

        self.assertIsNone(record.original)
        self.assertEqual(record.change_count, 3)

    def test_moved_off_event_final_is_moved(self) -> None:
        stale = self.make_event(scheduled_at=T0)
        target = self.make_event(scheduled_at=T0 + timedelta(days=7))
        signed = T0 - timedelta(days=3)
        moved_at = T0 - timedelta(days=1)
        self._row(
            stale,
            self.user,
            signed,
            after=_after(SignupStatus.APPROVED, signed_up_at=signed, line_seq=4),
        )
        before = {
            **_after(SignupStatus.APPROVED, signed_up_at=signed, line_seq=4),
            "extra": {"event_id": stale.pk},
        }
        after = {
            **_after(SignupStatus.APPROVED, signed_up_at=moved_at, line_seq=1),
            "extra": {"event_id": target.pk},
        }
        self._row(
            stale,
            self.user,
            moved_at,
            before=before,
            after=after,
            action=SignupAction.MOVED_EVENT,
            means=SignupMeans.SYSTEM,
        )
        self._row(
            target,
            self.user,
            moved_at,
            before=before,
            after=after,
            action=SignupAction.MOVED_EVENT,
            means=SignupMeans.SYSTEM,
        )

        by_event = {r.event_id: r for r in build_signup_records(self.org.pk, ALL)}

        old = by_event[stale.pk]
        self.assertEqual(
            old.final,
            {
                "status": "moved",
                "commitment": "main",
                "rsvp_class": "standard",
                "signed_up_at": signed,
                "line_seq": 4,
            },
        )
        self.assertIsNone(old.withdrawn_at)
        self.assertEqual(old.change_count, 1)
        self.assertEqual(old.last_changed_at, moved_at)
        new = by_event[target.pk]
        assert new.final is not None and new.original is not None
        self.assertEqual(new.final["status"], SignupStatus.APPROVED)
        self.assertEqual(new.final["line_seq"], 1)
        self.assertEqual(new.original["means"], SignupMeans.SYSTEM)

    def test_moved_back_onto_event_is_signed_up_again(self) -> None:
        stale = self.make_event(scheduled_at=T0)
        target = self.make_event(scheduled_at=T0 + timedelta(days=7))
        self._row(stale, self.user, T0 - timedelta(days=3), after=_after())
        self._row(
            stale,
            self.user,
            T0 - timedelta(days=2),
            before={**_after(), "extra": {"event_id": stale.pk}},
            after={**_after(), "extra": {"event_id": target.pk}},
            action=SignupAction.MOVED_EVENT,
        )
        self._row(
            stale,
            self.user,
            T0 - timedelta(days=1),
            after=_after(line_seq=7),
            action=SignupAction.RESIGNED_UP,
        )

        final = self._one().final
        assert final is not None
        self.assertEqual(final["status"], SignupStatus.CONFIRMED)
        self.assertEqual(final["line_seq"], 7)

    def test_filters_by_live_and_snapshot_user(self) -> None:
        event = self.make_event(scheduled_at=T0)
        gone = CustomUser.objects.create_user(username="gone_filter", password="x")
        gone_pk = gone.pk
        self._row(event, self.user, T0 - timedelta(days=1), after=_after())
        self._row(event, self.admin, T0 - timedelta(days=1), after=_after())
        self._row(event, gone, T0 - timedelta(days=1), after=_after())
        gone.delete()

        live = build_signup_records(
            self.org.pk, RecordsFilter(window=RecordsWindow(), user_id=self.user.pk)
        )
        snap = build_signup_records(
            self.org.pk, RecordsFilter(window=RecordsWindow(), user_id=gone_pk)
        )

        self.assertEqual([r.user_id for r in live], [self.user.pk])
        self.assertEqual([r.user_id for r in snap], [gone_pk])

    def test_filters_by_window(self) -> None:
        inside = self.make_event(scheduled_at=T0)
        before = self.make_event(scheduled_at=T0 - timedelta(days=10))
        after = self.make_event(scheduled_at=T0 + timedelta(days=10))
        for event in (inside, before, after):
            self._row(event, self.user, T0 - timedelta(days=20), after=_after())

        records = build_signup_records(
            self.org.pk,
            RecordsFilter(
                window=RecordsWindow(
                    since=T0 - timedelta(days=1), until=T0 + timedelta(days=1)
                )
            ),
        )

        self.assertEqual([r.event_id for r in records], [inside.pk])

    def test_ordering(self) -> None:
        late = self.make_event(scheduled_at=T0 + timedelta(days=1))
        early = self.make_event(scheduled_at=T0)
        unknown = self.make_event(scheduled_at=T0)
        unscheduled = {**event_snapshot(unknown), "scheduled_at": None}
        for event in (late, early, unknown):
            snap = unscheduled if event is unknown else None
            for user in (self.user, self.admin):
                self._row(
                    event, user, T0 - timedelta(days=1), after=_after(), snapshot=snap
                )
        Event.objects.filter(pk=unknown.pk).delete()

        records = build_signup_records(self.org.pk, ALL)
        users = sorted([self.user.pk, self.admin.pk])

        self.assertEqual(
            [(r.event_id, r.user_id) for r in records],
            [(early.pk, u) for u in users]
            + [(late.pk, u) for u in users]
            + [(unknown.pk, u) for u in users],
        )

    def test_empty_org_returns_empty_list(self) -> None:
        self.assertEqual(build_signup_records(self.org.pk, ALL), [])

    def test_max_rows(self) -> None:
        event = self.make_event(scheduled_at=T0)
        self._row(event, self.user, T0, after=_after())
        self._row(event, self.admin, T0, after=_after())

        with self.assertRaises(TooManyRecords):
            build_signup_records(self.org.pk, ALL, max_rows=1)
        self.assertEqual(len(build_signup_records(self.org.pk, ALL, max_rows=2)), 2)

    @override_settings(SIGNUP_RECORDS_MAX_ROWS=1)
    def test_max_rows_defaults_to_setting(self) -> None:
        event = self.make_event(scheduled_at=T0)
        self._row(event, self.user, T0, after=_after())
        self._row(event, self.admin, T0, after=_after())

        with self.assertRaises(TooManyRecords):
            build_signup_records(self.org.pk, ALL)

    def test_event_ids_are_chunked(self) -> None:
        events = [
            self.make_event(scheduled_at=T0 + timedelta(hours=i)) for i in range(5)
        ]
        for event in events:
            self._row(event, self.user, T0, after=_after())

        with patch("events.ledger.RESOLVE_CHUNK_SIZE", 2):
            records = build_signup_records(self.org.pk, ALL)

        self.assertEqual([r.event_id for r in records], [e.pk for e in events])

    def test_other_org_rows_excluded(self) -> None:
        event = self.make_event(scheduled_at=T0)
        other = Organization.objects.create(name="Other Org", owner=self.admin)
        self._row(event, self.user, T0, after=_after(), organization=other)

        self.assertEqual(build_signup_records(self.org.pk, ALL), [])

    def test_record_to_json(self) -> None:
        event = self.make_event(scheduled_at=T0, name="Inhouse Friday")
        self._row(event, self.user, T0 - timedelta(days=1), after=_after())

        data = record_to_json(self._one())

        self.assertEqual(
            data,
            {
                "event_id": event.pk,
                "event_name": "Inhouse Friday",
                "scheduled_at": "2026-03-01T18:00:00Z",
                "event_state": EventState.SIGNUPS_OPEN,
                "series_id": None,
                "user_id": self.user.pk,
                "discord_id": self.user.discordId,
                "original": {
                    "signed_up_at": "2026-03-01T18:00:00Z",
                    "commitment": "main",
                    "rsvp_class": "standard",
                    "means": SignupMeans.DISCORD_BUTTON,
                },
                "final": {
                    "status": SignupStatus.CONFIRMED,
                    "commitment": "main",
                    "rsvp_class": "standard",
                    "signed_up_at": "2026-03-01T18:00:00Z",
                    "line_seq": 1,
                },
                "withdrawn_at": None,
                "change_count": 0,
                "last_changed_at": "2026-02-28T18:00:00Z",
            },
        )
        self.assertNotIn("actor", str(data))

    def test_guard_csv_cell(self) -> None:
        for raw in ("=HYPERLINK(1)", "+1", "-Weekly Inhouse-", "@x", "\tx", "\rx"):
            self.assertEqual(guard_csv_cell(raw), "'" + raw)
        for clean in ("Inhouse", 5, None, ""):
            self.assertEqual(guard_csv_cell(clean), clean)

    def test_flatten_matches_columns(self) -> None:
        event = self.make_event(scheduled_at=T0, name="-Weekly Inhouse-")
        self._row(event, self.user, T0 - timedelta(days=2), after=_after())
        self._row(
            event, self.user, T0 - timedelta(days=1), after=_after(SignupStatus.DROPPED)
        )
        record = self._one()

        row = flatten_record(record)

        self.assertEqual(len(RECORD_COLUMNS), 19)
        self.assertEqual(len(row), len(RECORD_COLUMNS))
        self.assertEqual(
            RECORD_COLUMNS,
            (
                "event_id",
                "event_name",
                "scheduled_at",
                "event_state",
                "series_id",
                "user_id",
                "discord_id",
                "original_signed_up_at",
                "original_commitment",
                "original_rsvp_class",
                "original_means",
                "final_status",
                "final_commitment",
                "final_rsvp_class",
                "final_signed_up_at",
                "final_line_seq",
                "withdrawn_at",
                "change_count",
                "last_changed_at",
            ),
        )
        flat = dict(zip(RECORD_COLUMNS, row, strict=True))
        self.assertEqual(flat["event_name"], "-Weekly Inhouse-")
        self.assertEqual(flat["final_status"], SignupStatus.DROPPED)
        self.assertEqual(flat["withdrawn_at"], "2026-02-28T18:00:00Z")
        self.assertEqual(flat["original_signed_up_at"], "2026-03-01T18:00:00Z")
        self.assertEqual(flat["change_count"], 1)
        self.assertFalse(any("actor" in c for c in RECORD_COLUMNS))
        self.assertNotIn("actor", record_to_json(record))

    def test_flatten_empty_group(self) -> None:
        event = self.make_event(scheduled_at=T0)
        self._row(event, self.user, T0, after=None, action=SignupAction.EVENT_CANCELLED)

        flat = dict(zip(RECORD_COLUMNS, flatten_record(self._one()), strict=True))

        for key in RECORD_COLUMNS[7:17]:
            self.assertIsNone(flat[key])
