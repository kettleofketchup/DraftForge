from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from app.models import CustomUser, Organization
from org.models import OrgUser
from org.models_profiles import PlayerDotaProfile


class DeclareRankTest(TestCase):
    def test_declare_rank_sets_status_and_timestamp(self) -> None:
        profile = PlayerDotaProfile()
        self.assertIsNone(profile.rank_declared_at)
        profile.declare_rank("previous")
        self.assertEqual(profile.rank_status, "previous")
        self.assertIsNotNone(profile.rank_declared_at)


class RankDeclaredViewTest(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.owner = CustomUser.objects.create_user(username="rd_owner", password="x")
        cls.member = CustomUser.objects.create_user(username="rd_member", password="x")
        cls.org = Organization.objects.create(name="Rank Declared Org", owner=cls.owner)
        cls.org.staff.add(cls.owner)
        cls.org_user = OrgUser.objects.create(user=cls.member, organization=cls.org)

    def _profile(self) -> PlayerDotaProfile:
        return PlayerDotaProfile.objects.get(org_user=self.org_user)

    def test_my_profile_patch_with_rank_status_declares(self) -> None:
        client = APIClient()
        client.force_authenticate(self.member)
        url = reverse("update-my-dota-profile", args=[self.org.pk])
        resp = client.patch(url, {"rank_status": "never"}, format="json")
        self.assertEqual(resp.status_code, 200)
        self.assertIsNotNone(self._profile().rank_declared_at)

    def test_my_profile_patch_without_rank_status_leaves_undeclared(self) -> None:
        client = APIClient()
        client.force_authenticate(self.member)
        url = reverse("update-my-dota-profile", args=[self.org.pk])
        resp = client.patch(url, {"pos_1": True}, format="json")
        self.assertEqual(resp.status_code, 200)
        self.assertIsNone(self._profile().rank_declared_at)

    def test_staff_patch_with_rank_status_declares(self) -> None:
        client = APIClient()
        client.force_authenticate(self.owner)
        url = reverse("update-user-dota-profile", args=[self.org.pk, self.member.pk])
        resp = client.patch(url, {"rank_status": "active"}, format="json")
        self.assertEqual(resp.status_code, 200)
        profile = self._profile()
        self.assertEqual(profile.rank_status, "active")
        self.assertIsNotNone(profile.rank_declared_at)
