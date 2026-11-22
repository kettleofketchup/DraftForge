from typing import Any

from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from rest_framework import status
from rest_framework.test import APIClient

from app.models import CustomUser
from league.models import League
from org.features import FeatureKey, org_has_feature, set_org_feature
from org.models import Organization, OrgUser
from org.models_conduct import OrgConductSettings

FLAGS = (
    "can_use_promotion",
    "can_manage_promotion_templates",
    "can_manage_promoters",
    "can_view_contributions",
    "can_view_contributors",
    "can_manage_contributions",
    "can_view_conduct",
    "can_view_own_conduct",
    "can_view_conduct_details",
    "can_manage_conduct",
)

UNLOCKED: dict[str, dict[str, bool]] = {
    "owner": dict.fromkeys(FLAGS, True),
    "admin": dict.fromkeys(FLAGS, True),
    "staff": {
        "can_use_promotion": True,
        "can_manage_promotion_templates": True,
        "can_manage_promoters": False,
        "can_view_contributions": True,
        "can_view_contributors": True,
        "can_manage_contributions": False,
        "can_view_conduct": True,
        "can_view_own_conduct": True,
        "can_view_conduct_details": True,
        "can_manage_conduct": False,
    },
    "promoter": {
        "can_use_promotion": True,
        "can_manage_promotion_templates": False,
        "can_manage_promoters": False,
        "can_view_contributions": True,
        "can_view_contributors": True,
        "can_manage_contributions": False,
        "can_view_conduct": True,
        "can_view_own_conduct": True,
        "can_view_conduct_details": False,
        "can_manage_conduct": False,
    },
    "member": {
        "can_use_promotion": False,
        "can_manage_promotion_templates": False,
        "can_manage_promoters": False,
        "can_view_contributions": True,
        "can_view_contributors": True,
        "can_manage_contributions": False,
        "can_view_conduct": True,
        "can_view_own_conduct": True,
        "can_view_conduct_details": False,
        "can_manage_conduct": False,
    },
    "anon": {
        "can_use_promotion": False,
        "can_manage_promotion_templates": False,
        "can_manage_promoters": False,
        "can_view_contributions": True,
        "can_view_contributors": False,
        "can_manage_contributions": False,
        "can_view_conduct": True,
        "can_view_own_conduct": False,
        "can_view_conduct_details": False,
        "can_manage_conduct": False,
    },
}


class FlagsTestBase(TestCase):
    def setUp(self) -> None:
        self.site_admin = CustomUser.objects.create_user(
            username="flags_site_admin", password="x", is_staff=True
        )
        self.owner = CustomUser.objects.create_user(
            username="flags_owner", password="x"
        )
        self.admin = CustomUser.objects.create_user(
            username="flags_admin", password="x"
        )
        self.staff = CustomUser.objects.create_user(
            username="flags_staff", password="x"
        )
        self.promoter = CustomUser.objects.create_user(
            username="flags_promoter", password="x"
        )
        self.member = CustomUser.objects.create_user(
            username="flags_member", password="x"
        )
        self.org = Organization.objects.create(name="Flags Org", owner=self.owner)
        self.org.admins.add(self.admin)
        self.org.staff.add(self.staff)
        self.org.promoters.add(self.promoter)
        for user in (self.owner, self.admin, self.staff, self.promoter, self.member):
            OrgUser.objects.create(user=user, organization=self.org)
        self.client = APIClient()
        self.url = f"/api/organizations/{self.org.pk}/"

    def _users(self) -> dict[str, CustomUser | None]:
        return {
            "owner": self.owner,
            "admin": self.admin,
            "staff": self.staff,
            "promoter": self.promoter,
            "member": self.member,
            "anon": None,
        }

    def _unlock(self, feature: FeatureKey) -> None:
        set_org_feature(self.org, feature, enabled=True, actor=self.site_admin)

    def _get(self, user: CustomUser | None) -> dict[str, Any]:
        self.client.force_authenticate(user=user)
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        return resp.data

    def _warm_query_count(self, user: CustomUser) -> int:
        self._get(user)
        with CaptureQueriesContext(connection) as ctx:
            self._get(user)
        return len(ctx.captured_queries)


class OrgDetailFeatureFlagsTest(FlagsTestBase):
    def test_feature_toggle_after_cached_read(self) -> None:
        self.assertEqual(self._get(self.member)["features"], [])
        self._unlock(FeatureKey.PROMOTION)
        self.assertIn("promotion", self._get(self.member)["features"])
        set_org_feature(
            self.org, FeatureKey.PROMOTION, enabled=False, actor=self.site_admin
        )
        self.assertEqual(self._get(self.member)["features"], [])

    def test_flags_matrix_locked(self) -> None:
        for role, user in self._users().items():
            with self.subTest(role=role):
                data = self._get(user)
                self.assertEqual(data["features"], [])
                for flag in FLAGS:
                    self.assertIs(data[flag], False, flag)

    def test_flags_matrix_unlocked(self) -> None:
        self._unlock(FeatureKey.PROMOTION)
        self._unlock(FeatureKey.CONTRIBUTIONS)
        self._unlock(FeatureKey.CONDUCT)
        for role, user in self._users().items():
            with self.subTest(role=role):
                data = self._get(user)
                self.assertEqual(
                    data["features"], ["conduct", "contributions", "promotion"]
                )
                for flag, expected in UNLOCKED[role].items():
                    self.assertIs(data[flag], expected, flag)
                self.assertEqual(data["members_viewer_pk"], getattr(user, "pk", None))

    def test_flags_follow_each_switch_separately(self) -> None:
        self._unlock(FeatureKey.CONTRIBUTIONS)
        data = self._get(self.owner)
        self.assertEqual(data["features"], ["contributions"])
        self.assertIs(data["can_view_contributions"], True)
        self.assertIs(data["can_manage_contributions"], True)
        self.assertIs(data["can_use_promotion"], False)
        self.assertIs(data["can_manage_promoters"], False)

    def test_site_admin_without_role_gets_all_flags(self) -> None:
        self._unlock(FeatureKey.PROMOTION)
        self._unlock(FeatureKey.CONTRIBUTIONS)
        self._unlock(FeatureKey.CONDUCT)
        data = self._get(self.site_admin)
        for flag in FLAGS:
            expected = flag != "can_view_own_conduct"
            self.assertIs(data[flag], expected, flag)

    def test_detail_never_leaks_feature_notes(self) -> None:
        set_org_feature(
            self.org,
            FeatureKey.PROMOTION,
            enabled=True,
            actor=self.site_admin,
            notes="paid via PayPal",
        )
        self.client.force_authenticate(user=self.owner)
        resp = self.client.get(self.url)
        self.assertNotIn("paid via PayPal", resp.content.decode())
        self.assertNotIn("enabled_by", resp.data)
        self.assertNotIn("enabled_at", resp.data)
        self.assertNotIn("notes", resp.data)

    def test_members_private_hides_contributors_from_non_staff(self) -> None:
        self._unlock(FeatureKey.CONTRIBUTIONS)
        self.org.members_private = True
        self.org.save()
        league_staff = CustomUser.objects.create_user(
            username="flags_league_staff", password="x"
        )
        League.objects.create(name="Flags League", organization=self.org).staff.add(
            league_staff
        )
        expected = {
            "owner": True,
            "admin": True,
            "staff": True,
            "promoter": False,
            "member": False,
            "anon": False,
        }
        for role, user in self._users().items():
            with self.subTest(role=role):
                self.assertIs(self._get(user)["can_view_contributors"], expected[role])
        self.assertIs(self._get(league_staff)["can_view_contributors"], True)

    def test_unlocked_flags_add_no_queries_for_staff(self) -> None:
        locked = self._warm_query_count(self.staff)
        self._unlock(FeatureKey.PROMOTION)
        self._unlock(FeatureKey.CONTRIBUTIONS)
        self.assertEqual(self._warm_query_count(self.staff), locked)

    def test_patch_cannot_write_flags(self) -> None:
        self.client.force_authenticate(user=self.admin)
        resp = self.client.patch(
            self.url,
            {"features": ["promotion"], "can_use_promotion": True},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertFalse(org_has_feature(self.org, FeatureKey.PROMOTION))
        self.assertEqual(resp.data["features"], [])
        self.assertIs(resp.data["can_use_promotion"], False)

    def test_patch_response_reports_flags(self) -> None:
        self._unlock(FeatureKey.PROMOTION)
        self.client.force_authenticate(user=self.admin)
        resp = self.client.patch(self.url, {"description": "x"}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["features"], ["promotion"])
        self.assertIs(resp.data["can_manage_promoters"], True)


@override_settings(CACHEOPS_ENABLED=False)
class OrgDetailConductFlagsTest(FlagsTestBase):
    CONDUCT_FLAGS = (
        "can_view_conduct",
        "can_view_own_conduct",
        "can_view_conduct_details",
        "can_manage_conduct",
    )

    def test_conduct_flags_locked_all_false(self) -> None:
        self._unlock(FeatureKey.PROMOTION)
        self._unlock(FeatureKey.CONTRIBUTIONS)
        for role, user in self._users().items():
            with self.subTest(role=role):
                data = self._get(user)
                for flag in self.CONDUCT_FLAGS:
                    self.assertIs(data[flag], False, flag)

    def test_conduct_flags_matrix_unlocked(self) -> None:
        self._unlock(FeatureKey.CONDUCT)
        for role, user in self._users().items():
            with self.subTest(role=role):
                data = self._get(user)
                for flag in self.CONDUCT_FLAGS:
                    self.assertIs(data[flag], UNLOCKED[role][flag], flag)

    def test_conduct_private_ranking_member_own_only(self) -> None:
        self._unlock(FeatureKey.CONDUCT)
        OrgConductSettings.objects.create(
            organization=self.org, leaderboard_public=False
        )
        expected: dict[str, tuple[bool, bool, bool, bool]] = {
            "owner": (True, True, True, True),
            "admin": (True, True, True, True),
            "staff": (True, True, True, False),
            "promoter": (False, True, False, False),
            "member": (False, True, False, False),
            "anon": (False, False, False, False),
        }
        for role, user in self._users().items():
            with self.subTest(role=role):
                data = self._get(user)
                actual = tuple(data[flag] for flag in self.CONDUCT_FLAGS)
                self.assertEqual(actual, expected[role])

    def test_org_detail_get_does_not_create_settings_row(self) -> None:
        self._unlock(FeatureKey.CONDUCT)
        for user in self._users().values():
            self._get(user)
        self.assertFalse(
            OrgConductSettings.objects.filter(organization=self.org).exists()
        )

    def test_conduct_locked_adds_no_queries(self) -> None:
        locked = self._warm_query_count(self.staff)
        self._unlock(FeatureKey.PROMOTION)
        self._unlock(FeatureKey.CONTRIBUTIONS)
        self.assertEqual(self._warm_query_count(self.staff), locked)

    def test_unlocked_conduct_adds_two_queries_for_member(self) -> None:
        self._unlock(FeatureKey.PROMOTION)
        self._unlock(FeatureKey.CONTRIBUTIONS)
        baseline = self._warm_query_count(self.member)
        self._unlock(FeatureKey.CONDUCT)
        self.assertEqual(self._warm_query_count(self.member), baseline + 2)

    def test_unlocked_conduct_adds_two_queries_for_staff(self) -> None:
        self._unlock(FeatureKey.PROMOTION)
        self._unlock(FeatureKey.CONTRIBUTIONS)
        baseline = self._warm_query_count(self.staff)
        self._unlock(FeatureKey.CONDUCT)
        self.assertEqual(self._warm_query_count(self.staff), baseline + 2)

    def test_public_board_private_member_list_flags(self) -> None:
        self._unlock(FeatureKey.CONDUCT)
        self.org.members_private = True
        self.org.save()
        OrgConductSettings.objects.create(
            organization=self.org, leaderboard_public=True
        )
        outsider = CustomUser.objects.create_user(
            username="flags_outsider", password="x"
        )
        member = self._get(self.member)
        self.assertIs(member["can_view_conduct"], True)
        self.assertIs(member["can_view_own_conduct"], True)
        for viewer in (None, outsider):
            with self.subTest(viewer=viewer):
                self.assertIs(self._get(viewer)["can_view_conduct"], True)
        self.client.force_authenticate(user=self.member)
        board = self.client.get(
            f"/api/organizations/{self.org.pk}/standing/conduct/leaderboard/"
        )
        self.assertEqual(board.status_code, status.HTTP_200_OK)
        self.assertIs(board.data["rows_visible"], False)
        self.assertEqual(board.data["rows"], [])
        self.assertIsNotNone(board.data["own_row"])

    def test_standing_tracks_payload(self) -> None:
        self.assertEqual(self._get(self.member)["standing_tracks"], [])
        self._unlock(FeatureKey.CONTRIBUTIONS)
        self._unlock(FeatureKey.CONDUCT)
        OrgConductSettings.objects.create(
            organization=self.org, leaderboard_public=False
        )
        for role, user in self._users().items():
            with self.subTest(role=role):
                tracks = self._get(user)["standing_tracks"]
                self.assertEqual(
                    [t["key"] for t in tracks], ["contribution", "conduct"]
                )
                self.client.force_authenticate(user=user)
                generic = self.client.get(
                    f"/api/organizations/{self.org.pk}/standing/tracks/"
                )
                self.assertEqual(tracks, generic.data["tracks"])
        staff = self._get(self.staff)["standing_tracks"][1]
        self.assertEqual(
            (staff["can_view_rows"], staff["board_open"], staff["can_manage"]),
            (True, True, False),
        )
        member = self._get(self.member)["standing_tracks"][1]
        self.assertEqual(
            (member["can_view_rows"], member["can_view_own"], member["board_open"]),
            (False, True, False),
        )
