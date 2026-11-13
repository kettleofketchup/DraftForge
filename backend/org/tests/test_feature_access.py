from collections.abc import Callable

from django.contrib.auth.models import AnonymousUser
from django.test import TestCase
from rest_framework.exceptions import NotAuthenticated, PermissionDenied

from app.models import CustomUser, Organization
from app.permissions_org import (
    has_org_promoter_access,
    is_org_role_holder,
    is_site_admin,
)
from org.feature_errors import (
    feature_locked,
    not_permitted,
    require_feature,
    require_org_admin,
    require_org_staff,
    require_promoter,
)
from org.features import FeatureKey, set_org_feature
from org.models import OrgUser


class FeatureAccessTest(TestCase):
    def setUp(self) -> None:
        def make(name: str, **extra: bool) -> CustomUser:
            return CustomUser.objects.create_user(username=name, password="x", **extra)

        self.owner = make("fa_owner")
        self.admin = make("fa_admin")
        self.staff = make("fa_staff")
        self.promoter = make("fa_promoter")
        self.member = make("fa_member")
        self.outsider = make("fa_outsider")
        self.site_admin = make("fa_site_admin", is_staff=True)
        self.superuser = make("fa_superuser", is_superuser=True)
        self.anon = AnonymousUser()

        self.org = Organization.objects.create(name="Feature Access Org")
        self.org.owner = self.owner
        self.org.save()
        self.org.admins.add(self.admin)
        self.org.staff.add(self.staff)
        self.org.promoters.add(self.promoter)
        OrgUser.objects.create(user=self.member, organization=self.org)

    def _unlock(self, feature: FeatureKey = FeatureKey.PROMOTION) -> None:
        set_org_feature(self.org, feature, enabled=True, actor=self.site_admin)

    def _code(self, call: Callable[[], None]) -> str:
        with self.assertRaises(PermissionDenied) as ctx:
            call()
        return ctx.exception.detail["code"]

    def test_is_site_admin(self) -> None:
        self.assertIs(is_site_admin(self.site_admin), True)
        self.assertIs(is_site_admin(self.superuser), True)
        self.assertIs(is_site_admin(self.owner), False)
        self.assertIs(is_site_admin(self.anon), False)

    def test_promoter_access_matrix_unlocked(self) -> None:
        self._unlock()
        for user in (
            self.promoter,
            self.staff,
            self.admin,
            self.owner,
            self.site_admin,
            self.superuser,
        ):
            with self.subTest(user=user.username):
                self.assertIs(has_org_promoter_access(user, self.org), True)
        for user in (self.member, self.outsider, self.anon):
            with self.subTest(user=str(user)):
                self.assertIs(has_org_promoter_access(user, self.org), False)

    def test_promoter_access_false_for_all_when_locked(self) -> None:
        for user in (
            self.promoter,
            self.staff,
            self.admin,
            self.owner,
            self.site_admin,
            self.member,
            self.outsider,
            self.anon,
        ):
            with self.subTest(user=str(user)):
                self.assertIs(has_org_promoter_access(user, self.org), False)

    def test_contributions_switch_does_not_unlock_promotion(self) -> None:
        self._unlock(FeatureKey.CONTRIBUTIONS)
        self.assertIs(has_org_promoter_access(self.promoter, self.org), False)

    def test_require_promoter_locked_body(self) -> None:
        with self.assertRaises(PermissionDenied) as ctx:
            require_promoter(self.promoter, self.org)
        self.assertEqual(ctx.exception.detail["code"], "feature_locked")
        self.assertIn("detail", ctx.exception.detail)

    def test_require_promoter_locked_beats_outsider(self) -> None:
        self.assertEqual(
            self._code(lambda: require_promoter(self.outsider, self.org)),
            "feature_locked",
        )

    def test_require_promoter_revoked_role_body(self) -> None:
        self._unlock()
        require_promoter(self.promoter, self.org)
        self.org.promoters.remove(self.promoter)
        self.assertEqual(
            self._code(lambda: require_promoter(self.promoter, self.org)),
            "not_permitted",
        )

    def test_require_promoter_site_admin_without_role_passes(self) -> None:
        self._unlock()
        require_promoter(self.site_admin, self.org)

    def test_require_feature(self) -> None:
        self.assertEqual(
            self._code(lambda: require_feature(self.org, FeatureKey.PROMOTION)),
            "feature_locked",
        )
        self._unlock()
        require_feature(self.org, FeatureKey.PROMOTION)
        require_feature(self.org.pk, "promotion")

    def test_require_org_staff(self) -> None:
        feature = FeatureKey.CONTRIBUTIONS
        self.assertEqual(
            self._code(lambda: require_org_staff(self.staff, self.org, feature)),
            "feature_locked",
        )
        self._unlock(feature)
        require_org_staff(self.staff, self.org, feature)
        require_org_staff(self.admin, self.org, feature)
        require_org_staff(self.site_admin, self.org, feature)
        for user in (self.promoter, self.member, self.outsider):
            with self.subTest(user=user.username):
                self.assertEqual(
                    self._code(lambda: require_org_staff(user, self.org, feature)),
                    "not_permitted",
                )

    def test_require_org_admin(self) -> None:
        feature = FeatureKey.CONTRIBUTIONS
        self.assertEqual(
            self._code(lambda: require_org_admin(self.admin, self.org, feature)),
            "feature_locked",
        )
        self._unlock(feature)
        require_org_admin(self.admin, self.org, feature)
        require_org_admin(self.owner, self.org, feature)
        require_org_admin(self.site_admin, self.org, feature)
        for user in (self.staff, self.promoter, self.outsider):
            with self.subTest(user=user.username):
                self.assertEqual(
                    self._code(lambda: require_org_admin(user, self.org, feature)),
                    "not_permitted",
                )

    def test_require_org_admin_without_feature_skips_switch(self) -> None:
        require_org_admin(self.admin, self.org, None)
        self.assertEqual(
            self._code(lambda: require_org_admin(self.staff, self.org, None)),
            "not_permitted",
        )

    def test_require_helpers_anon_unlocked_not_authenticated(self) -> None:
        self._unlock(FeatureKey.PROMOTION)
        self._unlock(FeatureKey.CONTRIBUTIONS)
        calls: list[Callable[[], None]] = [
            lambda: require_promoter(self.anon, self.org),
            lambda: require_org_staff(self.anon, self.org, FeatureKey.CONTRIBUTIONS),
            lambda: require_org_admin(self.anon, self.org, FeatureKey.CONTRIBUTIONS),
            lambda: require_org_admin(self.anon, self.org, None),
        ]
        for call in calls:
            with self.subTest(call=call):
                with self.assertRaises(NotAuthenticated) as ctx:
                    call()
                self.assertNotIsInstance(ctx.exception.detail, dict)

    def test_require_helpers_anon_locked_feature_locked(self) -> None:
        calls: list[Callable[[], None]] = [
            lambda: require_promoter(self.anon, self.org),
            lambda: require_org_staff(self.anon, self.org, FeatureKey.CONTRIBUTIONS),
            lambda: require_org_admin(self.anon, self.org, FeatureKey.CONTRIBUTIONS),
        ]
        for call in calls:
            with self.subTest(call=call):
                self.assertEqual(self._code(call), "feature_locked")

    def test_error_factories(self) -> None:
        locked = feature_locked()
        denied = not_permitted()
        self.assertIsInstance(locked, PermissionDenied)
        self.assertIsInstance(denied, PermissionDenied)
        self.assertEqual(locked.detail["code"], "feature_locked")
        self.assertEqual(denied.detail["code"], "not_permitted")
        self.assertTrue(str(locked.detail["detail"]))
        self.assertTrue(str(denied.detail["detail"]))

    def test_is_org_role_holder_excludes_site_admin_without_role(self) -> None:
        for user in (self.owner, self.admin, self.staff, self.promoter):
            with self.subTest(user=user.username):
                self.assertIs(is_org_role_holder(user, self.org), True)
        for user in (
            self.site_admin,
            self.superuser,
            self.member,
            self.outsider,
            self.anon,
        ):
            with self.subTest(user=str(user)):
                self.assertIs(is_org_role_holder(user, self.org), False)
