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
            {"interaction_id": None},
            countdown=settings.SIGNUP_POST.debounce_seconds,
        )
        self.edit.assert_not_called()

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
