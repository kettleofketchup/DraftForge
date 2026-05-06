from django.test import TestCase

from app.models import CustomUser, GameType, Organization, PositionsModel
from discordbot.models import DiscordMessageLog
from events.constants import EventState, SignupStatus
from events.models import Event, EventSignup
from events.tests.base import EventTestCase
from org.models import OrgUser
from org.models_profiles import PlayerDotaProfile


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

    def test_unknown_discord_user_auto_creates_account(self):
        from app.models import CustomUser
        from events.discord import handle_signup_button

        result = handle_signup_button(
            self.event.pk, "999999999999999999", discord_username="newplayer"
        )
        # Should auto-create user and proceed to modal (not error)
        self.assertEqual(result["action"], "needs_modal")
        user = CustomUser.objects.get(discordId="999999999999999999")
        self.assertEqual(user.nickname, "newplayer")

    def test_closed_event_returns_error(self):
        from events.discord import handle_signup_button

        self.event.state = EventState.COMPLETED
        self.event.save()
        result = handle_signup_button(self.event.pk, "100000000000000001")
        self.assertEqual(result["action"], "error")

    def test_signup_button_returns_screenshot_config(self):
        """handle_signup_button includes screenshot config in needs_modal response."""
        from events.discord import handle_signup_button

        self.event.discord_require_rank_screenshot = True
        self.event.min_mmr = 3000
        self.event.save()

        result = handle_signup_button(
            event_id=self.event.pk,
            discord_user_id="100000000000000001",
        )
        self.assertEqual(result["action"], "needs_modal")
        self.assertTrue(result["require_rank_screenshot"])
        self.assertFalse(result["require_battlecup_screenshot"])
        self.assertEqual(result["min_mmr"], 3000)


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

    def test_dota_modal_writes_rank_status_and_returns_needs_rank_details(self):
        """Dota modal submit persists rank_status and friend ID, returns needs_rank_details.

        Positions are no longer written by the modal — they flow through
        PositionConfirmButton.callback after the modal closes.
        """
        from events.discord import handle_signup_modal_submit

        result = handle_signup_modal_submit(
            event_id=self.event.pk,
            discord_user_id="100000000000000001",
            game_type=1,
            values={
                "unverified_friend_id": "12345",
                "rank_status": "active",
            },
        )
        self.assertEqual(result["action"], "needs_rank_details")

        # Verify non-position profile fields saved on OrgUser
        from org.models_profiles import PlayerDotaProfile

        profile = PlayerDotaProfile.objects.get(org_user=self.org_user)
        self.assertEqual(profile.rank_status, "active")
        self.assertEqual(profile.unverified_friend_id, "12345")

        # Verify CustomUser.steam_account_id was NOT modified
        self.user.refresh_from_db()
        self.assertIsNone(self.user.steam_account_id)

    def test_modal_submit_calls_apply_signup_input_for_dota(self):
        """Dota 2 branch routes profile writes through apply_signup_input."""
        from unittest.mock import patch as mock_patch

        from events.discord import handle_signup_modal_submit
        from events.schemas import SignupInputPatch

        with mock_patch("events.services.apply_signup_input") as spy:
            handle_signup_modal_submit(
                event_id=self.event.pk,
                discord_user_id="100000000000000001",
                game_type=GameType.DOTA2,
                values={
                    "unverified_friend_id": "12345",
                    "rank_status": "active",
                    "positions": [],
                },
            )
        spy.assert_called_once()
        patch_arg = spy.call_args.kwargs["patch"]
        self.assertIsInstance(patch_arg, SignupInputPatch)
        self.assertEqual(patch_arg.unverified_friend_id, "12345")
        self.assertEqual(patch_arg.rank_status, "active")

    def test_deadlock_modal_signs_up_directly(self):
        from events.discord import handle_signup_modal_submit

        self.event.game_type = GameType.DEADLOCK
        self.event.save()

        result = handle_signup_modal_submit(
            event_id=self.event.pk,
            discord_user_id="100000000000000001",
            game_type=2,
            values={
                "unverified_friend_id": "12345",
                "deadlock_rank": "Phantom IV",
                "deadlock_date": "last week",
            },
        )
        self.assertEqual(result["action"], "signed_up")

        from org.models_profiles import PlayerDeadlockProfile

        profile = PlayerDeadlockProfile.objects.get(org_user=self.org_user)
        self.assertEqual(profile.rank, "Phantom IV")
        self.assertEqual(profile.unverified_friend_id, "12345")


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

    def test_handle_rank_medal_select_calls_apply_signup_input(self):
        """rank_medal write flows through apply_signup_input via SignupInputPatch."""
        from unittest.mock import patch as mock_patch

        from events.discord import handle_rank_medal_select
        from events.schemas import SignupInputPatch

        with mock_patch("events.services.apply_signup_input") as spy:
            handle_rank_medal_select(
                event_id=self.event.pk,
                discord_user_id="100000000000000001",
                medal="Legend 3",
            )
        spy.assert_called_once()
        patch_arg = spy.call_args.kwargs["patch"]
        self.assertIsInstance(patch_arg, SignupInputPatch)
        self.assertEqual(patch_arg.rank_medal, "Legend 3")


class HandleBattleCupSubmitTest(EventTestCase):
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

    def test_handle_battle_cup_submit_calls_apply_signup_input(self):
        """battle_cup_tier write flows through apply_signup_input via SignupInputPatch."""
        from unittest.mock import patch as mock_patch

        from events.discord import handle_battle_cup_submit
        from events.schemas import SignupInputPatch

        with mock_patch("events.services.apply_signup_input") as spy:
            handle_battle_cup_submit(
                event_id=self.event.pk,
                discord_user_id="100000000000000001",
                tier="5",
            )
        spy.assert_called_once()
        patch_arg = spy.call_args.kwargs["patch"]
        self.assertIsInstance(patch_arg, SignupInputPatch)
        self.assertEqual(patch_arg.battle_cup_tier, 5)


class HandleScreenshotUploadTest(EventTestCase):
    def setUp(self):
        super().setUp()
        self.event.state = EventState.SIGNUPS_OPEN
        self.event.game_type = GameType.DOTA2
        self.event.save()
        self.user.discordId = "100000000000000001"
        self.user.save()
        self.org_user = OrgUser.objects.create(
            user=self.user,
            organization=self.event.organization,
        )
        self.profile = PlayerDotaProfile.objects.create(org_user=self.org_user)

    def test_screenshot_upload_saves_url(self):
        """Screenshot upload handler saves URL to profile."""
        from events.discord import handle_screenshot_upload

        result = handle_screenshot_upload(
            event_id=self.event.pk,
            discord_user_id="100000000000000001",
            screenshot_type="rank",
            attachment_url="https://cdn.discord.com/test/screenshot.png",
        )
        self.assertTrue(result["success"])
        self.profile.refresh_from_db()
        self.assertEqual(
            self.profile.rank_screenshot,
            "https://cdn.discord.com/test/screenshot.png",
        )

    def test_screenshot_upload_rejects_invalid_extension(self):
        """Screenshot upload rejects non-image files."""
        from events.discord import handle_screenshot_upload

        result = handle_screenshot_upload(
            event_id=self.event.pk,
            discord_user_id="100000000000000001",
            screenshot_type="rank",
            attachment_url="https://cdn.discord.com/test/file.pdf",
        )
        self.assertFalse(result["success"])
        self.assertIn("Invalid file type", result["message"])
