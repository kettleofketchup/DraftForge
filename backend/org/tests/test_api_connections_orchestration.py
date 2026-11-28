import json
import time
from datetime import timedelta
from io import StringIO
from typing import Any
from unittest.mock import MagicMock, patch
from uuid import UUID, uuid4

from django.core.cache import cache
from django.core.management import call_command
from django.db import OperationalError
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from app.internal_client import org_api_sync as sync_client
from app.internal_client import transport
from app.models import CustomUser
from config import tasks_org_api_sync
from org.api_connections import internal_views, orchestration
from org.api_connections.crypto import seal_credential
from org.api_connections.limits import REQUEST_SECONDS, RUN_SECONDS
from org.api_connections.orchestration import (
    ABANDON_SECONDS,
    CLIENT_TIMEOUT_SECONDS,
    STEP_SECONDS,
    claim_work,
    purge_expired_runs,
    schedule_due_pulls,
    step_delivery,
    step_run,
)
from org.api_connections.push import acquire_delivery_lease
from org.api_connections.runs import LEASE_SECONDS
from org.api_connections.tls_adapter import SafeHttpError
from org.api_connections.types import (
    SafeHttpRawResponse,
    SafeHttpRequest,
    StepResult,
    WorkClaim,
)
from org.mmr import set_org_mmr
from org.models import (
    OrgApiConnection,
    OrgApiMmrDelivery,
    OrgApiMmrPullTarget,
    OrgApiRunCheckpoint,
    OrgApiSyncRun,
    OrgLog,
    OrgUser,
    OrgUserGameMmr,
)
from org.tests.test_api_connections_crypto import OLD_KEY
from org.tests.test_api_connections_pull import GAME, FakeRemote, PullBase, rows

TOKEN = "orchestration-internal-token"
PUSH_SECRET = "push-health-secret"
ORIGIN = "https://sync.example.test"


class HealthRemote:
    def __init__(self, status: int = 200) -> None:
        self.status = status
        self.requests: list[SafeHttpRequest] = []

    def __call__(
        self, request: SafeHttpRequest, *, deadline: float, max_bytes: int
    ) -> SafeHttpRawResponse:
        self.requests.append(request)
        return SafeHttpRawResponse(status=self.status, body=b"ok")


class OrchestrationBase(PullBase):
    def setUp(self) -> None:
        super().setUp()
        self.api = APIClient()
        self.api.force_authenticate(self.admin)
        self.base = (
            f"/api/organizations/{self.org.pk}/api-connections/{self.connection.pk}/"
        )

    def claim(self, **kwargs: Any) -> list[WorkClaim]:
        return claim_work(now=kwargs.pop("now", timezone.now()), **kwargs)

    def drive(
        self,
        claim: WorkClaim,
        remote: Any,
        *,
        target: str = "org.api_connections.pull.request_json",
        limit: int = 200,
    ) -> list[StepResult]:
        results: list[StepResult] = []
        fence: UUID | None = claim.fence
        with patch(target, side_effect=remote):
            for _ in range(limit):
                assert fence is not None
                result = step_run(claim.run_id, fence=fence)
                results.append(result)
                if not result.continuation:
                    break
                fence = result.fence
        return results

    def run_claim(self, run: OrgApiSyncRun) -> WorkClaim:
        claims = [c for c in self.claim() if c.run_id == run.pk]
        self.assertEqual(len(claims), 1)
        return claims[0]

    def post_test(self, direction: str = "mmr_pull") -> Any:
        return self.api.post(
            f"{self.base}test/", {"direction": direction}, format="json"
        )

    def disable_pull(self) -> None:
        OrgApiConnection.objects.filter(pk=self.connection.pk).update(
            enabled=False, mmr_pull_enabled=False, outbound_authorizer=None
        )
        self.connection.refresh_from_db()


class TestRunTests(OrchestrationBase):
    def test_disabled_saved_test_is_nonmutating_and_archived_refuses(self) -> None:
        self.disable_pull()
        before = OrgApiConnection.objects.filter(pk=self.connection.pk).values().get()
        logs = OrgLog.objects.count()
        response = self.post_test()
        self.assertEqual(response.status_code, 202, response.data)
        self.assertEqual(set(response.data), {"run_id", "state"})
        self.assertEqual(response.data["state"], "queued")
        run = OrgApiSyncRun.objects.get(pk=response.data["run_id"])
        self.assertEqual(run.kind, "test")
        remote = FakeRemote([rows((1001, 4000), (9999, 10), (1002, None))])
        results = self.drive(
            self.run_claim(run),
            remote,
            target="org.api_connections.orchestration.request_json",
        )
        run.refresh_from_db()
        self.assertEqual((run.state, run.error_code), ("succeeded", ""))
        self.assertEqual(results[-1].continuation, False)
        self.assertEqual(len(remote.requests), 1)
        self.assertEqual((run.row_count, run.unmatched_count), (3, 1))
        self.assertEqual(self.mmr(self.ou_alice), 0)
        self.assertFalse(OrgUserGameMmr.objects.exists())
        self.assertFalse(OrgApiMmrDelivery.objects.exists())
        self.assertFalse(OrgApiMmrPullTarget.objects.exists())
        self.assertEqual(OrgLog.objects.count(), logs)
        after = OrgApiConnection.objects.filter(pk=self.connection.pk).values().get()
        self.assertEqual(before, after)

        detail = self.api.get(f"{self.base}runs/{run.pk}/")
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.data["direction"], "mmr_pull")
        self.assertEqual(detail.data["kind"], "test")
        self.assertEqual(detail.data["issues"][0]["code"], "unmatched")

        archived = self.api.delete(self.base)
        self.assertEqual(archived.status_code, 200, archived.data)
        refused = self.post_test()
        self.assertEqual(refused.status_code, 400)
        self.assertEqual(refused.data["code"], "connection_archived")

    def test_requester_authority_rechecked_for_disabled_test(self) -> None:
        self.disable_pull()
        member = APIClient()
        member.force_authenticate(self.member)
        denied = member.post(
            f"{self.base}test/", {"direction": "mmr_pull"}, format="json"
        )
        self.assertIn(denied.status_code, (403, 404))
        response = self.post_test()
        run = OrgApiSyncRun.objects.get(pk=response.data["run_id"])
        self.org.admins.remove(self.admin)
        remote = FakeRemote([rows((1001, 4000))])
        self.drive(
            self.run_claim(run),
            remote,
            target="org.api_connections.orchestration.request_json",
        )
        run.refresh_from_db()
        self.assertEqual(run.state, "canceled")
        self.assertEqual(run.error_code, "not_permitted")
        self.assertEqual(remote.requests, [])

    def test_unknown_direction_and_body_rejected(self) -> None:
        cache.clear()
        for body in (
            {"direction": "nope"},
            {"direction": ["mmr_pull"]},
            {},
            {"direction": "mmr_pull", "x": 1},
            {"direction": "nope"},
            {"direction": "nope"},
        ):
            with self.subTest(body=body):
                response = self.api.post(f"{self.base}test/", body, format="json")
                self.assertEqual(response.status_code, 400)
        self.assertEqual(self.post_test().status_code, 202)

    def test_busy_test_run_reports_waiting_and_ends_at_run_deadline(self) -> None:
        self.disable_pull()
        run = OrgApiSyncRun.objects.get(pk=self.post_test().data["run_id"])
        claim = self.run_claim(run)
        with patch.object(orchestration, "outbound_busy", return_value=2):
            busy = step_run(run.pk, fence=claim.fence)
        self.assertEqual((busy.continuation, busy.error_code), (True, "org_busy"))
        OrgApiSyncRun.objects.filter(pk=run.pk).update(
            created_at=timezone.now() - timedelta(seconds=150)
        )
        run.refresh_from_db()
        self.assertEqual(run.state, "queued")
        self.assertIsNone(run.started_at)
        self.assertEqual(
            orchestration.worker_status(run, timezone.now()), "waiting_for_capacity"
        )
        OrgApiSyncRun.objects.filter(pk=run.pk).update(
            created_at=timezone.now() - timedelta(seconds=RUN_SECONDS + 1)
        )
        assert busy.fence is not None
        remote = FakeRemote([rows((1001, 4000))])
        with patch.object(orchestration, "request_json", side_effect=remote):
            done = step_run(run.pk, fence=busy.fence)
        self.assertEqual(
            (done.continuation, done.error_code), (False, "run_deadline_exceeded")
        )
        self.assertEqual(remote.requests, [])
        run.refresh_from_db()
        self.assertEqual(
            (run.state, run.error_code), ("failed", "run_deadline_exceeded")
        )
        self.assertIsNone(orchestration.worker_status(run, timezone.now()))

    @override_settings(ORG_API_CREDENTIAL_KEYS=json.dumps([OLD_KEY]))
    def test_push_health_test_never_sends_fake_members(self) -> None:
        envelope = seal_credential(
            PUSH_SECRET,
            org_id=self.org.pk,
            connection_id=self.connection.pk,
            origin=f"{ORIGIN}:443",
        )
        OrgApiConnection.objects.filter(pk=self.connection.pk).update(
            enabled=False,
            mmr_pull_enabled=False,
            outbound_auth="bearer",
            outbound_authorizer=None,
            outbound_credential_owner=self.admin,
            outbound_credential_ciphertext=envelope,
            outbound_credential_key_id="old",
        )
        set_org_mmr(self.ou_alice, GAME, 4000, mark_verified=False)
        response = self.post_test("mmr_push")
        self.assertEqual(response.status_code, 202, response.data)
        run = OrgApiSyncRun.objects.get(pk=response.data["run_id"])
        remote = HealthRemote()
        self.drive(
            self.run_claim(run),
            remote,
            target="org.api_connections.orchestration.request_bytes",
        )
        run.refresh_from_db()
        self.assertEqual(run.state, "succeeded", run.error_code)
        [request] = remote.requests
        self.assertEqual(request.method, "GET")
        self.assertEqual(request.url, f"{ORIGIN}/health")
        self.assertIsNone(request.body)
        self.assertEqual(request.query, {})
        self.assertEqual(request.credential, PUSH_SECRET)
        self.assertIsNone(request.idempotency_key)
        self.assertFalse(OrgApiMmrDelivery.objects.exists())
        detail = self.api.get(f"{self.base}runs/{run.pk}/").data
        self.assertIs(detail["health_only"], True)
        self.assertNotIn(PUSH_SECRET, json.dumps(detail, default=str))

        failing = self.post_test("mmr_push")
        run = OrgApiSyncRun.objects.get(pk=failing.data["run_id"])
        self.drive(
            self.run_claim(run),
            HealthRemote(status=401),
            target="org.api_connections.orchestration.request_bytes",
        )
        run.refresh_from_db()
        self.assertEqual((run.state, run.error_code), ("failed", "remote_auth_failed"))


class PullRouteTests(OrchestrationBase):
    def test_manual_pull_deduplicates_and_schedule_defers_first_run(self) -> None:
        first = self.api.post(f"{self.base}pull/", {}, format="json")
        second = self.api.post(f"{self.base}pull/", {}, format="json")
        self.assertEqual(first.status_code, 202, first.data)
        self.assertEqual(first.data["id"], second.data["id"])
        self.assertEqual(
            OrgApiSyncRun.objects.filter(connection=self.connection).count(), 1
        )
        OrgApiSyncRun.objects.update(state="succeeded")

        self.disable_pull()
        patched = self.api.patch(
            self.base,
            {
                "config_version": self.connection.config_version,
                "enabled": True,
                "mmr_pull_enabled": True,
                "interval_minutes": 60,
            },
            format="json",
        )
        self.assertEqual(patched.status_code, 200, patched.data)
        self.connection.refresh_from_db()
        assert self.connection.next_due_at is not None
        due = self.connection.next_due_at - timezone.now()
        self.assertGreater(due, timedelta(minutes=59))
        self.assertEqual(self.connection.outbound_authorizer, self.admin)
        with override_settings(ORG_API_SCHEDULED_PULLS=True):
            self.assertEqual(self.claim(), [])
            self.assertFalse(
                OrgApiSyncRun.objects.filter(state__in=["queued", "running"]).exists()
            )
            claims = self.claim(now=timezone.now() + timedelta(minutes=61))
        run = OrgApiSyncRun.objects.get(state="queued")
        self.assertEqual([c.run_id for c in claims], [run.pk])
        self.assertEqual(run.config_snapshot["trigger"], "scheduled")
        self.assertIsNone(run.requester)

        unchanged = self.api.patch(
            self.base,
            {"config_version": self.connection.config_version + 0, "name": "Renamed"},
            format="json",
        )
        self.assertEqual(unchanged.status_code, 200, unchanged.data)
        self.connection.refresh_from_db()
        self.assertGreater(self.connection.next_due_at, timezone.now())
        off = self.api.patch(
            self.base,
            {
                "config_version": self.connection.config_version,
                "mmr_pull_enabled": False,
            },
            format="json",
        )
        self.assertEqual(off.status_code, 200, off.data)
        self.connection.refresh_from_db()
        self.assertIsNone(self.connection.next_due_at)

    def test_per_member_over_100_requires_acknowledgement(self) -> None:
        self.configure(
            pull={
                "request_mode": "per_member",
                "query": {"id": "{{player.steam_account_id}}"},
            }
        )
        users = [
            CustomUser(username=f"bulk{i}", steam_account_id=50_000 + i)
            for i in range(101)
        ]
        CustomUser.objects.bulk_create(users)
        OrgUser.objects.bulk_create(
            [
                OrgUser(user=user, organization=self.org)
                for user in CustomUser.objects.filter(username__startswith="bulk")
            ]
        )
        refused = self.api.post(f"{self.base}pull/", {}, format="json")
        self.assertEqual(refused.status_code, 400)
        self.assertEqual(refused.data["code"], "per_member_acknowledgement_required")
        self.configure(pull={"acknowledge_per_member": True})
        self.assertEqual(
            self.api.post(f"{self.base}pull/", {}, format="json").status_code, 202
        )

    def test_shared_minute_budget_and_daily_test_cap(self) -> None:
        cache.clear()
        statuses = []
        for index in range(6):
            if index % 2:
                OrgApiSyncRun.objects.update(state="succeeded")
                statuses.append(
                    self.api.post(f"{self.base}pull/", {}, format="json").status_code
                )
            else:
                statuses.append(self.post_test().status_code)
        self.assertEqual(statuses, [202, 202, 202, 202, 202, 429])
        cache.clear()
        with (
            patch("org.api_connections.views.TEST_ACTIONS_PER_DAY", 1),
            patch("org.api_connections.views.MANUAL_ACTIONS_PER_MINUTE", 50),
        ):
            self.assertEqual(self.post_test().status_code, 202)
            self.assertEqual(self.post_test().status_code, 429)

    def test_history_is_bounded_cursor_scoped_and_foreign_404(self) -> None:
        now = timezone.now()
        OrgApiSyncRun.objects.bulk_create(
            [
                OrgApiSyncRun(
                    organization=self.org,
                    connection=self.connection,
                    kind="mmr_pull",
                    state="succeeded",
                    created_at=now - timedelta(minutes=index),
                )
                for index in range(60)
            ]
        )
        first = self.api.get(f"{self.base}runs/")
        self.assertEqual(first.status_code, 200)
        self.assertEqual(len(first.data["items"]), 50)
        self.assertNotIn("config_snapshot", first.data["items"][0])
        self.assertNotIn("issues", first.data["items"][0])
        second = self.api.get(
            f"{self.base}runs/", {"cursor": first.data["next_cursor"]}
        )
        self.assertEqual(len(second.data["items"]), 10)
        self.assertIsNone(second.data["next_cursor"])
        seen = {row["id"] for row in first.data["items"] + second.data["items"]}
        self.assertEqual(len(seen), 60)

        other = OrgApiConnection.objects.create(organization=self.org, name="Other")
        other_url = f"/api/organizations/{self.org.pk}/api-connections/{other.pk}/"
        self.assertEqual(
            self.api.get(
                f"{other_url}runs/", {"cursor": first.data["next_cursor"]}
            ).status_code,
            404,
        )
        self.assertEqual(
            self.api.get(f"{self.base}runs/", {"cursor": "garbage"}).status_code, 404
        )
        self.assertEqual(
            self.api.get(f"{self.base}runs/", {"limit": "5"}).status_code, 400
        )
        run_id = first.data["items"][0]["id"]
        self.assertEqual(self.api.get(f"{other_url}runs/{run_id}/").status_code, 404)
        self.assertEqual(self.api.get(f"{self.base}runs/{uuid4()}/").status_code, 404)
        foreign = APIClient()
        self.other_org.admins.add(self.admin2)
        foreign.force_authenticate(self.member)
        self.assertIn(foreign.get(f"{self.base}runs/").status_code, (403, 404))

    def test_queued_run_reports_worker_unavailable_without_changing_state(self) -> None:
        run = OrgApiSyncRun.objects.create(
            organization=self.org,
            connection=self.connection,
            kind="mmr_pull",
            created_at=timezone.now() - timedelta(minutes=3),
        )
        fresh = OrgApiSyncRun.objects.create(
            organization=self.org, connection=self.connection, kind="test"
        )
        rows_by_id = {
            row["id"]: row for row in self.api.get(f"{self.base}runs/").data["items"]
        }
        self.assertEqual(rows_by_id[str(run.pk)]["worker_status"], "worker_unavailable")
        self.assertEqual(rows_by_id[str(run.pk)]["state"], "queued")
        self.assertIsNone(rows_by_id[str(fresh.pk)]["worker_status"])
        run.refresh_from_db()
        self.assertEqual(run.state, "queued")


class FenceTests(OrchestrationBase):
    def test_expired_fence_cannot_finalize(self) -> None:
        run = self.api.post(f"{self.base}pull/", {}, format="json").data
        claim = self.run_claim(OrgApiSyncRun.objects.get(pk=run["id"]))

        def expire(request: SafeHttpRequest, **_: Any) -> Any:
            OrgApiSyncRun.objects.filter(pk=claim.run_id).update(
                lease_expires_at=timezone.now() - timedelta(seconds=1)
            )
            return FakeRemote([rows((1001, 4000))])(request, **_)

        results = self.drive(claim, expire)
        self.assertEqual(results[-1].error_code, "stale_fence")
        state = OrgApiSyncRun.objects.get(pk=claim.run_id)
        self.assertIn(state.state, ("queued", "running"))
        self.assertEqual(self.mmr(self.ou_alice), 0)
        self.assertFalse(OrgApiMmrPullTarget.objects.exists())

        [again] = [c for c in self.claim() if c.run_id == claim.run_id]
        self.assertNotEqual(again.fence, claim.fence)
        self.drive(again, FakeRemote([rows((1001, 4000))]))
        state.refresh_from_db()
        self.assertEqual(state.state, "succeeded", state.error_code)
        self.assertEqual(self.mmr(self.ou_alice), 4000)

    def test_role_config_membership_loss_after_io_prevents_commit(self) -> None:
        def demote() -> None:
            self.org.admins.remove(self.admin)

        def bump() -> None:
            OrgApiConnection.objects.filter(pk=self.connection.pk).update(
                config_version=99
            )

        def leave() -> None:
            OrgUser.objects.filter(pk=self.ou_alice.pk).delete()

        cases = (
            (demote, "canceled", "authority_lost"),
            (bump, "canceled", "configuration_changed"),
            (leave, "succeeded", ""),
        )
        for mutate, state, code in cases:
            with self.subTest(mutate=mutate.__name__):
                OrgApiSyncRun.objects.filter(
                    state__in=["queued", "running", "partial"]
                ).update(state="canceled")
                run = self.api.post(f"{self.base}pull/", {}, format="json").data
                claim = self.run_claim(OrgApiSyncRun.objects.get(pk=run["id"]))
                fake = FakeRemote([rows((1001, 4100), (1002, 4200))])

                def remote(request: SafeHttpRequest, **kwargs: Any) -> Any:
                    response = fake(request, **kwargs)
                    mutate()
                    return response

                self.drive(claim, remote)
                finished = OrgApiSyncRun.objects.get(pk=claim.run_id)
                self.assertEqual((finished.state, finished.error_code), (state, code))
                self.assertFalse(
                    OrgUserGameMmr.objects.filter(game_type=GAME, mmr=4100).exists()
                )
                if mutate is leave:
                    self.assertEqual(self.mmr(self.ou_bob), 4200)
                else:
                    self.assertEqual(self.mmr(self.ou_bob), 0)
                if mutate is demote:
                    self.connection.refresh_from_db()
                    self.assertFalse(self.connection.mmr_pull_enabled)
                    self.org.admins.add(self.admin)
                    OrgApiConnection.objects.filter(pk=self.connection.pk).update(
                        mmr_pull_enabled=True, outbound_authorizer=self.admin
                    )
                if mutate is bump:
                    OrgApiConnection.objects.filter(pk=self.connection.pk).update(
                        config_version=1
                    )
                self.connection.refresh_from_db()

    def test_lost_wakeup_and_duplicate_task_resume_same_step(self) -> None:
        self.configure(pull={"pagination": {"kind": "page", "page_size": 2}})
        run = self.api.post(f"{self.base}pull/", {}, format="json").data
        claim = self.run_claim(OrgApiSyncRun.objects.get(pk=run["id"]))
        remote = FakeRemote([rows((1001, 4000), (1002, 4100)), rows((1004, 4200))])
        with patch("org.api_connections.pull.request_json", side_effect=remote):
            first = step_run(claim.run_id, fence=claim.fence)
            self.assertTrue(first.continuation)
            assert first.fence is not None
            duplicate = step_run(claim.run_id, fence=claim.fence)
            self.assertEqual(
                (duplicate.continuation, duplicate.error_code), (False, "stale_fence")
            )
            second = step_run(claim.run_id, fence=first.fence)
            self.assertTrue(second.continuation)
        self.assertEqual(len(remote.requests), 1)
        OrgApiSyncRun.objects.filter(pk=claim.run_id).update(
            lease_expires_at=timezone.now() - timedelta(seconds=1)
        )
        assert second.fence is not None
        self.assertEqual(
            step_run(claim.run_id, fence=second.fence).error_code, "stale_fence"
        )
        [recovered] = [c for c in self.claim() if c.run_id == claim.run_id]
        self.drive(recovered, remote)
        finished = OrgApiSyncRun.objects.get(pk=claim.run_id)
        self.assertEqual(finished.state, "succeeded", finished.error_code)
        self.assertEqual(len(remote.requests), 2)
        self.assertEqual(finished.request_count, 2)
        self.assertEqual(
            [self.mmr(m) for m in (self.ou_alice, self.ou_bob, self.ou_carol)],
            [4000, 4100, 4200],
        )

    def test_internal_retry_cannot_duplicate_post_pull(self) -> None:
        self.configure(pull={"method": "POST", "body": {"org": "{{org.id}}"}})
        run = self.api.post(f"{self.base}pull/", {}, format="json").data
        claim = self.run_claim(OrgApiSyncRun.objects.get(pk=run["id"]))
        remote = FakeRemote([rows((1001, 4000))])
        with patch("org.api_connections.pull.request_json", side_effect=remote):
            snapshot = step_run(claim.run_id, fence=claim.fence)
        assert snapshot.fence is not None

        def crash(request: SafeHttpRequest, **kwargs: Any) -> Any:
            remote(request, **kwargs)
            raise KeyboardInterrupt

        with patch("org.api_connections.pull.request_json", side_effect=crash):
            with self.assertRaises(KeyboardInterrupt):
                step_run(claim.run_id, fence=snapshot.fence)
        OrgApiSyncRun.objects.filter(pk=claim.run_id).update(
            lease_expires_at=timezone.now() - timedelta(seconds=1)
        )
        [again] = [c for c in self.claim() if c.run_id == claim.run_id]
        results = self.drive(again, remote)
        self.assertEqual(results[-1].error_code, "pull_ambiguous")
        self.assertEqual(len(remote.requests), 1)
        self.assertEqual(self.mmr(self.ou_alice), 0)

    def test_org_outbound_concurrency_never_exceeds_two(self) -> None:
        others = [
            OrgApiConnection.objects.create(
                organization=self.org,
                name=f"Pull {index}",
                enabled=True,
                mmr_pull_enabled=True,
                outbound_base_url=ORIGIN,
                outbound_auth="none",
                outbound_authorizer=self.admin,
                game_type=int(GAME),
                mmr_pull_config={"path": "/players"},
            )
            for index in range(2)
        ]
        runs = [
            orchestration.enqueue_manual_pull(connection, requester=self.admin)
            for connection in (self.connection, *others)
        ]
        claims = {c.run_id: c for c in self.claim()}
        fences: dict[UUID, UUID] = {}
        for run in runs:
            result = step_run(run.pk, fence=claims[run.pk].fence)
            assert result.fence is not None
            fences[run.pk] = result.fence
        OrgApiRunCheckpoint.objects.filter(run__in=runs[:2]).update(
            phase="fetch_inflight"
        )
        remote = FakeRemote([rows((1001, 4000))])
        with patch("org.api_connections.pull.request_json", side_effect=remote):
            busy = step_run(runs[2].pk, fence=fences[runs[2].pk])
        self.assertEqual((busy.continuation, busy.error_code), (True, "org_busy"))
        self.assertEqual(remote.requests, [])
        set_org_mmr(self.ou_alice, GAME, 1, mark_verified=False)
        OrgApiConnection.objects.filter(pk=others[0].pk).update(mmr_push_enabled=True)
        delivery = OrgApiMmrDelivery.objects.create(
            connection=others[0],
            org_user=self.ou_alice,
            game_type=GAME,
            revision=999,
            payload={"org_id": self.org.pk},
            config_version=others[0].config_version,
            destination_origin=f"{ORIGIN}:443",
        )
        self.assertIsNone(acquire_delivery_lease(delivery.delivery_id))
        OrgApiRunCheckpoint.objects.filter(run=runs[0]).update(phase="fetch")
        self.assertIsNotNone(acquire_delivery_lease(delivery.delivery_id))

    def test_step_honours_request_and_step_deadlines(self) -> None:
        self.assertGreater(STEP_SECONDS, REQUEST_SECONDS)
        self.assertGreater(CLIENT_TIMEOUT_SECONDS, STEP_SECONDS)
        run = self.api.post(f"{self.base}pull/", {}, format="json").data
        claim = self.run_claim(OrgApiSyncRun.objects.get(pk=run["id"]))
        deadlines: list[float] = []

        def slow(request: SafeHttpRequest, *, deadline: float, max_bytes: int) -> Any:
            deadlines.append(deadline - time.monotonic())
            time.sleep(0.2)
            raise SafeHttpError("deadline_exceeded")

        started = time.monotonic()
        results = self.drive(claim, slow)
        self.assertLess(time.monotonic() - started, STEP_SECONDS)
        self.assertEqual(results[-1].error_code, "deadline_exceeded")
        self.assertTrue(all(0 < left <= REQUEST_SECONDS for left in deadlines))


class ScheduleTests(OrchestrationBase):
    def setUp(self) -> None:
        super().setUp()
        OrgApiConnection.objects.filter(pk=self.connection.pk).update(
            interval_minutes=15,
            next_due_at=timezone.now() - timedelta(days=10),
        )

    def test_schedule_missed_runs_coalesce_and_test_stacks_skip(self) -> None:
        with override_settings(ORG_API_SCHEDULED_PULLS=False):
            self.assertEqual(self.claim(), [])
        self.assertFalse(OrgApiSyncRun.objects.exists())
        with override_settings(ORG_API_SCHEDULED_PULLS=True):
            now = timezone.now()
            claims = self.claim(now=now)
            self.assertEqual(len(claims), 1)
            self.assertEqual(self.claim(now=now), [])
        self.assertEqual(OrgApiSyncRun.objects.count(), 1)
        self.connection.refresh_from_db()
        self.assertEqual(self.connection.next_due_at, now + timedelta(minutes=15))
        manual = self.api.post(f"{self.base}pull/", {}, format="json")
        self.assertEqual(manual.status_code, 202)
        self.assertEqual(OrgApiSyncRun.objects.count(), 1)

    @override_settings(ORG_API_SCHEDULED_PULLS=True)
    def test_unexpected_schedule_error_skips_only_that_connection(self) -> None:
        other = OrgApiConnection.objects.create(
            organization=self.org,
            name="Second pull",
            enabled=True,
            mmr_pull_enabled=True,
            outbound_base_url=ORIGIN,
            outbound_auth="none",
            outbound_authorizer=self.admin,
            game_type=int(GAME),
            mmr_pull_config={"path": "/players"},
            interval_minutes=15,
            next_due_at=timezone.now() - timedelta(days=11),
        )
        real = orchestration.create_pull_run

        def explode(connection: OrgApiConnection, **kwargs: Any) -> OrgApiSyncRun:
            if connection.pk == other.pk:
                raise OperationalError("database is locked")
            return real(connection, **kwargs)

        with patch.object(orchestration, "create_pull_run", side_effect=explode):
            self.assertEqual(schedule_due_pulls(now=timezone.now(), limit=20), 1)
        self.assertEqual(
            list(OrgApiSyncRun.objects.values_list("connection_id", flat=True)),
            [self.connection.pk],
        )
        with patch.object(
            orchestration, "schedule_due_pulls", side_effect=OperationalError("x")
        ):
            claims = self.claim()
        self.assertEqual(len(claims), 1)

    @override_settings(ORG_API_SCHEDULED_PULLS=True)
    def test_scheduled_auth_none_pull_rechecks_authorizer(self) -> None:
        for loss in ("demote", "delete"):
            with self.subTest(loss=loss):
                authorizer = CustomUser.objects.create_user(
                    username=f"authorizer-{loss}", password="x"
                )
                self.org.admins.add(authorizer)
                OrgApiConnection.objects.filter(pk=self.connection.pk).update(
                    enabled=True,
                    mmr_pull_enabled=True,
                    outbound_authorizer=authorizer,
                    next_due_at=timezone.now() - timedelta(minutes=1),
                )
                [claim] = self.claim()
                run = OrgApiSyncRun.objects.get(pk=claim.run_id)
                self.assertIsNone(run.requester)
                self.assertEqual(run.config_snapshot["trigger"], "scheduled")
                if loss == "demote":
                    self.org.admins.remove(authorizer)
                else:
                    authorizer.delete()
                remote = FakeRemote([rows((1001, 4000))])
                results = self.drive(claim, remote)
                run.refresh_from_db()
                self.assertEqual(
                    (run.state, run.error_code), ("canceled", "authority_lost")
                )
                self.assertEqual(results[-1].error_code, "authority_lost")
                self.assertEqual(remote.requests, [])
                self.assertEqual(self.mmr(self.ou_alice), 0)
                self.connection.refresh_from_db()
                self.assertFalse(self.connection.mmr_pull_enabled)
                self.assertIsNone(self.connection.outbound_authorizer_id)
                self.assertIsNone(self.connection.next_due_at)


@override_settings(INTERNAL_SERVICE_TOKEN=TOKEN)
class InternalRouteTests(OrchestrationBase):
    def internal(self, path: str, body: dict[str, Any], **headers: str) -> Any:
        return APIClient().post(
            f"/api/internal/org-api-sync/{path}", body, format="json", **headers
        )

    def authed(self, path: str, body: dict[str, Any]) -> Any:
        return self.internal(path, body, HTTP_X_INTERNAL_TOKEN=TOKEN)

    def test_internal_auth_and_timeout_contract(self) -> None:
        session = APIClient()
        session.force_authenticate(self.admin)
        for path in ("claim/", f"runs/{uuid4()}/step/", "cleanup/", "promotion/step/"):
            with self.subTest(path=path):
                self.assertEqual(self.internal(path, {}).status_code, 403)
                self.assertEqual(
                    self.internal(path, {}, HTTP_X_INTERNAL_TOKEN="wrong").status_code,
                    403,
                )
                self.assertEqual(
                    session.post(
                        f"/api/internal/org-api-sync/{path}", {}, format="json"
                    ).status_code,
                    403,
                )
        run = self.api.post(f"{self.base}pull/", {}, format="json").data
        claimed = self.authed("claim/", {"limit": 5})
        self.assertEqual(claimed.status_code, 200, claimed.data)
        self.assertEqual(set(claimed.data), {"claims", "promotion_due"})
        [claim] = claimed.data["claims"]
        self.assertEqual(set(claim), {"kind", "id", "fence"})
        self.assertEqual((claim["kind"], claim["id"]), ("run", run["id"]))
        stale = self.authed(f"runs/{run['id']}/step/", {"fence": str(uuid4())})
        self.assertEqual(stale.status_code, 200)
        self.assertEqual(
            stale.data,
            {
                "state": "queued",
                "continuation": False,
                "error_code": "stale_fence",
                "fence": None,
            },
        )
        stepped = self.authed(f"runs/{run['id']}/step/", {"fence": claim["fence"]})
        self.assertEqual(
            set(stepped.data), {"state", "continuation", "error_code", "fence"}
        )
        self.assertTrue(stepped.data["continuation"])
        self.assertEqual(
            self.authed(f"runs/{uuid4()}/step/", {"fence": str(uuid4())}).status_code,
            404,
        )
        self.assertEqual(
            self.authed(f"runs/{run['id']}/step/", {"fence": "nope"}).status_code, 400
        )
        self.assertEqual(self.authed("claim/", {"limit": 500}).status_code, 400)

        with patch.object(internal_views, "STEP_SLOTS") as slots:
            slots.acquire.return_value = False
            busy = self.authed(f"runs/{run['id']}/step/", {"fence": str(uuid4())})
        self.assertEqual(busy.status_code, 429)
        self.assertEqual(busy.data, {"code": "busy"})

        with patch("app.internal_client.transport.requests.post") as post:
            post.return_value = MagicMock(ok=True, status_code=200)
            post.return_value.json.return_value = {"claims": [], "promotion_due": False}
            sync_client.claim(limit=3)
        self.assertEqual(post.call_args.kwargs["timeout"], CLIENT_TIMEOUT_SECONDS)
        self.assertTrue(post.call_args.args[0].endswith("/org-api-sync/claim/"))
        self.assertEqual(transport.TIMEOUT, CLIENT_TIMEOUT_SECONDS)

    def test_delivery_step_rotates_fence(self) -> None:
        OrgApiConnection.objects.filter(pk=self.connection.pk).update(
            mmr_push_enabled=True
        )
        delivery = OrgApiMmrDelivery.objects.create(
            connection=self.connection,
            org_user=self.ou_alice,
            game_type=GAME,
            revision=5,
            payload={"org_id": self.org.pk},
            config_version=self.connection.config_version + 1,
            destination_origin=f"{ORIGIN}:443",
        )
        [claim] = [c for c in self.claim() if c.kind == "mmr_delivery"]
        self.assertEqual(claim.run_id, delivery.delivery_id)
        result = step_delivery(claim.run_id, fence=claim.fence)
        self.assertEqual(
            (result.state, result.error_code), ("paused", "configuration_changed")
        )
        again = step_delivery(claim.run_id, fence=claim.fence)
        self.assertEqual(again.error_code, "stale_fence")
        delivery.refresh_from_db()
        self.assertEqual(delivery.attempts, 1)

    def test_light_tasks_carry_ids_only_and_chain_continuations(self) -> None:
        fence = str(uuid4())
        replies = [
            {
                "state": "running",
                "continuation": True,
                "error_code": None,
                "fence": fence,
            },
            {
                "state": "succeeded",
                "continuation": False,
                "error_code": None,
                "fence": None,
            },
        ]
        with patch.object(sync_client, "step", side_effect=replies) as step:
            result = tasks_org_api_sync.org_api_sync_step("run-1", "fence-0")
        self.assertEqual(
            [c.args for c in step.call_args_list],
            [("run", "run-1", "fence-0"), ("run", "run-1", fence)],
        )
        self.assertEqual(
            result,
            {
                "run_id": "run-1",
                "kind": "run",
                "state": "running",
                "continuation": True,
                "error_code": None,
            },
        )
        claims = {
            "claims": [{"kind": "mmr_delivery", "id": "d-1", "fence": "f-1"}],
            "promotion_due": False,
        }
        with (
            patch.object(sync_client, "claim", return_value=claims),
            patch.object(tasks_org_api_sync.org_api_sync_step, "delay") as delay,
        ):
            summary = tasks_org_api_sync.org_api_sync_sweep()
        delay.assert_called_once_with("d-1", "f-1", kind="mmr_delivery")
        self.assertEqual(summary, {"claimed": 1, "promotion_due": False})

    def test_promotion_step_targets_only_enabled_adopted_orgs(self) -> None:
        with patch.object(orchestration, "dispatch_due") as dispatch:
            result = self.authed("promotion/step/", {})
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.data["continuation"], False)
        dispatch.assert_not_called()


class RetentionTests(OrchestrationBase):
    def test_retention_cascades_checkpoints_not_domain_history(self) -> None:
        old = timezone.now() - timedelta(days=91)
        run, _, _ = self.run_pull([rows((1001, 4000))])
        stale_active = OrgApiSyncRun.objects.create(
            organization=self.org,
            connection=self.connection,
            kind="test",
            created_at=old,
        )
        OrgApiSyncRun.objects.filter(pk=run.pk).update(finished_at=old, created_at=old)
        OrgApiRunCheckpoint.objects.get_or_create(run=run)
        recent, _, _ = self.run_pull([rows((1002, 4100))])
        logs = OrgLog.objects.filter(details__source="api_pull").count()
        self.assertTrue(OrgApiMmrPullTarget.objects.filter(run=run).exists())

        out = StringIO()
        call_command("cleanup_org_api_runs", "--dry-run", stdout=out)
        self.assertIn("1", out.getvalue())
        self.assertTrue(OrgApiSyncRun.objects.filter(pk=run.pk).exists())

        self.assertEqual(purge_expired_runs(now=timezone.now()), 1)
        self.assertFalse(OrgApiSyncRun.objects.filter(pk=run.pk).exists())
        self.assertFalse(OrgApiRunCheckpoint.objects.filter(run_id=run.pk).exists())
        self.assertFalse(OrgApiMmrPullTarget.objects.filter(run_id=run.pk).exists())
        self.assertTrue(OrgApiSyncRun.objects.filter(pk=recent.pk).exists())
        self.assertTrue(OrgApiSyncRun.objects.filter(pk=stale_active.pk).exists())
        young = OrgApiSyncRun.objects.create(
            organization=self.org,
            connection=self.connection,
            kind="mmr_pull",
            created_at=timezone.now() - timedelta(seconds=ABANDON_SECONDS - 60),
        )
        claimed = {claim.run_id for claim in self.claim()}
        stale_active.refresh_from_db()
        self.assertEqual(
            (stale_active.state, stale_active.error_code), ("failed", "run_abandoned")
        )
        self.assertIsNotNone(stale_active.finished_at)
        self.assertNotIn(stale_active.pk, claimed)
        self.assertIn(young.pk, claimed)
        self.assertGreater(ABANDON_SECONDS, RUN_SECONDS)
        self.assertEqual(
            OrgLog.objects.filter(details__source="api_pull").count(), logs
        )
        self.assertEqual(self.mmr(self.ou_alice), 4000)

        with override_settings(INTERNAL_SERVICE_TOKEN=TOKEN):
            response = APIClient().post(
                "/api/internal/org-api-sync/cleanup/",
                {},
                format="json",
                HTTP_X_INTERNAL_TOKEN=TOKEN,
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, {"deleted": 0})
        self.assertGreaterEqual(LEASE_SECONDS, STEP_SECONDS)
