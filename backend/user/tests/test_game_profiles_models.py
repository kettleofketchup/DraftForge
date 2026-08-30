from django.test import TestCase

from app.models import CustomUser, PositionsModel
from user.models import DeadlockUserProfile, DotaUserProfile


class GameProfileModelTests(TestCase):
    """Model shape/relationship tests.

    NOTE: `BaseUserProfile.save()` AUTO-CREATES one DotaUserProfile +
    DeadlockUserProfile per base_profile (T2.2), so these tests use the
    auto-created instances (`bp.dota_user_profile` / `bp.deadlock_user_profile`)
    rather than `.objects.create(...)` — creating a second would violate the
    OneToOne UNIQUE constraint on base_profile_id.
    """

    def test_dota_profile_fks_base_and_owns_positions(self):
        user = CustomUser.objects.create(username="dp")
        bp = user.base_profile
        dota = bp.dota_user_profile  # auto-created
        pos = PositionsModel.objects.create(carry=5)
        dota.positions = pos
        dota.save(update_fields=["positions"])
        assert dota.base_profile_id == bp.pk
        assert dota.positions.carry == 5
        # related_name discipline: default reverse accessor must be dotauserprofile_set
        assert list(pos.dotauserprofile_set.all()) == [dota]
        assert bp.dota_user_profile == dota

    def test_dota_profile_mmr_fields_default(self):
        user = CustomUser.objects.create(username="dp2")
        dota = user.base_profile.dota_user_profile  # auto-created
        assert dota.has_active_dota_mmr is False
        assert dota.dota_mmr_last_verified is None

    def test_deadlock_profile_fks_base_with_rank(self):
        user = CustomUser.objects.create(username="dl")
        dl = user.base_profile.deadlock_user_profile  # auto-created
        dl.rank = "Archon"
        dl.save(update_fields=["rank"])
        assert dl.base_profile.user_id == user.pk
        assert dl.rank == "Archon"
        assert user.base_profile.deadlock_user_profile == dl

    def test_one_dota_and_deadlock_per_base_profile(self):
        # The OneToOne + auto-create invariant: exactly one of each per user.
        user = CustomUser.objects.create(username="dp3")
        bp = user.base_profile
        assert DotaUserProfile.objects.filter(base_profile=bp).count() == 1
        assert DeadlockUserProfile.objects.filter(base_profile=bp).count() == 1
