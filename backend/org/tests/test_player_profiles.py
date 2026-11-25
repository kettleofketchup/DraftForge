from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from app.models import CustomUser
from org.models import Organization, OrgUser
from org.models_profiles import PlayerDeadlockProfile, PlayerDotaProfile
from steam.services.account_lookup import SteamLookupRateLimited
from user.models import PositionsModel


class PlayerDotaProfileTest(TestCase):
    def setUp(self):
        positions = PositionsModel.objects.create()
        self.user = CustomUser.objects.create(username="test_dota", positions=positions)
        self.org = Organization.objects.create(name="Test Org")
        self.org_user = OrgUser.objects.create(user=self.user, organization=self.org)

    def test_create_dota_profile(self):
        profile = PlayerDotaProfile.objects.create(
            org_user=self.org_user,
            rank_status="active",
            rank_medal="Legend",
            pos_1=True,
            pos_2=True,
            pos_3=False,
            pos_4=False,
            pos_5=True,
        )
        self.assertEqual(profile.rank_status, "active")
        self.assertEqual(profile.rank_medal, "Legend")
        self.assertTrue(profile.pos_1)
        self.assertFalse(profile.pos_3)

    def test_dota_profile_one_to_one(self):
        PlayerDotaProfile.objects.create(org_user=self.org_user)
        self.assertIsNotNone(self.org_user.dota_profile)

    def test_rank_status_choices(self):
        for status in ["active", "previous", "never"]:
            profile, _ = PlayerDotaProfile.objects.update_or_create(
                org_user=self.org_user, defaults={"rank_status": status}
            )
            self.assertEqual(profile.rank_status, status)

    def test_battle_cup_tier_nullable(self):
        profile = PlayerDotaProfile.objects.create(
            org_user=self.org_user, rank_status="never", battle_cup_tier=5
        )
        self.assertEqual(profile.battle_cup_tier, 5)


class PlayerDeadlockProfileTest(TestCase):
    def setUp(self):
        positions = PositionsModel.objects.create()
        self.user = CustomUser.objects.create(
            username="test_deadlock", positions=positions
        )
        self.org = Organization.objects.create(name="Test Org DL")
        self.org_user = OrgUser.objects.create(user=self.user, organization=self.org)

    def test_create_deadlock_profile(self):
        profile = PlayerDeadlockProfile.objects.create(
            org_user=self.org_user,
            rank="Phantom IV",
            rank_date="2026-03-01",
        )
        self.assertEqual(profile.rank, "Phantom IV")

    def test_rank_is_loose_string(self):
        profile = PlayerDeadlockProfile.objects.create(
            org_user=self.org_user,
            rank="idk maybe like medium?",
        )
        self.assertEqual(profile.rank, "idk maybe like medium?")


@override_settings(
    STEAM_ACCOUNT_LOOKUP_ENABLED=True,
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}},
)
class MyDotaProfileSteamLookupTest(TestCase):
    def setUp(self) -> None:
        cache.clear()
        self.owner = CustomUser.objects.create_user(username="mdp_owner", password="x")
        self.member = CustomUser.objects.create_user(
            username="mdp_member", password="x"
        )
        self.org = Organization.objects.create(name="MDP Org", owner=self.owner)
        self.org_user = OrgUser.objects.create(user=self.member, organization=self.org)
        self.client = APIClient()
        self.client.force_authenticate(self.member)

    def test_my_dota_profile_not_found_400(self) -> None:
        url = reverse("update-my-dota-profile", args=[self.org.pk])
        with patch(
            "events.eligibility.steam.ensure_steam_account_exists", return_value=False
        ):
            resp = self.client.patch(
                url, {"steam_account_id": "676767", "pos_1": True}, format="json"
            )
        self.assertEqual(resp.status_code, 400)
        self.assertIn(
            "No Steam account has Friend ID 676767", resp.data["steam_account_id"]
        )
        self.assertIsNone(CustomUser.objects.get(pk=self.member.pk).steam_account_id)
        self.assertFalse(
            PlayerDotaProfile.objects.filter(
                org_user=self.org_user, pos_1=True
            ).exists()
        )


@override_settings(
    STEAM_ACCOUNT_LOOKUP_ENABLED=True,
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}},
)
class DotaProfileFriendIdVerificationTest(TestCase):
    def setUp(self) -> None:
        cache.clear()
        self.owner = CustomUser.objects.create_user(username="dpv_owner", password="x")
        self.member = CustomUser.objects.create_user(
            username="dpv_member", password="x"
        )
        self.org = Organization.objects.create(name="DPV Org", owner=self.owner)
        self.org.admins.add(self.owner)
        self.org_user = OrgUser.objects.create(user=self.member, organization=self.org)
        self.client = APIClient()

    def _staff_patch(self, actor: CustomUser, data: dict[str, object]) -> object:
        self.client.force_authenticate(actor)
        url = reverse("update-user-dota-profile", args=[self.org.pk, self.member.pk])
        return self.client.patch(url, data, format="json")

    def test_staff_dota_profile_patch_trusted_verifies(self) -> None:
        staff = CustomUser.objects.create_user(username="dpv_staff", password="x")
        staff.is_staff = True
        staff.save()
        with patch("events.eligibility.steam.ensure_steam_account_exists") as ensure:
            resp = self._staff_patch(staff, {"steam_account_id": "686868"})
        self.assertEqual(resp.status_code, 200, resp.content)
        ensure.assert_not_called()
        user = CustomUser.objects.get(pk=self.member.pk)
        self.assertEqual(user.steam_account_id, 686868)
        self.assertTrue(user.steam_account_verified)
        self.assertEqual(user.steam_account_verified_by_id, staff.pk)

    def test_staff_dota_profile_patch_untrusted_prechecked(self) -> None:
        with patch(
            "events.eligibility.steam.ensure_steam_account_exists", return_value=False
        ) as ensure:
            resp = self._staff_patch(self.owner, {"steam_account_id": "696969"})
        self.assertEqual(resp.status_code, 400, resp.content)
        self.assertIn(
            "No Steam account has Friend ID 696969", resp.data["steam_account_id"]
        )
        self.assertEqual(ensure.call_args.kwargs["budget_user"], self.owner)
        self.assertIsNone(CustomUser.objects.get(pk=self.member.pk).steam_account_id)

        with patch(
            "events.eligibility.steam.ensure_steam_account_exists", return_value=None
        ):
            resp = self._staff_patch(self.owner, {"steam_account_id": "696970"})
        self.assertEqual(resp.status_code, 200, resp.content)
        user = CustomUser.objects.get(pk=self.member.pk)
        self.assertEqual(user.steam_account_id, 696970)
        self.assertFalse(user.steam_account_verified)

    def test_friend_id_rate_limit_is_429_with_code(self) -> None:
        my_url = reverse("update-my-dota-profile", args=[self.org.pk])
        cases: list[tuple[CustomUser, str]] = [
            (self.owner, "staff"),
            (self.member, "self"),
        ]
        for actor, label in cases:
            with self.subTest(path=label):
                with patch(
                    "events.eligibility.steam.ensure_steam_account_exists",
                    side_effect=SteamLookupRateLimited(),
                ):
                    if label == "staff":
                        resp = self._staff_patch(actor, {"steam_account_id": "717272"})
                    else:
                        self.client.force_authenticate(actor)
                        resp = self.client.patch(
                            my_url, {"steam_account_id": "717272"}, format="json"
                        )
                self.assertEqual(resp.status_code, 429, resp.content)
                self.assertEqual(resp.data["code"], "steam_lookup_rate_limited")
                self.assertIn("steam_account_id", resp.data)

    def test_my_dota_profile_patch_unverified(self) -> None:
        self.member.is_staff = True
        self.member.save()
        self.client.force_authenticate(self.member)
        url = reverse("update-my-dota-profile", args=[self.org.pk])
        with patch(
            "events.eligibility.steam.ensure_steam_account_exists", return_value=True
        ):
            resp = self.client.patch(url, {"steam_account_id": "707070"}, format="json")
        self.assertEqual(resp.status_code, 200, resp.content)
        user = CustomUser.objects.get(pk=self.member.pk)
        self.assertEqual(user.steam_account_id, 707070)
        self.assertFalse(user.steam_account_verified)
