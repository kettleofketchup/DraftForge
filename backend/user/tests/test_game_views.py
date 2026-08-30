from django.test import TestCase
from rest_framework.test import APIClient

from app.models import CustomUser


class MeProfileGamePatchTests(TestCase):
    def setUp(self):
        self.user = CustomUser.objects.create(username="gp")
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_patch_dota_positions(self):
        r = self.client.patch(
            "/api/users/me/profile/game/dota/",
            data={"positions": {"carry": 5, "mid": 1, "offlane": 0,
                                "soft_support": 0, "hard_support": 0}},
            format="json",
        )
        assert r.status_code == 200, r.content
        self.user.base_profile.dota_user_profile.refresh_from_db()
        assert self.user.base_profile.dota_user_profile.positions.carry == 5

    def test_patch_deadlock_rank(self):
        r = self.client.patch(
            "/api/users/me/profile/game/deadlock/",
            data={"rank": "Ascendant"}, format="json",
        )
        assert r.status_code == 200, r.content
        self.user.base_profile.deadlock_user_profile.refresh_from_db()
        assert self.user.base_profile.deadlock_user_profile.rank == "Ascendant"

    def test_patch_deadlock_rank_blank_and_null(self):
        # DeadlockUserProfile.rank is null=True/blank=True, so a bare
        # ModelSerializer auto-infers allow_blank/allow_null (same as T1's
        # nickname). Clearing must NOT 400 (lesson #5).
        r1 = self.client.patch("/api/users/me/profile/game/deadlock/",
                               data={"rank": ""}, format="json")
        assert r1.status_code == 200, r1.content
        r2 = self.client.patch("/api/users/me/profile/game/deadlock/",
                               data={"rank": None}, format="json")
        assert r2.status_code == 200, r2.content

    def test_unknown_game_404(self):
        r = self.client.patch("/api/users/me/profile/game/chess/",
                              data={}, format="json")
        assert r.status_code == 404

    def test_patch_unauthenticated(self):
        c = APIClient()
        r = c.patch("/api/users/me/profile/game/dota/", data={}, format="json")
        assert r.status_code in (401, 403)
