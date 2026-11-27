import json
from collections.abc import Callable
from typing import Any
from unittest.mock import patch
from uuid import UUID, uuid4

from django.test import override_settings
from rest_framework.exceptions import PermissionDenied
from structlog.testing import capture_logs

from app.models import CustomUser
from common.game import GameType
from org.api_connections.crypto import seal_credential
from org.api_connections.pull import create_pull_run, step_pull
from org.api_connections.runs import acquire_lease
from org.api_connections.tls_adapter import SafeHttpError
from org.api_connections.types import SafeHttpRequest, SafeHttpResponse, StepResult
from org.mmr import mark_org_mmr_verified, set_org_mmr
from org.models import (
    OrgApiConnection,
    OrgApiMmrPullTarget,
    OrgApiRunCheckpoint,
    OrgApiSyncRun,
    OrgLog,
    OrgMmrRevisionCounter,
    OrgMmrSyncState,
    OrgUser,
    OrgUserGameMmr,
)
from org.tests.test_api_connections_crypto import OLD_KEY
from org.tests.test_api_tokens import ApiTokenBase

GAME = GameType.DOTA2
SECRET = "sekret-xyz-123"


class FakeRemote:
    def __init__(self, pages: list[object | Exception]) -> None:
        self.pages = pages
        self.requests: list[SafeHttpRequest] = []

    def __call__(
        self, request: SafeHttpRequest, *, deadline: float, max_bytes: int
    ) -> SafeHttpResponse:
        self.requests.append(request)
        page = self.pages[min(len(self.requests), len(self.pages)) - 1]
        if isinstance(page, Exception):
            raise page
        return SafeHttpResponse(
            status=200, data=page, bytes_received=len(json.dumps(page))
        )


class PullBase(ApiTokenBase):
    def setUp(self) -> None:
        super().setUp()
        self.carol = CustomUser.objects.create_user(
            username="carol", password="x", steam_account_id=1004, discordId="d-carol"
        )
        self.ou_carol = OrgUser.objects.create(user=self.carol, organization=self.org)
        self.connection = OrgApiConnection.objects.create(
            organization=self.org,
            name="Pull",
            enabled=True,
            mmr_pull_enabled=True,
            outbound_base_url="https://sync.example.test",
            outbound_auth="none",
            outbound_authorizer=self.admin,
            game_type=int(GAME),
            mmr_pull_config={"path": "/players", "query": {"org": "{{org.id}}"}},
        )

    def configure(self, **updates: Any) -> None:
        pull = dict(self.connection.mmr_pull_config)
        pull.update(updates.pop("pull", {}))
        OrgApiConnection.objects.filter(pk=self.connection.pk).update(
            mmr_pull_config=pull, **updates
        )
        self.connection.refresh_from_db()

    def run_pull(
        self,
        pages: list[object | Exception],
        *,
        requester: CustomUser | None = None,
        between: Callable[[OrgApiSyncRun, StepResult], None] | None = None,
    ) -> tuple[OrgApiSyncRun, FakeRemote, list[StepResult]]:
        remote = FakeRemote(pages)
        run = create_pull_run(self.connection, requester=requester or self.admin)
        fence = acquire_lease(run.id)
        assert fence is not None
        results: list[StepResult] = []
        with patch("org.api_connections.pull.request_json", side_effect=remote):
            for _ in range(200):
                result = step_pull(run.id, fence=fence)
                results.append(result)
                run.refresh_from_db()
                if between is not None:
                    between(run, result)
                if not result.continuation:
                    break
        run.refresh_from_db()
        return run, remote, results

    def mmr(self, org_user: OrgUser) -> int:
        row = OrgUserGameMmr.objects.filter(org_user=org_user, game_type=GAME).first()
        return row.mmr if row else 0

    def counter(self) -> int:
        row = OrgMmrRevisionCounter.objects.filter(
            organization=self.org, game_type=GAME
        ).first()
        return row.revision if row else 0


def rows(*pairs: tuple[int, int | None]) -> list[dict[str, Any]]:
    return [{"id": steam, "mmr": mmr} for steam, mmr in pairs]


class PullPolicyTests(PullBase):
    def setUp(self) -> None:
        super().setUp()
        set_org_mmr(self.ou_bob, GAME, 3000, mark_verified=False)
        set_org_mmr(
            self.ou_carol, GAME, 2500, mark_verified=True, verified_by=self.admin
        )

    def test_overwrite_policy_matrix_defaults_unverified(self) -> None:
        expected = {
            "missing_only": (4000, 3000, 2500, 1, 2),
            "unverified_only": (4000, 4000, 2500, 2, 1),
            "replace": (4000, 4000, 4000, 3, 0),
        }
        for policy, (alice, bob, carol, updated, skipped) in expected.items():
            with self.subTest(policy=policy):
                set_org_mmr(self.ou_alice, GAME, None, mark_verified=False)
                set_org_mmr(self.ou_bob, GAME, 3000, mark_verified=False)
                set_org_mmr(
                    self.ou_carol,
                    GAME,
                    2500,
                    mark_verified=True,
                    verified_by=self.admin,
                )
                self.configure(overwrite_policy=policy)
                run, _, _ = self.run_pull(
                    [rows((1001, 4000), (1002, 4000), (1004, 4000))]
                )
                self.assertEqual(run.state, "succeeded", run.error_code)
                self.assertEqual(
                    [self.mmr(m) for m in (self.ou_alice, self.ou_bob, self.ou_carol)],
                    [alice, bob, carol],
                )
                self.assertEqual(run.updated_count, updated)
                self.assertEqual(run.skipped_policy_count, skipped)
                self.assertIsNone(
                    OrgUserGameMmr.objects.get(org_user=self.ou_alice).verified_at
                )
                self.assertTrue(
                    OrgLog.objects.filter(
                        organization=self.org,
                        target_user_id=self.alice.pk,
                        details__source="api_pull",
                    ).exists()
                )

    def test_mark_verified_uses_authority_principal(self) -> None:
        self.configure(mark_verified=True, overwrite_policy="replace")
        run, _, _ = self.run_pull([rows((1001, 4100))])
        row = OrgUserGameMmr.objects.get(org_user=self.ou_alice, game_type=GAME)
        self.assertEqual(row.mmr, 4100)
        self.assertEqual(row.verified_by, self.admin)
        self.assertEqual(run.verified_count, 1)

    def test_verification_between_fetch_and_commit_is_conflict(self) -> None:
        self.configure(overwrite_policy="unverified_only")

        def verify(run: OrgApiSyncRun, result: StepResult) -> None:
            checkpoint = OrgApiRunCheckpoint.objects.get(run=run)
            if checkpoint.phase == "commit" and run.updated_count == 0:
                if not OrgUserGameMmr.objects.get(org_user=self.ou_bob).verified_at:
                    mark_org_mmr_verified(self.ou_bob, GAME, self.admin)

        run, _, _ = self.run_pull([rows((1002, 3000))], between=verify)
        row = OrgUserGameMmr.objects.get(org_user=self.ou_bob, game_type=GAME)
        self.assertEqual(run.conflict_count, 1)
        self.assertEqual(run.unchanged_count, 0)
        self.assertIsNotNone(row.verified_at)
        self.assertEqual(row.mmr, 3000)


class PullStagingTests(PullBase):
    def test_unmatched_never_added_and_missing_rows_never_clear(self) -> None:
        set_org_mmr(self.ou_carol, GAME, 2000, mark_verified=False)
        members = OrgUser.objects.count()
        run, _, _ = self.run_pull([rows((1003, 5000), (9999, 5000), (1001, 3000))])
        self.assertEqual(run.state, "succeeded")
        self.assertEqual(OrgUser.objects.count(), members)
        self.assertEqual(run.unmatched_count, 2)
        self.assertEqual(self.mmr(self.ou_carol), 2000)
        self.assertEqual(self.mmr(self.ou_alice), 3000)

    def test_invalid_rows_reported_without_blocking_valid_rows(self) -> None:
        run, _, _ = self.run_pull(
            [[{"id": 1001, "mmr": "4000"}, {"id": 1002, "mmr": 4100}, {"mmr": 1}]]
        )
        self.assertEqual(run.invalid_count, 2)
        self.assertEqual(self.mmr(self.ou_bob), 4100)
        self.assertEqual(self.mmr(self.ou_alice), 0)

    def test_cross_page_conflicting_duplicates_apply_none(self) -> None:
        self.configure(pull={"pagination": {"kind": "page", "page_size": 2}})
        start = self.counter()
        run, remote, _ = self.run_pull(
            [
                rows((1001, 3000), (1002, 3100)),
                rows((1001, 3200), (1002, 3100)),
                [],
            ]
        )
        self.assertEqual(run.state, "succeeded", run.error_code)
        self.assertEqual(len(remote.requests), 3)
        self.assertEqual(self.mmr(self.ou_alice), 0)
        self.assertEqual(self.mmr(self.ou_bob), 3100)
        self.assertEqual(self.counter(), start + 1)
        self.assertIn("ambiguous_duplicate", [issue["code"] for issue in run.issues])

    def test_later_page_failure_applies_zero(self) -> None:
        self.configure(pull={"pagination": {"kind": "page", "page_size": 2}})
        start = self.counter()
        run, _, _ = self.run_pull(
            [rows((1001, 3000), (1002, 3100)), SafeHttpError("network_failed")]
        )
        self.assertEqual(run.state, "failed")
        self.assertEqual(run.error_code, "network_failed")
        self.assertEqual(self.counter(), start)
        self.assertFalse(
            OrgUserGameMmr.objects.filter(org_user__organization=self.org).exists()
        )
        self.assertFalse(OrgApiMmrPullTarget.objects.filter(run=run).exists())

    def test_signalled_more_at_cap_is_incomplete(self) -> None:
        self.configure(
            pull={
                "mapping": {"list_path": "items"},
                "pagination": {"kind": "page", "page_size": 1, "has_more_path": "more"},
            }
        )
        pages = [
            {"items": rows((1001, 3000)), "more": True},
            {"items": rows((1002, 3000)), "more": True},
        ]
        with patch("org.api_connections.pull.REQUESTS_PER_RUN", 2):
            run, remote, _ = self.run_pull(pages)
        self.assertEqual((run.state, run.error_code), ("failed", "pull_incomplete"))
        self.assertEqual(len(remote.requests), 2)
        self.assertEqual(self.mmr(self.ou_alice), 0)
        self.configure(pull={"mapping": {}, "pagination": {}})
        with patch("org.api_connections.pull.ROWS_PER_RUN", 1):
            run, _, _ = self.run_pull([rows((1001, 3000), (1002, 3000))])
        self.assertEqual((run.state, run.error_code), ("failed", "pull_incomplete"))
        self.assertEqual(self.mmr(self.ou_alice), 0)

    def test_interrupted_post_is_not_retried_but_get_is(self) -> None:
        for method, expected in (("POST", "pull_ambiguous"), ("GET", "")):
            with self.subTest(method=method):
                body = {"org": "{{org.id}}"} if method == "POST" else None
                self.configure(pull={"method": method, "body": body, "query": {}})
                run = create_pull_run(self.connection, requester=self.admin)
                fence = acquire_lease(run.id)
                assert fence is not None
                step_pull(run.id, fence=fence)
                with (
                    patch(
                        "org.api_connections.pull.request_json",
                        side_effect=RuntimeError,
                    ),
                    self.assertRaises(RuntimeError),
                ):
                    step_pull(run.id, fence=fence)
                remote = FakeRemote([rows((1001, 3500))])
                with patch("org.api_connections.pull.request_json", side_effect=remote):
                    while step_pull(run.id, fence=fence).continuation:
                        pass
                run.refresh_from_db()
                self.assertEqual(run.error_code, expected)
                self.assertEqual(len(remote.requests), 0 if method == "POST" else 1)
                self.assertEqual(run.request_count, 1 if method == "POST" else 2)

    def test_run_byte_budget_is_enforced(self) -> None:
        with patch("org.api_connections.pull.RUN_BYTES", 0):
            run, remote, _ = self.run_pull([rows((1001, 3000))])
        self.assertEqual((run.state, run.error_code), ("failed", "pull_incomplete"))
        self.assertEqual(len(remote.requests), 0)

    def test_cursor_loop_fails_without_writes(self) -> None:
        self.configure(
            pull={
                "mapping": {"list_path": "items"},
                "query": {"org": "{{org.id}}", "c": "{{cursor}}"},
                "pagination": {"kind": "cursor", "next_cursor_path": "next"},
            }
        )
        run, remote, _ = self.run_pull(
            [
                {"items": rows((1001, 3000)), "next": "a"},
                {"items": rows((1002, 3000)), "next": "a"},
            ]
        )
        self.assertEqual((run.state, run.error_code), ("failed", "pagination_loop"))
        self.assertEqual(remote.requests[0].query, {"org": self.org.pk})
        self.assertEqual(remote.requests[1].query, {"org": self.org.pk, "c": "a"})
        self.assertEqual(self.mmr(self.ou_alice), 0)

    def test_snapshot_does_not_rematch_changed_identity(self) -> None:
        def change(run: OrgApiSyncRun, result: StepResult) -> None:
            checkpoint = OrgApiRunCheckpoint.objects.get(run=run)
            if checkpoint.phase == "fetch" and self.alice.steam_account_id == 1001:
                self.alice.steam_account_id = 5005
                self.alice.save()
                self.bob.steam_account_id = 6006
                self.bob.save()

        run, _, _ = self.run_pull([rows((5005, 3000), (1002, 3100))], between=change)
        self.assertEqual(run.unmatched_count, 1)
        self.assertEqual(run.conflict_count, 1)
        self.assertEqual(self.mmr(self.ou_alice), 0)
        self.assertEqual(self.mmr(self.ou_bob), 0)

    def test_per_member_mode_reports_missing_identifier(self) -> None:
        self.configure(
            pull={
                "request_mode": "per_member",
                "query": {"discord": "{{player.discord_id}}"},
                "mapping": {"player_id_type": "discord_id"},
            }
        )
        pages = [[{"id": "d-ignored", "mmr": 1}]]
        run, remote, _ = self.run_pull(pages)
        self.assertEqual(run.state, "succeeded", run.error_code)
        self.assertEqual(run.missing_identifier_count, 1)
        self.assertEqual(
            sorted(r.query["discord"] for r in remote.requests),
            ["d-alice", "d-bob", "d-carol"],
        )
        self.assertTrue(all("None" not in json.dumps(r.query) for r in remote.requests))

    def test_issue_examples_are_bounded_with_full_totals(self) -> None:
        run, _, _ = self.run_pull([rows(*((50_000 + i, 10) for i in range(150)))])
        self.assertEqual(run.unmatched_count, 150)
        self.assertEqual(run.issue_count, 150)
        self.assertEqual(len(run.issues), 100)
        self.assertEqual(
            run.issues[0],
            {"code": "unmatched", "page": 1, "index": 0, "player_id": "50000"},
        )

    def test_chunk_501_crash_resumes_without_reapply(self) -> None:
        users = CustomUser.objects.bulk_create(
            CustomUser(username=f"bulk-{i}", steam_account_id=200_000 + i)
            for i in range(501)
        )
        OrgUser.objects.bulk_create(
            OrgUser(user=user, organization=self.org) for user in users
        )
        remote = FakeRemote([rows(*((200_000 + i, 1000 + i) for i in range(501)))])
        run = create_pull_run(self.connection, requester=self.admin)
        fence = acquire_lease(run.id)
        assert fence is not None
        with patch("org.api_connections.pull.request_json", side_effect=remote):
            self.assertTrue(step_pull(run.id, fence=fence).continuation)
            self.assertTrue(step_pull(run.id, fence=fence).continuation)
            first = step_pull(run.id, fence=fence)
        self.assertTrue(first.continuation)
        run.refresh_from_db()
        self.assertEqual((run.state, run.updated_count), ("partial", 500))
        start = self.counter()
        with (
            patch("org.api_connections.pull.set_org_mmr", side_effect=RuntimeError),
            self.assertRaises(RuntimeError),
        ):
            step_pull(run.id, fence=fence)
        run.refresh_from_db()
        self.assertEqual((run.state, run.updated_count), ("partial", 500))
        self.assertEqual(self.counter(), start)
        final = step_pull(run.id, fence=fence)
        run.refresh_from_db()
        self.assertFalse(final.continuation)
        self.assertEqual((run.state, run.updated_count), ("succeeded", 501))
        self.assertEqual(self.counter(), start + 1)
        self.assertEqual(
            OrgMmrSyncState.objects.filter(
                org_user__organization=self.org, game_type=GAME
            ).count(),
            501,
        )


class PullAuthorityTests(PullBase):
    def test_auth_none_manual_pull_uses_authorizer(self) -> None:
        self.assertEqual(self.connection.outbound_credential_ciphertext, "")
        run, remote, _ = self.run_pull([rows((1001, 3300))], requester=self.admin2)
        self.assertEqual(run.state, "succeeded", run.error_code)
        self.assertEqual(run.requester, self.admin2)
        self.assertEqual(remote.requests[0].auth, "none")
        self.assertIsNone(remote.requests[0].credential)
        log = OrgLog.objects.get(
            target_user_id=self.alice.pk, details__source="api_pull"
        )
        self.assertEqual(log.actor, self.admin)

        def demote(run: OrgApiSyncRun, result: StepResult) -> None:
            if OrgApiRunCheckpoint.objects.get(run=run).phase == "commit":
                self.org.admins.remove(self.admin)

        run, _, results = self.run_pull([rows((1002, 3400))], between=demote)
        self.assertEqual((run.state, run.error_code), ("canceled", "authority_lost"))
        self.assertEqual(results[-1].error_code, "authority_lost")
        self.assertEqual(self.mmr(self.ou_bob), 0)
        self.connection.refresh_from_db()
        self.assertFalse(self.connection.mmr_pull_enabled)
        self.assertIsNone(self.connection.outbound_authorizer_id)

    def test_create_requires_authority_and_reuses_active_run(self) -> None:
        run = create_pull_run(self.connection, requester=self.admin)
        again = create_pull_run(self.connection, requester=self.admin2)
        self.assertEqual(run.pk, again.pk)
        self.assertEqual(run.config_snapshot["mmr_pull_config"]["path"], "/players")
        with self.assertRaises(PermissionDenied):
            create_pull_run(self.connection, requester=self.member)
        OrgApiSyncRun.objects.filter(pk=run.pk).update(state="succeeded")
        OrgApiConnection.objects.filter(pk=self.connection.pk).update(
            mmr_pull_enabled=False
        )
        with self.assertRaises(PermissionDenied):
            create_pull_run(self.connection, requester=self.admin)

    def test_stale_fence_and_config_change_stop_run(self) -> None:
        run = create_pull_run(self.connection, requester=self.admin)
        self.assertIsNotNone(acquire_lease(run.id))
        self.assertIsNone(acquire_lease(run.id))
        stale = step_pull(run.id, fence=uuid4())
        self.assertEqual((stale.continuation, stale.error_code), (False, "stale_fence"))
        run.refresh_from_db()
        self.assertEqual(run.state, "queued")
        fence = UUID(str(run.lease_token))
        OrgApiConnection.objects.filter(pk=self.connection.pk).update(config_version=9)
        result = step_pull(run.id, fence=fence)
        run.refresh_from_db()
        self.assertEqual(
            (run.state, run.error_code, result.error_code),
            ("canceled", "configuration_changed", "configuration_changed"),
        )

    @override_settings(ORG_API_CREDENTIAL_KEYS=json.dumps([OLD_KEY]))
    def test_secret_and_rendered_values_absent_from_diagnostics(self) -> None:
        envelope = seal_credential(
            SECRET,
            org_id=self.org.pk,
            connection_id=self.connection.pk,
            origin="https://sync.example.test:443",
        )
        self.configure(
            outbound_auth="bearer",
            outbound_authorizer=None,
            outbound_credential_owner=self.admin,
            outbound_credential_ciphertext=envelope,
            outbound_credential_key_id="old",
        )
        with capture_logs() as logs:
            run, remote, results = self.run_pull([rows((1001, 3000), (1777, 3000))])
        self.assertEqual(run.state, "succeeded", run.error_code)
        self.assertEqual(remote.requests[0].credential, SECRET)
        self.assertEqual(
            remote.requests[0].credential_origin, "https://sync.example.test:443"
        )
        persisted = json.dumps(
            [
                list(OrgApiSyncRun.objects.filter(pk=run.pk).values()),
                list(OrgApiRunCheckpoint.objects.filter(run=run).values()),
                list(OrgApiMmrPullTarget.objects.filter(run=run).values()),
                [repr(r) for r in results],
                logs,
            ],
            default=str,
        )
        self.assertNotIn(SECRET, persisted)
        self.assertNotIn(f"org={self.org.pk}", persisted)
