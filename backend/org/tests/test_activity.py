from unittest import mock

from django.core.cache import cache
from django.http import HttpRequest
from django.test import TestCase, override_settings
from rest_framework.request import ForcedAuthentication, Request
from rest_framework.test import APIRequestFactory
from structlog.testing import capture_logs

from app.auth import InternalServiceAuth, InternalServiceUser
from app.models import CustomUser, Organization
from org import activity
from org.activity import (
    ORG_ACTIVITY_TTL_S,
    active_org_ids,
    activity_tracking_enabled,
    enqueue_org_name_sync,
    guild_sync_lock,
    release_guild_sync_lock,
    touch_org_activity,
)

LOCMEM = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "test_activity",
    }
}
DUMMY = {"default": {"BACKEND": "django.core.cache.backends.dummy.DummyCache"}}

APPLY = "org.activity.sync_org_discord_names.apply_async"


def _request(user: object, authenticator: object | None = None) -> Request:
    auth = authenticator or ForcedAuthentication(user, None)
    return Request(APIRequestFactory().get("/"), authenticators=(auth,))


@override_settings(CACHES=LOCMEM)
class TouchOrgActivityTest(TestCase):
    def setUp(self) -> None:
        cache.clear()
        self.user = CustomUser.objects.create_user(username="dragon", password="x")
        self.org = Organization.objects.create(name="DTX", discord_server_id="111")
        self.org_shared = Organization.objects.create(
            name="DTX2", discord_server_id="111"
        )

    def _touch(self, org_id: int | None, **kwargs: object) -> None:
        touch_org_activity(_request(self.user), org_id, **kwargs)

    def test_first_touch_enqueues_on_commit(self) -> None:
        with mock.patch(APPLY) as apply_async:
            with self.captureOnCommitCallbacks(execute=False) as callbacks:
                self._touch(self.org.pk)
            apply_async.assert_not_called()
            for callback in callbacks:
                callback()
        apply_async.assert_called_once()
        self.assertEqual(apply_async.call_args.kwargs["args"], [self.org.pk])
        self.assertIs(apply_async.call_args.kwargs["retry"], False)
        self.assertIn("connection", apply_async.call_args.kwargs)
        self.assertIsNotNone(cache.get(f"org_activity_{self.org.pk}"))

    def test_anonymous_request_ignored(self) -> None:
        request = Request(APIRequestFactory().get("/"))
        with mock.patch(APPLY) as apply_async:
            with self.captureOnCommitCallbacks(execute=True):
                touch_org_activity(request, self.org.pk)
        apply_async.assert_not_called()
        self.assertIsNone(cache.get(f"org_activity_{self.org.pk}"))

    def test_internal_authenticator_ignored(self) -> None:
        auth = mock.Mock(spec=InternalServiceAuth)
        auth.authenticate.return_value = (self.user, None)
        with mock.patch(APPLY) as apply_async:
            with self.captureOnCommitCallbacks(execute=True):
                touch_org_activity(_request(self.user, auth), self.org.pk)
        apply_async.assert_not_called()
        self.assertIsNone(cache.get(f"org_activity_{self.org.pk}"))

    def test_internal_service_user_ignored(self) -> None:
        request = HttpRequest()
        request.user = InternalServiceUser()
        with mock.patch(APPLY) as apply_async:
            with self.captureOnCommitCallbacks(execute=True):
                touch_org_activity(request, self.org.pk)  # type: ignore[arg-type]
        apply_async.assert_not_called()
        self.assertIsNone(cache.get(f"org_activity_{self.org.pk}"))

    def test_plain_http_request_does_not_raise(self) -> None:
        request = HttpRequest()
        request.user = self.user
        with mock.patch(APPLY):
            with self.captureOnCommitCallbacks(execute=True):
                self.assertIsNone(touch_org_activity(request, self.org.pk))  # type: ignore[arg-type]

    def test_second_touch_slides_ttl_without_enqueue(self) -> None:
        with mock.patch(APPLY) as apply_async:
            with self.captureOnCommitCallbacks(execute=True):
                self._touch(self.org.pk)
            apply_async.reset_mock()
            with mock.patch.object(cache, "touch", wraps=cache.touch) as touch:
                with self.captureOnCommitCallbacks(execute=True):
                    self._touch(self.org.pk)
        apply_async.assert_not_called()
        touch.assert_called_once_with(f"org_activity_{self.org.pk}", ORG_ACTIVITY_TTL_S)

    def test_orgs_sharing_guild_enqueue_once(self) -> None:
        with mock.patch(APPLY) as apply_async:
            with self.captureOnCommitCallbacks(execute=True):
                self._touch(self.org.pk)
                self._touch(self.org_shared.pk)
        apply_async.assert_called_once()

    def test_explicit_guild_id_skips_lookup(self) -> None:
        with mock.patch(APPLY) as apply_async:
            with self.captureOnCommitCallbacks(execute=True):
                with self.assertNumQueries(0):
                    self._touch(self.org.pk, guild_id="111")
        apply_async.assert_called_once()

    def test_org_without_guild_never_enqueues(self) -> None:
        none_org = Organization.objects.create(name="NoGuild", discord_server_id=None)
        blank_org = Organization.objects.create(name="Blank", discord_server_id="")
        with mock.patch(APPLY) as apply_async:
            with self.captureOnCommitCallbacks(execute=True):
                self._touch(none_org.pk)
                self._touch(blank_org.pk)
                self._touch(self.org.pk, guild_id="")
        apply_async.assert_not_called()
        self.assertIsNone(cache.get("discord_name_sync_pending_"))

    def test_deleted_or_missing_org_does_not_raise(self) -> None:
        gone = Organization.objects.create(name="Gone", discord_server_id="333")
        gone_pk = gone.pk
        gone.delete()
        with mock.patch(APPLY) as apply_async:
            with self.captureOnCommitCallbacks(execute=True):
                self.assertIsNone(self._touch(gone_pk))
                self.assertIsNone(self._touch(None))
        apply_async.assert_not_called()

    @override_settings(CACHES=DUMMY)
    def test_dummy_cache_is_noop(self) -> None:
        self.assertFalse(activity_tracking_enabled())
        with (
            mock.patch(APPLY) as apply_async,
            mock.patch.object(activity, "cache") as fake_cache,
        ):
            with self.captureOnCommitCallbacks(execute=True):
                self._touch(self.org.pk)
        apply_async.assert_not_called()
        self.assertEqual(fake_cache.mock_calls, [])

    @override_settings(CACHEOPS_ENABLED=False)
    def test_cacheops_disabled_is_noop(self) -> None:
        self.assertFalse(activity_tracking_enabled())
        with (
            mock.patch(APPLY) as apply_async,
            mock.patch.object(activity, "cache") as fake_cache,
        ):
            with self.captureOnCommitCallbacks(execute=True):
                self._touch(self.org.pk)
        apply_async.assert_not_called()
        self.assertEqual(fake_cache.mock_calls, [])

    def test_prod_shape_settings_enabled(self) -> None:
        self.assertTrue(activity_tracking_enabled())
        with mock.patch(APPLY) as apply_async:
            with self.captureOnCommitCallbacks(execute=True):
                self._touch(self.org.pk)
        apply_async.assert_called_once()

    def test_broker_unreachable_swallowed_and_logged(self) -> None:
        with (
            mock.patch.object(
                activity.sync_org_discord_names.app,
                "connection_for_write",
                side_effect=OSError("down"),
            ) as conn,
            capture_logs() as logs,
        ):
            with self.captureOnCommitCallbacks(execute=True):
                self.assertIsNone(self._touch(self.org.pk))
        self.assertEqual(conn.call_args.kwargs["connect_timeout"], 0.5)
        transport = conn.call_args.kwargs["transport_options"]
        self.assertEqual(transport["socket_connect_timeout"], 0.5)
        self.assertEqual(transport["socket_timeout"], 0.5)
        self.assertIn("name_sync_enqueue_failed", [e["event"] for e in logs])

    def test_apply_async_raising_swallowed(self) -> None:
        with mock.patch(APPLY, side_effect=RuntimeError("boom")):
            with self.captureOnCommitCallbacks(execute=True):
                self.assertIsNone(self._touch(self.org.pk))

    def test_cache_add_raising_swallowed(self) -> None:
        with (
            mock.patch(APPLY) as apply_async,
            mock.patch.object(cache, "add", side_effect=ConnectionError("redis down")),
        ):
            with self.captureOnCommitCallbacks(execute=True):
                self.assertIsNone(self._touch(self.org.pk))
        apply_async.assert_not_called()


@override_settings(CACHES=LOCMEM)
class GuildLockAndActiveOrgsTest(TestCase):
    def setUp(self) -> None:
        cache.clear()

    def test_guild_sync_lock_round_trip(self) -> None:
        self.assertTrue(guild_sync_lock("111"))
        self.assertFalse(guild_sync_lock("111"))
        self.assertTrue(guild_sync_lock("222"))
        release_guild_sync_lock("111")
        self.assertTrue(guild_sync_lock("111"))

    def test_active_org_ids_returns_only_touched(self) -> None:
        user = CustomUser.objects.create_user(username="u", password="x")
        a = Organization.objects.create(name="A", discord_server_id="111")
        b = Organization.objects.create(name="B", discord_server_id="222")
        with mock.patch(APPLY):
            with self.captureOnCommitCallbacks(execute=True):
                touch_org_activity(_request(user), a.pk)
        self.assertEqual(active_org_ids([a.pk, b.pk]), {a.pk})
        self.assertEqual(active_org_ids([]), set())

    def test_enqueue_outside_transaction_hook_publishes(self) -> None:
        with mock.patch(APPLY) as apply_async:
            with self.captureOnCommitCallbacks(execute=True):
                enqueue_org_name_sync(7)
        self.assertEqual(apply_async.call_args.kwargs["args"], [7])
