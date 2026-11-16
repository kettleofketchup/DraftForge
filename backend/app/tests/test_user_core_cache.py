from django.test import TransactionTestCase  # on_commit invalidation

from app.models import CustomUser
from app.user_cache import serialize_user_core


class SerializeUserCoreTests(TransactionTestCase):
    def test_core_fields_no_mmr(self) -> None:
        u = CustomUser.objects.create(username="core", discordNickname="Core")
        d = serialize_user_core(u.pk)
        assert d["pk"] == u.pk and d["discordNickname"] == "Core"
        assert d["nickname"] is None
        assert "positions" in d
        assert "mmr" not in d and "league_mmr" not in d

    def test_invalidates_on_avatar_edit(self) -> None:
        # avatar writes through to base_profile (bp.save), NOT user.save —
        # the cache MUST depend on BaseUserProfile or this returns stale.
        u = CustomUser.objects.create(username="c2", avatar="old")
        assert serialize_user_core(u.pk)["avatar"] == "old"
        u.avatar = "new"  # property setter → bp.save(update_fields=["avatar"])
        assert serialize_user_core(u.pk)["avatar"] == "new"

    def test_invalidates_on_discord_nickname_edit(self) -> None:
        u = CustomUser.objects.create(username="c4", discordNickname="Old")
        assert serialize_user_core(u.pk)["discordNickname"] == "Old"
        u.discordNickname = "New"
        u.save()
        assert serialize_user_core(u.pk)["discordNickname"] == "New"

    def test_invalidates_on_positions_edit(self) -> None:
        u = CustomUser.objects.create(username="c3")
        u.positions.carry = 5
        u.positions.save()  # PositionsModel.save() → invalidate_obj(user)
        assert serialize_user_core(u.pk)["positions"]["carry"] == 5

    def test_invalidation_is_user_specific(self) -> None:
        # Editing user X must invalidate ONLY X's entry, never Y's. The per-pk
        # cache key (user_core:{pk}) + pk-filtered dep querysets scope the
        # eviction to the edited user — not a broad flush of all users.
        x = CustomUser.objects.create(username="x", avatar="x-old")
        y = CustomUser.objects.create(username="y", avatar="y-old")
        assert serialize_user_core(x.pk)["avatar"] == "x-old"
        assert serialize_user_core(y.pk)["avatar"] == "y-old"
        x.avatar = "x-new"
        assert serialize_user_core(x.pk)["avatar"] == "x-new"
        assert serialize_user_core(y.pk)["avatar"] == "y-old"


class BulkUsersCacheTests(TransactionTestCase):
    def setUp(self) -> None:
        from rest_framework.test import APIClient

        self.client = APIClient()
        self.requester = CustomUser.objects.create(username="bulk_requester")
        self.client.force_authenticate(user=self.requester)

    def test_bulk_users_returns_core_and_reflects_edit(self) -> None:
        u = CustomUser.objects.create(username="b1", avatar="b1")
        r = self.client.post("/api/users/bulk/", {"pks": [u.pk]}, format="json")
        assert r.status_code == 200 and r.json()[0]["avatar"] == "b1"
        assert r.json()[0]["nickname"] is None
        u.avatar = "b1x"
        r2 = self.client.post("/api/users/bulk/", {"pks": [u.pk]}, format="json")
        assert r2.json()[0]["avatar"] == "b1x"
