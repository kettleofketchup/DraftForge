from django.test import TestCase

from app.models import CustomUser, Organization
from app.tests.raw_site_nickname import set_raw_guild_nickname
from org.models import OrgUser
from org.serializers import OrgUserSerializer


class OrgUserSerializerGuildNicknameTest(TestCase):
    def setUp(self) -> None:
        self.user = CustomUser.objects.create(username="serializer_guildnick")
        set_raw_guild_nickname(self.user.pk, "UserLevelNick")
        self.org = Organization.objects.create(name="Serializer Guild Org")

    def test_emits_org_user_guild_nickname(self) -> None:
        org_user = OrgUser.objects.create(
            user=self.user, organization=self.org, guild_nickname="DragonClaw"
        )
        self.assertEqual(
            OrgUserSerializer(org_user).data["guildNickname"], "DragonClaw"
        )

    def test_ignores_user_guild_nickname(self) -> None:
        org_user = OrgUser.objects.create(user=self.user, organization=self.org)
        self.assertIsNone(OrgUserSerializer(org_user).data["guildNickname"])
