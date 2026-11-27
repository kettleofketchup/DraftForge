"""Shared Discord send gates match the inline task conditions they replaced."""

import subprocess
import sys
from collections.abc import Callable, Iterable
from datetime import date, time, timedelta
from itertools import product
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

from django.utils import timezone as tz
from rest_framework.test import APIClient

from discordbot.models import DiscordEvent, DiscordEventMsgSignup, DiscordMessageLog
from discordbot.schemas import DiscordEventStateSchema
from events.constants import EventState, RepeatFrequency, SignupOpenMode
from events.discord import gates
from events.discord.gates import (
    Destination,
    GateResult,
    announcement_branch,
    announcement_notice_gate,
    announcement_send_state,
    attendance_reminder_gate,
    initial_state_for_new_event,
    new_event_post_gate,
    profile_reminder_gate,
    repeater_generates,
    scheduled_event_gate,
    scheduled_event_sync_gate,
    signup_post_destination,
    signup_post_gate,
    signup_reminder_gate,
    start_mention_gate,
)
from events.models import Event, EventRepeater
from events.services import generate_events_for_repeater
from events.tasks import (
    _create_discord_scheduled_event_impl,
    _send_event_announcement_impl,
    _send_new_event_notification_impl,
    _send_start_mention_impl,
    _sync_discord_event_signups_impl,
    fire_event_reminder,
    send_attendance_reminder,
    send_profile_reminder,
    send_subscriber_notifications,
)
from events.tests._internal_client_orm import _get_event_for_task_orm
from events.tests.base import EventTestCase
from events.tests.test_discord_tasks import _DiscordTaskTestCase, _ok_response
from events.utils import starts_in_future
from org.models import Organization

FUTURE = timedelta(days=7)
STATES = [EventState.UPCOMING, EventState.SIGNUPS_OPEN, EventState.ROLL_CALL]
NOTIFY = "events.discord.dispatch.notify_signup_changed"


def _shapes(event: Event) -> list[Any]:
    return [Event.objects.nocache().get(pk=event.pk), _get_event_for_task_orm(event.pk)]


def _discord_state(**fields: Any) -> DiscordEventStateSchema:
    return DiscordEventStateSchema.model_validate(fields)


class _GateTable(EventTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.guild_org = Organization.objects.create(
            name="Guild Org", owner=self.admin, discord_server_id="g-1"
        )

    def _rows(self, **axes: Iterable[Any]) -> list[dict[str, Any]]:
        keys = list(axes)
        return [dict(zip(keys, values)) for values in product(*axes.values())]

    def _event(self, **fields: Any) -> Event:
        fields.setdefault("scheduled_at", tz.now() + FUTURE)
        fields.setdefault("organization", self.org)
        return Event.objects.create(created_by=self.admin, name="Gate Event", **fields)

    def _check(
        self,
        rows: list[dict[str, Any]],
        old: Callable[..., str | None],
        new: Callable[..., str | None],
        extra: Callable[[dict[str, Any]], dict[str, Any]] = lambda row: {},
    ) -> None:
        for row in rows:
            event_fields = {k: v for k, v in row.items() if not k.startswith("_")}
            if event_fields.pop("guild", False):
                event_fields["organization"] = self.guild_org
            model = self._event(**event_fields)
            for shape in _shapes(model):
                with self.subTest(row=row, shape=type(shape).__name__):
                    self.assertEqual(new(shape, **extra(row)), old(shape, **extra(row)))


class SignupPostGateTableTest(_GateTable):
    """tasks.py _send_event_announcement_impl pre-send checks."""

    @staticmethod
    def _old(event: Any) -> str | None:
        if event.state != "signups_open":
            return "state"
        signup_available = bool(
            event.discord_post_signups and event.discord_post_signups_channel_id
        )
        announcement_available = bool(
            event.discord_announcement and event.discord_announcement_channel_id
        )
        if not (signup_available or announcement_available):
            return "no_destination"
        return None

    @staticmethod
    def _new(event: Any) -> str | None:
        if "state_not_signups_open" in signup_post_gate(event).reasons:
            return "state"
        if announcement_branch(event) == "none":
            return "no_destination"
        return None

    def test_matches_inline_condition(self) -> None:
        rows = self._rows(
            state=STATES,
            discord_post_signups=[True, False],
            discord_post_signups_channel_id=["", "s-1"],
            discord_announcement=[True, False],
            discord_announcement_channel_id=["", "a-1"],
        )
        self._check(rows, self._old, self._new)

    def test_would_send_matches_task_reaching_send(self) -> None:
        rows = self._rows(
            state=STATES,
            discord_post_signups=[True, False],
            discord_post_signups_channel_id=["", "s-1"],
            discord_announcement=[True, False],
            discord_announcement_channel_id=["", "a-1"],
        )
        self._check(
            rows,
            lambda e: str(self._old(e) is None),
            lambda e: str(signup_post_gate(e).would_send),
        )


class AnnouncementBranchTest(_GateTable):
    def test_announcement_branch_values(self) -> None:
        cases = [
            ("s-1", "", "signup_post_only"),
            ("s-1", "a-1", "signup_post_and_notice"),
            ("", "a-1", "fallback_signup_post"),
            ("", "", "none"),
        ]
        for signup, announcement, expected in cases:
            model = self._event(
                discord_post_signups=True,
                discord_post_signups_channel_id=signup,
                discord_announcement=True,
                discord_announcement_channel_id=announcement,
            )
            for shape in _shapes(model):
                with self.subTest(expected=expected, shape=type(shape).__name__):
                    self.assertEqual(announcement_branch(shape), expected)

    def test_announcement_send_state(self) -> None:
        self.assertEqual(announcement_send_state(), EventState.SIGNUPS_OPEN)

    def test_signup_post_destination(self) -> None:
        both = self._event(
            discord_post_signups=True,
            discord_post_signups_channel_id="s-1",
            discord_announcement=True,
            discord_announcement_channel_id="a-1",
        )
        for shape in _shapes(both):
            self.assertEqual(
                signup_post_destination(shape),
                Destination(
                    type="forum_thread",
                    channel_id="s-1",
                    thread_name="Gate Event",
                    fallback_channel_id="a-1",
                ),
            )
        titled = self._event(
            discord_event_title="t" * 130,
            discord_post_signups=True,
            discord_post_signups_channel_id="s-1",
        )
        for shape in _shapes(titled):
            dest = signup_post_destination(shape)
            assert dest is not None
            self.assertEqual(dest.thread_name, "t" * 100)
            self.assertIsNone(dest.fallback_channel_id)
        fallback = self._event(
            discord_announcement=True, discord_announcement_channel_id="a-1"
        )
        for shape in _shapes(fallback):
            self.assertEqual(
                signup_post_destination(shape),
                Destination(type="channel", channel_id="a-1"),
            )
        for shape in _shapes(self._event()):
            self.assertIsNone(signup_post_destination(shape))


class AnnouncementNoticeGateTest(_GateTable):
    """The notice is sent when the announcement destination exists (step 2)."""

    @staticmethod
    def _old(event: Any) -> str | None:
        if event.state != "signups_open":
            return "state"
        if not bool(
            event.discord_announcement and event.discord_announcement_channel_id
        ):
            return "no_announcement"
        return None

    @staticmethod
    def _new(event: Any) -> str | None:
        gate = announcement_notice_gate(event)
        if "state_not_signups_open" in gate.reasons:
            return "state"
        if not gate.would_send:
            return "no_announcement"
        return None

    def test_matches_inline_condition(self) -> None:
        rows = self._rows(
            state=STATES,
            discord_announcement=[True, False],
            discord_announcement_channel_id=["", "a-1"],
        )
        self._check(rows, self._old, self._new)

    def test_reasons(self) -> None:
        event = self._event(state=EventState.SIGNUPS_OPEN)
        self.assertEqual(
            announcement_notice_gate(event).reasons, ["toggle_off", "no_channel"]
        )
        self.assertEqual(
            announcement_notice_gate(event, manual=True).reasons, ["no_channel"]
        )


class ReminderGateTableTest(_GateTable):
    """send_attendance_reminder / send_profile_reminder inline checks."""

    @staticmethod
    def _old_attendance(event: Any) -> str | None:
        if not event.discord_announcement_channel_id:
            return "no_channel"
        if not event.discord_confirm_attendance:
            return "disabled"
        return None

    @staticmethod
    def _old_profile(event: Any) -> str | None:
        if not event.discord_announcement_channel_id:
            return "no_channel"
        if not event.discord_profile_reminder:
            return "disabled"
        return None

    @staticmethod
    def _new_with(gate_fn: Callable[[Any], GateResult]) -> Callable[[Any], str | None]:
        def new(event: Any) -> str | None:
            gate = gate_fn(event)
            if "no_channel" in gate.reasons:
                return "no_channel"
            if "toggle_off" in gate.reasons:
                return "disabled"
            return None

        return new

    def test_attendance_matches_inline_condition(self) -> None:
        rows = self._rows(
            discord_confirm_attendance=[True, False],
            discord_announcement_channel_id=["", "a-1"],
        )
        self._check(
            rows, self._old_attendance, self._new_with(attendance_reminder_gate)
        )

    def test_profile_matches_inline_condition(self) -> None:
        rows = self._rows(
            discord_profile_reminder=[True, False],
            discord_announcement_channel_id=["", "a-1"],
        )
        self._check(rows, self._old_profile, self._new_with(profile_reminder_gate))

    def test_registry_states_and_manual(self) -> None:
        event = self._event(
            state=EventState.UPCOMING,
            discord_announcement_channel_id="a-1",
        )
        self.assertEqual(
            attendance_reminder_gate(event).reasons,
            ["toggle_off", "state_not_open_or_roll_call"],
        )
        self.assertEqual(
            profile_reminder_gate(event, manual=True, already_fired=True).reasons,
            ["state_not_signups_open", "already_sent"],
        )
        event.state = EventState.ROLL_CALL
        event.discord_confirm_attendance = True
        self.assertTrue(attendance_reminder_gate(event).would_send)


class StartMentionGateTableTest(_GateTable):
    @staticmethod
    def _old(
        event: Any, discord_state: Any, fired_by_user_id: int | None
    ) -> str | None:
        if event.state not in frozenset({"signups_open", "roll_call"}):
            return "state"
        if not event.discord_start_mention and fired_by_user_id is None:
            return "disabled"
        if not (
            discord_state
            and discord_state.signup_posted
            and discord_state.signup_message_id
        ):
            return "no_post"
        return None

    @staticmethod
    def _new(
        event: Any, discord_state: Any, fired_by_user_id: int | None
    ) -> str | None:
        manual = fired_by_user_id is not None
        gate = start_mention_gate(event, discord_state=discord_state, manual=manual)
        if "state_not_open_or_roll_call" in gate.reasons:
            return "state"
        if "toggle_off" in gate.reasons:
            return "disabled"
        if "no_signup_post_yet" in gate.reasons:
            return "no_post"
        return None

    def test_matches_inline_condition(self) -> None:
        states = [
            None,
            _discord_state(signup_posted=False),
            _discord_state(signup_posted=True),
            _discord_state(signup_posted=True, signup_message_id="m-1"),
        ]
        rows = self._rows(
            state=STATES,
            discord_start_mention=[True, False],
            _state=range(len(states)),
            _fired=[None, 5],
        )
        self._check(
            rows,
            self._old,
            self._new,
            extra=lambda row: {
                "discord_state": states[row["_state"]],
                "fired_by_user_id": row["_fired"],
            },
        )

    def test_start_mention_gate_manual_bypasses_toggle(self) -> None:
        event = self._event(state=EventState.SIGNUPS_OPEN, discord_start_mention=False)
        posted = _discord_state(signup_posted=True, signup_message_id="m-1")
        self.assertEqual(
            start_mention_gate(event, discord_state=posted).reasons, ["toggle_off"]
        )
        self.assertTrue(
            start_mention_gate(event, discord_state=posted, manual=True).would_send
        )
        self.assertEqual(
            start_mention_gate(
                event, discord_state=posted, manual=True, already_fired=True
            ).reasons,
            ["already_sent"],
        )


class NewEventPostGateTest(_GateTable):
    def test_matches_inline_condition(self) -> None:
        rows = self._rows(
            discord_announcement_channel_id=["", "a-1"],
            discord_announcement=[True, False],
        )
        self._check(
            rows,
            lambda e: None if e.discord_announcement_channel_id else "no_channel",
            lambda e: "no_channel"
            if "no_channel" in new_event_post_gate(e).reasons
            else None,
        )

    def test_only_checks_channel(self) -> None:
        event = self._event(discord_announcement_channel_id="a-1")
        self.assertEqual(new_event_post_gate(event), GateResult(True, []))


class ScheduledEventGateTableTest(_GateTable):
    @staticmethod
    def _old(event: Any) -> str | None:
        if not event.discord_create_event:
            return "disabled"
        if not event.organization.discord_server_id:
            return "no_guild"
        if not starts_in_future(event.scheduled_at):
            return "past"
        return None

    @staticmethod
    def _new(event: Any) -> str | None:
        gate = scheduled_event_gate(event)
        for code, label in (
            ("toggle_off", "disabled"),
            ("no_discord_server", "no_guild"),
            ("start_in_past", "past"),
        ):
            if code in gate.reasons:
                return label
        return None

    def test_matches_inline_condition(self) -> None:
        rows = self._rows(
            discord_create_event=[True, False],
            guild=[True, False],
            scheduled_at=[tz.now() + FUTURE, tz.now() - FUTURE],
        )
        self._check(rows, self._old, self._new)


class ScheduledEventSyncGateTableTest(_GateTable):
    @staticmethod
    def _old(event: Any, creation_log: Any) -> str | None:
        if not event.discord_sync_signups:
            return "disabled"
        if not creation_log or not creation_log.discord_message_id:
            return "no_event"
        return None

    @staticmethod
    def _new(event: Any, creation_log: Any) -> str | None:
        gate = scheduled_event_sync_gate(
            event,
            scheduled_event_message_id=(
                creation_log.discord_message_id if creation_log else None
            ),
        )
        if "toggle_off" in gate.reasons:
            return "disabled"
        if "no_scheduled_event_yet" in gate.reasons:
            return "no_event"
        return None

    def test_matches_inline_condition(self) -> None:
        logs = [
            None,
            SimpleNamespace(discord_message_id=""),
            SimpleNamespace(discord_message_id="se-1"),
        ]
        rows = self._rows(discord_sync_signups=[True, False], _log=range(3))
        self._check(
            rows,
            self._old,
            self._new,
            extra=lambda row: {"creation_log": logs[row["_log"]]},
        )


class SignupReminderGateTableTest(_GateTable):
    @staticmethod
    def _old(event: Any, discord_state: Any) -> str | None:
        if not event.event_repeater_id:
            return "no_repeater"
        if not discord_state or not discord_state.has_discord_event:
            return "no_discord_event"
        return None

    @staticmethod
    def _new(event: Any, discord_state: Any) -> str | None:
        gate = signup_reminder_gate(event, discord_state=discord_state)
        if "not_a_series" in gate.reasons:
            return "no_repeater"
        if "no_discord_server" in gate.reasons:
            return "no_discord_event"
        return None

    def test_matches_inline_condition(self) -> None:
        repeater = EventRepeater.objects.create(
            organization=self.org,
            name="Series",
            frequency=RepeatFrequency.WEEKLY,
            day_of_week=2,
            time_of_day=time(19, 0),
            starts_at=date(2026, 3, 1),
            created_by=self.admin,
        )
        states = [
            None,
            _discord_state(has_discord_event=False),
            _discord_state(has_discord_event=True, discord_event_pk=1),
        ]
        rows = self._rows(event_repeater=[None, repeater], _state=range(3))
        self._check(
            rows,
            self._old,
            self._new,
            extra=lambda row: {"discord_state": states[row["_state"]]},
        )

    def test_registry_conditions_reported(self) -> None:
        event = self._event(state=EventState.UPCOMING, discord_signup_reminder=False)
        self.assertEqual(
            signup_reminder_gate(event, already_fired=True).reasons,
            [
                "toggle_off",
                "not_a_series",
                "no_discord_server",
                "state_not_signups_open",
                "already_sent",
            ],
        )


class InitialStateTest(EventTestCase):
    def test_initial_state_for_new_event(self) -> None:
        self.assertEqual(initial_state_for_new_event(True), EventState.SIGNUPS_OPEN)
        self.assertEqual(initial_state_for_new_event(False), EventState.UPCOMING)

    @patch("events.views.notify_create_discord_event")
    def test_create_with_open_signups_in_manual_mode_opens_and_refreshes(
        self, _notify: MagicMock
    ) -> None:
        client = APIClient()
        client.force_authenticate(self.admin)
        for mode in (
            SignupOpenMode.MANUAL,
            SignupOpenMode.SCHEDULED,
            SignupOpenMode.IMMEDIATE,
        ):
            with self.subTest(mode=mode):
                with (
                    patch(NOTIFY) as refresh,
                    patch(
                        "events.views.initial_state_for_new_event",
                        wraps=initial_state_for_new_event,
                    ) as spy,
                    self.captureOnCommitCallbacks(execute=True),
                ):
                    resp = client.post(
                        "/api/events/?open_signups=true",
                        {
                            "organization": self.org.pk,
                            "name": f"Open {mode}",
                            "scheduled_at": (tz.now() + FUTURE).isoformat(),
                            "signup_open_mode": mode,
                        },
                        format="json",
                    )
                self.assertEqual(resp.status_code, 201, resp.content)
                spy.assert_called_once_with(True)
                event = Event.objects.nocache().get(pk=resp.json()["id"])
                self.assertEqual(event.state, EventState.SIGNUPS_OPEN)
                refresh.assert_called()

    @patch("events.views.notify_create_discord_event")
    def test_create_without_open_signups_stays_upcoming(
        self, _notify: MagicMock
    ) -> None:
        client = APIClient()
        client.force_authenticate(self.admin)
        resp = client.post(
            "/api/events/",
            {
                "organization": self.org.pk,
                "name": "Closed",
                "scheduled_at": (tz.now() + FUTURE).isoformat(),
                "signup_open_mode": SignupOpenMode.MANUAL,
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        event = Event.objects.nocache().get(pk=resp.json()["id"])
        self.assertEqual(event.state, EventState.UPCOMING)

    @patch("events.services.ensure_discord_event")
    @patch("events.services.create_tournament_for_event")
    @patch("events.services.notify_create_discord_event")
    @patch("events.services.notify_new_event")
    def test_one_off_open_signups_opens_and_refreshes(self, *_mocks: MagicMock) -> None:
        repeater = EventRepeater.objects.create(
            organization=self.org,
            name="Sunday Turbo",
            frequency=RepeatFrequency.WEEKLY,
            day_of_week=0,
            time_of_day=time(18, 0),
            starts_at=tz.now().date(),
            created_by=self.admin,
            signup_open_mode=SignupOpenMode.MANUAL,
        )
        client = APIClient()
        client.force_authenticate(self.admin)
        with (
            patch(NOTIFY) as refresh,
            patch(
                "events.views.initial_state_for_new_event",
                wraps=initial_state_for_new_event,
            ) as spy,
            self.captureOnCommitCallbacks(execute=True),
        ):
            resp = client.post(
                f"/api/events/repeaters/{repeater.pk}/create-event/",
                {
                    "scheduled_at": (tz.now() + timedelta(days=2, hours=5)).isoformat(),
                    "open_signups": True,
                },
                format="json",
            )
        self.assertEqual(resp.status_code, 201, resp.content)
        spy.assert_called_once_with(True)
        self.assertEqual(resp.data["state"], EventState.SIGNUPS_OPEN)
        refresh.assert_called()


class RepeaterGeneratesTest(EventTestCase):
    def _repeater(self, **fields: Any) -> EventRepeater:
        defaults: dict[str, Any] = {
            "organization": self.org,
            "name": "Weekly",
            "frequency": RepeatFrequency.WEEKLY,
            "day_of_week": 2,
            "time_of_day": time(19, 0),
            "starts_at": date(2026, 3, 1),
            "generate_days_ahead": 7,
            "is_active": True,
            "created_by": self.admin,
        }
        defaults.update(fields)
        return EventRepeater.objects.create(**defaults)

    def test_repeater_generates_paused_and_ended(self) -> None:
        today = date(2026, 3, 2)
        self.assertEqual(repeater_generates(self._repeater(), today), GateResult(True))
        self.assertEqual(
            repeater_generates(self._repeater(is_active=False), today).reasons,
            ["series_paused"],
        )
        self.assertEqual(
            repeater_generates(self._repeater(ends_at=date(2026, 3, 1)), today).reasons,
            ["series_ended"],
        )
        self.assertTrue(
            repeater_generates(self._repeater(ends_at=today), today).would_send
        )

    @patch("events.services._today", return_value=date(2026, 3, 2))
    def test_generate_events_for_repeater_calls_it(self, _today: MagicMock) -> None:
        for fields, expected in (
            ({}, 1),
            ({"is_active": False}, 0),
            ({"ends_at": date(2026, 3, 1)}, 0),
        ):
            repeater = self._repeater(**fields)
            with (
                self.subTest(fields=fields),
                patch(
                    "events.services.repeater_generates", wraps=repeater_generates
                ) as spy,
            ):
                self.assertEqual(len(generate_events_for_repeater(repeater)), expected)
                spy.assert_called_once_with(repeater, date(2026, 3, 2))


class TaskCallsGateTest(_DiscordTaskTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.ev = self.make_event(discord_announcement_channel_id="a-1")

    def _assert_called(self, name: str, run: Callable[[], Any]) -> None:
        real = getattr(gates, name)
        with patch(f"events.tasks.{name}", wraps=real) as spy:
            run()
        spy.assert_called()
        self.assertEqual(spy.call_args.args[0].pk, self.ev.pk)

    @patch("discordbot.utils._rate_limited_request")
    def test_task_calls_gates(self, mock_req: MagicMock) -> None:
        mock_req.return_value = _ok_response({"id": "m1"})
        cases: list[tuple[str, Callable[[], Any]]] = [
            ("signup_post_gate", lambda: _send_event_announcement_impl(self.ev.pk)),
            ("announcement_branch", lambda: _send_event_announcement_impl(self.ev.pk)),
            ("attendance_reminder_gate", lambda: send_attendance_reminder(self.ev.pk)),
            ("profile_reminder_gate", lambda: send_profile_reminder(self.ev.pk)),
            ("start_mention_gate", lambda: _send_start_mention_impl(self.ev.pk, 1)),
            (
                "new_event_post_gate",
                lambda: _send_new_event_notification_impl(self.ev.pk),
            ),
            (
                "scheduled_event_gate",
                lambda: _create_discord_scheduled_event_impl(self.ev.pk),
            ),
            (
                "scheduled_event_sync_gate",
                lambda: _sync_discord_event_signups_impl(self.ev.pk),
            ),
            (
                "signup_reminder_gate",
                lambda: send_subscriber_notifications(self.ev.pk),
            ),
        ]
        for name, run in cases:
            with self.subTest(gate=name):
                self._assert_called(name, run)

    @patch("discordbot.utils._rate_limited_request")
    def test_start_mention_task_manual_bypasses_toggle(
        self, mock_req: MagicMock
    ) -> None:
        mock_req.return_value = _ok_response({"id": "m1"})
        event = self.make_event(
            state=EventState.SIGNUPS_OPEN,
            discord_start_mention=False,
            discord_post_signups=True,
            discord_post_signups_channel_id="s-1",
        )
        DiscordEventMsgSignup.objects.create(
            event=event, channel_id="s-1", message_id="m-1", has_posted=True
        )
        self.assertEqual(
            _send_start_mention_impl(event.pk, None),
            f"Start mention disabled for event {event.pk}",
        )
        mock_req.assert_not_called()
        result = _send_start_mention_impl(event.pk, self.admin.pk)
        self.assertTrue(result.startswith("Mentioned"), result)
        self.assertTrue(
            DiscordMessageLog.objects.filter(
                source="start_mention", source_id=event.pk
            ).exists()
        )

    @patch("discordbot.utils._rate_limited_request")
    def test_fire_event_reminder_ignores_toggles(self, mock_req: MagicMock) -> None:
        mock_req.return_value = _ok_response({"id": "m1"})
        event = self.make_event(
            state=EventState.UPCOMING,
            discord_announcement_channel_id="a-1",
            discord_confirm_attendance=False,
            discord_profile_reminder=False,
        )
        for reminder_type in ("confirm_attendance", "profile_reminder"):
            with self.subTest(reminder_type=reminder_type):
                mock_req.reset_mock()
                result = fire_event_reminder(event.pk, reminder_type)
                self.assertEqual(result, f"Fired {reminder_type} for event {event.pk}")
                posts = [c for c in mock_req.call_args_list if c.args[0] == "POST"]
                self.assertEqual(len(posts), 1)

    @patch("discordbot.utils._rate_limited_request")
    def test_signup_only_event_still_posts_signup(self, mock_req: MagicMock) -> None:
        mock_req.return_value = _ok_response({"id": "m1"})
        event = self.make_event(
            discord_post_signups=True,
            discord_post_signups_channel_id="s-1",
        )
        result = _send_event_announcement_impl(event.pk)
        self.assertEqual(result, f"Posted signup for event {event.pk}")
        posts = [c for c in mock_req.call_args_list if c.args[0] == "POST"]
        self.assertEqual(len(posts), 1)
        self.assertIn("/channels/s-1/threads", posts[0].args[1])

    def test_signup_reminder_task_returns_same_skip_strings(self) -> None:
        self.assertEqual(send_subscriber_notifications(self.ev.pk), "No repeater")
        repeater = EventRepeater.objects.create(
            organization=self.org,
            name="Series",
            frequency=RepeatFrequency.WEEKLY,
            day_of_week=2,
            time_of_day=time(19, 0),
            starts_at=date(2026, 3, 1),
            created_by=self.admin,
        )
        event = self.make_event(event_repeater=repeater)
        self.assertEqual(send_subscriber_notifications(event.pk), "No Discord event")
        DiscordEvent.objects.create(event=event, guild_id="g-1")
        self.assertTrue(
            send_subscriber_notifications(event.pk).startswith("Sent 0 DMs"),
        )


class PreviewCodesDjangoFreeTest(EventTestCase):
    def test_preview_codes_module_imports_without_django(self) -> None:
        path = Path(__file__).resolve().parents[1] / "discord" / "preview_codes.py"
        code = (
            "import importlib.util, sys; "
            f"spec = importlib.util.spec_from_file_location('preview_codes', {str(path)!r}); "
            "module = importlib.util.module_from_spec(spec); "
            "spec.loader.exec_module(module); "
            "assert 'django' not in sys.modules, 'django imported'; "
            "assert 'already_sent' in module.GateCode.__args__"
        )
        result = subprocess.run(
            [sys.executable, "-I", "-c", code], capture_output=True, text=True
        )
        self.assertEqual(result.returncode, 0, result.stderr)
