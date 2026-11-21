from django.db import connection
from django.test import TestCase

from app.models import CustomUser, ProfileClaimRequest
from org.models import Organization
from org.serializers import ProfileClaimRequestSerializer


class ClaimNamesTest(TestCase):
    def setUp(self) -> None:
        self.org = Organization.objects.create(name="Claim Names Org")
        self.claimer = CustomUser.objects.create_user(
            username="cn_claimer", password="x"
        )
        self.target = CustomUser.objects.create_user(
            username="steam_76561198000300001", password="x"
        )
        self.target.steamid = 76561198000300001
        self.target.save()
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE user_baseuserprofile SET nickname='Site' WHERE user_id=%s",
                [self.target.pk],
            )
        self.claim = ProfileClaimRequest.objects.create(
            claimer=self.claimer,
            target_user=self.target,
            organization=self.org,
            status=ProfileClaimRequest.Status.PENDING,
        )

    def _data(self) -> dict:
        self.claim.refresh_from_db()
        return ProfileClaimRequestSerializer(self.claim).data

    def test_steam_only_target(self) -> None:
        data = self._data()
        self.assertEqual(data["target_username"], "steam_76561198000300001")
        self.assertIn("target_discordNickname", data)
        self.assertIsNone(data["target_discordNickname"])
        self.assertEqual(data["target_nickname"], "Site")

    def test_target_with_discord_name(self) -> None:
        self.target.discordNickname = "Gwaihir"
        self.target.save()
        data = self._data()
        self.assertEqual(data["target_discordNickname"], "Gwaihir")
        self.assertEqual(data["target_nickname"], "Site")

    def test_deleted_target_keeps_keys_null(self) -> None:
        self.target.delete()
        data = self._data()
        self.assertIsNone(data["target_user"])
        self.assertIsNone(data["target_username"])
        self.assertIsNone(data["target_discordNickname"])
