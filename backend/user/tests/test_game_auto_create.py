from django.test import TestCase

from app.models import CustomUser
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
