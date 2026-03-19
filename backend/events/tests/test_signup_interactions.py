from django.test import TestCase

from app.models import CustomUser, GameType, Organization, PositionsModel
from discordbot.models import DiscordMessageLog
from events.models import Event, EventSignup, EventState, SignupStatus
from events.tests.base import EventTestCase
from org.models import OrgUser


class HandleSignupButtonTest(EventTestCase):
    def setUp(self):
        super().setUp()
        self.event.state = EventState.SIGNUPS_OPEN
        self.event.game_type = GameType.DOTA2
        self.event.auto_approve = True
        self.event.save()
        self.user.discordId = "100000000000000001"
        self.user.save()
        # Create OrgUser for the event's org
        self.org_user = OrgUser.objects.create(
            user=self.user,
            organization=self.event.organization,
        )

    def test_complete_profile_signs_up_directly(self):
        """User with complete Dota profile skips modal."""
        from events.discord import handle_signup_button
        from org.models_profiles import PlayerDotaProfile

        PlayerDotaProfile.objects.create(
            org_user=self.org_user,
            rank_status="active",
            rank_medal="Legend",
            pos_1=True,
            pos_2=True,
            pos_5=True,
        )
        result = handle_signup_button(self.event.pk, "100000000000000001")
        self.assertEqual(result["action"], "signed_up")

    def test_missing_profile_returns_needs_modal(self):
        """User without profile gets modal."""
        from events.discord import handle_signup_button

        result = handle_signup_button(self.event.pk, "100000000000000001")
        self.assertEqual(result["action"], "needs_modal")
        self.assertEqual(result["game_type"], GameType.DOTA2)

    def test_unlinked_user_returns_error(self):
        from events.discord import handle_signup_button

        result = handle_signup_button(self.event.pk, "999999999999999999")
        self.assertEqual(result["action"], "error")

    def test_closed_event_returns_error(self):
        from events.discord import handle_signup_button

        self.event.state = EventState.COMPLETED
        self.event.save()
        result = handle_signup_button(self.event.pk, "100000000000000001")
        self.assertEqual(result["action"], "error")


class HandleSignupModalSubmitTest(EventTestCase):
    def setUp(self):
        super().setUp()
        self.event.state = EventState.SIGNUPS_OPEN
        self.event.game_type = GameType.DOTA2
        self.event.auto_approve = True
        self.event.save()
        self.user.discordId = "100000000000000001"
        self.user.save()
        self.org_user = OrgUser.objects.create(
            user=self.user,
            organization=self.event.organization,
        )

    def test_dota_modal_saves_profile_and_returns_needs_rank(self):
        from events.discord import handle_signup_modal_submit

        result = handle_signup_modal_submit(
            event_id=self.event.pk,
            discord_user_id="100000000000000001",
            game_type=1,
            values={
                "unverified_steam_id": "12345",
                "positions": ["1", "2", "5"],
                "rank_status": "active",
            },
        )
        self.assertEqual(result["action"], "needs_rank_details")

        # Verify profile saved on OrgUser
        from org.models_profiles import PlayerDotaProfile

        profile = PlayerDotaProfile.objects.get(org_user=self.org_user)
        self.assertTrue(profile.pos_1)
        self.assertTrue(profile.pos_2)
        self.assertTrue(profile.pos_5)
        self.assertFalse(profile.pos_3)
        self.assertEqual(profile.unverified_steam_id, "12345")

        # Verify CustomUser.steam_account_id was NOT modified
        self.user.refresh_from_db()
        self.assertIsNone(self.user.steam_account_id)

    def test_deadlock_modal_signs_up_directly(self):
        from events.discord import handle_signup_modal_submit

        self.event.game_type = GameType.DEADLOCK
        self.event.save()

        result = handle_signup_modal_submit(
            event_id=self.event.pk,
            discord_user_id="100000000000000001",
            game_type=2,
            values={
                "unverified_steam_id": "12345",
                "deadlock_rank": "Phantom IV",
                "deadlock_date": "last week",
            },
        )
        self.assertEqual(result["action"], "signed_up")

        from org.models_profiles import PlayerDeadlockProfile

        profile = PlayerDeadlockProfile.objects.get(org_user=self.org_user)
        self.assertEqual(profile.rank, "Phantom IV")
        self.assertEqual(profile.unverified_steam_id, "12345")


class HandleRankMedalSelectTest(EventTestCase):
    def setUp(self):
        super().setUp()
        self.event.state = EventState.SIGNUPS_OPEN
        self.event.auto_approve = True
        self.event.save()
        self.user.discordId = "100000000000000001"
        self.user.save()
        self.org_user = OrgUser.objects.create(
            user=self.user,
            organization=self.event.organization,
        )
        from org.models_profiles import PlayerDotaProfile

        PlayerDotaProfile.objects.create(
            org_user=self.org_user,
            rank_status="active",
            pos_1=True,
        )

    def test_saves_medal_and_signs_up(self):
        from events.discord import handle_rank_medal_select

        result = handle_rank_medal_select(self.event.pk, "100000000000000001", "Legend")
        self.assertEqual(result["action"], "signed_up")

        from org.models_profiles import PlayerDotaProfile

        profile = PlayerDotaProfile.objects.get(org_user=self.org_user)
        self.assertEqual(profile.rank_medal, "Legend")

        self.assertTrue(
            EventSignup.objects.filter(event=self.event, user=self.user).exists()
        )
