from collections.abc import Callable

import redis
from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase, override_settings
from structlog.testing import capture_logs

from app.redis_client import get_redis_client, set_client_for_tests
from app.redis_keys import namespaced_key
from config.signup_post import SignupPostConfig
from events import signup_post_lock as lock

ENABLED = SignupPostConfig(disabled=False)
DISABLED = SignupPostConfig(disabled=True)


class FakeRedis:
    def __init__(self) -> None:
        self.data: dict[str, str] = {}
        self.ttls: dict[str, int | None] = {}

    def set(
        self, key: str, value: str, *, nx: bool = False, ex: int | None = None
    ) -> bool | None:
        if nx and key in self.data:
            return None
        self.data[key] = value
        self.ttls[key] = ex
        return True

    def get(self, key: str) -> str | None:
        return self.data.get(key)

    def delete(self, *keys: str) -> int:
        removed = 0
        for key in keys:
            if self.data.pop(key, None) is not None:
                removed += 1
        return removed

    def register_script(self, script: str) -> Callable[..., int]:
        """Stand-in for the compare-and-delete Lua script, run atomically."""
        assert "redis.call('del'" in script, script

        def run(keys: list[str], args: list[str]) -> int:
            if self.data.get(keys[0]) == args[0]:
                return self.delete(keys[0])
            return 0

        return run


class RacingRedis(FakeRedis):
    """A plain GET of the lock returns the old token, then the lock expires and
    another run takes it before the caller can act on the answer."""

    def __init__(self) -> None:
        super().__init__()
        self.deleted: list[str] = []

    def delete(self, *keys: str) -> int:
        self.deleted.extend(self.data[k] for k in keys if k in self.data)
        return super().delete(*keys)

    def get(self, key: str) -> str | None:
        value = super().get(key)
        if key == lock.lock_key(5):
            self.data[key] = "other-run"
        return value


class BrokenRedis:
    def __getattr__(self, name: str) -> object:
        def fail(*args: object, **kwargs: object) -> None:
            raise redis.ConnectionError("down")

        return fail


@override_settings(SIGNUP_POST=ENABLED)
class SignupPostLockTests(SimpleTestCase):
    def setUp(self) -> None:
        self.redis = FakeRedis()
        set_client_for_tests(self.redis)
        self.addCleanup(set_client_for_tests, None)

    def test_keys_use_namespaced_key(self) -> None:
        self.assertEqual(
            lock.pending_key(5), namespaced_key("events:signup_post:pending:5")
        )
        self.assertEqual(lock.lock_key(5), namespaced_key("events:signup_post:lock:5"))

    def test_mark_pending_once(self) -> None:
        self.assertTrue(lock.mark_pending(5))
        self.assertFalse(lock.mark_pending(5))
        self.assertEqual(
            self.redis.ttls[lock.pending_key(5)], ENABLED.pending_ttl_seconds
        )

    def test_clear_pending_allows_new_mark(self) -> None:
        lock.mark_pending(5)
        lock.clear_pending(5)
        self.assertTrue(lock.mark_pending(5))

    def test_lock_exclusive_and_release_by_token(self) -> None:
        token = lock.acquire_lock(5)
        self.assertIsNotNone(token)
        self.assertNotEqual(token, lock.FAIL_OPEN)
        self.assertEqual(self.redis.ttls[lock.lock_key(5)], ENABLED.lock_seconds)
        self.assertIsNone(lock.acquire_lock(5))
        self.assertIsNotNone(lock.acquire_lock(6))
        lock.release_lock(5, token)
        self.assertIsNotNone(lock.acquire_lock(5))

    def test_release_with_wrong_token_keeps_lock(self) -> None:
        token = lock.acquire_lock(5)
        lock.release_lock(5, "someone-else")
        self.assertEqual(self.redis.get(lock.lock_key(5)), token)
        self.assertIsNone(lock.acquire_lock(5))

    def test_release_does_not_delete_a_lock_taken_after_expiry(self) -> None:
        racing = RacingRedis()
        set_client_for_tests(racing)
        token = lock.acquire_lock(5)
        assert token is not None
        lock.release_lock(5, token)
        self.assertNotIn("other-run", racing.deleted)

    def test_redis_error_fails_open_and_logs(self) -> None:
        set_client_for_tests(BrokenRedis())
        with capture_logs() as logs:
            self.assertEqual(lock.acquire_lock(5), lock.FAIL_OPEN)
            self.assertTrue(lock.mark_pending(5))
            lock.clear_pending(5)
            lock.release_lock(5, "token")
        events = [e for e in logs if e["event"] == "signup_post_lock_unavailable"]
        self.assertEqual(len(events), 4)
        for entry in events:
            self.assertEqual(entry["log_level"], "warning")
            self.assertEqual(entry["system"], "discord")
            self.assertIn(entry["subsystem"], ("dispatch", "celery"))
            self.assertEqual(entry["event_id"], 5)
            self.assertEqual(entry["tags_csv"], "events,signup")

    def test_release_fail_open_token_is_noop(self) -> None:
        set_client_for_tests(BrokenRedis())
        with capture_logs() as logs:
            lock.release_lock(5, lock.FAIL_OPEN)
        self.assertEqual(logs, [])


@override_settings(SIGNUP_POST=ENABLED)
class SignupPostLockRealRedisTests(SimpleTestCase):
    """The release script runs on the test Redis, under this run's namespace."""

    def setUp(self) -> None:
        set_client_for_tests(None)
        self.addCleanup(get_redis_client().delete, lock.lock_key(987654))

    def test_release_script_deletes_only_own_token(self) -> None:
        client = get_redis_client()
        token = lock.acquire_lock(987654)
        assert token is not None
        lock.release_lock(987654, "someone-else")
        self.assertEqual(client.get(lock.lock_key(987654)), token)
        lock.release_lock(987654, token)
        self.assertIsNone(client.get(lock.lock_key(987654)))


@override_settings(SIGNUP_POST=DISABLED)
class SignupPostLockDisabledTests(SimpleTestCase):
    def setUp(self) -> None:
        self.redis = FakeRedis()
        set_client_for_tests(self.redis)
        self.addCleanup(set_client_for_tests, None)

    def test_disabled_always_acquires(self) -> None:
        self.assertTrue(lock.mark_pending(5))
        self.assertTrue(lock.mark_pending(5))
        self.assertEqual(lock.acquire_lock(5), lock.FAIL_OPEN)
        self.assertEqual(lock.acquire_lock(5), lock.FAIL_OPEN)
        self.assertEqual(self.redis.data, {})


class SignupPostConfigTests(SimpleTestCase):
    def test_defaults(self) -> None:
        config = SignupPostConfig.from_env(environ={})
        self.assertEqual(config, SignupPostConfig())
        self.assertEqual(config.debounce_seconds, 2)
        self.assertEqual(config.lock_seconds, 90)
        self.assertFalse(config.disabled)
        self.assertEqual(config.read_retries, 3)
        self.assertEqual(config.pending_ttl_seconds, 102)

    def test_from_env_parses_mapping(self) -> None:
        config = SignupPostConfig.from_env(
            environ={
                "SIGNUP_POST_DEBOUNCE_SECONDS": "5",
                "SIGNUP_POST_LOCK_SECONDS": "30",
                "SIGNUP_POST_DISABLED": "true",
                "SIGNUP_POST_READ_RETRIES": "0",
            }
        )
        self.assertEqual(
            config,
            SignupPostConfig(
                debounce_seconds=5, lock_seconds=30, disabled=True, read_retries=0
            ),
        )
        self.assertEqual(config.pending_ttl_seconds, 45)

    def test_zero_debounce_allowed(self) -> None:
        config = SignupPostConfig.from_env(
            environ={"SIGNUP_POST_DEBOUNCE_SECONDS": "0"}
        )
        self.assertEqual(config.debounce_seconds, 0)

    def test_disabled_default_and_explicit_false(self) -> None:
        self.assertTrue(
            SignupPostConfig.from_env(environ={}, disabled_default=True).disabled
        )
        self.assertFalse(
            SignupPostConfig.from_env(
                environ={"SIGNUP_POST_DISABLED": "false"}, disabled_default=True
            ).disabled
        )

    def test_disable_cache_disables(self) -> None:
        self.assertTrue(
            SignupPostConfig.from_env(environ={"DISABLE_CACHE": "1"}).disabled
        )

    def test_invalid_values_rejected(self) -> None:
        for env in (
            {"SIGNUP_POST_LOCK_SECONDS": "abc"},
            {"SIGNUP_POST_LOCK_SECONDS": "0"},
            {"SIGNUP_POST_DEBOUNCE_SECONDS": "-1"},
            {"SIGNUP_POST_READ_RETRIES": "-1"},
        ):
            with self.subTest(env=env), self.assertRaises(ImproperlyConfigured):
                SignupPostConfig.from_env(environ=env)
