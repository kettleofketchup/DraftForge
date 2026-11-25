from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from app.models import CustomUser
from config.celery import app as celery_app
from discordbot.dm import DMOutcome
from discordbot.dm_keys import tournament_draft_link_key, tournament_herodraft_link_key
from discordbot.dm_ledger import ClaimResult
from discordbot.models import (
    DiscordDM,
    DiscordMessageLog,
    DiscordTournamentLog,
    DMKind,
    DMStatus,
    DMSubject,
)
from discordbot.schemas import DMClaimBody
from discordbot.tests.ledger_bridge import ledger_bridge
from discordbot.utils import DiscordAuthError
from events.models import Event, EventRepeater, OrgEventDefaults
from events.tournament_tasks import (
    send_tournament_draft_links,
    send_tournament_herodraft_links,
    sweep_auto_herodrafts,
)
from league.models import League
from org.models import Organization
from tournament.models import Tournament
from tournament.schemas import (
    AutoHeroDraftGameSchema,
    TournamentParticipantSchema,
    TournamentTaskSchema,
)

SENT = DMOutcome(
    status=DMStatus.SENT,
    ledger_id=1,
    message_id="msg123",
    channel_id="chan1",
    error_code=None,
)


class DiscordTournamentLogTest(TestCase):
    def setUp(self):
        self.tournament = Tournament.objects.create(
            name="Test", state="future", date_played=timezone.now()
        )

    def test_create_log(self):
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
        t = Tournament()
        self.assertFalse(t.auto_create_hero_drafts)
        # Draft/herodraft DM defaults flipped to True in 81af2454
        self.assertTrue(t.discord_send_draft_link)
        self.assertTrue(t.discord_send_herodraft_link)

    def test_event_has_tournament_discord_fields(self):
        self.assertTrue(hasattr(Event, "discord_send_draft_link"))
        self.assertTrue(hasattr(Event, "discord_send_herodraft_link"))

    def test_event_repeater_has_fields(self):
        self.assertTrue(hasattr(EventRepeater, "discord_send_draft_link"))
        self.assertTrue(hasattr(EventRepeater, "auto_create_hero_drafts"))

    def test_org_event_defaults_has_fields(self):
        self.assertTrue(hasattr(OrgEventDefaults, "auto_create_hero_drafts"))
        self.assertTrue(hasattr(OrgEventDefaults, "discord_send_draft_link"))


class TournamentDiscordLogAPITest(TestCase):
    def setUp(self):
        self.user = CustomUser.objects.create_user(
            username="admin", password="testpass", is_staff=True
        )
        self.tournament = Tournament.objects.create(
            name="API Test", state="future", date_played=timezone.now()
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_get_discord_logs(self):
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
    @patch("events.tournament_tasks.send_dm")
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
        mock_dm.return_value = SENT
        mock_log.return_value = MagicMock(ok=True, json=lambda: {"id": 1})

        send_tournament_draft_links(1, 42)
        self.assertEqual(mock_dm.call_count, 2)

    @override_settings(DISCORD_ACTIVITY_ENABLED=True)
    @patch(
        "events.tournament_tasks.create_activity_notification_invite", return_value=None
    )
    @patch("events.tournament_tasks.update_tournament_log")
    @patch("events.tournament_tasks.create_tournament_log")
    @patch("events.tournament_tasks.send_dm")
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
        mock_dm.return_value = SENT
        mock_log.return_value = MagicMock(ok=True, json=lambda: {"id": 1})
        send_tournament_draft_links(1, 42)
        buttons = mock_dm.call_args.args[0].components[0]["components"]
        self.assertEqual(buttons[1]["custom_id"], "draft_activity:team:42")
        self.assertIn("voice channel", mock_dm.call_args.args[0].embed["description"])

    @override_settings(DISCORD_ACTIVITY_ENABLED=True)
    @patch("events.tournament_tasks.create_activity_notification_invite")
    @patch("events.tournament_tasks.update_tournament_log")
    @patch("events.tournament_tasks.create_tournament_log")
    @patch("events.tournament_tasks.send_dm")
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
        mock_dm.return_value = SENT
        mock_log.return_value = MagicMock(ok=True, json=lambda: {"id": 1})
        mock_invite.return_value = "https://discord.gg/team-room"

        send_tournament_draft_links(1, 42)

        mock_invite.assert_called_once_with("team", 42)
        for call in mock_dm.call_args_list:
            launch = call.args[0].components[0]["components"][1]
            self.assertEqual(launch["url"], "https://discord.gg/team-room")
            self.assertNotIn("custom_id", launch)

    @override_settings(DISCORD_ACTIVITY_ENABLED=True)
    @patch("events.tournament_tasks.create_activity_notification_invite")
    @patch("events.tournament_tasks.update_tournament_log")
    @patch("events.tournament_tasks.create_tournament_log")
    @patch("events.tournament_tasks.send_dm")
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
        mock_dm.return_value = SENT
        mock_log.return_value = MagicMock(ok=True, json=lambda: {"id": 1})
        mock_invite.return_value = None

        send_tournament_herodraft_links(1, 7, 3, "A", "B")

        mock_invite.assert_called_once_with("hero", 7)
        launch = mock_dm.call_args.args[0].components[0]["components"][1]
        self.assertEqual(launch["custom_id"], "draft_activity:hero:7")

    @patch("events.tournament_tasks.get_tournament_for_task")
    def test_skips_when_disabled(self, mock_get):
        mock_get.return_value = TournamentTaskSchema(
            id=1,
            name="Test",
            state="in_progress",
            discord_send_draft_link=False,
        )

        result = send_tournament_draft_links(1, 42)
        self.assertIn("disabled", result.lower())

    @patch("events.tournament_tasks.create_tournament_log")
    @patch("events.tournament_tasks.send_dm")
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
        mock_dm.return_value = SENT
        mock_log.return_value = MagicMock(ok=True, json=lambda: {"id": 1})

        send_tournament_draft_links(1, 42)
        # Tournament log is created before DMs (for FK linking)
        mock_log.assert_called_once()
        call_kwargs = mock_log.call_args[1]
        self.assertEqual(call_kwargs["notification_type"], "draft_link")
        self.assertEqual(call_kwargs["tournament_id"], 1)


class SendHeroDraftLinksTaskTest(TestCase):
    @patch("events.tournament_tasks.create_tournament_log")
    @patch("events.tournament_tasks.send_dm")
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
        mock_dm.return_value = SENT
        mock_log.return_value = MagicMock(ok=True, json=lambda: {"id": 1})

        send_tournament_herodraft_links(
            1, 99, 10, radiant_name="Alpha", dire_name="Bravo"
        )
        self.assertEqual(mock_dm.call_count, 2)

    @override_settings(DISCORD_ACTIVITY_ENABLED=True)
    @patch("events.tournament_tasks.update_tournament_log")
    @patch("events.tournament_tasks.create_tournament_log")
    @patch("events.tournament_tasks.send_dm")
    @patch("events.tournament_tasks.get_match_participants")
    @patch("events.tournament_tasks.get_tournament_for_task")
    def test_activity_button_is_in_hero_draft_dm(
        self, mock_tournament, mock_participants, mock_dm, mock_log, mock_update
    ):
        mock_tournament.return_value = TournamentTaskSchema(
            id=1,
            name="Test",
            state="in_progress",
            discord_send_herodraft_link=True,
        )
        mock_participants.return_value = [
            TournamentParticipantSchema(user_pk=1, discord_id="111", username="p1")
        ]
        mock_dm.return_value = SENT
        mock_log.return_value = MagicMock(ok=True, json=lambda: {"id": 1})
        send_tournament_herodraft_links(1, 99, 10, radiant_name="A", dire_name="B")
        buttons = mock_dm.call_args.args[0].components[0]["components"]
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

        sweep_auto_herodrafts()
        self.assertEqual(mock_create.call_count, 2)
        mock_links.assert_called_once()

    def test_sweep_is_on_the_beat_schedule(self) -> None:
        tasks = {e["task"] for e in celery_app.conf.beat_schedule.values()}
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
        self.tournament = Tournament.objects.create(
            name="Nullable", state="future", date_played=timezone.now()
        )

    def test_success_can_be_null_at_create(self):
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
    @patch("events.tournament_tasks.send_dm")
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
        mock_dm.return_value = SENT
        mock_create.return_value = MagicMock(ok=True, json=lambda: {"id": 42})

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
    @patch("events.tournament_tasks.send_dm")
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
        mock_dm.return_value = SENT
        mock_create.return_value = MagicMock(ok=True, json=lambda: {"id": 42})

        send_tournament_draft_links(1, 99)

        mock_update.assert_called_once()
        update_kwargs = mock_update.call_args.kwargs
        self.assertTrue(update_kwargs.get("success"))
        self.assertEqual(update_kwargs.get("recipient_count"), 2)


class SendHerodraftLinksRaceTest(TestCase):
    """Same contract as SendDraftLinksRaceTest, for herodraft variant."""

    @patch("events.tournament_tasks.update_tournament_log")
    @patch("events.tournament_tasks.create_tournament_log")
    @patch("events.tournament_tasks.send_dm")
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
        mock_dm.return_value = SENT
        mock_create.return_value = MagicMock(ok=True, json=lambda: {"id": 42})

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


def _not_granted() -> ClaimResult:
    return ClaimResult(
        id=1, granted=False, status=DMStatus.SENT, attempts=1, created=False
    )


@override_settings(TEST=False)
@patch("events.tournament_tasks.update_tournament_log")
@patch(
    "events.tournament_tasks.create_tournament_log",
    return_value=MagicMock(ok=True, json=lambda: {"id": None}),
)
@patch("events.tournament_tasks.get_tournament_for_task")
class TournamentLinkLedgerKeyTest(TestCase):
    def setUp(self) -> None:
        self.enterContext(
            patch(
                "events.tournament_tasks.create_activity_notification_invite",
                return_value=None,
            )
        )

    def _tournament(self) -> TournamentTaskSchema:
        return TournamentTaskSchema(
            id=1,
            name="Keys",
            state="in_progress",
            discord_send_draft_link=True,
            discord_send_herodraft_link=True,
            draft_type="snake",
        )

    def _claim_body(self, mock_claim: MagicMock) -> DMClaimBody:
        mock_claim.assert_called_once()
        return mock_claim.call_args.args[0]

    @patch("discordbot.dm.claim_dm")
    @patch("events.tournament_tasks.get_tournament_participants")
    def test_draft_link_key_uses_task_id(
        self,
        mock_parts: MagicMock,
        mock_claim: MagicMock,
        mock_tourn: MagicMock,
        _create: MagicMock,
        _update: MagicMock,
    ) -> None:
        mock_claim.return_value = _not_granted()
        mock_tourn.return_value = self._tournament()
        mock_parts.return_value = [
            TournamentParticipantSchema(user_pk=1, discord_id="111", username="p1")
        ]

        send_tournament_draft_links.apply(args=(1, 42), task_id="run-a", throw=True)

        body = self._claim_body(mock_claim)
        self.assertEqual(
            body.idempotency_key,
            tournament_draft_link_key(task_id="run-a", discord_id="111"),
        )
        self.assertEqual(body.kind, DMKind.TOURNAMENT_DRAFT_LINK.value)
        self.assertEqual(body.subject_type, DMSubject.TOURNAMENT.value)
        self.assertEqual(body.subject_id, 1)
        self.assertEqual(body.recipient_user_id, 1)
        self.assertTrue(body.has_components)
        self.assertEqual(body.context["draft_id"], 42)

    @patch("discordbot.dm.claim_dm")
    @patch("events.tournament_tasks.get_match_participants")
    def test_herodraft_link_key_uses_task_id(
        self,
        mock_parts: MagicMock,
        mock_claim: MagicMock,
        mock_tourn: MagicMock,
        _create: MagicMock,
        _update: MagicMock,
    ) -> None:
        mock_claim.return_value = _not_granted()
        mock_tourn.return_value = self._tournament()
        mock_parts.return_value = [
            TournamentParticipantSchema(user_pk=1, discord_id="111", username="p1")
        ]

        send_tournament_herodraft_links.apply(
            args=(1, 99, 10),
            kwargs={"radiant_name": "A", "dire_name": "B"},
            task_id="run-b",
            throw=True,
        )

        body = self._claim_body(mock_claim)
        self.assertEqual(
            body.idempotency_key,
            tournament_herodraft_link_key(task_id="run-b", discord_id="111"),
        )
        self.assertEqual(body.kind, DMKind.TOURNAMENT_HERODRAFT_LINK.value)
        self.assertEqual(body.context["draft_id"], 99)
        self.assertEqual(body.context["game_id"], 10)
        self.assertTrue(body.has_components)


@override_settings(TEST=False)
class TournamentLinkLedgerRowTest(TestCase):
    def setUp(self) -> None:
        self.enterContext(
            patch(
                "events.tournament_tasks.create_activity_notification_invite",
                return_value=None,
            )
        )
        self.user = CustomUser.objects.create_user(username="ledger_p1", password="x")
        self.user.discordId = "111"
        self.user.save()
        tournament = Tournament.objects.create(
            name="Ledger", state="in_progress", date_played=timezone.now()
        )
        self.tlog = DiscordTournamentLog.objects.create(
            tournament=tournament, notification_type="draft_link", message="..."
        )

    @patch("discordbot.dm._rate_limited_request")
    @patch("events.tournament_tasks.update_tournament_log")
    @patch("events.tournament_tasks.create_tournament_log")
    @patch("events.tournament_tasks.get_tournament_participants")
    @patch("events.tournament_tasks.get_tournament_for_task")
    def test_no_tournament_dm_message_log_written(
        self,
        mock_tourn: MagicMock,
        mock_parts: MagicMock,
        mock_create: MagicMock,
        _update: MagicMock,
        mock_req: MagicMock,
    ) -> None:
        mock_tourn.return_value = TournamentTaskSchema(
            id=self.tlog.tournament_id,
            name="Ledger",
            state="in_progress",
            discord_send_draft_link=True,
            draft_type="snake",
        )
        mock_parts.return_value = [
            TournamentParticipantSchema(
                user_pk=self.user.pk, discord_id="111", username="p1"
            )
        ]
        mock_create.return_value = MagicMock(ok=True, json=lambda: {"id": self.tlog.pk})
        channel = MagicMock(status_code=200)
        channel.json.return_value = {"id": "900100"}
        message = MagicMock(status_code=200)
        message.json.return_value = {"id": "900200"}
        mock_req.side_effect = [channel, message]

        with ledger_bridge():
            send_tournament_draft_links.apply(
                args=(self.tlog.tournament_id, 42), task_id="run-c", throw=True
            )

        self.assertFalse(
            DiscordMessageLog.objects.filter(source="tournament_dm").exists()
        )
        row = DiscordDM.objects.get()
        self.assertEqual(row.status, DMStatus.SENT)
        self.assertEqual(row.tournament_log_id, self.tlog.pk)
        self.assertEqual(row.recipient_id, self.user.pk)
        self.assertEqual(row.discord_message_id, "900200")


@override_settings(TEST=False)
class TournamentLinkAuthErrorTest(TestCase):
    def setUp(self) -> None:
        self.enterContext(
            patch(
                "events.tournament_tasks.create_activity_notification_invite",
                return_value=None,
            )
        )
        self.enterContext(
            patch(
                "discordbot.dm._rate_limited_request",
                side_effect=DiscordAuthError("401: Unauthorized"),
            )
        )
        self.mock_update = self.enterContext(
            patch("events.tournament_tasks.update_tournament_log")
        )
        self.org = Organization.objects.create(name="Auth Org")
        league = League.objects.create(
            name="Auth League", organization=self.org, steam_league_id=77401
        )
        self.tournament = Tournament.objects.create(
            name="Auth", state="in_progress", date_played=timezone.now(), league=league
        )
        self.tlog = DiscordTournamentLog.objects.create(
            tournament=self.tournament, notification_type="draft_link", message="..."
        )
        self.task = TournamentTaskSchema(
            id=self.tournament.pk,
            name="Auth",
            state="in_progress",
            discord_send_draft_link=True,
            discord_send_herodraft_link=True,
            organization_id=self.org.pk,
        )
        users = [
            CustomUser.objects.create_user(username=f"auth_p{i}", password="x")
            for i in (1, 2)
        ]
        self.participants = [
            TournamentParticipantSchema(
                user_pk=u.pk, discord_id=f"{i}11", username=u.username
            )
            for i, u in enumerate(users, start=1)
        ]

    def _assert_failed_log(self) -> None:
        self.mock_update.assert_called_once()
        kwargs = self.mock_update.call_args.kwargs
        self.assertEqual(self.mock_update.call_args.args, (self.tlog.pk,))
        self.assertIs(kwargs["success"], False)
        self.assertEqual(kwargs["recipient_count"], 0)
        self.assertIn("Discord rejected the bot token", kwargs["message"])
        row = DiscordDM.objects.get()
        self.assertEqual(row.status, DMStatus.FAILED)
        self.assertEqual(row.organization_id, self.org.pk)

    def test_draft_links_fail_log_and_stop(self) -> None:
        with (
            patch(
                "events.tournament_tasks.get_tournament_for_task",
                return_value=self.task,
            ),
            patch(
                "events.tournament_tasks.get_tournament_participants",
                return_value=self.participants,
            ),
            patch(
                "events.tournament_tasks.create_tournament_log",
                return_value=MagicMock(ok=True, json=lambda: {"id": self.tlog.pk}),
            ),
            ledger_bridge(),
        ):
            result = send_tournament_draft_links(self.tournament.pk, 42)
        self.assertIn("rejected the bot token", result)
        self._assert_failed_log()

    def test_herodraft_links_fail_log_and_stop(self) -> None:
        with (
            patch(
                "events.tournament_tasks.get_tournament_for_task",
                return_value=self.task,
            ),
            patch(
                "events.tournament_tasks.get_match_participants",
                return_value=self.participants,
            ),
            patch(
                "events.tournament_tasks.create_tournament_log",
                return_value=MagicMock(ok=True, json=lambda: {"id": self.tlog.pk}),
            ),
            ledger_bridge(),
        ):
            result = send_tournament_herodraft_links(self.tournament.pk, 7, 3, "A", "B")
        self.assertIn("rejected the bot token", result)
        self._assert_failed_log()


class TournamentTaskOrganizationTest(TestCase):
    def test_internal_view_returns_league_org(self) -> None:
        org = Organization.objects.create(name="Task Org")
        league = League.objects.create(
            name="Task League", organization=org, steam_league_id=77402
        )
        with_league = Tournament.objects.create(
            name="T1", state="future", date_played=timezone.now(), league=league
        )
        without = Tournament.objects.create(
            name="T2", state="future", date_played=timezone.now()
        )
        client = APIClient()
        client.credentials(HTTP_X_INTERNAL_TOKEN="org-token")
        with override_settings(INTERNAL_SERVICE_TOKEN="org-token"):
            got = [
                client.get(f"/api/internal/tournaments/{t.pk}/full/").json()
                for t in (with_league, without)
            ]
        self.assertEqual([g.get("organization_id") for g in got], [org.pk, None])
