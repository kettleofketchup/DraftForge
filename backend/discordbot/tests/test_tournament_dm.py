from unittest.mock import MagicMock, patch

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient


class DiscordTournamentLogTest(TestCase):
    def setUp(self):
        from app.models import Tournament

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

        log1 = DiscordTournamentLog.objects.create(
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
        from app.models import Tournament

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
        from app.models import CustomUser, Tournament

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
    @patch("app.internal_client.create_tournament_log")
    @patch("discordbot.utils.sync_send_dm")
    @patch("app.internal_client.get_tournament_participants")
    @patch("app.internal_client.get_tournament_for_task")
    def test_sends_dm_to_participants(
        self, mock_get_tourn, mock_get_parts, mock_dm, mock_log
    ):
        from app.schemas import TournamentParticipantSchema, TournamentTaskSchema

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

    @patch("app.internal_client.get_tournament_for_task")
    def test_skips_when_disabled(self, mock_get):
        from app.schemas import TournamentTaskSchema

        mock_get.return_value = TournamentTaskSchema(
            id=1,
            name="Test",
            state="in_progress",
            discord_send_draft_link=False,
        )
        from events.tournament_tasks import send_tournament_draft_links

        result = send_tournament_draft_links(1, 42)
        self.assertIn("disabled", result.lower())

    @patch("app.internal_client.create_tournament_log")
    @patch("discordbot.utils.sync_send_dm")
    @patch("app.internal_client.get_tournament_participants")
    @patch("app.internal_client.get_tournament_for_task")
    def test_creates_log(self, mock_get_tourn, mock_get_parts, mock_dm, mock_log):
        from app.schemas import TournamentParticipantSchema, TournamentTaskSchema

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
    @patch("app.internal_client.create_tournament_log")
    @patch("discordbot.utils.sync_send_dm")
    @patch("app.internal_client.get_match_participants")
    @patch("app.internal_client.get_tournament_for_task")
    def test_sends_dm_to_match_players(self, mock_tourn, mock_parts, mock_dm, mock_log):
        from app.schemas import TournamentParticipantSchema, TournamentTaskSchema

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


class AutoCreateHeroDraftsTaskTest(TestCase):
    @patch("events.tournament_tasks.auto_create_herodrafts.apply_async")
    @patch("app.internal_client.create_herodraft_for_game")
    @patch("app.internal_client.get_games_without_herodraft")
    @patch("app.internal_client.get_tournament_for_task")
    def test_creates_herodrafts(
        self, mock_tourn, mock_games, mock_create, mock_resched
    ):
        from app.schemas import GameWithoutHeroDraftSchema, TournamentTaskSchema

        mock_tourn.return_value = TournamentTaskSchema(
            id=1,
            name="Test",
            state="in_progress",
            auto_create_hero_drafts=True,
        )
        mock_games.return_value = [
            GameWithoutHeroDraftSchema(
                id=10,
                radiant_team_id=1,
                dire_team_id=2,
                radiant_team_name="A",
                dire_team_name="B",
                has_captains=True,
            ),
        ]
        mock_create.return_value = MagicMock(
            ok=True, json=lambda: {"id": 99, "created": True}
        )

        from events.tournament_tasks import auto_create_herodrafts

        auto_create_herodrafts(1)
        mock_create.assert_called_once_with(10)
        mock_resched.assert_called_once()

    @patch("events.tournament_tasks.auto_create_herodrafts.apply_async")
    @patch("app.internal_client.get_tournament_for_task")
    def test_stops_when_completed(self, mock_tourn, mock_resched):
        from app.schemas import TournamentTaskSchema

        mock_tourn.return_value = TournamentTaskSchema(
            id=1,
            name="Test",
            state="past",
            auto_create_hero_drafts=True,
        )
        from events.tournament_tasks import auto_create_herodrafts

        auto_create_herodrafts(1)
        mock_resched.assert_not_called()

    @patch("events.tournament_tasks.auto_create_herodrafts.apply_async")
    @patch("app.internal_client.get_tournament_for_task")
    def test_stops_when_disabled(self, mock_tourn, mock_resched):
        from app.schemas import TournamentTaskSchema

        mock_tourn.return_value = TournamentTaskSchema(
            id=1,
            name="Test",
            state="in_progress",
            auto_create_hero_drafts=False,
        )
        from events.tournament_tasks import auto_create_herodrafts

        auto_create_herodrafts(1)
        mock_resched.assert_not_called()

    @patch("events.tournament_tasks.auto_create_herodrafts.apply_async")
    @patch("app.internal_client.get_games_without_herodraft")
    @patch("app.internal_client.get_tournament_for_task")
    def test_skips_games_without_captains(self, mock_tourn, mock_games, mock_resched):
        from app.schemas import GameWithoutHeroDraftSchema, TournamentTaskSchema

        mock_tourn.return_value = TournamentTaskSchema(
            id=1,
            name="Test",
            state="in_progress",
            auto_create_hero_drafts=True,
        )
        mock_games.return_value = [
            GameWithoutHeroDraftSchema(
                id=10,
                radiant_team_id=1,
                dire_team_id=2,
                has_captains=False,
            ),
        ]
        from events.tournament_tasks import auto_create_herodrafts

        auto_create_herodrafts(1)
        # Should not have tried to create herodraft (no captains)
        mock_resched.assert_called_once()  # Still reschedules


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
        from app.models import Tournament

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
        """The internal view at app.views.internal.create_discord_tournament_log
        forwards request.data fields directly into DiscordTournamentLog.objects.create
        (see ALLOWED_FIELDS at app/views/internal.py:524-531). Verify the ORM path
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

    @patch("app.internal_client.update_tournament_log")
    @patch("app.internal_client.create_tournament_log")
    @patch("discordbot.utils.sync_send_dm")
    @patch("app.internal_client.get_tournament_participants")
    @patch("app.internal_client.get_tournament_for_task")
    def test_create_log_passes_success_none(
        self, mock_tourn, mock_parts, mock_dm, mock_create, mock_update
    ):
        from app.schemas import TournamentParticipantSchema, TournamentTaskSchema

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

    @patch("app.internal_client.update_tournament_log")
    @patch("app.internal_client.create_tournament_log")
    @patch("discordbot.utils.sync_send_dm")
    @patch("app.internal_client.get_tournament_participants")
    @patch("app.internal_client.get_tournament_for_task")
    def test_update_log_sets_terminal_state(
        self, mock_tourn, mock_parts, mock_dm, mock_create, mock_update
    ):
        from app.schemas import TournamentParticipantSchema, TournamentTaskSchema

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

    @patch("app.internal_client.update_tournament_log")
    @patch("app.internal_client.create_tournament_log")
    @patch("discordbot.utils.sync_send_dm")
    @patch("app.internal_client.get_match_participants")
    @patch("app.internal_client.get_tournament_for_task")
    def test_create_log_passes_success_none(
        self, mock_tourn, mock_parts, mock_dm, mock_create, mock_update
    ):
        from app.schemas import TournamentParticipantSchema, TournamentTaskSchema

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
