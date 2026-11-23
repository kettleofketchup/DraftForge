from base64 import urlsafe_b64encode
from datetime import UTC, datetime, timedelta, timezone

from app.models import CustomUser
from events.constants import SignupAction
from events.history import (
    HISTORY_EXTRA_KEYS,
    HISTORY_MAX_PAGE_SIZE,
    HISTORY_PAGE_SIZE,
    MAX_DB_INT,
    HistoryCursor,
    decode_history_cursor,
    history_after_q,
    signup_history_queryset,
)
from events.ledger import SignupActor, record_signup_change
from events.models import Event, EventSignup, SignupLedgerEntry
from events.tests.base import EventTestCase


def _b64(raw: str) -> str:
    return urlsafe_b64encode(raw.encode()).decode().rstrip("=")


class HistoryCursorTest(EventTestCase):
    def _entry(
        self,
        occurred_at: datetime,
        *,
        event: Event | None = None,
        subject: CustomUser | None = None,
        action: SignupAction = SignupAction.SIGNED_UP,
        signup: EventSignup | None = None,
    ) -> SignupLedgerEntry:
        return record_signup_change(
            event=event or self.event,
            subject=subject or self.user,
            actor=SignupActor.system(),
            action=action,
            signup=signup,
            occurred_at=occurred_at,
        )

    def test_constants(self) -> None:
        self.assertEqual(HISTORY_PAGE_SIZE, 50)
        self.assertEqual(HISTORY_MAX_PAGE_SIZE, 100)
        self.assertEqual(MAX_DB_INT, 2**63 - 1)
        self.assertEqual(
            HISTORY_EXTRA_KEYS,
            frozenset(
                {
                    "staff_power",
                    "mmr_override",
                    "game_type",
                    "from_user_id",
                    "discarded_duplicate",
                    "discarded_signup_id",
                    "event_id",
                }
            ),
        )

    def test_token_round_trip(self) -> None:
        dt = datetime(2026, 3, 4, 5, 6, 7, 891011, tzinfo=timezone(timedelta(hours=-6)))
        token = HistoryCursor(dt, 42).token
        self.assertNotIn("=", token)
        self.assertEqual(
            decode_history_cursor(token), HistoryCursor(dt.astimezone(UTC), 42)
        )

    def test_decode_rejects(self) -> None:
        bad = [
            "",
            "!!!",
            _b64("2026-01-01T00:00:00|5"),
            _b64("2026-01-01T00:00:00+00:00|0"),
            _b64("2026-01-01T00:00:00+00:00|9223372036854775808"),
            _b64("2026-01-01T00:00:00+00:00|abc"),
            _b64("2026-01-01T00:00:00+00:00|5|6"),
            _b64("not-a-date|5"),
        ]
        for token in bad:
            with self.subTest(token=token), self.assertRaises(ValueError):
                decode_history_cursor(token)

    def test_decode_accepts_max_pk(self) -> None:
        cursor = decode_history_cursor(_b64(f"2026-01-01T00:00:00+00:00|{MAX_DB_INT}"))
        self.assertEqual(cursor.pk, MAX_DB_INT)

    def test_queryset_newest_first_with_pk_tiebreak(self) -> None:
        now = datetime(2026, 5, 1, 12, tzinfo=UTC)
        older = self._entry(now - timedelta(minutes=1))
        t1 = self._entry(now)
        t2 = self._entry(now)
        t3 = self._entry(now)
        ids = list(signup_history_queryset(self.event).values_list("pk", flat=True))
        self.assertEqual(ids, [t3.pk, t2.pk, t1.pk, older.pk])

    def test_queryset_select_related_users(self) -> None:
        self._entry(datetime(2026, 5, 1, tzinfo=UTC))
        qs = signup_history_queryset(self.event)
        self.assertEqual(
            qs.query.select_related,
            {
                "subject_user": {"base_profile": {}},
                "actor_user": {"base_profile": {}},
            },
        )
        with self.assertNumQueries(1):
            rows = list(qs)
            for row in rows:
                _ = row.subject_user.nickname if row.subject_user else None
                _ = row.actor_user.nickname if row.actor_user else None

    def test_after_q_walks_identical_timestamps(self) -> None:
        now = datetime(2026, 5, 1, 12, tzinfo=UTC)
        expected = [self._entry(now).pk for _ in range(5)]
        self._entry(now - timedelta(seconds=1))
        expected.append(SignupLedgerEntry.objects.order_by("-pk").first().pk)
        seen: list[int] = []
        cursor: HistoryCursor | None = None
        for _ in range(10):
            qs = signup_history_queryset(self.event)
            if cursor is not None:
                qs = qs.filter(history_after_q(cursor))
            page = list(qs[:2])
            if not page:
                break
            seen.extend(e.pk for e in page)
            last = page[-1]
            cursor = decode_history_cursor(
                HistoryCursor(last.occurred_at, last.pk).token
            )
        self.assertEqual(sorted(seen), sorted(expected))
        self.assertEqual(len(seen), len(set(seen)))
        self.assertEqual(seen, sorted(expected[:5], reverse=True) + [expected[5]])

    def test_filters_by_subject_user_not_signup(self) -> None:
        now = datetime(2026, 5, 1, 12, tzinfo=UTC)
        other_event = self.make_event()
        other_user = self.make_user()
        signup = EventSignup.objects.create(event=self.event, user=self.user)
        with_signup = self._entry(now, signup=signup, action=SignupAction.SIGNED_UP)
        signup.delete()
        orphan = self._entry(now, signup=None, action=SignupAction.WITHDREW)
        other = self._entry(now, subject=other_user)
        self._entry(now, event=other_event)

        by_user = list(
            signup_history_queryset(self.event, user_id=self.user.pk).values_list(
                "pk", flat=True
            )
        )
        self.assertEqual(by_user, [orphan.pk, with_signup.pk])

        by_action = list(
            signup_history_queryset(
                self.event, action=SignupAction.WITHDREW
            ).values_list("pk", flat=True)
        )
        self.assertEqual(by_action, [orphan.pk])

        both = list(
            signup_history_queryset(
                self.event, user_id=other_user.pk, action=SignupAction.SIGNED_UP
            ).values_list("pk", flat=True)
        )
        self.assertEqual(both, [other.pk])

        all_ids = set(signup_history_queryset(self.event).values_list("pk", flat=True))
        self.assertEqual(all_ids, {with_signup.pk, orphan.pk, other.pk})
