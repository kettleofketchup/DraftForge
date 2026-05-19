from django.test import TestCase

from app.models import CustomUser
from user.models import BaseUserProfile


class CustomUserAutoCreateTests(TestCase):
    def test_new_user_gets_base_profile(self):
        user = CustomUser.objects.create(username="eve")
        assert BaseUserProfile.objects.filter(user=user).exists()

    def test_idempotent_on_resave(self):
        user = CustomUser.objects.create(username="frank")
        original_pk = user.base_profile.pk
        user.save()
        user.refresh_from_db()
        assert user.base_profile.pk == original_pk
