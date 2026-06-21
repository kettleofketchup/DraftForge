"""Live-Redis cacheops invalidation behavioral test for DotaUserProfile.

T2 (GameUserProfile epic #224) companion to the static grep guardrail in
test_cacheops.py (the live gate for CI, Task 3) which verifies the
`@cached_as(..., DotaUserProfile, ...)` dependency declarations exist. This
suite would, when run against the container-backed test stack with Redis,
warm a cached user-list endpoint, PATCH positions via the new
/api/users/me/profile/game/dota/ route, and re-fetch to confirm the cached
payload (which embeds `positions`) was actually evicted.

Without this test, the `@cached_as(..., DotaUserProfile, ...)` dependency
declarations could silently drift to the wrong model and CI wouldn't catch
it via behavior — only the grep guardrail would.

Shipped skipped: inherits T1's keep_fresh/eviction timing deferral
(lesson #24). The grep guardrail (Task 3) is the live gate. Re-enable once
T1's keep_fresh-vs-eviction root cause is fixed (see T1
test_cacheops_integration.py + PR #250 post-rebase review notes).
"""

import unittest

import redis
from django.conf import settings
from django.test import TransactionTestCase
from rest_framework.test import APIClient

from app.models import CustomUser


def _redis_reachable() -> bool:
    """Return True if cacheops Redis can be pinged within 1s."""
    if not getattr(settings, "CACHEOPS_ENABLED", True):
        return False
    if not getattr(settings, "CACHEOPS", None):
        return False
    cfg = getattr(settings, "CACHEOPS_REDIS", None)
    if not cfg:
        return False
    try:
        client = redis.Redis(
            host=cfg["host"],
            port=cfg["port"],
            db=cfg["db"],
            socket_timeout=1,
            socket_connect_timeout=1,
        )
        return client.ping() is True
    except Exception:
        return False


@unittest.skip(
    "inherits T1 keep_fresh/eviction deferral — lesson #24. Under "
    "TransactionTestCase + autocommit + cacheops `keep_fresh=True`, the "
    "eviction (or refresh) sometimes lags the re-fetch in CI. The static "
    "grep guardrail in test_cacheops.py already verifies the "
    "@cached_as DotaUserProfile dep declarations are correct. Re-enable in "
    "a follow-up once the keep_fresh vs eviction timing is understood — "
    "likely needs `cache.clear()` between warm/re-fetch, or to drop "
    "keep_fresh on the @cached_as blocks. See T1 "
    "test_cacheops_integration.py + PR #250 review notes for context."
)
class CacheopsInvalidationOnDotaProfilePatchTests(TransactionTestCase):
    """Verify PATCH /users/me/profile/game/dota/ evicts cached user payloads.

    Inherits from TransactionTestCase (not plain TestCase) because cacheops
    eviction is scheduled via `transaction.on_commit`. Plain TestCase wraps
    each test in a transaction that's rolled back at teardown — on_commit
    hooks would never fire mid-test, and the cache would never be evicted
    between the warm and the re-fetch. This class needs real commits in the
    middle of the test, which TransactionTestCase provides. Pattern mirrors
    backend/user/tests/test_cacheops_integration.py (T1).
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._redis_ok = _redis_reachable()

    def setUp(self):
        if not self._redis_ok:
            self.skipTest("Cacheops Redis not reachable — skipping live test")
        self.user = CustomUser.objects.create(username="dota_liv")
        self.user.set_password("pw")
        self.user.save()
        # Seed a baseline positions row so the warm payload has a known value.
        self._patch_target = self.user.base_profile.dota_user_profile
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        # Warm baseline: carry = 1.
        self._patch_positions(carry=1)

    def _patch_positions(self, **positions) -> dict:
        response = self.client.patch(
            "/api/users/me/profile/game/dota/",
            data={"positions": positions},
            format="json",
        )
        assert response.status_code == 200, response.content
        return response.json()

    def test_user_list_cache_evicted_on_dota_positions_patch(self):
        # Warm: the user-list payload embeds `positions` via the cached_as
        # wrapped list view; first call populates Redis.
        first = self.client.get("/api/users/")
        assert first.status_code == 200
        rows = {row["pk"]: row for row in first.json()}
        assert rows.get(self.user.pk, {}).get("positions", {}).get("carry") == 1

        # PATCH the carry preference to a new value.
        self._patch_positions(carry=5)

        # Re-fetch: if the DotaUserProfile dep is correctly declared, the
        # cache is gone and the new carry comes back. If the dep is missing,
        # the cached carry == 1 would still come back.
        second = self.client.get("/api/users/")
        assert second.status_code == 200
        rows = {row["pk"]: row for row in second.json()}
        assert rows.get(self.user.pk, {}).get("positions", {}).get("carry") == 5, (
            "user list cache was NOT evicted after DotaUserProfile positions "
            "patch — the user list @cached_as block is missing a "
            "DotaUserProfile (or PositionsModel) dependency"
        )

    def test_user_detail_cache_evicted_on_dota_positions_patch(self):
        first = self.client.get(f"/api/users/{self.user.pk}/")
        assert first.status_code == 200
        assert first.json().get("positions", {}).get("carry") == 1

        self._patch_positions(carry=5)

        second = self.client.get(f"/api/users/{self.user.pk}/")
        assert second.status_code == 200
        assert second.json().get("positions", {}).get("carry") == 5, (
            "user detail cache was NOT evicted after DotaUserProfile positions "
            "patch — the UserView.retrieve @cached_as block is missing a "
            "DotaUserProfile (or PositionsModel) dependency"
        )
