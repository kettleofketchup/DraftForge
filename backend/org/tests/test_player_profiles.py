from django.test import TestCase

from app.models import CustomUser, Organization, PositionsModel
from org.models import OrgUser


class PlayerDotaProfileTest(TestCase):
    def setUp(self):
        positions = PositionsModel.objects.create()
        self.user = CustomUser.objects.create(username="test_dota", positions=positions)
        self.org = Organization.objects.create(name="Test Org")
        self.org_user = OrgUser.objects.create(user=self.user, organization=self.org)

    def test_create_dota_profile(self):
        from org.models_profiles import PlayerDotaProfile

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
        from org.models_profiles import PlayerDotaProfile

        PlayerDotaProfile.objects.create(org_user=self.org_user)
        self.assertIsNotNone(self.org_user.dota_profile)

    def test_rank_status_choices(self):
        from org.models_profiles import PlayerDotaProfile

        for status in ["active", "previous", "never"]:
            profile, _ = PlayerDotaProfile.objects.update_or_create(
                org_user=self.org_user, defaults={"rank_status": status}
            )
            self.assertEqual(profile.rank_status, status)

    def test_battle_cup_tier_nullable(self):
        from org.models_profiles import PlayerDotaProfile

        profile = PlayerDotaProfile.objects.create(
            org_user=self.org_user, rank_status="never", battle_cup_tier=5
        )
        self.assertEqual(profile.battle_cup_tier, 5)

    def test_unverified_steam_id(self):
        from org.models_profiles import PlayerDotaProfile

        profile = PlayerDotaProfile.objects.create(
            org_user=self.org_user,
            unverified_steam_id="123456789",
        )
        self.assertEqual(profile.unverified_steam_id, "123456789")
        # Verify it did NOT touch CustomUser.steam_account_id
        self.user.refresh_from_db()
        self.assertIsNone(self.user.steam_account_id)


class PlayerDeadlockProfileTest(TestCase):
    def setUp(self):
        positions = PositionsModel.objects.create()
        self.user = CustomUser.objects.create(
            username="test_deadlock", positions=positions
        )
        self.org = Organization.objects.create(name="Test Org DL")
        self.org_user = OrgUser.objects.create(user=self.user, organization=self.org)

    def test_create_deadlock_profile(self):
        from org.models_profiles import PlayerDeadlockProfile

        profile = PlayerDeadlockProfile.objects.create(
            org_user=self.org_user,
            rank="Phantom IV",
            rank_date="2026-03-01",
        )
        self.assertEqual(profile.rank, "Phantom IV")

    def test_rank_is_loose_string(self):
        from org.models_profiles import PlayerDeadlockProfile

        profile = PlayerDeadlockProfile.objects.create(
            org_user=self.org_user,
            rank="idk maybe like medium?",
        )
        self.assertEqual(profile.rank, "idk maybe like medium?")

    def test_unverified_steam_id_on_deadlock(self):
        from org.models_profiles import PlayerDeadlockProfile

        profile = PlayerDeadlockProfile.objects.create(
            org_user=self.org_user,
            unverified_steam_id="987654321",
        )
        self.assertEqual(profile.unverified_steam_id, "987654321")
