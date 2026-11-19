import json
from collections.abc import Callable
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import redis
from celery.exceptions import Retry
from django.conf import settings
from django.test import override_settings
from structlog.testing import capture_logs

from app.internal_client import InternalAPIUnavailable
from app.redis_client import set_client_for_tests
from config.signup_post import SignupPostConfig
from events import signup_post_lock
from events.constants import SignupStatus
from events.discord.dispatch import notify_signup_changed
from events.models import Event, EventSignup
from events.tasks import send_signup_update
from events.tests._internal_client_orm import DiscordTestMixin, _get_event_signups_orm
from events.tests.base import EventTestCase


class FakePipeline:
    def __init__(self, client: "FakeRedis") -> None:
        self.client = client
        self.calls: list[tuple[str, tuple[str, ...]]] = []

    def delete(self, *keys: str) -> "FakePipeline":
        self.calls.append(("delete", keys))
        return self

    def getdel(self, key: str) -> "FakePipeline":
        self.calls.append(("getdel", (key,)))
        return self

    def execute(self) -> list[object]:
        return [getattr(self.client, name)(*args) for name, args in self.calls]


class FakeRedis:
    def __init__(self) -> None:
        self.data: dict[str, str] = {}

    def set(
        self, key: str, value: str, *, nx: bool = False, ex: int | None = None
    ) -> bool | None:
        if nx and key in self.data:
            return None
        self.data[key] = value
        return True

    def get(self, key: str) -> str | None:
        return self.data.get(key)

    def delete(self, *keys: str) -> int:
        return sum(1 for key in keys if self.data.pop(key, None) is not None)

    def getdel(self, key: str) -> str | None:
        return self.data.pop(key, None)

    def pipeline(self) -> FakePipeline:
        return FakePipeline(self)

    def register_script(self, script: str) -> Callable[..., int]:
        def run(keys: list[str], args: list[str]) -> int:
            if self.data.get(keys[0]) == args[0]:
                return self.delete(keys[0])
            return 0

        return run


class BrokenRedis:
    def __getattr__(self, name: str) -> object:
        def fail(*args: object, **kwargs: object) -> None:
            raise redis.ConnectionError("down")

        return fail


def _posted_state() -> SimpleNamespace:
    return SimpleNamespace(
        signup_posted=True,
        signup_message_id="555",
        signup_channel_type="text",
        signup_channel_id="777",
        signup_thread_id=None,
    )


@override_settings(SIGNUP_POST=SignupPostConfig(disabled=False))
class SignupPostSerialisationTest(DiscordTestMixin, EventTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.redis = FakeRedis()
        set_client_for_tests(self.redis)
        self.addCleanup(set_client_for_tests, None)
        self.post_event = self.make_event(
            discord_announcement=True,
            discord_announcement_channel_id="1482767177063858216",
        )
        self.pk = self.post_event.pk
        for target, kwargs in (
            ("events.tasks.send_signup_update.apply_async", {}),
            ("events.tasks.sync_edit_message", {"return_value": {"id": "555"}}),
            ("events.tasks.get_discord_event_state", {"return_value": _posted_state()}),
        ):
            patcher = patch(target, **kwargs)
            mock = patcher.start()
            self.addCleanup(patcher.stop)
            if target.endswith("apply_async"):
                self.apply_async: MagicMock = mock
            elif target.endswith("sync_edit_message"):
                self.edit: MagicMock = mock

    def _add_signup(self, nickname: str) -> None:
        user = self.make_user()
        user.nickname = nickname
        user.save()
        EventSignup.objects.create(
            event=self.post_event, user=user, status=SignupStatus.TENTATIVE
        )

    def test_burst_enqueues_one_task(self) -> None:
        for _ in range(5):
            notify_signup_changed(self.post_event)

        self.apply_async.assert_called_once_with(
            (self.pk,),
            {"interaction_id": None},
            countdown=settings.SIGNUP_POST.debounce_seconds,
        )

    def test_second_run_reschedules_while_locked(self) -> None:
        self.assertIsNotNone(signup_post_lock.acquire_lock(self.pk))

        send_signup_update(self.pk)

        self.apply_async.assert_called_once_with(
            (self.pk,),
            {"interaction_id": None, "busy_passes": 1},
            countdown=settings.SIGNUP_POST.retry_seconds,
        )
        self.edit.assert_not_called()

    @override_settings(SIGNUP_POST=SignupPostConfig(disabled=False, debounce_seconds=0))
    def test_zero_debounce_still_waits_before_busy_reschedule(self) -> None:
        self.assertIsNotNone(signup_post_lock.acquire_lock(self.pk))

        send_signup_update(self.pk)

        self.assertGreaterEqual(self.apply_async.call_args.kwargs["countdown"], 1)

    @override_settings(SIGNUP_POST=SignupPostConfig(disabled=False, debounce_seconds=0))
    def test_zero_debounce_still_waits_before_read_retry(self) -> None:
        with (
            patch(
                "events.discord.embeds.get_event_signups",
                side_effect=InternalAPIUnavailable("signups"),
            ),
            patch.object(send_signup_update, "retry", side_effect=Retry()) as retry,
            self.assertRaises(Retry),
        ):
            send_signup_update(self.pk)

        self.assertGreaterEqual(retry.call_args.kwargs["countdown"], 1)

    def test_busy_lock_warns_once_after_configured_passes(self) -> None:
        self.assertIsNotNone(signup_post_lock.acquire_lock(self.pk))
        threshold = settings.SIGNUP_POST.busy_warn_passes

        with capture_logs() as logs:
            for passes in range(threshold + 2):
                send_signup_update(self.pk, busy_passes=passes)

        stalled = [e for e in logs if e["event"] == "signup_update_lock_stalled"]
        self.assertEqual(len(stalled), 1)
        self.assertEqual(stalled[0]["log_level"], "warning")
        self.assertEqual(stalled[0]["busy_passes"], threshold)
        self.assertEqual(stalled[0]["system"], "discord")
        busy = [e for e in logs if e["event"] == "signup_update_lock_busy"]
        self.assertEqual(len(busy), threshold + 2)
        self.assertTrue(all(e["log_level"] == "debug" for e in busy))

    def test_overlapping_run_reschedules_and_final_patch_has_latest_list(
        self,
    ) -> None:
        self._add_signup("FirstSigner")

        def read_while_b_runs(event_id: int) -> list:
            self._add_signup("MidRunSigner")
            send_signup_update(self.pk)
            return _get_event_signups_orm(event_id)

        with patch(
            "events.discord.embeds.get_event_signups", side_effect=read_while_b_runs
        ):
            send_signup_update(self.pk)

        self.assertEqual(self.edit.call_count, 1)
        self.apply_async.assert_called_once()
        args, kwargs = self.apply_async.call_args.args
        self.assertEqual(args, (self.pk,))

        send_signup_update(*args, **kwargs)

        self.assertEqual(self.edit.call_count, 2)
        last_payload = json.dumps(self.edit.call_args.kwargs["embed"])
        self.assertIn("MidRunSigner", last_payload)
        self.assertIn("FirstSigner", last_payload)

    def test_change_during_run_enqueues_new_run(self) -> None:
        notify_signup_changed(self.post_event)
        self.apply_async.reset_mock()

        def read_while_changing(event_id: int) -> list:
            notify_signup_changed(self.post_event)
            return _get_event_signups_orm(event_id)

        with patch(
            "events.discord.embeds.get_event_signups", side_effect=read_while_changing
        ):
            send_signup_update(self.pk)

        self.apply_async.assert_called_once()
        self.edit.assert_called_once()

    def test_last_patch_has_latest_list(self) -> None:
        self._add_signup("FirstSigner")
        send_signup_update(self.pk)
        self._add_signup("LatestSigner")
        send_signup_update(self.pk)

        self.assertEqual(self.edit.call_count, 2)
        last_payload = json.dumps(self.edit.call_args.kwargs["embed"])
        self.assertIn("LatestSigner", last_payload)
        self.assertIn("FirstSigner", last_payload)

    def test_read_error_retries_without_failed_log(self) -> None:
        with (
            patch(
                "events.discord.embeds.get_event_signups",
                side_effect=InternalAPIUnavailable("signups"),
            ),
            capture_logs() as logs,
            self.assertRaises(Retry),
        ):
            send_signup_update(self.pk)

        self.edit.assert_not_called()
        events = [entry["event"] for entry in logs]
        self.assertIn("celery_task_retry", events)
        unavailable = next(e for e in logs if e["event"] == "signup_list_unavailable")
        self.assertFalse(unavailable["retries_exhausted"])
        self.assertEqual(unavailable["attempt"], 0)
        self.assertNotIn("celery_task_failed", events)
        self.assertNotIn("celery_task_finished", events)
        self.assertNotIn(signup_post_lock.lock_key(self.pk), self.redis.data)
        self.assertIn(signup_post_lock.pending_key(self.pk), self.redis.data)

    def test_read_error_gives_up_after_configured_retries(self) -> None:
        send_signup_update.push_request(retries=settings.SIGNUP_POST.read_retries)
        self.addCleanup(send_signup_update.pop_request)
        with (
            patch(
                "events.discord.embeds.get_event_signups",
                side_effect=InternalAPIUnavailable("signups"),
            ),
            capture_logs() as logs,
        ):
            send_signup_update.run(self.pk)

        self.edit.assert_not_called()
        events = [entry["event"] for entry in logs]
        self.assertIn("signup_list_unavailable", events)
        unavailable = next(e for e in logs if e["event"] == "signup_list_unavailable")
        self.assertTrue(unavailable["retries_exhausted"])
        self.assertEqual(unavailable["attempt"], settings.SIGNUP_POST.read_retries)
        self.assertNotIn("celery_task_failed", events)
        self.assertNotIn(signup_post_lock.lock_key(self.pk), self.redis.data)
        self.assertNotIn(signup_post_lock.pending_key(self.pk), self.redis.data)

    def test_redis_error_falls_back_to_apply_async(self) -> None:
        set_client_for_tests(BrokenRedis())

        with capture_logs() as logs:
            notify_signup_changed(self.post_event)

        self.apply_async.assert_called_once_with(
            (self.pk,),
            {"interaction_id": None},
            countdown=settings.SIGNUP_POST.debounce_seconds,
        )
        self.assertIn(
            "signup_post_lock_unavailable", [entry["event"] for entry in logs]
        )

    def test_deleted_event_releases_lock_and_pending(self) -> None:
        notify_signup_changed(self.post_event)
        Event.objects.filter(pk=self.pk).delete()

        send_signup_update(self.pk)

        self.edit.assert_not_called()
        self.assertNotIn(signup_post_lock.pending_key(self.pk), self.redis.data)
        self.assertIsNotNone(signup_post_lock.acquire_lock(self.pk))

    def _drain_queued_runs(self) -> None:
        while self.apply_async.call_args_list:
            call = self.apply_async.call_args_list.pop(0)
            args, kwargs = call.args
            send_signup_update(*args, **kwargs)

    def _applied(self, logs: list[dict]) -> list[dict]:
        return [e for e in logs if e["event"] == "signup_post_edit_applied"]

    def test_burst_of_changes_edits_once_with_final_list(self) -> None:
        for n in range(30):
            self._add_signup(f"Burst{n:02d}")
            notify_signup_changed(self.post_event)

        self._drain_queued_runs()

        self.assertLessEqual(self.edit.call_count, 2)
        last_payload = json.dumps(self.edit.call_args.kwargs["embed"])
        self.assertIn("Burst29", last_payload)

    def test_edit_applied_logs_lag_from_oldest_change(self) -> None:
        with patch.object(signup_post_lock, "now_ms", side_effect=[1_000, 5_000]):
            notify_signup_changed(self.post_event)
            notify_signup_changed(self.post_event)

        with (
            patch("events.tasks.now_ms", return_value=12_500),
            capture_logs() as logs,
        ):
            send_signup_update(self.pk)

        [applied] = self._applied(logs)
        self.assertEqual(applied["lag_ms"], 11_500)
        self.assertEqual(applied["log_level"], "warning")
        self.assertEqual(applied["system"], "discord")
        self.assertEqual(applied["subsystem"], "celery")
        self.assertEqual(applied["event_id"], self.pk)
        self.assertNotIn(signup_post_lock.dirty_key(self.pk), self.redis.data)

    def test_edit_applied_within_threshold_logs_info(self) -> None:
        with patch.object(signup_post_lock, "now_ms", return_value=1_000):
            notify_signup_changed(self.post_event)

        with (
            patch("events.tasks.now_ms", return_value=11_000),
            capture_logs() as logs,
        ):
            send_signup_update(self.pk)

        [applied] = self._applied(logs)
        self.assertEqual(applied["lag_ms"], 10_000)
        self.assertEqual(applied["log_level"], "info")

    def test_edit_without_dirty_time_logs_no_lag(self) -> None:
        with capture_logs() as logs:
            send_signup_update(self.pk)

        [applied] = self._applied(logs)
        self.assertIsNone(applied["lag_ms"])
        self.assertEqual(applied["log_level"], "info")

    def test_change_during_render_is_timed_by_the_trailing_run(self) -> None:
        with patch.object(signup_post_lock, "now_ms", return_value=1_000):
            notify_signup_changed(self.post_event)
        self.apply_async.reset_mock()

        def read_while_changing(event_id: int) -> list:
            with patch.object(signup_post_lock, "now_ms", return_value=2_000):
                notify_signup_changed(self.post_event)
            return _get_event_signups_orm(event_id)

        with (
            patch(
                "events.discord.embeds.get_event_signups",
                side_effect=read_while_changing,
            ),
            patch("events.tasks.now_ms", return_value=4_000),
            capture_logs() as first,
        ):
            send_signup_update(self.pk)
        with (
            patch("events.tasks.now_ms", return_value=4_500),
            capture_logs() as trailing,
        ):
            self._drain_queued_runs()

        self.assertEqual(self.edit.call_count, 2)
        self.assertEqual(self._applied(first)[0]["lag_ms"], 3_000)
        self.assertEqual(self._applied(trailing)[0]["lag_ms"], 2_500)

    def test_read_retry_keeps_dirty_time(self) -> None:
        with patch.object(signup_post_lock, "now_ms", return_value=1_000):
            notify_signup_changed(self.post_event)

        with (
            patch(
                "events.discord.embeds.get_event_signups",
                side_effect=InternalAPIUnavailable("signups"),
            ),
            patch.object(send_signup_update, "retry", side_effect=Retry()),
            self.assertRaises(Retry),
        ):
            send_signup_update(self.pk)

        self.assertEqual(self.redis.data[signup_post_lock.dirty_key(self.pk)], "1000")

    def test_failed_edit_keeps_dirty_time_and_logs_nothing_applied(self) -> None:
        with patch.object(signup_post_lock, "now_ms", return_value=1_000):
            notify_signup_changed(self.post_event)
        self.edit.return_value = None

        with capture_logs() as logs:
            send_signup_update(self.pk)

        self.assertEqual(self._applied(logs), [])
        self.assertEqual(self.redis.data[signup_post_lock.dirty_key(self.pk)], "1000")
