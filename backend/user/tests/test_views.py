from django.test import TestCase
from rest_framework.test import APIClient

from app.models import CustomUser


class MeProfileViewTests(TestCase):
    def setUp(self):
        self.user = CustomUser.objects.create(username="kara")
        self.user.set_password("pw")
        self.user.save()
        self.user.base_profile.nickname = "Kara"
        self.user.base_profile.save()
        self.client = APIClient()

    def test_unauthenticated_get_returns_401_or_403(self):
        response = self.client.get("/api/users/me/profile/")
        assert response.status_code in (401, 403)

    def test_authenticated_get_returns_layered_shape(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.get("/api/users/me/profile/")
        assert response.status_code == 200
        body = response.json()
        assert body["pk"] == self.user.pk
        assert body["base"]["nickname"] == "Kara"
        assert body["gameUser"] == {}
        assert body["orgProfiles"] == {}

    def test_patch_base_updates_only_sent_fields(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.patch(
            "/api/users/me/profile/base/",
            data={"nickname": "Kara Renamed"},
            format="json",
        )
        assert response.status_code == 200
        self.user.base_profile.refresh_from_db()
        assert self.user.base_profile.nickname == "Kara Renamed"
        assert self.user.base_profile.avatar is None

    def test_patch_base_unauthenticated(self):
        response = self.client.patch(
            "/api/users/me/profile/base/",
            data={"nickname": "x"},
            format="json",
        )
        assert response.status_code in (401, 403)
