from django.test import TransactionTestCase  # on_commit invalidation

from app.models import CustomUser
from app.user_cache import serialize_user_core


class SerializeUserCoreTests(TransactionTestCase):
    def test_core_fields_no_mmr(self):
        u = CustomUser.objects.create(username="core", nickname="Core")
        d = serialize_user_core(u.pk)
        assert d["pk"] == u.pk and d["nickname"] == "Core"
        assert "positions" in d
        assert "mmr" not in d and "league_mmr" not in d

    def test_invalidates_on_nickname_edit(self):
        # nickname writes through to base_profile (bp.save), NOT user.save —
        # the cache MUST depend on BaseUserProfile or this returns stale.
        u = CustomUser.objects.create(username="c2", nickname="Old")
        assert serialize_user_core(u.pk)["nickname"] == "Old"
        u.nickname = "New"  # property setter → bp.save(update_fields=["nickname"])
        assert serialize_user_core(u.pk)["nickname"] == "New"

    def test_invalidates_on_positions_edit(self):
        u = CustomUser.objects.create(username="c3")
        u.positions.carry = 5
        u.positions.save()  # PositionsModel.save() → invalidate_obj(user)
        assert serialize_user_core(u.pk)["positions"]["carry"] == 5

    def test_invalidation_is_user_specific(self):
        # Editing user X must invalidate ONLY X's entry, never Y's. The per-pk
        # cache key (user_core:{pk}) + pk-filtered dep querysets scope the
        # eviction to the edited user — not a broad flush of all users.
        x = CustomUser.objects.create(username="x", nickname="X-old")
        y = CustomUser.objects.create(username="y", nickname="Y-old")
        # Prime both caches.
        assert serialize_user_core(x.pk)["nickname"] == "X-old"
        assert serialize_user_core(y.pk)["nickname"] == "Y-old"
        # Edit only X.
        x.nickname = "X-new"
        # X reflects the edit (its entry was invalidated)...
        assert serialize_user_core(x.pk)["nickname"] == "X-new"
        # ...and Y is unaffected and correct.
        assert serialize_user_core(y.pk)["nickname"] == "Y-old"


class BulkUsersCacheTests(TransactionTestCase):
    def setUp(self):
        from rest_framework.test import APIClient

        self.client = APIClient()
        self.requester = CustomUser.objects.create(username="bulk_requester")
        self.client.force_authenticate(user=self.requester)

    def test_bulk_users_returns_core_and_reflects_edit(self):
        u = CustomUser.objects.create(username="b1", nickname="B1")
        r = self.client.post("/api/users/bulk/", {"pks": [u.pk]}, format="json")
        assert r.status_code == 200 and r.json()[0]["nickname"] == "B1"
        u.nickname = "B1x"
        r2 = self.client.post("/api/users/bulk/", {"pks": [u.pk]}, format="json")
        assert r2.json()[0]["nickname"] == "B1x"
