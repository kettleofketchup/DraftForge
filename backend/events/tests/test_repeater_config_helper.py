"""apply_repeater_config_to_event copies what the plain cascade copies."""

from datetime import date, datetime, time
from datetime import timezone as dt_tz

from events.models import Event, EventRepeater
from events.services import apply_repeater_config_to_event
from events.tests.base import EventTestCase
from events.tests.test_repeater_config_copy import (
    COPIED_UNCONDITIONALLY,
    EVENT_POLICY,
    HAND_SET_OPEN_AT,
    SCHEDULED_AT,
    SERIES_CONFIG,
    SERIES_POLICY,
)

SERIES_TOURNAMENT_DATE = datetime(2001, 1, 1, tzinfo=dt_tz.utc)


class ApplyRepeaterConfigTest(EventTestCase):
    def test_apply_repeater_config_matches_cascade_case_a(self) -> None:
        repeater = EventRepeater.objects.create(
            organization=self.org,
            name="Series Name",
            description="Series description",
            frequency="weekly",
            day_of_week=1,
            time_of_day=time(20, 0),
            starts_at=date(2026, 1, 1),
            tournament_league=self.league,
            tournament_date=SERIES_TOURNAMENT_DATE,
            dota_lobby_password="seriespw",
            **{**SERIES_CONFIG, **SERIES_POLICY},
        )
        event = Event(
            organization=self.org,
            event_repeater=repeater,
            name="Old Name",
            scheduled_at=SCHEDULED_AT,
            signups_open_at=HAND_SET_OPEN_AT,
            dota_lobby_password_mode="fixed",
            dota_lobby_password="evtpass1",
            **EVENT_POLICY,
        )

        apply_repeater_config_to_event(repeater, event)

        expected = {
            **COPIED_UNCONDITIONALLY,
            "tournament_date": SERIES_TOURNAMENT_DATE,
            **EVENT_POLICY,
            "signups_open_at": HAND_SET_OPEN_AT,
            "dota_lobby_password": "evtpass1",
            "tournament_league_id": self.league.pk,
        }
        self.assertEqual({k: getattr(event, k) for k in expected}, expected)
        self.assertIsNone(event.pk)
