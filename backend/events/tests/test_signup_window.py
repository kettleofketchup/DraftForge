from datetime import UTC, datetime, timedelta
from typing import Any

from django.test import TestCase, override_settings

from app.models import League, Organization, Tournament
from events.constants import EventState
from events.models import Event
from events.signup_window import user_signups_open_tournament_ids

NOW = datetime(2026, 11, 13, 12, 0, tzinfo=UTC)
START = NOW + timedelta(days=2)


@override_settings(CACHEOPS_ENABLED=False)
class UserSignupsOpenTournamentIdsTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.org = Organization.objects.create(name="Window Org")
        cls.league = League.objects.create(organization=cls.org, name="Window League")

    def _event(self, **overrides: Any) -> Tournament:
        tournament = Tournament.objects.create(
            name="Window Cup", date_played=START, league=self.league
        )
        fields: dict[str, Any] = {
            "organization": self.org,
            "name": "Window Event",
            "scheduled_at": START,
            "state": EventState.SIGNUPS_OPEN,
            "tournament": tournament,
        }
        fields.update(overrides)
        Event.objects.create(**fields)
        return tournament

    def assertOpen(self, tournament: Tournament, expected: bool) -> None:
        self.assertEqual(
            tournament.pk in user_signups_open_tournament_ids(NOW), expected
        )

    def test_signups_open_state_is_open(self) -> None:
        self.assertOpen(self._event(), True)

    def test_other_states_are_closed(self) -> None:
        for state in (
            EventState.UPCOMING,
            EventState.ROLL_CALL,
            EventState.IN_PROGRESS,
            EventState.COMPLETED,
            EventState.CANCELLED,
        ):
            with self.subTest(state=state):
                self.assertOpen(self._event(state=state), False)

    def test_user_signups_disabled_is_closed(self) -> None:
        self.assertOpen(self._event(allow_user_signups=False), False)

    def test_signups_open_at_in_future_is_closed(self) -> None:
        self.assertOpen(self._event(signups_open_at=NOW + timedelta(minutes=1)), False)

    def test_signups_open_at_reached_is_open(self) -> None:
        self.assertOpen(self._event(signups_open_at=NOW), True)

    def test_before_deadline_is_open(self) -> None:
        self.assertOpen(
            self._event(scheduled_at=NOW + timedelta(hours=3), signup_deadline_hours=2),
            True,
        )

    def test_at_or_past_deadline_is_closed(self) -> None:
        self.assertOpen(
            self._event(scheduled_at=NOW + timedelta(hours=2), signup_deadline_hours=2),
            False,
        )
        self.assertOpen(
            self._event(scheduled_at=NOW + timedelta(hours=1), signup_deadline_hours=2),
            False,
        )

    def test_no_deadline_stays_open_until_state_changes(self) -> None:
        self.assertOpen(self._event(scheduled_at=NOW - timedelta(hours=1)), True)

    def test_event_without_tournament_is_ignored(self) -> None:
        Event.objects.create(
            organization=self.org,
            name="Loose Event",
            scheduled_at=START,
            state=EventState.SIGNUPS_OPEN,
        )
        self.assertEqual(user_signups_open_tournament_ids(NOW), set())
