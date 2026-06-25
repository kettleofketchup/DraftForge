from django.test import TestCase

from app.models import CustomUser, PositionsModel
from user.models import DeadlockUserProfile, DotaUserProfile


class GameProfileAutoCreateTests(TestCase):
    def test_creating_user_creates_both_game_profiles(self):
        user = CustomUser.objects.create(username="auto")
        bp = user.base_profile
        assert DotaUserProfile.objects.filter(base_profile=bp).count() == 1
        assert DeadlockUserProfile.objects.filter(base_profile=bp).count() == 1
        assert bp.dota_user_profile is not None
        assert bp.deadlock_user_profile is not None

    def test_idempotent_on_resave(self):
        user = CustomUser.objects.create(username="idem")
        user.base_profile.save()
        user.base_profile.save()
        assert DotaUserProfile.objects.filter(base_profile=user.base_profile).count() == 1
        assert DeadlockUserProfile.objects.filter(base_profile=user.base_profile).count() == 1

    def test_resave_does_not_leak_orphan_positions(self):
        # Guards the get_or_create callable-default fix: a bare
        # defaults={"positions": PositionsModel.objects.create()} would leak a
        # new PositionsModel on every resave even though the DotaUserProfile
        # already exists. The DotaUserProfile-count assertion above does NOT
        # catch that (the orphan has no profile pointing at it).
        user = CustomUser.objects.create(username="orphan")
        before = PositionsModel.objects.count()
        user.base_profile.save()
        user.base_profile.save()
        assert PositionsModel.objects.count() == before
