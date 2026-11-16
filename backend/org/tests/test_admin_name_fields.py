from django.test import TestCase

from app.models import CustomUser, Organization
from org.models import OrgUser


class AdminNameFieldsTest(TestCase):
    def setUp(self) -> None:
        self.superuser = CustomUser.objects.create_superuser(
            username="names_admin", password="x", email="na@example.com"
        )
        self.client.force_login(self.superuser)
        self.org = Organization.objects.create(name="Admin Names Org")
        self.user = CustomUser.objects.create_user(
            username="names_target", password="x", discordNickname="Gwaihir"
        )
        self.org_user = OrgUser.objects.create(
            user=self.user, organization=self.org, guild_nickname="DragonClaw"
        )

    def test_org_user_guild_nickname_read_only(self) -> None:
        resp = self.client.get(f"/admin/org/orguser/{self.org_user.pk}/change/")
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode()
        self.assertNotIn('name="guild_nickname"', html)
        self.assertIn("DragonClaw", html)

    def test_custom_user_discord_nickname_read_only_guild_absent(self) -> None:
        resp = self.client.get(f"/admin/app/customuser/{self.user.pk}/change/")
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode()
        self.assertNotIn('name="discordNickname"', html)
        self.assertIn("Gwaihir", html)
        self.assertNotIn("guildNickname", html)
