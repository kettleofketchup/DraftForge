from django.db import connection
from django.test import TestCase

from app.models import CustomUser, Organization, ProfileClaimRequest
from app.tests.raw_site_nickname import raw_site_nickname, set_raw_site_nickname
from org.serializers import ProfileClaimRequestSerializer
from org.views import ClaimRequestViewSet


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
        self.assertIn("target_nickname", data)
        self.assertIsNone(data["target_nickname"])

    def test_target_with_discord_name(self) -> None:
        self.target.discordNickname = "Gwaihir"
        self.target.save()
        data = self._data()
        self.assertEqual(data["target_discordNickname"], "Gwaihir")
        self.assertIsNone(data["target_nickname"])

    def test_deleted_target_keeps_keys_null(self) -> None:
        self.target.delete()
        data = self._data()
        self.assertIsNone(data["target_user"])
        self.assertIsNone(data["target_username"])
        self.assertIsNone(data["target_discordNickname"])
        self.assertIsNone(data["target_nickname"])

    def test_str_uses_discord_names_never_site_nickname(self) -> None:
        self.claim.refresh_from_db()
        self.assertEqual(
            str(self.claim), "cn_claimer -> steam_76561198000300001 (pending)"
        )
        self.target.discordNickname = "Gwaihir"
        self.target.save()
        self.claim.refresh_from_db()
        self.assertEqual(str(self.claim), "cn_claimer -> Gwaihir (pending)")
        self.target.discordNickname = None
        self.target.username = None
        self.target.save()
        self.claim.refresh_from_db()
        self.assertEqual(str(self.claim), "cn_claimer -> 76561198000300001 (pending)")


class ClaimMergeNicknameTest(TestCase):
    def test_merge_does_not_carry_site_nickname(self) -> None:
        claimer = CustomUser.objects.create_user(username="cm_claimer", password="x")
        target = CustomUser.objects.create_user(
            username="steam_76561198000300002", password="x"
        )
        target.steamid = 76561198000300002
        target.save()
        set_raw_site_nickname(target.pk, "Site")

        ClaimRequestViewSet()._merge_profiles(
            claimer, CustomUser.objects.nocache().get(pk=target.pk)
        )

        self.assertIsNone(raw_site_nickname(claimer.pk))
