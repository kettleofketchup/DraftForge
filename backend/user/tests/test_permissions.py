from django.contrib.auth.models import AnonymousUser
from django.test import SimpleTestCase

from app.models import CustomUser
from user.permissions import is_site_admin


class SiteAdminPermissionTests(SimpleTestCase):
    def test_is_site_admin_lives_in_user(self) -> None:
        self.assertEqual(is_site_admin.__module__, "user.permissions")

    def test_superuser_and_staff_semantics(self) -> None:
        cases: list[tuple[CustomUser | AnonymousUser, bool]] = [
            (CustomUser(is_superuser=True, is_staff=False), True),
            (CustomUser(is_superuser=False, is_staff=True), True),
            (CustomUser(is_superuser=True, is_staff=True), True),
            (CustomUser(is_superuser=False, is_staff=False), False),
            (AnonymousUser(), False),
        ]
        for user, expected in cases:
            with self.subTest(user=user, expected=expected):
                self.assertIs(is_site_admin(user), expected)
