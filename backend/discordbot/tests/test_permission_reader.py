import threading
import time
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import replace
from datetime import timedelta
from typing import Any
from unittest.mock import patch

import requests
from django.core.cache import cache
from django.test import SimpleTestCase, override_settings
from django.utils import timezone

from discordbot.permissions.reader import (
    FixtureSource,
    RestSource,
    SnapshotReader,
    source_for,
)
from discordbot.permissions.schemas import ActionKind as A
from discordbot.permissions.schemas import (
    Observation,
    PermissionCheckIn,
    ResolvedCheckInput,
)
from discordbot.permissions.service import preview_checks, run_checks

G = "900000000000000001"
B = "900000000000000002"
C = "900000000000000003"
T = "900000000000000004"
E = "900000000000000005"
M = "900000000000000006"


def scenario() -> dict[str, Any]:
    return {
        "/users/@me": {"id": B},
        f"/guilds/{G}": {
            "id": G,
            "owner_id": E,
            "roles": [
                {
                    "id": G,
                    "permissions": "17592253237256",
                    "mentionable": False,
                    "managed": False,
                }
            ],
        },
        f"/guilds/{G}/members/{B}": {
            "user": {"id": B},
            "roles": [],
            "communication_disabled_until": None,
        },
        f"/guilds/{G}/channels": [
            {"id": C, "type": 0, "name": "updates", "permission_overwrites": []}
        ],
        f"/channels/{T}": {
            "id": T,
            "guild_id": G,
            "type": 12,
            "name": "private",
            "parent_id": C,
            "thread_metadata": {"archived": False, "locked": False},
        },
        f"/channels/{T}/thread-members/{B}": {"id": T, "user_id": B},
        f"/channels/{T}/messages/{M}": {"id": M, "channel_id": T, "author": {"id": B}},
        f"/guilds/{G}/scheduled-events/{E}": {"id": E, "guild_id": G, "creator_id": B},
    }


class RecordingSource(FixtureSource):
    def __init__(self, data: dict[str, Any]) -> None:
        super().__init__(data)
        self.calls: list[str] = []

    def get(self, path: str, timeout: float) -> tuple[int, Any, dict[str, str]]:
        self.calls.append(path)
        if not 0 < timeout <= 5:
            raise AssertionError(timeout)
        return super().get(path, timeout)


def check(
    action: A = A.ANNOUNCEMENT,
    channel: str | None = C,
    key: str = "post",
    **kwargs: Any,
) -> ResolvedCheckInput:
    return ResolvedCheckInput(
        key=key,
        action=action,
        channel_id=channel,
        destination_source="configured",
        **kwargs,
    )


@override_settings(
    DISCORD_BOT_TOKEN="synthetic",
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}},
)
class ReaderTests(SimpleTestCase):
    def setUp(self) -> None:
        cache.clear()
        self.data = scenario()
        self.source = RecordingSource(self.data)

    def run_checks(
        self, checks: list[ResolvedCheckInput], refresh: bool = False
    ) -> Any:
        with patch(
            "discordbot.permissions.service.source_for", return_value=self.source
        ):
            return run_checks(G, checks, refresh=refresh)

    def test_fetches_exact_get_paths(self) -> None:
        result = self.run_checks([check(), check(key="duplicate")])
        self.assertEqual(result.checks[0].status, "verified")
        self.assertCountEqual(
            self.source.calls,
            [
                "/users/@me",
                f"/guilds/{G}",
                f"/guilds/{G}/members/{B}",
                f"/guilds/{G}/channels",
            ],
        )

    def test_never_issues_non_get(self) -> None:
        with patch.multiple(
            requests,
            post=lambda *a, **k: self.fail("POST"),
            put=lambda *a, **k: self.fail("PUT"),
            patch=lambda *a, **k: self.fail("PATCH"),
            delete=lambda *a, **k: self.fail("DELETE"),
        ):
            self.assertEqual(self.run_checks([check()]).checks[0].status, "verified")

    @override_settings(DISCORD_BOT_TOKEN="")
    def test_missing_token_no_http(self) -> None:
        with patch("requests.get", side_effect=AssertionError("HTTP")):
            self.assertEqual(
                SnapshotReader(RestSource()).guild_bundle(G, False).error,
                "credential_unavailable",
            )

    def test_status_mapping(self) -> None:
        for status, reason in [
            (401, "credential_unavailable"),
            (403, "forbidden_read"),
            (404, "bot_unavailable"),
            (429, "rate_limited"),
            (503, "network_error"),
        ]:
            with self.subTest(status=status):
                cache.clear()
                self.data["/users/@me"] = {"status": status, "body": {}}
                self.assertEqual(self.run_checks([check()]).checks[0].reason, reason)

    def test_429_returns_retry_after_without_sleep(self) -> None:
        self.data["/users/@me"] = {
            "status": 429,
            "body": {"retry_after": 2.2},
            "headers": {},
        }
        with patch("time.sleep", side_effect=AssertionError("sleep")):
            self.assertEqual(
                self.run_checks([check()]).checks[0].retry_after_seconds, 3
            )

    def test_timeout_and_bad_json(self) -> None:
        for exc, reason in [
            (requests.Timeout(), "network_error"),
            (ValueError(), "malformed_snapshot"),
            (
                requests.exceptions.JSONDecodeError("invalid JSON", "", 0),
                "malformed_snapshot",
            ),
        ]:
            with self.subTest(reason=reason):
                cache.clear()
                with patch.object(self.source, "get", side_effect=exc):
                    self.assertEqual(
                        self.run_checks([check()]).checks[0].reason, reason
                    )

    def test_budget_exhaustion_marks_remaining_unknown(self) -> None:
        reader = SnapshotReader(self.source, budget_s=0)
        self.assertEqual(reader.guild_bundle(G, False).error, "network_error")
        self.assertEqual(self.source.calls, [])

    def test_cache_partitioned_by_guild_and_token(self) -> None:
        first = SnapshotReader(RestSource())
        with patch("requests.get") as get:
            get.return_value.status_code = 200
            get.return_value.json.side_effect = [
                self.data["/users/@me"],
                self.data[f"/guilds/{G}"],
                self.data[f"/guilds/{G}/members/{B}"],
            ]
            self.assertIsNone(first.guild_bundle(G, False).error)
        with (
            override_settings(DISCORD_BOT_TOKEN="another-synthetic"),
            patch("requests.get", side_effect=requests.Timeout),
        ):
            self.assertEqual(
                SnapshotReader(RestSource()).guild_bundle(G, False).error,
                "network_error",
            )
        self.assertEqual(
            SnapshotReader(self.source).guild_bundle(E, False).error, "bot_unavailable"
        )

    def test_refresh_bypasses_all_snapshot_kinds(self) -> None:
        checks = [
            check(A.SIGNUP_EDIT, T, reference_present=True, message_id=M),
            check(
                A.SCHEDULED_EVENT_UPDATE,
                None,
                key="event",
                reference_present=True,
                scheduled_event_id=E,
            ),
        ]
        self.assertTrue(
            all(x.status == "verified" for x in self.run_checks(checks).checks)
        )
        original = list(self.source.calls)
        self.source.calls.clear()
        self.assertTrue(
            all(x.status == "verified" for x in self.run_checks(checks, True).checks)
        )
        self.assertCountEqual(original, self.source.calls)

    def test_failed_refresh_does_not_revive_cached_success(self) -> None:
        self.assertEqual(self.run_checks([check()]).checks[0].status, "verified")
        self.data[f"/guilds/{G}"] = {"status": 503, "body": {}}
        self.assertEqual(
            self.run_checks([check()], True).checks[0].reason, "network_error"
        )
        self.assertEqual(self.run_checks([check()]).checks[0].reason, "network_error")

    def test_exhausted_refresh_supersedes_cached_success(self) -> None:
        cases = [
            ("/users/@me", check()),
            (f"/guilds/{G}", check()),
            (f"/guilds/{G}/channels", check()),
            (
                f"/channels/{T}/thread-members/{B}",
                check(A.START_MENTION, T, reference_present=True),
            ),
            (
                f"/channels/{T}/messages/{M}",
                check(A.SIGNUP_EDIT, T, reference_present=True, message_id=M),
            ),
            (
                f"/guilds/{G}/scheduled-events/{E}",
                check(
                    A.SCHEDULED_EVENT_UPDATE,
                    None,
                    reference_present=True,
                    scheduled_event_id=E,
                ),
            ),
        ]
        for delayed_path, requested in cases:
            with self.subTest(path=delayed_path):
                cache.clear()
                self.assertEqual(
                    self.run_checks([requested]).checks[0].status, "verified"
                )
                release = threading.Event()
                finished = threading.Event()
                original = self.source.get

                def get(path: str, timeout: float) -> tuple[int, Any, dict[str, str]]:
                    if path == delayed_path:
                        try:
                            release.wait(timeout=3)
                            return original(path, timeout)
                        finally:
                            finished.set()
                    return original(path, timeout)

                reader = SnapshotReader(self.source, budget_s=0.15)
                try:
                    with (
                        patch.object(self.source, "get", side_effect=get),
                        patch(
                            "discordbot.permissions.service.SnapshotReader",
                            return_value=reader,
                        ),
                    ):
                        failed = self.run_checks([requested], True).checks[0]
                    self.assertEqual(
                        (failed.status, failed.reason), ("unknown", "network_error")
                    )
                    for refresh in (False, True):
                        result = self.run_checks([requested], refresh).checks[0]
                        self.assertEqual(result.status, "unknown")
                        self.assertIn(
                            result.reason, ("network_error", "resource_unavailable")
                        )
                        if refresh:
                            self.assertEqual(result.refresh_state, "coalesced")
                finally:
                    release.set()
                    self.assertTrue(finished.wait(timeout=3))
                self.assertEqual(
                    self.run_checks([requested]).checks[0].status, "unknown"
                )
                cache.delete(f"discord_perm_refresh:test-fixture-v1:{G}")
                self.assertEqual(
                    self.run_checks([requested], True).checks[0].status, "verified"
                )

    def test_coalesced_refresh_reports_original_checked_at(self) -> None:
        first = self.run_checks([check()], True).checks[0]
        calls = len(self.source.calls)
        second = self.run_checks([check()], True).checks[0]
        self.assertEqual(second.refresh_state, "coalesced")
        self.assertEqual(second.checked_at, first.checked_at)
        self.assertEqual(len(self.source.calls), calls)

    def test_foreign_channel_rejected_and_uncached(self) -> None:
        self.data[f"/channels/{T}"]["guild_id"] = E
        result = self.run_checks([check(channel=T)]).checks[0]
        self.assertEqual(result.reason, "resource_unavailable")
        self.assertIsNone(result.destination.name)
        self.data[f"/channels/{T}"]["guild_id"] = G
        self.assertIsNone(SnapshotReader(self.source).channel(G, T, False)[1])

    def test_thread_fetches_parent(self) -> None:
        self.assertEqual(
            self.run_checks([check(A.START_MENTION, T, reference_present=True)])
            .checks[0]
            .status,
            "verified",
        )
        self.assertIn(f"/channels/{T}", self.source.calls)
        self.assertIn(f"/guilds/{G}/channels", self.source.calls)

    def test_partial_failure_keeps_other_checks(self) -> None:
        self.data[f"/channels/{T}"] = {"status": 403, "body": {}}
        results = self.run_checks([check(channel=T), check(key="good")]).checks
        self.assertEqual([r.status for r in results], ["unknown", "verified"])

    def test_unsupported_and_dm_only_batch_needs_no_reads(self) -> None:
        result = self.run_checks(
            [check(A.MARK_INTERESTED), check(A.TOURNAMENT_DM, key="dm")]
        )
        self.assertEqual(
            [r.status for r in result.checks], ["unsupported", "not_applicable"]
        )
        self.assertEqual(self.source.calls, [])

    def test_fixture_source_only_under_test_setting(self) -> None:
        cache.set(f"discord_perm_fixture:{G}", self.data)
        with override_settings(TEST=False):
            self.assertIsInstance(source_for(G), RestSource)
        with override_settings(TEST=True):
            self.assertIsInstance(source_for(G), FixtureSource)

    @override_settings(TEST=True, DISCORD_BOT_TOKEN="")
    def test_fixture_source_needs_no_token(self) -> None:
        cache.set(f"discord_perm_fixture:{G}", self.data)
        self.assertEqual(
            run_checks(G, [check()], refresh=False).checks[0].status, "verified"
        )

    def test_checked_at_is_oldest_observation(self) -> None:
        old = timezone.now() - timedelta(seconds=30)
        with patch("discordbot.permissions.reader.timezone.now", return_value=old):
            SnapshotReader(self.source).guild_bundle(G, False)
        result = self.run_checks([check()]).checks[0]
        self.assertEqual(result.checked_at, old)
        self.assertEqual(result.expires_at, old + timedelta(seconds=60))

    def test_private_thread_member_reads(self) -> None:
        path = f"/channels/{T}/thread-members/{B}"
        for payload, member, reason in [
            ({"id": T, "user_id": B}, True, None),
            ({"status": 404, "body": {}}, False, None),
            ({"status": 403, "body": {}}, None, "forbidden_read"),
            ({"user_id": E, "id": T}, None, "malformed_snapshot"),
            ([], None, "malformed_snapshot"),
        ]:
            with self.subTest(payload=payload):
                cache.clear()
                self.data[path] = payload
                reader = SnapshotReader(self.source)
                channel, error = reader.channel(G, T, False)
                self.assertIs(channel.thread_meta.bot_is_member, member)
                self.assertEqual(error, reason)
                self.assertIn(path, reader.observations)
                results = self.run_checks(
                    [
                        check(A.START_MENTION, T, reference_present=True),
                        check(key="independent"),
                    ]
                ).checks
                self.assertEqual(results[0].status, "verified" if member else "unknown")
                self.assertEqual(results[1].status, "verified")

    def test_malformed_snapshots_never_verify(self) -> None:
        for value in [True, 1.5, -1, "-1", "oops"]:
            with self.subTest(value=value):
                cache.clear()
                data = deepcopy(scenario())
                data[f"/guilds/{G}"]["roles"][0]["permissions"] = value
                self.source = RecordingSource(data)
                self.assertEqual(
                    self.run_checks([check()]).checks[0].reason, "malformed_snapshot"
                )

    def test_preview_cannot_claim_persisted_ownership(self) -> None:
        result = preview_checks(
            [
                PermissionCheckIn(
                    key="edit", action=A.SCHEDULED_EVENT_UPDATE, channel_id=None
                )
            ]
        )[0]
        self.assertIs(result.reference_present, False)
        self.assertIsNone(result.scheduled_event_id)
        self.assertIsNone(result.message_id)

    def test_resource_freshness_is_action_specific(self) -> None:
        old = timezone.now() - timedelta(seconds=30)
        path = f"/channels/{T}/thread-members/{B}"
        with patch("discordbot.permissions.reader.timezone.now", return_value=old):
            reader = SnapshotReader(self.source)
            reader.channel(G, T, False)
        cache.delete(f"discord_perm:v1:test-fixture-v1:{G}:channels")
        cache.delete(f"discord_perm:v1:test-fixture-v1:{G}:bot")
        result = self.run_checks(
            [check(A.START_MENTION, T, reference_present=True), check(key="other")]
        ).checks
        self.assertEqual(result[0].checked_at, old)
        self.assertEqual(result[0].expires_at, old + timedelta(seconds=60))
        self.assertGreater(result[1].checked_at, old)
        self.assertIn(path, reader.observations)

    def test_wrong_channel_id_is_rejected_before_cache(self) -> None:
        self.data[f"/channels/{T}"]["id"] = E
        self.assertEqual(
            SnapshotReader(self.source).channel(G, T, False)[1], "malformed_snapshot"
        )
        self.data[f"/channels/{T}"]["id"] = T
        self.assertIsNone(SnapshotReader(self.source).channel(G, T, False)[1])

    def test_invalid_ids_cannot_form_upstream_paths(self) -> None:
        for invalid in ["../messages", "123?limit=100", "https://example.invalid"]:
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    SnapshotReader(self.source).channel(G, invalid, False)
        self.assertEqual(self.source.calls, [])

    def test_coalesced_cache_miss_does_not_poison_inflight_refresh(self) -> None:
        cache.add(f"discord_perm_refresh:test-fixture-v1:{G}", True, timeout=10)
        result = self.run_checks([check()], refresh=True).checks[0]
        self.assertEqual(result.status, "unknown")
        self.assertEqual(result.refresh_state, "coalesced")
        self.assertIsNone(cache.get(f"discord_perm:v1:test-fixture-v1:{G}:bot"))

    def test_unknown_assigned_role_timeout_and_overwrite_are_incomplete(self) -> None:
        mutations = [
            (f"/guilds/{G}/members/{B}", "roles", [E]),
            (
                f"/guilds/{G}/members/{B}",
                "communication_disabled_until",
                "2026-11-26T12:00:00",
            ),
        ]
        for path, key, value in mutations:
            with self.subTest(key=key):
                cache.clear()
                data = scenario()
                data[path][key] = value
                self.source = RecordingSource(data)
                self.assertEqual(
                    self.run_checks([check()]).checks[0].reason, "malformed_snapshot"
                )
        cache.clear()
        data = scenario()
        data[f"/guilds/{G}/channels"][0]["permission_overwrites"] = [
            {"id": G, "type": True, "allow": "0", "deny": "0"}
        ]
        self.source = RecordingSource(data)
        self.assertNotEqual(self.run_checks([check()]).checks[0].status, "verified")

    @override_settings(DISCORD_API_BASE_URL="https://discord.invalid/api/v10")
    def test_rest_source_uses_get_with_bounded_timeout(self) -> None:
        with patch("requests.get") as get:
            get.return_value.status_code = 200
            get.return_value.json.return_value = {"id": B}
            get.return_value.headers = {}
            self.assertEqual(RestSource().get("/users/@me", 2)[1], {"id": B})
            get.assert_called_once_with(
                "https://discord.invalid/api/v10/users/@me",
                headers={"Authorization": "Bot synthetic"},
                timeout=2,
                allow_redirects=False,
            )

    def test_invalid_reference_ids_are_rejected_before_reads(self) -> None:
        for method, args in [
            ("guild_bundle", ("../bad", False)),
            ("scheduled_event_creator", (G, "../bad", False)),
            ("message_author", (G, C, "../bad", False)),
        ]:
            with self.subTest(method=method), self.assertRaises(ValueError):
                getattr(SnapshotReader(self.source), method)(*args)
        self.assertEqual(self.source.calls, [])

    def test_private_membership_refresh_failure_keeps_sibling_fresh(self) -> None:
        checks = [
            check(A.START_MENTION, T, reference_present=True),
            check(key="sibling"),
        ]
        self.assertEqual(self.run_checks(checks).checks[0].status, "verified")
        self.data[f"/channels/{T}/thread-members/{B}"] = {"status": 403, "body": {}}
        results = self.run_checks(checks, True).checks
        self.assertEqual(
            (results[0].status, results[0].reason), ("unknown", "forbidden_read")
        )
        self.assertEqual(results[1].status, "verified")
        self.assertNotEqual(self.run_checks(checks).checks[0].status, "verified")

    def test_saved_reference_errors_are_independent(self) -> None:
        self.data[f"/channels/{T}/messages/{M}"] = {"status": 404, "body": {}}
        results = self.run_checks(
            [
                check(A.SIGNUP_EDIT, T, reference_present=True, message_id=M),
                check(key="sibling"),
            ]
        ).checks
        self.assertEqual(
            (results[0].status, results[0].reason), ("unknown", "resource_unavailable")
        )
        self.assertEqual(results[1].status, "verified")

    def test_missing_thread_parent_never_verifies(self) -> None:
        self.data[f"/channels/{T}"]["parent_id"] = E
        result = self.run_checks(
            [check(A.START_MENTION, T, reference_present=True)]
        ).checks[0]
        self.assertEqual(
            (result.status, result.reason), ("unknown", "resource_unavailable")
        )

    def test_read_that_outlasts_budget_cannot_verify(self) -> None:
        clock = [0.0]
        original = self.source.get

        def get(path: str, timeout: float) -> tuple[int, Any, dict[str, str]]:
            response = original(path, timeout)
            if path == f"/guilds/{G}/channels":
                clock[0] = 16.0
            return response

        with (
            patch(
                "discordbot.permissions.reader.time.monotonic",
                side_effect=lambda: clock[0],
            ),
            patch.object(self.source, "get", side_effect=get),
        ):
            result = self.run_checks([check()]).checks[0]
        self.assertEqual((result.status, result.reason), ("unknown", "network_error"))

    def test_rest_rate_limit_preserves_header_without_json(self) -> None:
        with patch("requests.get") as get:
            get.return_value.status_code = 429
            get.return_value.json.side_effect = ValueError("not JSON")
            get.return_value.headers = {"Retry-After": "4"}
            bundle = SnapshotReader(RestSource()).guild_bundle(G, False)
        self.assertEqual((bundle.error, bundle.retry_after), ("rate_limited", 4))

    def test_rest_cache_identity_uses_actual_source_token(self) -> None:
        source = RestSource()
        with override_settings(DISCORD_BOT_TOKEN="different"):
            reader = SnapshotReader(source)
        self.assertEqual(reader.token_fp, SnapshotReader(source).token_fp)

    def test_membership_observation_alone_limits_thread_freshness(self) -> None:
        self.run_checks([check(A.START_MENTION, T, reference_present=True)])
        key = f"discord_perm:v1:test-fixture-v1:{G}:thread-member:{T}"
        entry = cache.get(key)
        old = timezone.now() - timedelta(seconds=45)
        cache.set(
            key,
            replace(entry, observation=Observation(old, old + timedelta(seconds=60))),
            timeout=60,
        )
        results = self.run_checks(
            [check(A.START_MENTION, T, reference_present=True), check(key="other")]
        ).checks
        self.assertEqual(results[0].checked_at, old)
        self.assertEqual(results[0].expires_at, old + timedelta(seconds=60))
        self.assertGreater(results[1].checked_at, old)

    def test_interrupted_guild_body_is_unknown(self) -> None:
        original = self.source.get

        def get(path: str, timeout: float) -> tuple[int, Any, dict[str, str]]:
            if path == f"/guilds/{G}":
                raise requests.exceptions.ChunkedEncodingError("interrupted")
            return original(path, timeout)

        with patch.object(self.source, "get", side_effect=get):
            result = self.run_checks([check()]).checks[0]
        self.assertEqual((result.status, result.reason), ("unknown", "network_error"))

    def test_interrupted_channel_body_keeps_sibling_verified(self) -> None:
        original = self.source.get

        def get(path: str, timeout: float) -> tuple[int, Any, dict[str, str]]:
            if path == f"/channels/{T}":
                raise requests.exceptions.ChunkedEncodingError("interrupted")
            return original(path, timeout)

        with patch.object(self.source, "get", side_effect=get):
            results = self.run_checks([check(channel=T), check(key="sibling")]).checks
        self.assertEqual(
            (results[0].status, results[0].reason), ("unknown", "network_error")
        )
        self.assertEqual(results[1].status, "verified")

    def test_channel_rate_limit_preserves_retry_after(self) -> None:
        self.data[f"/channels/{T}"] = {
            "status": 429,
            "headers": {"Retry-After": "7"},
        }
        results = self.run_checks([check(channel=T), check(key="sibling")]).checks
        self.assertEqual(
            (results[0].reason, results[0].retry_after_seconds), ("rate_limited", 7)
        )
        self.assertEqual(results[1].status, "verified")
        self.assertIsNone(results[1].retry_after_seconds)

    def test_wall_clock_budget_bounds_every_upstream_read(self) -> None:
        cases = [
            (f"/guilds/{G}", check()),
            (f"/channels/{T}", check(channel=T)),
            (f"/channels/{E}", check(A.START_MENTION, T, reference_present=True)),
            (
                f"/channels/{T}/messages/{M}",
                check(A.SIGNUP_EDIT, T, reference_present=True, message_id=M),
            ),
            (
                f"/guilds/{G}/scheduled-events/{E}",
                check(
                    A.SCHEDULED_EVENT_UPDATE,
                    None,
                    reference_present=True,
                    scheduled_event_id=E,
                ),
            ),
        ]
        for index, (delayed_path, requested) in enumerate(cases):
            with self.subTest(path=delayed_path):
                cache.clear()
                self.data[f"/channels/{T}"]["parent_id"] = E
                self.data[f"/channels/{E}"] = {
                    "id": E,
                    "guild_id": G,
                    "type": 0,
                    "name": "parent",
                    "permission_overwrites": [],
                }
                release = threading.Event()
                finished = threading.Event()
                original = self.source.get

                def get(path: str, timeout: float) -> tuple[int, Any, dict[str, str]]:
                    if path == delayed_path:
                        try:
                            release.wait(timeout=2)
                            return original(path, timeout)
                        finally:
                            finished.set()
                    return original(path, timeout)

                reader = SnapshotReader(self.source, budget_s=0.15)
                reader.token_fp = f"deadline-{index}"
                try:
                    with (
                        patch.object(self.source, "get", side_effect=get),
                        patch(
                            "discordbot.permissions.service.SnapshotReader",
                            return_value=reader,
                        ),
                    ):
                        started = time.monotonic()
                        result = self.run_checks([requested]).checks[0]
                        elapsed = time.monotonic() - started
                    self.assertLess(elapsed, 0.75)
                    self.assertEqual(
                        (result.status, result.reason), ("unknown", "network_error")
                    )
                finally:
                    release.set()
                    self.assertTrue(finished.wait(timeout=3))

    def test_timed_out_reads_keep_worker_count_bounded(self) -> None:
        release = threading.Event()
        started = [threading.Event() for _ in range(4)]
        finished = [threading.Event() for _ in range(4)]
        guard = threading.Lock()
        calls = 0

        def get(path: str, timeout: float) -> tuple[int, Any, dict[str, str]]:
            nonlocal calls
            with guard:
                index = calls
                calls += 1
            started[index].set()
            try:
                release.wait(timeout=3)
                return 200, {"id": B}, {}
            finally:
                finished[index].set()

        executor = ThreadPoolExecutor(max_workers=4)
        try:
            with patch.object(self.source, "get", side_effect=get):
                readers = [SnapshotReader(self.source, budget_s=0.3) for _ in range(4)]
                futures = [
                    executor.submit(reader.guild_bundle, G, False) for reader in readers
                ]
                self.assertTrue(all(event.wait(timeout=1) for event in started))
                self.assertEqual(
                    [future.result(timeout=1).error for future in futures],
                    ["network_error"] * 4,
                )
                cache.clear()
                result = SnapshotReader(self.source, budget_s=0.1).guild_bundle(
                    G, False
                )
                self.assertEqual(result.error, "network_error")
                self.assertEqual(calls, 4)
        finally:
            release.set()
            executor.shutdown(wait=True, cancel_futures=True)
            self.assertTrue(all(event.wait(timeout=1) for event in finished))
        self.assertIsNone(cache.get(f"discord_perm:v1:test-fixture-v1:{G}:bot"))
        self.assertIsNone(SnapshotReader(self.source).guild_bundle(G, False).error)

    def test_late_source_completion_cannot_replace_newer_refresh(self) -> None:
        release = threading.Event()
        finished = threading.Event()
        original = self.source.get

        def get(path: str, timeout: float) -> tuple[int, Any, dict[str, str]]:
            try:
                release.wait(timeout=3)
                return original(path, timeout)
            finally:
                finished.set()

        reader = SnapshotReader(self.source, budget_s=0.1)
        try:
            with patch.object(self.source, "get", side_effect=get):
                self.assertEqual(reader.guild_bundle(G, False).error, "network_error")
            key = f"discord_perm:v1:test-fixture-v1:{G}:bot"
            self.assertIsNone(cache.get(key))
            self.assertIsNone(
                SnapshotReader(FixtureSource(self.data)).guild_bundle(G, True).error
            )
            refreshed = cache.get(key)
        finally:
            release.set()
            self.assertTrue(finished.wait(timeout=1))
        self.assertEqual(cache.get(key), refreshed)
        self.assertIsNone(refreshed.error)

    def test_expired_refresh_owner_cannot_replace_newer_observation(self) -> None:
        clock = [0.0]
        newer: list[Any] = []
        original = self.source.get
        key = f"discord_perm:v1:test-fixture-v1:{G}:bot"

        def get(path: str, timeout: float) -> tuple[int, Any, dict[str, str]]:
            cache.delete(f"discord_perm_refresh:test-fixture-v1:{G}")
            self.assertIsNone(
                SnapshotReader(FixtureSource(self.data)).guild_bundle(G, True).error
            )
            newer.append(cache.get(key))
            clock[0] = 16.0
            return original(path, timeout)

        with (
            patch(
                "discordbot.permissions.reader.time.monotonic",
                side_effect=lambda: clock[0],
            ),
            patch.object(self.source, "get", side_effect=get),
        ):
            reader = SnapshotReader(self.source, budget_s=15)
            self.assertEqual(reader.guild_bundle(G, True).error, "network_error")
        self.assertEqual(len(newer), 1)
        self.assertEqual(cache.get(key), newer[0])
        self.assertIsNone(cache.get(key).error)

    def test_late_refresh_completion_cannot_replace_newer_observation(self) -> None:
        self.assertEqual(self.run_checks([check()]).checks[0].status, "verified")
        release = threading.Event()
        finished = threading.Event()
        original = self.source.get

        def get(path: str, timeout: float) -> tuple[int, Any, dict[str, str]]:
            try:
                release.wait(timeout=3)
                return original(path, timeout)
            finally:
                finished.set()

        reader = SnapshotReader(self.source, budget_s=0.1)
        key = f"discord_perm:v1:test-fixture-v1:{G}:bot"
        try:
            with patch.object(self.source, "get", side_effect=get):
                self.assertEqual(reader.guild_bundle(G, True).error, "network_error")
            self.assertEqual(cache.get(key).error, "network_error")
            cache.delete(f"discord_perm_refresh:test-fixture-v1:{G}")
            self.assertEqual(
                self.run_checks([check()], True).checks[0].status, "verified"
            )
            refreshed = cache.get(key)
        finally:
            release.set()
            self.assertTrue(finished.wait(timeout=1))
        self.assertEqual(cache.get(key), refreshed)
        self.assertIsNone(refreshed.error)

    def test_rest_source_closes_response_after_invalid_json(self) -> None:
        with patch("requests.get") as get:
            get.return_value.status_code = 200
            get.return_value.json.side_effect = ValueError("invalid JSON")
            with self.assertRaises(ValueError):
                RestSource().get("/users/@me", 1)
            get.return_value.close.assert_called_once_with()

    def test_unconfigured_server(self) -> None:
        result = run_checks(None, [check()], refresh=False).checks[0]
        self.assertEqual(
            (result.status, result.reason), ("unconfigured", "no_server_configured")
        )
