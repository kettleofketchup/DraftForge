"""sync_future_events copies repeater config onto upcoming series events."""

from datetime import date, datetime, time, timedelta
from datetime import timezone as dt_tz
from typing import Any

from events.models import Event, EventRepeater
from events.services import (
    DISCORD_CONFIG_FIELDS,
    DOTA_LOBBY_CONFIG_FIELDS,
    EVENT_CONFIG_FIELDS,
    TOURNAMENT_TEMPLATE_FIELDS,
    sync_future_events,
)
from events.tests.base import EventTestCase

SCHEDULED_AT = datetime(2099, 1, 5, 20, 0, tzinfo=dt_tz.utc)
HAND_SET_OPEN_AT = datetime(2099, 1, 1, 12, 0, tzinfo=dt_tz.utc)

SERIES_CONFIG: dict[str, Any] = {
    "tournament_name": "Series Cup",
    "tournament_type": "swiss",
    "game_type": 2,
    "draft_type": "snake",
    "people_per_team": 3,
    "number_of_teams": 4,
    "game_mode": "turbo",
    "custom_game_name": "Series Custom",
    "captains_draft_time": 20,
    "lobby_steam_league_id": 4242,
    "auto_create_hero_drafts": True,
    "draft_timer_enabled": False,
    "draft_grace_time_ms": 11000,
    "draft_reserve_time_ms": 12000,
    "draft_timeout_action": "skip_turn",
    "hero_timer_enabled": False,
    "hero_grace_time_ms": 13000,
    "hero_reserve_time_ms": 14000,
    "timezone": "Europe/Berlin",
    "min_players": 4,
    "max_players": 12,
    "signup_deadline_hours": 3,
    "allow_team_signups": True,
    "allow_user_signups": False,
    "auto_approve": True,
    "auto_confirm": True,
    "require_mmr_verified": True,
    "require_steam_id": True,
    "require_profile_complete": True,
    "roll_call_enabled": True,
    "roll_call_mode": "automatic",
    "ready_check_scope": "main_and_fill",
    "ready_check_open_minutes": 61,
    "ready_check_escalation_minutes": 21,
    "ready_check_close_minutes": 11,
    "ready_check_chase_minutes": 41,
    "ready_check_min_completion_pct": 55,
    "ready_check_low_completion_action": "drop_anyway",
    "ready_check_notify_on_signup": False,
    "ready_check_drop_notice": False,
    "start_cull_enabled": True,
    "start_cull_minutes_after": 3,
    "post_cull_fill_mode": "voice_arrival",
    "line_withdraw_forfeits": False,
    "line_switch_restamps": False,
    "staff_reason_policy": "all_staff_changes",
    "allow_active_mmr": False,
    "allow_previous_rank": False,
    "allow_battlecup_rating": False,
    "discord_create_event": True,
    "discord_sync_signups": True,
    "discord_event_title": "Series Title",
    "discord_event_description": "Series discord description",
    "discord_event_info": "Series info",
    "discord_signup_reminder": False,
    "discord_signup_reminder_hours": 6,
    "discord_confirm_attendance": True,
    "discord_confirm_attendance_hours": 3,
    "discord_profile_reminder": True,
    "discord_profile_reminder_hours": 5,
    "discord_mark_interested": True,
    "discord_post_signups": True,
    "discord_post_signups_channel_id": "1110001",
    "discord_announcement": True,
    "discord_announcement_channel_id": "2220002",
    "discord_announcement_hours": 7,
    "discord_confirm_attendance_channel_id": "6660006",
    "discord_profile_reminder_channel_id": "7770007",
    "discord_new_event_channel_id": "8880008",
    "discord_announcement_role_ids": ["3330003"],
    "discord_signup_role_ids": ["4440004"],
    "discord_start_mention": True,
    "discord_start_mention_minutes": 9,
    "discord_start_mention_scope": "main",
    "discord_require_rank_screenshot": True,
    "discord_require_battlecup_screenshot": True,
    "min_mmr": 2500,
    "event_voice_channel_id": "5550005",
    "voice_presence_confirms": True,
    "dota_lobby_mode": "auto",
    "dota_lobby_launch": "auto",
    "dota_lobby_region": "europe",
    "discord_send_lobby_info": True,
    "dota_lobby_password_mode": "random",
}
SERIES_POLICY: dict[str, Any] = {
    "signup_open_mode": "scheduled",
    "signups_open_hours_before": 30,
}
EVENT_POLICY: dict[str, Any] = {
    "signup_open_mode": "scheduled",
    "signups_open_hours_before": 5,
}

COPIED_UNCONDITIONALLY: dict[str, Any] = {
    "name": "Series Name",
    "description": "Series description",
    "tournament_date": SCHEDULED_AT,
    **SERIES_CONFIG,
}


class RepeaterConfigCascadeTest(EventTestCase):
    def _make(self, **repeater_overrides: Any) -> tuple[EventRepeater, Event]:
        repeater = EventRepeater.objects.create(
            organization=self.org,
            name="Series Name",
            description="Series description",
            frequency="weekly",
            day_of_week=1,
            time_of_day=time(20, 0),
            starts_at=date(2026, 1, 1),
            is_active=False,
            tournament_league=self.league,
            tournament_date=datetime(2001, 1, 1, tzinfo=dt_tz.utc),
            **{**SERIES_CONFIG, **SERIES_POLICY, **repeater_overrides},
        )
        event = Event.objects.create(
            organization=self.org,
            event_repeater=repeater,
            name="Old Name",
            description="Old description",
            scheduled_at=SCHEDULED_AT,
            state="upcoming",
            signups_open_at=HAND_SET_OPEN_AT,
            dota_lobby_password_mode="random",
            dota_lobby_password="evtpass1",
            **EVENT_POLICY,
        )
        return repeater, event

    def _fields(self, event: Event) -> dict[str, Any]:
        event.refresh_from_db()
        keys = [
            *COPIED_UNCONDITIONALLY,
            *SERIES_POLICY,
            "signups_open_at",
            "dota_lobby_password",
        ]
        return {
            **{k: getattr(event, k) for k in keys},
            "league": event.tournament_league_id,
        }

    def test_literal_config_covers_every_copied_field(self) -> None:
        copied = {
            *TOURNAMENT_TEMPLATE_FIELDS,
            *EVENT_CONFIG_FIELDS,
            *DISCORD_CONFIG_FIELDS,
            *DOTA_LOBBY_CONFIG_FIELDS,
        }
        literal = {
            *SERIES_CONFIG,
            *SERIES_POLICY,
            "tournament_league",
            "tournament_date",
        }
        self.assertEqual(copied, literal)

    def test_plain_cascade(self) -> None:
        repeater, event = self._make()
        sync_future_events(repeater)
        self.assertEqual(
            self._fields(event),
            {
                **COPIED_UNCONDITIONALLY,
                **EVENT_POLICY,
                "signups_open_at": HAND_SET_OPEN_AT,
                "dota_lobby_password": "evtpass1",
                "league": self.league.pk,
            },
        )

    def test_policy_changed_cascade(self) -> None:
        repeater, event = self._make()
        sync_future_events(repeater, policy_changed=True)
        self.assertEqual(
            self._fields(event),
            {
                **COPIED_UNCONDITIONALLY,
                **SERIES_POLICY,
                "signups_open_at": SCHEDULED_AT - timedelta(hours=30),
                "dota_lobby_password": "evtpass1",
                "league": self.league.pk,
            },
        )

    def test_realign_cascade(self) -> None:
        repeater, event = self._make()
        sync_future_events(repeater, realign_schedule=True)
        self.assertEqual(
            self._fields(event),
            {
                **COPIED_UNCONDITIONALLY,
                **EVENT_POLICY,
                "signups_open_at": SCHEDULED_AT - timedelta(hours=5),
                "dota_lobby_password": "evtpass1",
                "league": self.league.pk,
            },
        )

    def test_fixed_series_password_replaces_event_password(self) -> None:
        repeater, event = self._make(
            dota_lobby_password_mode="fixed", dota_lobby_password="seriespw"
        )
        sync_future_events(repeater)
        fields = self._fields(event)
        self.assertEqual(fields["dota_lobby_password_mode"], "fixed")
        self.assertEqual(fields["dota_lobby_password"], "seriespw")
