from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from app.models import CustomUser, Organization
from org.models import OrgUser
from org.models_profiles import PlayerDeadlockProfile, PlayerDotaProfile


class MyDotaProfileResolvedFriendIdTest(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.user = CustomUser.objects.create_user(username="rf_member", password="x")
        cls.org = Organization.objects.create(name="Resolved Friend ID Org")
        cls.org_user = OrgUser.objects.create(user=cls.user, organization=cls.org)

    def _get(self) -> dict[str, object]:
        client = APIClient()
        client.force_authenticate(self.user)
        resp = client.get(reverse("my-dota-profile", args=[self.org.pk]))
        self.assertEqual(resp.status_code, 200)
        return resp.json()

    def test_falls_back_to_deadlock_profile(self) -> None:
        PlayerDeadlockProfile.objects.create(
            org_user=self.org_user, unverified_friend_id="616161"
        )
        body = self._get()
        self.assertEqual(body["unverified_friend_id"], "")
        self.assertEqual(body["resolved_friend_id"], "616161")

    def test_prefers_dota_profile(self) -> None:
        PlayerDotaProfile.objects.create(
            org_user=self.org_user, unverified_friend_id="626262"
        )
        PlayerDeadlockProfile.objects.create(
            org_user=self.org_user, unverified_friend_id="636363"
        )
        body = self._get()
        self.assertEqual(body["unverified_friend_id"], "626262")
        self.assertEqual(body["resolved_friend_id"], "626262")

    def test_empty_when_no_profile_has_one(self) -> None:
        self.assertEqual(self._get()["resolved_friend_id"], "")
