import threading
from concurrent.futures import ThreadPoolExecutor
from unittest import skipUnless

from django.db import connection, connections
from django.test import TransactionTestCase
from rest_framework.test import APIClient

from app.models import CustomUser
from org.api_connections.lifecycle import ConnectionConflict, issue_connection_key
from org.features import FeatureKey, set_org_feature
from org.models import Organization, OrgApiConnection, OrgApiToken


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
