from django.test import TestCase

from app.models import CustomUser, PositionsModel


class PositionsShimTests(TestCase):
    def test_positions_getter_reads_from_dota_profile(self):
        user = CustomUser.objects.create(username="g")
        user.dota_user_profile.positions = PositionsModel.objects.create(carry=5)
        user.dota_user_profile.save()
        assert user.positions.carry == 5

    def test_positions_setter_writes_to_dota_profile(self):
        user = CustomUser.objects.create(username="s")
        pos = PositionsModel.objects.create(mid=3)
        user.positions = pos  # transitional setter persists immediately
        user.base_profile.dota_user_profile.refresh_from_db()
        assert user.base_profile.dota_user_profile.positions_id == pos.pk

    def test_has_active_dota_mmr_shim_round_trip(self):
        user = CustomUser.objects.create(username="m")
        user.has_active_dota_mmr = True
        user.base_profile.dota_user_profile.refresh_from_db()
        assert user.base_profile.dota_user_profile.has_active_dota_mmr is True
        assert user.has_active_dota_mmr is True

    def test_positions_removed_from_meta(self):
        names = {f.name for f in CustomUser._meta.get_fields()}
        assert "positions" not in names  # column dropped; property remains
        assert "has_active_dota_mmr" not in names
        assert "dota_mmr_last_verified" not in names

    def test_objects_create_with_positions_uses_setter(self):
        # populate-style call shape (lesson: __init__ dispatches to the descriptor)
        pos = PositionsModel.objects.create(carry=2)
        user = CustomUser.objects.create(username="pc", positions=pos)
        user.base_profile.dota_user_profile.refresh_from_db()
        assert user.base_profile.dota_user_profile.positions_id == pos.pk
        assert not hasattr(user, "_pending_positions")
