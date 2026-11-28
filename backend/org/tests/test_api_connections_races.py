import json
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any
from unittest import skipUnless
from unittest.mock import patch

from django.db import connection, connections, transaction
from django.test import TransactionTestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from app.models import CustomUser
from common.game import GameType
from config.promotion_sync import OrgPromotionBinding, PromotionSyncConfig
from events.models import Event
from org.api_connections import tls_adapter
from org.api_connections.lifecycle import ConnectionConflict, issue_connection_key
from org.api_connections.mutations import MmrMutationContext, MmrRevisionConflict
from org.api_connections.promotion_config import (
    PromotionStreamError,
    adopt_legacy_promotion,
    set_promotion_binding,
)
from org.api_connections.pull import create_pull_run
from org.api_connections.push import acquire_delivery_lease
from org.api_connections.revisions import next_revision
from org.api_tokens.sync import SyncResult, sync_mmrs
from org.features import FeatureKey, set_org_feature
from org.mmr import mark_org_mmr_verified, merge_org_mmrs, set_org_mmr
from org.models import (
    Organization,
    OrgApiConnection,
    OrgApiMmrDelivery,
    OrgApiPromotionAdoption,
    OrgApiPromotionBinding,
    OrgApiPromotionEventBinding,
    OrgApiSyncRun,
    OrgApiToken,
    OrgMmrRevisionCounter,
    OrgMmrSyncState,
    OrgUser,
    OrgUserGameMmr,
)
from org.tests.test_api_connections_crypto import OLD_KEY


@skipUnless(connection.vendor == "postgresql", "Requires PostgreSQL row locks")
class ConnectionKeyRaceTests(TransactionTestCase):
    def test_concurrent_issue_rotate_single_usable_credential(self) -> None:
        owner = CustomUser.objects.create_user(username="race-admin")
        org = Organization.objects.create(name="Race Org", owner=owner)
        set_org_feature(org, FeatureKey.MMR_SYNC, enabled=True, actor=None)
        for rotate in (False, True):
            with self.subTest(rotate=rotate):
                connection_row = OrgApiConnection.objects.create(
                    organization=org,
                    name="Race",
                    operations=["mmr:read"],
                    enabled=True,
                    inbound_enabled=True,
                )
                barrier = threading.Barrier(2, timeout=10)

                def worker(rotate_key: bool) -> tuple[int | None, str]:
                    try:
                        snapshot = OrgApiConnection.objects.get(pk=connection_row.pk)
                        actor = CustomUser.objects.get(pk=owner.pk)
                        barrier.wait()
                        try:
                            token, raw = issue_connection_key(
                                snapshot, actor=actor, rotate=rotate_key
                            )
                            return token.pk, raw
                        except ConnectionConflict as exc:
                            self.assertEqual(exc.status_code, 409)
                            self.assertEqual(
                                str(exc.detail["code"]), "configuration_changed"
                            )
                            return None, "configuration_changed"
                    finally:
                        connections.close_all()

                with ThreadPoolExecutor(max_workers=2) as pool:
                    futures = [pool.submit(worker, False), pool.submit(worker, rotate)]
                    results = [future.result(timeout=30) for future in futures]
                winners = [(pk, raw) for pk, raw in results if pk is not None]
                self.assertEqual(len(winners), 1, results)
                self.assertEqual(sum(pk is None for pk, _ in results), 1)
                self.assertEqual(
                    OrgApiToken.objects.filter(
                        connection=connection_row,
                        revoked_at__isnull=True,
                        legacy_credential=False,
                    ).count(),
                    1,
                )
                client = APIClient()
                client.credentials(HTTP_AUTHORIZATION=f"Bearer {winners[0][1]}")
                self.assertEqual(
                    client.get(f"/api/organizations/{org.pk}/mmr-sync/").status_code,
                    200,
                )


@skipUnless(connection.vendor == "postgresql", "Requires PostgreSQL row locks")
class MmrMutationRaceTests(TransactionTestCase):
    def setUp(self) -> None:
        self.owner = CustomUser.objects.create_user(username="mmr-race-admin")
        self.user = CustomUser.objects.create_user(username="mmr-race-player")
        self.org = Organization.objects.create(name="MMR Race", owner=self.owner)
        self.member = OrgUser.objects.create(organization=self.org, user=self.user)
        self.game = GameType.DOTA2

    def test_first_row_writes_share_membership_lock(self) -> None:
        barrier = threading.Barrier(2, timeout=10)

        def write(value: int) -> None:
            try:
                member = OrgUser.objects.get(pk=self.member.pk)
                barrier.wait()
                set_org_mmr(member, self.game, value, mark_verified=False)
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(write, value) for value in (4000, 5000)]
            for future in futures:
                future.result(timeout=30)
        state = OrgMmrSyncState.objects.get(org_user=self.member, game_type=self.game)
        self.assertEqual(state.revision, 2)
        self.assertEqual(
            OrgUserGameMmr.objects.get(org_user=self.member, game_type=self.game).mmr,
            state.value,
        )
        self.assertEqual(
            OrgMmrRevisionCounter.objects.get(
                organization=self.org, game_type=self.game
            ).revision,
            2,
        )

    def test_verify_during_import_advances_revision(self) -> None:
        set_org_mmr(self.member, self.game, 4000, mark_verified=False)
        expected = OrgMmrSyncState.objects.get(
            org_user=self.member, game_type=self.game
        ).revision
        ready = threading.Event()

        def import_value() -> str:
            try:
                member = OrgUser.objects.get(pk=self.member.pk)
                ready.set()
                try:
                    set_org_mmr(
                        member,
                        self.game,
                        5000,
                        mark_verified=False,
                        sync_context=MmrMutationContext(expected_revision=expected),
                    )
                except MmrRevisionConflict:
                    return "conflict"
                return "applied"
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=1) as pool:
            with transaction.atomic():
                OrgUser.objects.select_for_update().get(pk=self.member.pk)
                future = pool.submit(import_value)
                self.assertTrue(ready.wait(timeout=10))
                mark_org_mmr_verified(self.member, self.game, self.owner)
            self.assertEqual(future.result(timeout=30), "conflict")
        state = OrgMmrSyncState.objects.get(org_user=self.member, game_type=self.game)
        self.assertGreater(state.revision, expected)
        self.assertEqual(state.value, 4000)
        self.assertIsNotNone(state.verified_at)

    def test_inbound_identity_matching_rereads_after_membership_lock(self) -> None:
        self.user.steam_account_id = 12345
        self.user.save(update_fields=["steam_account_id"])
        attempted = threading.Event()

        def import_value() -> SyncResult:
            def observe(
                execute: Callable[..., Any],
                sql: str,
                params: Any,
                many: bool,
                context: dict[str, Any],
            ) -> Any:
                if '"org_orguser"' in sql and "FOR UPDATE" in sql:
                    attempted.set()
                return execute(sql, params, many, context)

            try:
                with connections["default"].execute_wrapper(observe):
                    return sync_mmrs(
                        self.org,
                        self.owner,
                        [{"steam_id": 12345, "mmr": 5000}],
                        mark_verified=False,
                    )
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=1) as pool:
            with transaction.atomic():
                OrgUser.objects.select_for_update().get(pk=self.member.pk)
                future = pool.submit(import_value)
                self.assertTrue(attempted.wait(timeout=10))
                self.user.steam_account_id = 22222
                self.user.save(update_fields=["steam_account_id"])
            result = future.result(timeout=30)
        self.assertEqual(result.updated, 0)
        self.assertEqual(len(result.unmatched), 1)
        self.assertFalse(OrgUserGameMmr.objects.filter(org_user=self.member).exists())

    def test_membership_delete_locks_before_collecting_concurrent_mmr(self) -> None:
        self._delete_while_writing(account=False)

    def test_account_delete_locks_before_collecting_concurrent_mmr(self) -> None:
        self._delete_while_writing(account=True)

    def test_org_delete_locks_before_collecting_concurrent_mmr(self) -> None:
        self._delete_while_writing(account=False, organization=True)

    def _delete_while_writing(
        self, *, account: bool, organization: bool = False
    ) -> None:
        attempted = threading.Event()

        def remove() -> None:
            def observe(
                execute: Callable[..., Any],
                sql: str,
                params: Any,
                many: bool,
                context: dict[str, Any],
            ) -> Any:
                if sql.startswith('DELETE FROM "org_orguser" ') or (
                    '"org_orguser"' in sql and "FOR UPDATE" in sql
                ):
                    attempted.set()
                return execute(sql, params, many, context)

            try:
                with connections["default"].execute_wrapper(observe):
                    if organization:
                        self.org.delete()
                    elif account:
                        client = APIClient()
                        actor = CustomUser.objects.create_superuser(
                            username="delete-race-admin", password="testpass"
                        )
                        client.force_authenticate(actor)
                        response = client.delete(f"/api/users/{self.user.pk}/")
                        self.assertEqual(response.status_code, 204)
                    else:
                        OrgUser.objects.filter(pk=self.member.pk).delete()
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=1) as pool:
            with transaction.atomic():
                OrgUser.objects.select_for_update().get(pk=self.member.pk)
                future = pool.submit(remove)
                self.assertTrue(attempted.wait(timeout=10))
                set_org_mmr(self.member, self.game, 5000, mark_verified=False)
            future.result(timeout=30)
        self.assertFalse(OrgUser.objects.filter(pk=self.member.pk).exists())
        self.assertFalse(
            OrgMmrSyncState.objects.filter(org_user_id=self.member.pk).exists()
        )

    def test_rejoin_and_merge_never_reuse_revision(self) -> None:
        set_org_mmr(self.member, self.game, 4000, mark_verified=False)
        before = OrgMmrSyncState.objects.get(
            org_user=self.member, game_type=self.game
        ).revision
        stale = OrgUser.objects.get(pk=self.member.pk)
        self.member.delete()
        self.member = OrgUser.objects.create(organization=self.org, user=self.user)
        set_org_mmr(self.member, self.game, 4500, mark_verified=False)
        keeper_user = CustomUser.objects.create_user(username="mmr-race-keeper")
        keeper = OrgUser.objects.create(organization=self.org, user=keeper_user)
        barrier = threading.Barrier(2, timeout=10)

        def merge() -> None:
            try:
                barrier.wait()
                merge_org_mmrs(self.member, keeper)
            finally:
                connections.close_all()

        def stale_write() -> None:
            try:
                barrier.wait()
                with self.assertRaises(OrgUser.DoesNotExist):
                    set_org_mmr(stale, self.game, 6000, mark_verified=False)
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(merge), pool.submit(stale_write)]
            for future in futures:
                future.result(timeout=30)
        state = OrgMmrSyncState.objects.get(org_user=keeper, game_type=self.game)
        self.assertGreater(state.revision, before)
        self.assertEqual(state.value, 4500)


@skipUnless(connection.vendor == "postgresql", "Requires PostgreSQL row locks")
class IdentityRevisionRaceTests(TransactionTestCase):
    def test_shared_org_identity_changes_do_not_deadlock(self) -> None:
        owner = CustomUser.objects.create_user(username="identity-race-admin")
        orgs = [
            Organization.objects.create(name=f"Identity Race {n}", owner=owner)
            for n in (1, 2)
        ]
        first = CustomUser.objects.create_user(
            username="identity-race-a", discordId="987654321012345601"
        )
        second = CustomUser.objects.create_user(
            username="identity-race-b", discordId="987654321012345602"
        )
        memberships = [
            OrgUser.objects.create(organization=orgs[0], user=first),
            OrgUser.objects.create(organization=orgs[1], user=second),
            OrgUser.objects.create(organization=orgs[1], user=first),
            OrgUser.objects.create(organization=orgs[0], user=second),
        ]
        for member in memberships:
            set_org_mmr(member, GameType.DOTA2, 4000, mark_verified=False)
        barrier = threading.Barrier(2, timeout=3)
        allocations = threading.local()

        def allocate(organization_id: int, game_type: int) -> int:
            revision = next_revision(organization_id, game_type)
            if not getattr(allocations, "seen", False):
                allocations.seen = True
                try:
                    barrier.wait()
                except threading.BrokenBarrierError:
                    pass
            return revision

        def change(user_id: int, discord_id: str) -> None:
            try:
                user = CustomUser.objects.get(pk=user_id)
                user.discordId = discord_id
                user.save(update_fields=["discordId"])
            finally:
                connections.close_all()

        with patch("org.api_connections.revisions.next_revision", allocate):
            with ThreadPoolExecutor(max_workers=2) as pool:
                futures = [
                    pool.submit(change, first.pk, "987654321012345611"),
                    pool.submit(change, second.pk, "987654321012345612"),
                ]
                for future in futures:
                    future.result(timeout=30)
        states = OrgMmrSyncState.objects.filter(game_type=GameType.DOTA2)
        self.assertEqual(states.count(), 4)
        self.assertEqual(
            sorted(
                OrgMmrRevisionCounter.objects.filter(
                    game_type=GameType.DOTA2
                ).values_list("revision", flat=True)
            ),
            [4, 4],
        )


@skipUnless(connection.vendor == "postgresql", "Requires PostgreSQL row locks")
class PullRunRaceTests(TransactionTestCase):
    def test_concurrent_create_pull_run_returns_same_active_run(self) -> None:
        owner = CustomUser.objects.create_user(username="pull-race-admin")
        org = Organization.objects.create(name="Pull Race", owner=owner)
        org.admins.add(owner)
        set_org_feature(org, FeatureKey.MMR_SYNC, enabled=True, actor=None)
        connection_row = OrgApiConnection.objects.create(
            organization=org,
            name="Pull race",
            enabled=True,
            mmr_pull_enabled=True,
            outbound_base_url="https://sync.example.test",
            outbound_authorizer=owner,
            game_type=GameType.DOTA2,
        )
        barrier = threading.Barrier(2, timeout=10)

        def create() -> str:
            try:
                snapshot = OrgApiConnection.objects.get(pk=connection_row.pk)
                actor = CustomUser.objects.get(pk=owner.pk)
                barrier.wait()
                return str(create_pull_run(snapshot, requester=actor).pk)
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(create) for _ in range(2)]
            run_ids = [future.result(timeout=30) for future in futures]
        self.assertEqual(run_ids[0], run_ids[1])
        self.assertEqual(
            OrgApiSyncRun.objects.filter(
                connection=connection_row,
                kind="mmr_pull",
                state__in=["queued", "running", "partial"],
            ).count(),
            1,
        )


@skipUnless(connection.vendor == "postgresql", "Requires PostgreSQL row locks")
class MmrDeliveryLeaseRaceTests(TransactionTestCase):
    def setUp(self) -> None:
        owner = CustomUser.objects.create_user(username="push-race-admin")
        self.org = Organization.objects.create(name="Push Race", owner=owner)
        self.org.admins.add(owner)
        set_org_feature(self.org, FeatureKey.MMR_SYNC, enabled=True, actor=None)
        self.connections = [
            OrgApiConnection.objects.create(
                organization=self.org,
                name=f"Push race {index}",
                enabled=True,
                mmr_push_enabled=True,
                outbound_base_url="https://push.example.test",
                outbound_authorizer=owner,
                game_type=GameType.DOTA2,
            )
            for index in range(3)
        ]
        player = CustomUser.objects.create_user(
            username="push-race-player", steam_account_id=4242
        )
        member = OrgUser.objects.create(organization=self.org, user=player)
        set_org_mmr(member, GameType.DOTA2, 4000, mark_verified=False)

    def acquire_all(self, delivery_ids: list[object]) -> list[object]:
        barrier = threading.Barrier(len(delivery_ids), timeout=10)

        def acquire(delivery_id: object) -> object:
            try:
                barrier.wait()
                return acquire_delivery_lease(delivery_id)
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=len(delivery_ids)) as pool:
            futures = [pool.submit(acquire, value) for value in delivery_ids]
            return [future.result(timeout=30) for future in futures]

    def test_concurrent_connections_share_two_request_org_semaphore(self) -> None:
        ids = list(
            OrgApiMmrDelivery.objects.filter(
                connection__in=self.connections
            ).values_list("delivery_id", flat=True)
        )
        self.assertEqual(len(ids), 3)
        fences = self.acquire_all(ids)
        self.assertEqual(sum(fence is not None for fence in fences), 2)
        self.assertEqual(OrgApiMmrDelivery.objects.filter(state="in_flight").count(), 2)

    def test_concurrent_claims_of_one_delivery_issue_one_fence(self) -> None:
        delivery_id = OrgApiMmrDelivery.objects.filter(
            connection=self.connections[0]
        ).values_list("delivery_id", flat=True)[0]
        fences = self.acquire_all([delivery_id, delivery_id])
        self.assertEqual(sum(fence is not None for fence in fences), 1)
        self.assertEqual(
            OrgApiMmrDelivery.objects.get(delivery_id=delivery_id).attempts, 1
        )


GUILD = "770000000000000001"


@skipUnless(connection.vendor == "postgresql", "Requires PostgreSQL row locks")
@override_settings(ORG_API_CREDENTIAL_KEYS=json.dumps([OLD_KEY]))
class PromotionStreamRaceTests(TransactionTestCase):
    def setUp(self) -> None:
        resolve = patch.object(tls_adapter, "_resolve", return_value=("93.184.216.34",))
        resolve.start()
        self.addCleanup(resolve.stop)
        self.operator = CustomUser.objects.create_superuser(
            username="stream-operator", password="x"
        )

    def org(self, name: str, *, env_bound: bool) -> tuple[Organization, Event]:
        org = Organization.objects.create(
            name=name, owner=self.operator, discord_server_id=GUILD
        )
        org.admins.add(self.operator)
        set_org_feature(org, FeatureKey.PROMOTION, enabled=True, actor=None)
        event = Event.objects.create(
            organization=org,
            name=f"{name} event",
            scheduled_at=timezone.now(),
            created_by=self.operator,
        )
        if env_bound:
            config = PromotionSyncConfig(
                bindings=(
                    OrgPromotionBinding(
                        org_id=org.pk, guild_id=int(GUILD), events={event.pk: 88}
                    ),
                )
            )
            override = override_settings(PROMOTION_SYNC=config)
            override.enable()
            self.addCleanup(override.disable)
        return org, event

    def race(self, *jobs: Callable[[], object]) -> list[str]:
        barrier = threading.Barrier(len(jobs), timeout=10)

        def run(job: Callable[[], object]) -> str:
            try:
                barrier.wait()
                try:
                    job()
                    return "ok"
                except PromotionStreamError as exc:
                    return exc.code
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=len(jobs)) as pool:
            futures = [pool.submit(run, job) for job in jobs]
            return sorted(future.result(timeout=30) for future in futures)

    def adopt(self, org: Organization) -> Callable[[], object]:
        return lambda: adopt_legacy_promotion(
            org_id=org.pk,
            actor=CustomUser.objects.get(pk=self.operator.pk),
            credential="per-org-key",
            base_url="https://adaptor.example",
            dry_run=False,
        )

    def bind(
        self, connection_row: OrgApiConnection, event: Event
    ) -> Callable[[], object]:
        return lambda: set_promotion_binding(
            OrgApiConnection.objects.get(pk=connection_row.pk),
            actor=CustomUser.objects.get(pk=self.operator.pk),
            events={event.pk: 99},
        )

    def assertSingleStream(self, org: Organization, events: int) -> None:
        adoption = OrgApiPromotionAdoption.objects.get(organization=org)
        binding = OrgApiPromotionBinding.objects.get(organization=org)
        self.assertEqual(binding.connection_id, adoption.connection_id)
        self.assertEqual(
            OrgApiPromotionEventBinding.objects.filter(
                binding__organization=org
            ).count(),
            events,
        )

    def test_concurrent_promotion_stream_adoption_single_authority(self) -> None:
        org, _ = self.org("Adopt twice", env_bound=True)
        self.assertEqual(
            self.race(self.adopt(org), self.adopt(org)),
            ["ok", "promotion_stream_exists"],
        )
        self.assertSingleStream(org, 1)

        org, event = self.org("Adopt vs bind", env_bound=True)
        rival = OrgApiConnection.objects.create(organization=org, name="Rival")
        outcome = self.race(self.adopt(org), self.bind(rival, event))
        self.assertEqual(outcome.count("ok"), 1, outcome)
        self.assertTrue(
            {"managed_by_deployment", "promotion_stream_exists"} & set(outcome),
            outcome,
        )
        self.assertSingleStream(org, 1)
        self.assertNotEqual(
            OrgApiPromotionAdoption.objects.get(organization=org).connection_id,
            rival.pk,
        )

        org, event = self.org("Bind twice", env_bound=False)
        first = OrgApiConnection.objects.create(organization=org, name="First")
        second = OrgApiConnection.objects.create(organization=org, name="Second")
        self.assertEqual(
            self.race(self.bind(first, event), self.bind(second, event)),
            ["ok", "promotion_stream_exists"],
        )
        self.assertSingleStream(org, 1)
