from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from app.models import CustomUser, Organization
from discordbot.models import DiscordEvent, DiscordEventLog, LogCategory
from discordbot.serializers_discord_event import DiscordEventDetailSerializer
from events.models import Event
from org.models import OrgUser


class DiscordEventLogGuildNicknameTest(TestCase):
    def setUp(self) -> None:
        owner = CustomUser.objects.create_user(username="owner", password="pw")
        self.org = Organization.objects.create(name="DTX", owner=owner)
        event = Event.objects.create(
            organization=self.org,
            name="Inhouse",
            scheduled_at=timezone.now(),
            created_by=owner,
        )
        self.discord_event = DiscordEvent.objects.create(event=event, guild_id="1")
        self.member = CustomUser.objects.create_user(
            username="gwen", password="pw", discordId="9001"
        )
        self.member.discordNickname = "GwaihirTheWindlord"
        self.member.save()
        OrgUser.objects.create(
            user=self.member, organization=self.org, guild_nickname="  DragonClaw "
        )
        self.outsider = CustomUser.objects.create_user(
            username="outsider", password="pw", discordId="9002"
        )
        for discord_id in ("9001", "9002", "", "404"):
            DiscordEventLog.objects.create(
                discord_event=self.discord_event,
                category=LogCategory.SIGNUP,
                action="rsvp",
                discord_user_id=discord_id,
            )

    def _logs_by_discord_id(self) -> dict[str, dict]:
        data = DiscordEventDetailSerializer(self.discord_event).data
        return {log["discord_user_id"]: log for log in data["logs"]}

    def test_log_rows_carry_org_server_nickname(self) -> None:
        logs = self._logs_by_discord_id()
        self.assertEqual(logs["9001"]["guildNickname"], "DragonClaw")
        self.assertEqual(logs["9001"]["discordNickname"], "GwaihirTheWindlord")
        self.assertEqual(logs["9001"]["username"], "gwen")
        self.assertIsNone(logs["9002"]["guildNickname"])
        self.assertIsNone(logs[""]["guildNickname"])
        self.assertIsNone(logs["404"]["guildNickname"])

    def test_private_member_list_hides_server_nickname(self) -> None:
        self.org.members_private = True
        self.org.save()
        logs = self._logs_by_discord_id()
        self.assertIsNone(logs["9001"]["guildNickname"])
        self.assertEqual(logs["9001"]["username"], "gwen")

    def _query_count(self) -> int:
        with CaptureQueriesContext(connection) as ctx:
            DiscordEventDetailSerializer(self.discord_event).data
        return len(ctx.captured_queries)

    def test_nickname_lookup_is_batched(self) -> None:
        baseline = self._query_count()
        third = CustomUser.objects.create_user(
            username="third", password="pw", discordId="9003"
        )
        OrgUser.objects.create(
            user=third, organization=self.org, guild_nickname="ThirdNick"
        )
        DiscordEventLog.objects.create(
            discord_event=self.discord_event,
            category=LogCategory.SIGNUP,
            action="rsvp",
            discord_user_id="9003",
        )
        self.assertEqual(self._query_count(), baseline)
        self.assertEqual(
            self._logs_by_discord_id()["9003"]["guildNickname"], "ThirdNick"
        )
