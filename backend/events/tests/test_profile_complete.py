from datetime import timedelta

from django.test import TestCase
from django.utils import timezone as tz

from app.models import CustomUser, Organization
from events.constants import EventState
from events.models import Event
from events.services import check_requirements


class RequireProfileCompleteTest(TestCase):
    def setUp(self) -> None:
        self.admin = CustomUser.objects.create(username="pc_admin")
        self.org = Organization.objects.create(name="PC Org", owner=self.admin)
        self.event = Event.objects.create(
            organization=self.org,
            name="PC Event",
            scheduled_at=tz.now() + timedelta(days=3),
            state=EventState.SIGNUPS_OPEN,
            created_by=self.admin,
            require_profile_complete=True,
        )

    def test_steam_and_discord_without_nickname_is_eligible(self) -> None:
        user = CustomUser.objects.create(
            username="fresh", steamid=76561198000000042, discordId="4242"
        )
        self.assertTrue(check_requirements(self.event, user))

    def test_without_steam_is_not_eligible(self) -> None:
        user = CustomUser.objects.create(username="nosteam", discordId="4343")
        self.assertFalse(check_requirements(self.event, user))

    def test_without_discord_is_not_eligible(self) -> None:
        user = CustomUser.objects.create(
            username="nodiscord", steamid=76561198000000043
        )
        self.assertFalse(check_requirements(self.event, user))
