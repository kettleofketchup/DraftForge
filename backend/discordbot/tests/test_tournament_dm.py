from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from tournament.schemas import (
    AutoHeroDraftGameSchema,
    TournamentParticipantSchema,
    TournamentTaskSchema,
)


class DiscordTournamentLogTest(TestCase):
    def setUp(self):
        from tournament.models import Tournament

        self.tournament = Tournament.objects.create(
            name="Test", state="future", date_played=timezone.now()
        )

    def test_create_log(self):
        from discordbot.models import DiscordTournamentLog

        # success is nullable (NULL = in flight). Unset defaults to None, not
        # True — see model docstring for the state machine. Callers MUST flip
        # to True/False explicitly when the work is done.
        log_entry = DiscordTournamentLog.objects.create(
            tournament=self.tournament,
            notification_type="draft_link",
            message="Sent to 5/8",
            recipient_count=5,
            success=True,
        )
        self.assertTrue(log_entry.success)
        self.assertEqual(log_entry.notification_type, "draft_link")

    def test_log_ordering_newest_first(self):
        from discordbot.models import DiscordTournamentLog

        DiscordTournamentLog.objects.create(
            tournament=self.tournament,
            notification_type="draft_link",
            message="First",
        )
        log2 = DiscordTournamentLog.objects.create(
            tournament=self.tournament,
            notification_type="herodraft_link",
            message="Second",
        )
        logs = list(DiscordTournamentLog.objects.filter(tournament=self.tournament))
        self.assertEqual(logs[0].pk, log2.pk)


class DiscordTournamentConfigFieldsTest(TestCase):
    def test_tournament_has_config_fields(self):
        from tournament.models import Tournament

        t = Tournament()
        self.assertFalse(t.auto_create_hero_drafts)
        # Draft/herodraft DM defaults flipped to True in 81af2454
        self.assertTrue(t.discord_send_draft_link)
        self.assertTrue(t.discord_send_herodraft_link)

    def test_event_has_tournament_discord_fields(self):
        from events.models import Event

        self.assertTrue(hasattr(Event, "discord_send_draft_link"))
        self.assertTrue(hasattr(Event, "discord_send_herodraft_link"))

    def test_event_repeater_has_fields(self):
        from events.models import EventRepeater

        self.assertTrue(hasattr(EventRepeater, "discord_send_draft_link"))
        self.assertTrue(hasattr(EventRepeater, "auto_create_hero_drafts"))

    def test_org_event_defaults_has_fields(self):
        from events.models import OrgEventDefaults

        self.assertTrue(hasattr(OrgEventDefaults, "auto_create_hero_drafts"))
        self.assertTrue(hasattr(OrgEventDefaults, "discord_send_draft_link"))


class TournamentDiscordLogAPITest(TestCase):
    def setUp(self):
        from app.models import CustomUser
        from tournament.models import Tournament

        self.user = CustomUser.objects.create_user(
            username="admin", password="testpass", is_staff=True
        )
        self.tournament = Tournament.objects.create(
            name="API Test", state="future", date_played=timezone.now()
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_get_discord_logs(self):
        from discordbot.models import DiscordTournamentLog

        DiscordTournamentLog.objects.create(
            tournament=self.tournament,
            notification_type="draft_link",
            message="Test log",
            recipient_count=5,
        )
        response = self.client.get(
            f"/api/tournaments/{self.tournament.pk}/discord-logs/"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["notification_type"], "draft_link")

    def test_tournament_serializer_has_config_fields(self):
        response = self.client.get(f"/api/tournaments/{self.tournament.pk}/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("auto_create_hero_drafts", response.data)
        self.assertIn("discord_send_draft_link", response.data)
        self.assertIn("discord_send_herodraft_link", response.data)
        self.assertFalse(response.data["auto_create_hero_drafts"])


class SendDraftLinksTaskTest(TestCase):
    @patch("events.tournament_tasks.create_tournament_log")
    @patch("events.tournament_tasks.sync_send_dm")
    @patch("events.tournament_tasks.get_tournament_participants")
    @patch("events.tournament_tasks.get_tournament_for_task")
    def test_sends_dm_to_participants(
        self, mock_get_tourn, mock_get_parts, mock_dm, mock_log
    ):
        mock_get_tourn.return_value = TournamentTaskSchema(
            id=1,
            name="Test",
            state="in_progress",
            discord_send_draft_link=True,
            draft_type="snake",
        )
        mock_get_parts.return_value = [
            TournamentParticipantSchema(user_pk=1, discord_id="111", username="p1"),
            TournamentParticipantSchema(user_pk=2, discord_id="222", username="p2"),
        ]
        mock_dm.return_value = {"id": "msg123"}
        mock_log.return_value = MagicMock(ok=True, json=lambda: {"id": 1})

        from events.tournament_tasks import send_tournament_draft_links

        send_tournament_draft_links(1, 42)
        self.assertEqual(mock_dm.call_count, 2)

    @override_settings(DISCORD_ACTIVITY_ENABLED=True)
    @patch(
        "events.tournament_tasks.create_activity_notification_invite", return_value=None
    )
    @patch("events.tournament_tasks.update_tournament_log")
    @patch("events.tournament_tasks.create_tournament_log")
    @patch("events.tournament_tasks.sync_send_dm")
    @patch("events.tournament_tasks.get_tournament_participants")
    @patch("events.tournament_tasks.get_tournament_for_task")
    def test_activity_button_uses_actual_draft_id_in_sent_dm(
        self,
        mock_tournament,
        mock_participants,
        mock_dm,
        mock_log,
        mock_update,
        _invite,
    ):
        from events.tournament_tasks import send_tournament_draft_links

        mock_tournament.return_value = TournamentTaskSchema(
            id=1,
            name="Test",
            state="in_progress",
            discord_send_draft_link=True,
            draft_type="snake",
        )
        mock_participants.return_value = [
            TournamentParticipantSchema(user_pk=1, discord_id="111", username="p1")
        ]
        mock_dm.return_value = {"id": "msg123"}
        mock_log.return_value = MagicMock(ok=True, json=lambda: {"id": 1})
        send_tournament_draft_links(1, 42)
        buttons = mock_dm.call_args.kwargs["components"][0]["components"]
        self.assertEqual(buttons[1]["custom_id"], "draft_activity:team:42")
        self.assertIn("voice channel", mock_dm.call_args.kwargs["embed"]["description"])

    @override_settings(DISCORD_ACTIVITY_ENABLED=True)
    @patch("events.tournament_tasks.create_activity_notification_invite")
    @patch("events.tournament_tasks.update_tournament_log")
    @patch("events.tournament_tasks.create_tournament_log")
    @patch("events.tournament_tasks.sync_send_dm")
    @patch("events.tournament_tasks.get_tournament_participants")
    @patch("events.tournament_tasks.get_tournament_for_task")
    def test_known_voice_channel_sends_one_click_invite_to_everyone(
        self,
        mock_tournament,
        mock_participants,
        mock_dm,
        mock_log,
        mock_update,
        mock_invite,
    ):
        from events.tournament_tasks import send_tournament_draft_links

        mock_tournament.return_value = TournamentTaskSchema(
            id=1,
            name="Test",
            state="in_progress",
            discord_send_draft_link=True,
            draft_type="snake",
        )
        mock_participants.return_value = [
            TournamentParticipantSchema(user_pk=1, discord_id="111", username="p1"),
            TournamentParticipantSchema(user_pk=2, discord_id="222", username="p2"),
        ]
        mock_dm.return_value = {"id": "msg123"}
        mock_log.return_value = MagicMock(ok=True, json=lambda: {"id": 1})
        mock_invite.return_value = "https://discord.gg/team-room"

        send_tournament_draft_links(1, 42)

        mock_invite.assert_called_once_with("team", 42)
        for call in mock_dm.call_args_list:
            launch = call.kwargs["components"][0]["components"][1]
            self.assertEqual(launch["url"], "https://discord.gg/team-room")
            self.assertNotIn("custom_id", launch)

    @override_settings(DISCORD_ACTIVITY_ENABLED=True)
    @patch("events.tournament_tasks.create_activity_notification_invite")
    @patch("events.tournament_tasks.update_tournament_log")
    @patch("events.tournament_tasks.create_tournament_log")
    @patch("events.tournament_tasks.sync_send_dm")
    @patch("events.tournament_tasks.get_match_participants")
    @patch("events.tournament_tasks.get_tournament_for_task")
    def test_hero_draft_without_shared_channel_keeps_two_step_launch(
        self,
        mock_tournament,
        mock_participants,
        mock_dm,
        mock_log,
        mock_update,
        mock_invite,
    ):
        from events.tournament_tasks import send_tournament_herodraft_links

        mock_tournament.return_value = TournamentTaskSchema(
            id=1,
            name="Test",
            state="in_progress",
            discord_send_herodraft_link=True,
            draft_type="snake",
        )
        mock_participants.return_value = [
            TournamentParticipantSchema(user_pk=1, discord_id="111", username="p1")
        ]
        mock_dm.return_value = {"id": "msg123"}
        mock_log.return_value = MagicMock(ok=True, json=lambda: {"id": 1})
        mock_invite.return_value = None

        send_tournament_herodraft_links(1, 7, 3, "A", "B")

        mock_invite.assert_called_once_with("hero", 7)
        launch = mock_dm.call_args.kwargs["components"][0]["components"][1]
        self.assertEqual(launch["custom_id"], "draft_activity:hero:7")

    @patch("events.tournament_tasks.get_tournament_for_task")
    def test_skips_when_disabled(self, mock_get):
        mock_get.return_value = TournamentTaskSchema(
            id=1,
            name="Test",
            state="in_progress",
            discord_send_draft_link=False,
        )
        from events.tournament_tasks import send_tournament_draft_links

        result = send_tournament_draft_links(1, 42)
        self.assertIn("disabled", result.lower())

    @patch("events.tournament_tasks.create_tournament_log")
    @patch("events.tournament_tasks.sync_send_dm")
    @patch("events.tournament_tasks.get_tournament_participants")
    @patch("events.tournament_tasks.get_tournament_for_task")
    def test_creates_log(self, mock_get_tourn, mock_get_parts, mock_dm, mock_log):
        mock_get_tourn.return_value = TournamentTaskSchema(
            id=1,
            name="Test",
            state="in_progress",
            discord_send_draft_link=True,
            draft_type="snake",
        )
        mock_get_parts.return_value = [
            TournamentParticipantSchema(user_pk=1, discord_id="111", username="p1"),
        ]
        mock_dm.return_value = {"id": "msg123"}
        mock_log.return_value = MagicMock(ok=True, json=lambda: {"id": 1})

        from events.tournament_tasks import send_tournament_draft_links

        send_tournament_draft_links(1, 42)
        # Tournament log is created before DMs (for FK linking)
        mock_log.assert_called_once()
        call_kwargs = mock_log.call_args[1]
        self.assertEqual(call_kwargs["notification_type"], "draft_link")
        self.assertEqual(call_kwargs["tournament_id"], 1)


class SendHeroDraftLinksTaskTest(TestCase):
    @patch("events.tournament_tasks.create_tournament_log")
    @patch("events.tournament_tasks.sync_send_dm")
    @patch("events.tournament_tasks.get_match_participants")
    @patch("events.tournament_tasks.get_tournament_for_task")
    def test_sends_dm_to_match_players(self, mock_tourn, mock_parts, mock_dm, mock_log):
        mock_tourn.return_value = TournamentTaskSchema(
            id=1,
            name="Test",
            state="in_progress",
            discord_send_herodraft_link=True,
        )
        mock_parts.return_value = [
            TournamentParticipantSchema(user_pk=1, discord_id="111", username="p1"),
            TournamentParticipantSchema(user_pk=2, discord_id="222", username="p2"),
        ]
        mock_dm.return_value = {"id": "msg123"}
        mock_log.return_value = MagicMock(ok=True, json=lambda: {"id": 1})

        from events.tournament_tasks import send_tournament_herodraft_links

        send_tournament_herodraft_links(
            1, 99, 10, radiant_name="Alpha", dire_name="Bravo"
        )
        self.assertEqual(mock_dm.call_count, 2)

    @override_settings(DISCORD_ACTIVITY_ENABLED=True)
    @patch("events.tournament_tasks.update_tournament_log")
    @patch("events.tournament_tasks.create_tournament_log")
    @patch("events.tournament_tasks.sync_send_dm")
    @patch("events.tournament_tasks.get_match_participants")
    @patch("events.tournament_tasks.get_tournament_for_task")
    def test_activity_button_is_in_hero_draft_dm(
        self, mock_tournament, mock_participants, mock_dm, mock_log, mock_update
    ):
        from events.tournament_tasks import send_tournament_herodraft_links

        mock_tournament.return_value = TournamentTaskSchema(
            id=1,
            name="Test",
            state="in_progress",
            discord_send_herodraft_link=True,
        )
        mock_participants.return_value = [
            TournamentParticipantSchema(user_pk=1, discord_id="111", username="p1")
        ]
        mock_dm.return_value = {"id": "msg123"}
        mock_log.return_value = MagicMock(ok=True, json=lambda: {"id": 1})
        send_tournament_herodraft_links(1, 99, 10, radiant_name="A", dire_name="B")
        buttons = mock_dm.call_args.kwargs["components"][0]["components"]
        self.assertEqual(buttons[1]["custom_id"], "draft_activity:hero:99")


class SweepAutoHeroDraftsTaskTest(TestCase):
    @staticmethod
    def _game(game_id: int, tournament_id: int = 1, send_link: bool = True):
        return AutoHeroDraftGameSchema(
            id=game_id,
            tournament_id=tournament_id,
            discord_send_herodraft_link=send_link,
            radiant_team_id=1,
            dire_team_id=2,
            radiant_team_name="A",
            dire_team_name="B",
            has_captains=True,
        )

    @patch("events.tournament_tasks.send_tournament_herodraft_links.delay")
    @patch("events.tournament_tasks.create_herodraft_for_game")
    @patch("events.tournament_tasks.get_auto_herodraft_games")
    def test_creates_drafts_and_sends_links(
        self, mock_games, mock_create, mock_links
    ) -> None:
        mock_games.return_value = [self._game(10, 1), self._game(20, 2, False)]
        mock_create.side_effect = [
            MagicMock(ok=True, json=lambda: {"id": 99, "created": True}),
            MagicMock(ok=True, json=lambda: {"id": 98, "created": True}),
        ]

        from events.tournament_tasks import sweep_auto_herodrafts

        sweep_auto_herodrafts()
        self.assertEqual([c.args for c in mock_create.call_args_list], [(10,), (20,)])
        mock_links.assert_called_once_with(1, 99, 10, radiant_name="A", dire_name="B")

    @patch("events.tournament_tasks.send_tournament_herodraft_links.delay")
    @patch("events.tournament_tasks.create_herodraft_for_game")
    @patch("events.tournament_tasks.get_auto_herodraft_games")
    def test_existing_draft_sends_no_link(
        self, mock_games, mock_create, mock_links
    ) -> None:
        mock_games.return_value = [self._game(10)]
        mock_create.return_value = MagicMock(
            ok=True, json=lambda: {"id": 99, "created": False}
        )

        from events.tournament_tasks import sweep_auto_herodrafts

        sweep_auto_herodrafts()
        mock_links.assert_not_called()

    @patch("events.tournament_tasks.send_tournament_herodraft_links.delay")
    @patch("events.tournament_tasks.create_herodraft_for_game")
    @patch("events.tournament_tasks.get_auto_herodraft_games")
    def test_failed_create_continues_with_next_game(
        self, mock_games, mock_create, mock_links
    ) -> None:
        mock_games.return_value = [self._game(10), self._game(20)]
        mock_create.side_effect = [
            None,
            MagicMock(ok=True, json=lambda: {"id": 98, "created": True}),
        ]

        from events.tournament_tasks import sweep_auto_herodrafts

        sweep_auto_herodrafts()
        self.assertEqual(mock_create.call_count, 2)
        mock_links.assert_called_once()

    def test_sweep_is_on_the_beat_schedule(self) -> None:
        from config.celery import app

        tasks = {e["task"] for e in app.conf.beat_schedule.values()}
        self.assertIn("events.tournament_tasks.sweep_auto_herodrafts", tasks)


# ---------------------------------------------------------------------------
# DiscordTournamentLog.success state machine
#
# Pinning #220: send_tournament_draft_links used to create the parent log row
# with success=True, recipient_count=0 BEFORE actually sending any DMs, then
# updated to the final state after the loop. A consumer of the API (frontend,
# test, dashboard) polling between the two writes would see an incoherent row
# that claimed success while showing zero recipients.
#
# Contract these tests pin:
#   - DiscordTournamentLog.success is nullable (NULL = in flight).
#   - create_tournament_log on both tasks passes success=None at create time.
#   - update_tournament_log sets success=True/False after the loop completes.
# ---------------------------------------------------------------------------


class DiscordTournamentLogSuccessNullableTest(TestCase):
    """The model must allow success=None so callers can express the
    'in-flight' state between create and update."""

    def setUp(self):
        from tournament.models import Tournament

        self.tournament = Tournament.objects.create(
            name="Nullable", state="future", date_played=timezone.now()
        )

    def test_success_can_be_null_at_create(self):
        from discordbot.models import DiscordTournamentLog

        log = DiscordTournamentLog.objects.create(
            tournament=self.tournament,
            notification_type="draft_link",
            message="Sending...",
            success=None,
        )
        log.refresh_from_db()
        self.assertIsNone(log.success)

    def test_internal_view_writes_success_null_via_orm(self):
        """The internal view at app.views.internal.create_tournament_log
        forwards request.data fields (filtered by its ALLOWED_FIELDS) directly into
        DiscordTournamentLog.objects.create. Verify the ORM path
        the view ultimately calls accepts success=None — covers what the view does
        without going through the IP-whitelisted internal HTTP auth layer."""
        from discordbot.models import DiscordTournamentLog

        # Mirror the keys the internal view passes through (it filters to
        # ALLOWED_FIELDS but is otherwise a thin .create wrapper).
        data = {
            "tournament_id": self.tournament.pk,
            "category": "notification",
            "notification_type": "draft_link",
            "message": "Sending...",
            "recipient_count": 0,
            "success": None,
        }
        entry = DiscordTournamentLog.objects.create(**data)
        entry.refresh_from_db()
        self.assertIsNone(entry.success)


class SendDraftLinksRaceTest(TestCase):
    """send_tournament_draft_links must NOT claim success=True at create.
    The create-time row should be in-flight (success=None); the post-loop
    update is what flips success to True/False with the final count."""

    @patch("events.tournament_tasks.update_tournament_log")
    @patch("events.tournament_tasks.create_tournament_log")
    @patch("events.tournament_tasks.sync_send_dm")
    @patch("events.tournament_tasks.get_tournament_participants")
    @patch("events.tournament_tasks.get_tournament_for_task")
    def test_create_log_passes_success_none(
        self, mock_tourn, mock_parts, mock_dm, mock_create, mock_update
    ):
        mock_tourn.return_value = TournamentTaskSchema(
            id=1,
            name="Race",
            state="in_progress",
            discord_send_draft_link=True,
            draft_type="snake",
        )
        mock_parts.return_value = [
            TournamentParticipantSchema(user_pk=1, discord_id="111", username="p1"),
            TournamentParticipantSchema(user_pk=2, discord_id="222", username="p2"),
        ]
        mock_dm.return_value = {"id": "msg123"}
        mock_create.return_value = MagicMock(ok=True, json=lambda: {"id": 42})

        from events.tournament_tasks import send_tournament_draft_links

        send_tournament_draft_links(1, 99)

        # The create call is the one a poller could observe mid-flight. It
        # MUST NOT lie about success — pass None so consumers can distinguish
        # "task running" from "task finished successfully".
        create_kwargs = mock_create.call_args.kwargs
        self.assertIsNone(
            create_kwargs.get("success"),
            f"create_tournament_log should pass success=None (got "
            f"{create_kwargs.get('success')!r}); see #220",
        )
        self.assertEqual(create_kwargs.get("recipient_count"), 0)

    @patch("events.tournament_tasks.update_tournament_log")
    @patch("events.tournament_tasks.create_tournament_log")
    @patch("events.tournament_tasks.sync_send_dm")
    @patch("events.tournament_tasks.get_tournament_participants")
    @patch("events.tournament_tasks.get_tournament_for_task")
    def test_update_log_sets_terminal_state(
        self, mock_tourn, mock_parts, mock_dm, mock_create, mock_update
    ):
        mock_tourn.return_value = TournamentTaskSchema(
            id=1,
            name="Race",
            state="in_progress",
            discord_send_draft_link=True,
            draft_type="snake",
        )
        mock_parts.return_value = [
            TournamentParticipantSchema(user_pk=1, discord_id="111", username="p1"),
            TournamentParticipantSchema(user_pk=2, discord_id="222", username="p2"),
        ]
        mock_dm.return_value = {"id": "msg123"}
        mock_create.return_value = MagicMock(ok=True, json=lambda: {"id": 42})

        from events.tournament_tasks import send_tournament_draft_links

        send_tournament_draft_links(1, 99)

        mock_update.assert_called_once()
        update_kwargs = mock_update.call_args.kwargs
        self.assertTrue(update_kwargs.get("success"))
        self.assertEqual(update_kwargs.get("recipient_count"), 2)


class SendHerodraftLinksRaceTest(TestCase):
    """Same contract as SendDraftLinksRaceTest, for herodraft variant."""

    @patch("events.tournament_tasks.update_tournament_log")
    @patch("events.tournament_tasks.create_tournament_log")
    @patch("events.tournament_tasks.sync_send_dm")
    @patch("events.tournament_tasks.get_match_participants")
    @patch("events.tournament_tasks.get_tournament_for_task")
    def test_create_log_passes_success_none(
        self, mock_tourn, mock_parts, mock_dm, mock_create, mock_update
    ):
        mock_tourn.return_value = TournamentTaskSchema(
            id=1,
            name="Race",
            state="in_progress",
            discord_send_herodraft_link=True,
        )
        mock_parts.return_value = [
            TournamentParticipantSchema(user_pk=1, discord_id="111", username="p1"),
        ]
        mock_dm.return_value = {"id": "msg123"}
        mock_create.return_value = MagicMock(ok=True, json=lambda: {"id": 42})

        from events.tournament_tasks import send_tournament_herodraft_links

        send_tournament_herodraft_links(
            1, 99, 10, radiant_name="Alpha", dire_name="Bravo"
        )

        create_kwargs = mock_create.call_args.kwargs
        self.assertIsNone(
            create_kwargs.get("success"),
            f"create_tournament_log should pass success=None (got "
            f"{create_kwargs.get('success')!r}); see #220",
        )
        self.assertEqual(create_kwargs.get("recipient_count"), 0)
