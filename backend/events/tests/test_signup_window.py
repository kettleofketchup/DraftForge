from datetime import timedelta
from typing import Any

from django.test import TestCase, override_settings
from django.utils import timezone

from app.models import CustomUser, League, Organization, PositionsModel, Tournament
from events.constants import EventState
from events.models import Event
from events.services import process_rsvp
from events.signup_window import user_signups_open_tournament_ids


@override_settings(CACHEOPS_ENABLED=False)
class UserSignupsOpenTournamentIdsTests(TestCase):
    org: Organization
    league: League
    user: CustomUser

    @classmethod
    def setUpTestData(cls) -> None:
        cls.org = Organization.objects.create(name="Window Org")
        cls.league = League.objects.create(organization=cls.org, name="Window League")
        cls.user = CustomUser.objects.create_user(username="window_player", password="x")
        cls.user.positions = PositionsModel.objects.create()
        cls.user.save()

    def _event(self, **overrides: Any) -> tuple[Event, Tournament]:
        start = timezone.now() + timedelta(days=2)
        tournament = Tournament.objects.create(
            name="Window Cup", date_played=start, league=self.league
        )
        fields: dict[str, Any] = {
            "organization": self.org,
            "name": "Window Event",
            "scheduled_at": start,
            "state": EventState.SIGNUPS_OPEN,
            "tournament": tournament,
        }
        fields.update(overrides)
        return Event.objects.create(**fields), tournament

    def _rsvp_accepted(self, event: Event) -> bool:
        try:
            process_rsvp(event, self.user)
        except ValueError:
            return False
        return True

    def test_listed_exactly_when_process_rsvp_accepts(self) -> None:
        now = timezone.now()
        cases: dict[str, dict[str, Any]] = {
            "signups_open": {},
            "opened_early": {"signups_open_at": now + timedelta(hours=1)},
            "inside_deadline": {
                "scheduled_at": now + timedelta(hours=1),
                "signup_deadline_hours": 2,
            },
            "user_signups_disabled": {"allow_user_signups": False},
            "upcoming": {"state": EventState.UPCOMING},
            "roll_call": {"state": EventState.ROLL_CALL},
            "in_progress": {"state": EventState.IN_PROGRESS},
            "completed": {"state": EventState.COMPLETED},
            "cancelled": {"state": EventState.CANCELLED},
        }
        for name, overrides in cases.items():
            with self.subTest(case=name):
                event, tournament = self._event(**overrides)
                listed = tournament.pk in user_signups_open_tournament_ids()
                self.assertEqual(listed, self._rsvp_accepted(event))

    def test_signups_open_regardless_of_schedule_fields(self) -> None:
        now = timezone.now()
        for overrides in (
            {"signups_open_at": now + timedelta(days=1)},
            {"scheduled_at": now + timedelta(minutes=30), "signup_deadline_hours": 1},
            {"allow_user_signups": False},
        ):
            with self.subTest(**{k: str(v) for k, v in overrides.items()}):
                _, tournament = self._event(**overrides)
                self.assertIn(tournament.pk, user_signups_open_tournament_ids())

    def test_event_without_tournament_is_ignored(self) -> None:
        Event.objects.create(
            organization=self.org,
            name="Loose Event",
            scheduled_at=timezone.now() + timedelta(days=2),
            state=EventState.SIGNUPS_OPEN,
        )
        self.assertEqual(user_signups_open_tournament_ids(), set())
