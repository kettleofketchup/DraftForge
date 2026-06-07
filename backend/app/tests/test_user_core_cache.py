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
