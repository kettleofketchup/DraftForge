from django.test import TestCase

from app.models import CustomUser
from org.models import Organization, OrgUser
from org.serializers import OrgUserSerializer


class OrgUserSerializerGuildNicknameTest(TestCase):
    def setUp(self) -> None:
        self.user = CustomUser.objects.create(
            username="serializer_guildnick", guildNickname="UserLevelNick"
        )
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
