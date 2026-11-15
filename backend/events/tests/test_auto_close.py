"""Internal auto-close endpoint, stale_before filter, cleanup task and Discord end time."""

from datetime import datetime, timedelta
from datetime import timezone as dt_tz
from typing import Any
from unittest.mock import MagicMock, patch

from django.test import override_settings
from django.utils import timezone as tz
from rest_framework.response import Response
from rest_framework.test import APIClient

from app.internal_client import auto_close_event
from app.models import CustomUser, PositionsModel
from events.completion import CloseResult, close_event
from events.constants import EventState
from events.models import Event
from events.schemas import EventTaskSchema
from events.tasks import cleanup_stale_events, create_discord_scheduled_event
from events.tests.base import EventTestCase
from org.contributions.kinds import ContributionKind
from org.models import ContributionEntry

TOKEN = "test-internal-token"
HEADERS = {"HTTP_X_INTERNAL_TOKEN": TOKEN}


def _make_user(username: str) -> CustomUser:
    user = CustomUser.objects.create_user(username=username, password="x")
    user.positions = PositionsModel.objects.create()
    user.save()
    return user


@override_settings(INTERNAL_SERVICE_TOKEN=TOKEN)
class AutoCloseEndpointTest(EventTestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
        cls.host = _make_user("auto_close_host")
        cls.helper = _make_user("auto_close_helper")

    def setUp(self) -> None:
        self.client = APIClient()

    def _event(self, state: EventState, *, staffed: bool = False) -> Event:
        start = tz.now() - timedelta(days=2)
        ev = Event.objects.create(
            organization=self.org,
            name=f"Auto Close {state}",
            scheduled_at=start,
            ends_at=start + timedelta(hours=3),
            state=state,
            created_by=self.admin,
        )
        if staffed:
            ev.host = self.host
            ev.save(update_fields=["host"])
            ev.helpers.add(self.helper)
        return ev

    def _post(self, pk: int, **extra: Any) -> Response:
        return self.client.post(
            f"/api/internal/events/{pk}/auto-close/", {}, format="json", **extra
        )

    def _entries(self, ev: Event) -> int:
        return ContributionEntry.objects.nocache().filter(event=ev).count()

    def test_requires_internal_token(self) -> None:
        ev = self._event(EventState.IN_PROGRESS)
        resp = self._post(ev.pk)
        self.assertIn(resp.status_code, (401, 403))
        ev.refresh_from_db()
        self.assertEqual(ev.state, EventState.IN_PROGRESS)

    def test_missing_event_404(self) -> None:
        resp = self._post(999999, **HEADERS)
        self.assertEqual(resp.status_code, 404)

    def test_unknown_state_400(self) -> None:
        ev = self._event(EventState.IN_PROGRESS)
        Event.objects.nocache().filter(pk=ev.pk).update(state="bogus")
        resp = self._post(ev.pk, **HEADERS)
        self.assertEqual(resp.status_code, 400)

    def test_terminal_returns_closed_false(self) -> None:
        for state in (EventState.COMPLETED, EventState.CANCELLED):
            ev = self._event(state)
            resp = self._post(ev.pk, **HEADERS)
            self.assertEqual(resp.status_code, 200)
            self.assertEqual(resp.json(), {"closed": False, "state": state.value})

    def test_never_started_is_cancelled(self) -> None:
        for state in (EventState.UPCOMING, EventState.SIGNUPS_OPEN):
            ev = self._event(state)
            resp = self._post(ev.pk, **HEADERS)
            self.assertEqual(resp.status_code, 200)
            self.assertEqual(
                resp.json(), {"closed": True, "state": EventState.CANCELLED.value}
            )
            ev.refresh_from_db()
            self.assertEqual(ev.state, EventState.CANCELLED)

    def test_started_is_completed_and_awards_staff(self) -> None:
        for state in (EventState.ROLL_CALL, EventState.IN_PROGRESS):
            ev = self._event(state, staffed=True)
            resp = self._post(ev.pk, **HEADERS)
            self.assertEqual(resp.status_code, 200)
            self.assertEqual(
                resp.json(), {"closed": True, "state": EventState.COMPLETED.value}
            )
            ev.refresh_from_db()
            self.assertEqual(ev.state, EventState.COMPLETED)
            self.assertIsNotNone(ev.contributions_awarded_at)
            kinds = set(
                ContributionEntry.objects.nocache()
                .filter(event=ev)
                .values_list("kind", flat=True)
            )
            self.assertEqual(
                kinds, {ContributionKind.EVENT_HOST, ContributionKind.EVENT_HELPER}
            )

    def test_auto_close_after_admin_complete_returns_closed_false(self) -> None:
        ev = self._event(EventState.IN_PROGRESS, staffed=True)
        first = close_event(
            ev, new_state=EventState.COMPLETED, source="admin", actor=self.admin
        )
        self.assertTrue(first.closed)
        before = self._entries(ev)
        self.assertEqual(before, 2)

        resp = self._post(ev.pk, **HEADERS)

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(
            resp.json(), {"closed": False, "state": EventState.COMPLETED.value}
        )
        self.assertEqual(self._entries(ev), before)

    def test_state_moved_after_read_is_not_cancelled(self) -> None:
        ev = self._event(EventState.SIGNUPS_OPEN, staffed=True)

        def move_then_close(event: Event, **kwargs: Any) -> CloseResult:
            Event.objects.nocache().filter(pk=event.pk).update(
                state=EventState.ROLL_CALL
            )
            return close_event(event, **kwargs)

        with patch("app.views.internal.close_event", side_effect=move_then_close):
            resp = self._post(ev.pk, **HEADERS)

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(
            resp.json(), {"closed": False, "state": EventState.ROLL_CALL.value}
        )
        ev.refresh_from_db()
        self.assertEqual(ev.state, EventState.ROLL_CALL)
        self.assertEqual(self._entries(ev), 0)


class StaleBeforeFilterTest(EventTestCase):
    def test_stale_before_uses_end_time(self) -> None:
        now = tz.now()
        cutoff = now - timedelta(days=1)
        multi_day = Event.objects.create(
            organization=self.org,
            name="Multi Day",
            scheduled_at=now - timedelta(days=3),
            ends_at=now + timedelta(days=1),
            state=EventState.IN_PROGRESS,
            created_by=self.admin,
        )
        no_end = Event.objects.create(
            organization=self.org,
            name="No End",
            scheduled_at=now - timedelta(days=3),
            state=EventState.IN_PROGRESS,
            created_by=self.admin,
        )
        ended = Event.objects.create(
            organization=self.org,
            name="Ended",
            scheduled_at=now - timedelta(days=4),
            ends_at=now - timedelta(days=2),
            state=EventState.IN_PROGRESS,
            created_by=self.admin,
        )

        resp = APIClient().get(
            "/api/events/",
            {
                "states": "roll_call,in_progress",
                "scheduled_before": cutoff.isoformat(),
                "stale_before": cutoff.isoformat(),
            },
        )

        self.assertEqual(resp.status_code, 200)
        ids = {row["id"] for row in resp.json()}
        self.assertNotIn(multi_day.pk, ids)
        self.assertIn(no_end.pk, ids)
        self.assertIn(ended.pk, ids)

    def test_malformed_stale_before_is_400(self) -> None:
        for value in ("garbage", "2026-13-40T00:00:00"):
            resp = APIClient().get("/api/events/", {"stale_before": value})
            self.assertEqual(resp.status_code, 400, value)
            self.assertIn("stale_before", resp.json())


@override_settings(INTERNAL_SERVICE_TOKEN=TOKEN)
class EventForTaskEndsAtTest(EventTestCase):
    def test_full_payload_carries_ends_at(self) -> None:
        start = tz.now() + timedelta(days=1)
        ev = Event.objects.create(
            organization=self.org,
            name="Ends At Payload",
            scheduled_at=start,
            ends_at=start + timedelta(days=2),
            created_by=self.admin,
        )
        resp = APIClient().get(f"/api/internal/events/{ev.pk}/full/", **HEADERS)
        self.assertEqual(resp.status_code, 200)
        parsed = EventTaskSchema.model_validate(resp.json())
        self.assertEqual(parsed.ends_at, ev.ends_at)


class AutoCloseClientTest(EventTestCase):
    @patch("app.internal_client._post")
    def test_returns_json_on_success(self, mock_post: MagicMock) -> None:
        mock_post.return_value = MagicMock(
            ok=True, json=lambda: {"closed": True, "state": "completed"}
        )
        self.assertEqual(auto_close_event(5), {"closed": True, "state": "completed"})
        mock_post.assert_called_once_with("/events/5/auto-close/", {})

    @patch("app.internal_client._post")
    def test_returns_none_on_error(self, mock_post: MagicMock) -> None:
        mock_post.return_value = MagicMock(ok=False, status_code=400)
        self.assertIsNone(auto_close_event(5))
        mock_post.return_value = None
        self.assertIsNone(auto_close_event(5))


class CleanupStaleEventsTaskTest(EventTestCase):
    @patch("events.tasks.log")
    @patch("events.tasks.auto_close_event")
    @patch("events.tasks.get_events_list")
    def test_sends_both_cutoffs_and_logs_by_result(
        self,
        mock_list: MagicMock,
        mock_close: MagicMock,
        mock_log: MagicMock,
    ) -> None:
        mock_list.side_effect = [[{"id": 1}, {"id": 2}], [{"id": 3}]]
        mock_close.side_effect = [
            {"closed": True, "state": "cancelled"},
            {"closed": False, "state": "completed"},
            None,
        ]

        cleanup_stale_events()

        self.assertEqual(mock_list.call_count, 2)
        states_seen = []
        for call in mock_list.call_args_list:
            kwargs = call.kwargs
            self.assertIn("scheduled_before", kwargs)
            self.assertEqual(kwargs["scheduled_before"], kwargs["stale_before"])
            cutoff = datetime.fromisoformat(kwargs["stale_before"])
            delta = datetime.now(dt_tz.utc) - cutoff
            self.assertAlmostEqual(delta.total_seconds(), 86400, delta=60)
            states_seen.append(kwargs["states"])
        self.assertEqual(
            states_seen, ["upcoming,signups_open", "roll_call,in_progress"]
        )
        self.assertEqual([c.args[0] for c in mock_close.call_args_list], [1, 2, 3])

        info_events = [c.args[0] for c in mock_log.info.call_args_list]
        warn_events = [c.args[0] for c in mock_log.warning.call_args_list]
        self.assertIn("event_auto_closed", info_events)
        self.assertIn("event_auto_close_skipped", info_events)
        self.assertIn("event_auto_close_failed", warn_events)
        for call in mock_log.info.call_args_list + mock_log.warning.call_args_list:
            if call.args[0].startswith("event_auto_close"):
                self.assertEqual(call.kwargs["system"], "events")
                self.assertEqual(call.kwargs["subsystem"], "tasks")

    @patch("events.tasks.log")
    @patch("events.tasks.auto_close_event")
    @patch("events.tasks.get_events_list")
    def test_error_on_one_event_does_not_stop_sweep(
        self,
        mock_list: MagicMock,
        mock_close: MagicMock,
        mock_log: MagicMock,
    ) -> None:
        mock_list.side_effect = [[{"id": 1}, {"id": 2}], [{"id": 3}]]
        mock_close.side_effect = [
            RuntimeError("boom"),
            {"closed": True, "state": "cancelled"},
            {"closed": True, "state": "completed"},
        ]

        summary = cleanup_stale_events()

        self.assertEqual([c.args[0] for c in mock_close.call_args_list], [1, 2, 3])
        self.assertEqual(summary, "Auto-closed 2, skipped 0, failed 1")
        mock_log.exception.assert_called_once()
        call = mock_log.exception.call_args
        self.assertEqual(call.args[0], "event_auto_close_error")
        self.assertEqual(call.kwargs["system"], "events")
        self.assertEqual(call.kwargs["subsystem"], "tasks")
        self.assertEqual(call.kwargs["event_id"], 1)


class DiscordScheduledEventEndTimeTest(EventTestCase):
    def _event(self, ends_at: datetime | None) -> EventTaskSchema:
        start = datetime.now(dt_tz.utc) + timedelta(days=1)
        return EventTaskSchema.model_validate(
            {
                "id": 12,
                "name": "Weekend Cup",
                "state": "upcoming",
                "scheduled_at": start.isoformat(),
                "ends_at": ends_at.isoformat() if ends_at else None,
                "organization_discord_server_id": "734185035623825559",
                "discord_create_event": True,
            }
        )

    def _payload(self, event: EventTaskSchema) -> dict[str, Any]:
        resp = MagicMock(status_code=200)
        resp.json.return_value = {"id": "999"}
        with (
            patch("events.tasks.get_event_for_task", return_value=event),
            patch(
                "events.tasks.get_or_create_discord_event",
                return_value=MagicMock(ok=True, json=lambda: {"id": 17}),
            ),
            patch("events.tasks.update_discord_event"),
            patch("events.tasks.create_message_log"),
            patch("events.tasks.create_event_log"),
            patch("events.tasks.req.post", return_value=resp) as mock_post,
        ):
            create_discord_scheduled_event(12)
        return mock_post.call_args.kwargs["json"]

    def test_uses_ends_at_when_set(self) -> None:
        ends = datetime.now(dt_tz.utc) + timedelta(days=3)
        event = self._event(ends)
        payload = self._payload(event)
        self.assertEqual(payload["scheduled_end_time"], event.ends_at.isoformat())

    def test_defaults_to_three_hours(self) -> None:
        event = self._event(None)
        payload = self._payload(event)
        self.assertEqual(
            payload["scheduled_end_time"],
            (event.scheduled_at + timedelta(hours=3)).isoformat(),
        )
