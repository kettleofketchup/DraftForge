from django.test import TestCase
from app.models import CustomUser, PositionsModel
from user.models import BaseUserProfile, DotaUserProfile, DeadlockUserProfile


class GameProfileModelTests(TestCase):
    def test_dota_profile_fks_base_and_owns_positions(self):
        user = CustomUser.objects.create(username="dp")
        bp = user.base_profile
        pos = PositionsModel.objects.create(carry=5)
        dota = DotaUserProfile.objects.create(base_profile=bp, positions=pos)
        assert dota.base_profile_id == bp.pk
        assert dota.positions.carry == 5
        # related_name discipline: default reverse accessor must be dotauserprofile_set
        assert list(pos.dotauserprofile_set.all()) == [dota]
        assert bp.dota_user_profile == dota

    def test_dota_profile_mmr_fields_default(self):
        user = CustomUser.objects.create(username="dp2")
        dota = DotaUserProfile.objects.create(base_profile=user.base_profile)
        assert dota.has_active_dota_mmr is False
        assert dota.dota_mmr_last_verified is None

    def test_deadlock_profile_fks_base_with_rank(self):
        user = CustomUser.objects.create(username="dl")
        dl = DeadlockUserProfile.objects.create(
            base_profile=user.base_profile, rank="Archon"
        )
        assert dl.base_profile.user_id == user.pk
        assert dl.rank == "Archon"
        assert user.base_profile.deadlock_user_profile == dl
