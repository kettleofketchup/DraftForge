from django.test import TestCase
from rest_framework.test import APIClient

from app.models import CustomUser, League, Organization
from app.serializers import (
    HeroDraftUserSerializer,
    TournamentUserSerializer,
    UserSerializer,
)
from app.serializers_ssr import UserSerializerSSR
from app.steam_accounts import steam_account_id_conflict_payload
from app.user_cache import serialize_user_core
from league.models import LeagueUser
from league.serializers import LeagueUserSerializer
from org.models import OrgUser
from org.serializers import OrgUserSerializer
from user.serializers import BaseUserProfileSerializer

STEAM_ID = 765353730


class NoNicknameKeyTests(TestCase):
    def setUp(self) -> None:
        self.user = CustomUser.objects.create(
            username="dc", discordNickname="Gwaihir", steam_account_id=STEAM_ID
        )
        self.org = Organization.objects.create(name="Legacy Org")
        self.org_user = OrgUser.objects.create(
            user=self.user, organization=self.org, guild_nickname="DragonClaw"
        )
        self.league = League.objects.create(
            name="Legacy League", organization=self.org, steam_league_id=4242
        )
        self.league_user = LeagueUser.objects.create(
            user=self.user, org_user=self.org_user, league=self.league
        )

    def assert_no_nickname(self, data: dict) -> None:
        self.assertNotIn("nickname", data)

    def test_tournament_user_serializer(self) -> None:
        data = TournamentUserSerializer(self.user).data
        self.assert_no_nickname(data)
        self.assertEqual(data["discordNickname"], "Gwaihir")

    def test_user_serializer(self) -> None:
        data = UserSerializer(self.user).data
        self.assert_no_nickname(data)
        self.assertEqual(data["discordNickname"], "Gwaihir")

    def test_base_profile_serializer(self) -> None:
        self.assert_no_nickname(BaseUserProfileSerializer(self.user.base_profile).data)

    def test_org_user_serializer(self) -> None:
        data = OrgUserSerializer(self.org_user).data
        self.assert_no_nickname(data)
        self.assertEqual(data["guildNickname"], "DragonClaw")
        self.assertEqual(data["discordNickname"], "Gwaihir")

    def test_league_user_serializer(self) -> None:
        data = LeagueUserSerializer(self.league_user).data
        self.assert_no_nickname(data)
        self.assertEqual(data["guildNickname"], "DragonClaw")

    def test_ssr_user_serializer(self) -> None:
        data = UserSerializerSSR(self.user).data
        self.assert_no_nickname(data)
        self.assertEqual(data["discordNickname"], "Gwaihir")

    def test_herodraft_user_serializer(self) -> None:
        data = HeroDraftUserSerializer(self.user).data
        self.assert_no_nickname(data)

    def test_serialize_user_core(self) -> None:
        self.assert_no_nickname(serialize_user_core(self.user.pk))

    def test_steam_conflict_payload(self) -> None:
        body = steam_account_id_conflict_payload(STEAM_ID, self.user)
        self.assert_no_nickname(body["conflict"])
        self.assertEqual(body["conflict"]["discordNickname"], "Gwaihir")
        self.assertEqual(
            body["error"], f"Friend ID {STEAM_ID} is already assigned to Gwaihir (@dc)."
        )

    def test_steam_conflict_label_steam_only_user(self) -> None:
        steam_only = CustomUser.objects.create(username=None)
        body = steam_account_id_conflict_payload(1, steam_only)
        self.assertEqual(
            body["error"], f"Friend ID 1 is already assigned to User {steam_only.pk}."
        )

    def test_steam_conflict_label_omits_redundant_username(self) -> None:
        plain = CustomUser.objects.create(username="plainuser")
        body = steam_account_id_conflict_payload(2, plain)
        self.assertEqual(body["error"], "Friend ID 2 is already assigned to plainuser.")

    def test_steam_lookup_holder(self) -> None:
        client = APIClient()
        client.force_authenticate(user=self.user)
        holder = client.get(f"/api/users/steam-account-id/{STEAM_ID}/").json()["holder"]
        self.assert_no_nickname(holder)
        self.assertEqual(holder["discordNickname"], "Gwaihir")


class NicknameWriteIgnoredTests(TestCase):
    def setUp(self) -> None:
        self.staff = CustomUser.objects.create_superuser(
            username="legacy-staff", password="pw"
        )
        self.user = CustomUser.objects.create(username="legacy-target")
        self.client = APIClient()

    def test_staff_user_patch_ignores_nickname(self) -> None:
        self.client.force_authenticate(user=self.staff)
        resp = self.client.patch(
            f"/api/users/{self.user.pk}/", {"nickname": "X"}, format="json"
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertNotIn("nickname", resp.json())

    def test_me_profile_base_patch_ignores_nickname(self) -> None:
        self.client.force_authenticate(user=self.user)
        resp = self.client.patch(
            "/api/users/me/profile/base/", {"nickname": "X"}, format="json"
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertNotIn("nickname", resp.json())
