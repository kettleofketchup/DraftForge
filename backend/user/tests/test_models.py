from django.db import IntegrityError
from django.test import TestCase

from app.models import CustomUser
from user.models import BaseUserProfile


class BaseUserProfileModelTests(TestCase):
    def test_create_profile_with_user(self):
        user = CustomUser.objects.create(username="alice")
        # Auto-create from Task 3 makes the initial profile; replace it so we
        # can assert on the nickname/avatar we set explicitly here.
        BaseUserProfile.objects.filter(user=user).delete()
        profile = BaseUserProfile.objects.create(
            user=user,
            nickname="Alice Wonderland",
            avatar="https://example.com/alice.png",
        )
        assert profile.user == user
        assert profile.nickname == "Alice Wonderland"
        assert profile.avatar == "https://example.com/alice.png"

    def test_one_to_one_constraint(self):
        # Auto-create from Task 3 makes the first BaseUserProfile; the second
        # explicit create must violate uniqueness.
        user = CustomUser.objects.create(username="bob")
        BaseUserProfile.objects.filter(user=user).delete()  # clear if auto-created
        BaseUserProfile.objects.create(user=user, nickname="Bob")
        with self.assertRaises(IntegrityError):
            BaseUserProfile.objects.create(user=user, nickname="Bob 2")

    def test_str_includes_username(self):
        user = CustomUser.objects.create(username="carol")
        profile = BaseUserProfile.objects.filter(user=user).first()
        # Tolerant of auto-create from Task 3
        if profile is None:
            profile = BaseUserProfile.objects.create(user=user, nickname="Carol")
        assert "carol" in str(profile)

    def test_reverse_accessor_named_base_profile(self):
        user = CustomUser.objects.create(username="dave")
        # Either created in setUp helper or by auto-create
        BaseUserProfile.objects.get_or_create(user=user)
        user.refresh_from_db()
        assert hasattr(user, "base_profile")
