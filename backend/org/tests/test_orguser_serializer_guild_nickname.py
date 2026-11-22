from django.test import TestCase

from app.models import CustomUser
from org.mmr import game_mmrs_prefetch
from org.models import Organization, OrgUser
from org.serializers import OrgUserSerializer


def _prefetched(org_user: OrgUser) -> OrgUser:
    return OrgUser.objects.prefetch_related(game_mmrs_prefetch(fresh=False)).get(
        pk=org_user.pk
    )


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
            OrgUserSerializer(_prefetched(org_user)).data["guildNickname"], "DragonClaw"
        )

    def test_ignores_user_guild_nickname(self) -> None:
        org_user = OrgUser.objects.create(user=self.user, organization=self.org)
        self.assertIsNone(
            OrgUserSerializer(_prefetched(org_user)).data["guildNickname"]
        )
