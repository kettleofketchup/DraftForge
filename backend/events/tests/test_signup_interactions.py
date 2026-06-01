from django.test import TestCase
from structlog.contextvars import clear_contextvars

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
        clear_contextvars()
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

    def tearDown(self):
        clear_contextvars()
        super().tearDown()

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
        cfg = result["modal_config"]
        self.assertEqual(cfg["kind"], "dota")
        self.assertTrue(cfg["require_rank_screenshot"])
        self.assertFalse(cfg["require_battlecup_screenshot"])
        self.assertEqual(cfg["min_mmr"], 3000)


class HandleSignupModalSubmitTest(EventTestCase):
    def setUp(self):
        super().setUp()
        clear_contextvars()
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

    def tearDown(self):
        clear_contextvars()
        super().tearDown()

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

        # Verify CustomUser.steam_account_id was NOT modified by the modal.
        # The setUp sets steamid, and CustomUser.save() syncs steam_account_id
        # from steamid (32-bit vs 64-bit are the same identity — see T1.5
        # resurrection of the steam-id sync). So the baseline is the derived
        # value, not None. Confirm the modal handler didn't *change* it.
        baseline_steam_account_id = self.user.steam_account_id
        self.user.refresh_from_db()
        self.assertEqual(self.user.steam_account_id, baseline_steam_account_id)

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

    def test_modal_submit_returns_vocabulary_message_on_disallowed_rank_status(self):
        """Discord adapter surfaces the EXACT vocabulary-table message when
        apply_signup_input raises DjangoValidationError from a policy gate.

        This pins the contract that the {"action": "error", "message": ...}
        return shape preserves the curated vocabulary from
        events.services._RANK_STATUS_DISALLOWED_MESSAGES verbatim, rather
        than wrapping/munging it via str(exc) (which would yield
        "['This event...']" with the list brackets).
        """
        from events.discord import handle_signup_modal_submit

        # Configure event to disallow active MMR signups.
        self.event.allow_active_mmr = False
        self.event.save()

        result = handle_signup_modal_submit(
            event_id=self.event.pk,
            discord_user_id="100000000000000001",
            game_type=GameType.DOTA2,
            values={"rank_status": "active"},
        )
        self.assertEqual(result["action"], "error")
        self.assertEqual(
            result["message"],
            "This event does not accept active MMR signups.",
        )


class HandleRankMedalSelectTest(EventTestCase):
    def setUp(self):
        super().setUp()
        clear_contextvars()
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

    def tearDown(self):
        clear_contextvars()
        super().tearDown()

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


class HandleRankStatusSelectTest(EventTestCase):
    def setUp(self):
        super().setUp()
        clear_contextvars()
        self.event.state = EventState.SIGNUPS_OPEN
        self.event.auto_approve = True
        self.event.save()
        self.user.discordId = "100000000000000001"
        self.user.save()
        self.org_user = OrgUser.objects.create(
            user=self.user,
            organization=self.event.organization,
        )

    def tearDown(self):
        clear_contextvars()
        super().tearDown()

    def test_handle_rank_status_select_calls_apply_signup_input(self):
        """rank_status write flows through apply_signup_input via SignupInputPatch."""
        from unittest.mock import patch as mock_patch

        from events.discord import handle_rank_status_select
        from events.schemas import SignupInputPatch

        with mock_patch("events.services.apply_signup_input") as spy:
            handle_rank_status_select(
                event_id=self.event.pk,
                discord_user_id="100000000000000001",
                rank_status="active",
            )
        spy.assert_called_once()
        patch_arg = spy.call_args.kwargs["patch"]
        self.assertIsInstance(patch_arg, SignupInputPatch)
        self.assertEqual(patch_arg.rank_status, "active")


class HandlePreviousRankSubmitTest(EventTestCase):
    def setUp(self):
        super().setUp()
        clear_contextvars()
        self.event.state = EventState.SIGNUPS_OPEN
        self.event.auto_approve = True
        self.event.save()
        self.user.discordId = "100000000000000001"
        self.user.save()
        self.org_user = OrgUser.objects.create(
            user=self.user,
            organization=self.event.organization,
        )

    def tearDown(self):
        clear_contextvars()
        super().tearDown()

    def test_handle_previous_rank_submit_calls_apply_signup_input(self):
        """rank_medal write (previous rank flow) flows through apply_signup_input."""
        from unittest.mock import patch as mock_patch

        from events.discord import handle_previous_rank_submit
        from events.schemas import SignupInputPatch

        with mock_patch("events.services.apply_signup_input") as spy:
            handle_previous_rank_submit(
                event_id=self.event.pk,
                discord_user_id="100000000000000001",
                medal="Legend 4",
                date_text="2024",
            )
        spy.assert_called_once()
        patch_arg = spy.call_args.kwargs["patch"]
        self.assertIsInstance(patch_arg, SignupInputPatch)
        self.assertEqual(patch_arg.rank_medal, "Legend 4")


class HandleBattleCupSubmitTest(EventTestCase):
    def setUp(self):
        super().setUp()
        clear_contextvars()
        self.event.state = EventState.SIGNUPS_OPEN
        self.event.auto_approve = True
        self.event.save()
        self.user.discordId = "100000000000000001"
        self.user.save()
        self.org_user = OrgUser.objects.create(
            user=self.user,
            organization=self.event.organization,
        )

    def tearDown(self):
        clear_contextvars()
        super().tearDown()

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
        clear_contextvars()
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

    def tearDown(self):
        clear_contextvars()
        super().tearDown()

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
        self.assertEqual(
            result["message"],
            "Screenshot must be a direct .png/.jpg/.jpeg/.webp URL.",
        )

    def test_handle_screenshot_upload_calls_apply_signup_input(self):
        """rank_screenshot write flows through apply_signup_input via SignupInputPatch."""
        from unittest.mock import patch as mock_patch

        from events.discord import handle_screenshot_upload
        from events.schemas import SignupInputPatch

        with mock_patch("events.services.apply_signup_input") as spy:
            handle_screenshot_upload(
                event_id=self.event.pk,
                discord_user_id="100000000000000001",
                screenshot_type="rank",
                attachment_url="https://example.com/a.png",
            )
        spy.assert_called_once()
        patch_arg = spy.call_args.kwargs["patch"]
        self.assertIsInstance(patch_arg, SignupInputPatch)
        self.assertEqual(patch_arg.rank_screenshot, "https://example.com/a.png")


class HandleSetPositionTest(EventTestCase):
    """Smoke coverage for handle_set_position (legacy pos_select_* flow)."""

    def setUp(self):
        super().setUp()
        clear_contextvars()
        self.event.state = EventState.SIGNUPS_OPEN
        self.event.game_type = GameType.DOTA2
        self.event.save()
        self.user.discordId = "100000000000000001"
        self.user.save()
        self.org_user = OrgUser.objects.create(
            user=self.user,
            organization=self.event.organization,
        )

    def tearDown(self):
        clear_contextvars()
        super().tearDown()

    def test_handle_set_position_writes_pos_n(self):
        """Calling handle_set_position(position=2) sets pos_2=True on the profile."""
        from events.discord.handlers import handle_set_position

        result = handle_set_position(
            self.event.pk, "100000000000000001", position=2
        )
        self.assertEqual(result["action"], "position_set")
        profile = PlayerDotaProfile.objects.get(org_user=self.org_user)
        self.assertTrue(profile.pos_2)
        # Other positions should remain at their default (False).
        self.assertFalse(profile.pos_1)
        self.assertFalse(profile.pos_3)

    def test_handle_set_position_rejects_out_of_range(self):
        from events.discord.handlers import handle_set_position

        result = handle_set_position(
            self.event.pk, "100000000000000001", position=99
        )
        self.assertEqual(result["action"], "error")


class HandleGetRankFlowStateTest(EventTestCase):
    """Smoke coverage for handle_get_rank_flow_state (legacy pos_confirm flow)."""

    def setUp(self):
        super().setUp()
        clear_contextvars()
        self.event.state = EventState.SIGNUPS_OPEN
        self.event.game_type = GameType.DOTA2
        self.event.discord_require_rank_screenshot = True
        self.event.min_mmr = 3500
        self.event.save()
        self.user.discordId = "100000000000000001"
        self.user.save()
        self.org_user = OrgUser.objects.create(
            user=self.user,
            organization=self.event.organization,
        )
        PlayerDotaProfile.objects.create(
            org_user=self.org_user,
            rank_status="active",
        )

    def tearDown(self):
        clear_contextvars()
        super().tearDown()

    def test_handle_get_rank_flow_state_returns_event_config(self):
        from events.discord.handlers import handle_get_rank_flow_state

        result = handle_get_rank_flow_state(self.event.pk, "100000000000000001")
        self.assertEqual(result["rank_status"], "active")
        self.assertTrue(result["require_screenshot"])
        self.assertEqual(result["min_mmr"], 3500)
        self.assertNotIn("error", {k for k, v in result.items() if v is not None})

    def test_handle_get_rank_flow_state_event_not_found(self):
        from events.discord.handlers import handle_get_rank_flow_state

        result = handle_get_rank_flow_state(999999, "100000000000000001")
        self.assertEqual(result.get("error"), "event_not_found")
