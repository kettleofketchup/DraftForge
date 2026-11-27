from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase, override_settings

from discordbot.dm_ledger import ClaimResult
from discordbot.models import DMStatus
from discordbot.utils import DiscordRateLimitTimeout
from events.tournament_tasks import (
    send_tournament_draft_links,
    send_tournament_herodraft_links,
)
from tournament.schemas import TournamentParticipantSchema, TournamentTaskSchema

RATE_LIMIT_TIMEOUT = DiscordRateLimitTimeout(
    "Discord rate limit: no token within 10.0s"
)


def _ok_response(data: dict[str, str]) -> MagicMock:
    response = MagicMock(status_code=200)
    response.json.return_value = data
    response.raise_for_status.return_value = None
    return response


GRANTED = ClaimResult(
    id=1, granted=True, status=DMStatus.PENDING, attempts=1, created=True
)


def _discord_request(method: str, url: str, **kwargs: object) -> MagicMock:
    if url.endswith("/users/@me/channels"):
        return _ok_response({"id": "900100"})
    return _ok_response({"id": "900200"})


PARTICIPANTS = [
    TournamentParticipantSchema(user_pk=1, discord_id="111", username="p1"),
    TournamentParticipantSchema(user_pk=2, discord_id="222", username="p2"),
]


@override_settings(TEST=False)
@patch("discordbot.dm.finalize_dm", return_value=True)
@patch("discordbot.dm.mark_dm_sending", return_value=True)
@patch("discordbot.dm.claim_dm", return_value=GRANTED)
@patch("discordbot.utils.requests.request", side_effect=_discord_request)
@patch("events.tournament_tasks.create_activity_notification_invite", return_value=None)
@patch("events.tournament_tasks.update_tournament_log")
@patch(
    "events.tournament_tasks.create_tournament_log",
    return_value=MagicMock(ok=True, json=lambda: {"id": 1}),
)
class TournamentDmLoopRateLimitTimeoutTest(SimpleTestCase):
    # Recipient 1: channel token ok, send token times out. Recipient 2: both ok.
    TOKENS = [True, RATE_LIMIT_TIMEOUT, True, True]

    def _assert_finalized(self, update_log: MagicMock, request: MagicMock) -> None:
        sent_messages = [
            c for c in request.call_args_list if c.args[1].endswith("/messages")
        ]
        self.assertEqual(len(sent_messages), 1)
        update_log.assert_called_once()
        self.assertEqual(update_log.call_args.args[0], 1)
        self.assertEqual(update_log.call_args.kwargs["recipient_count"], 1)
        self.assertTrue(update_log.call_args.kwargs["success"])
        self.assertIn("Failed: p1", update_log.call_args.kwargs["message"])

    @patch(
        "events.tournament_tasks.get_tournament_participants", return_value=PARTICIPANTS
    )
    @patch(
        "events.tournament_tasks.get_tournament_for_task",
        return_value=TournamentTaskSchema(
            id=1,
            name="Test",
            state="in_progress",
            discord_send_draft_link=True,
            draft_type="snake",
        ),
    )
    def test_draft_links_continue_after_rate_limit_timeout(
        self,
        _tournament: MagicMock,
        _participants: MagicMock,
        _create_log: MagicMock,
        update_log: MagicMock,
        _invite: MagicMock,
        request: MagicMock,
        _claim: MagicMock,
        _mark: MagicMock,
        finalize: MagicMock,
    ) -> None:
        with patch(
            "discordbot.utils._acquire_rate_limit_token", side_effect=self.TOKENS
        ):
            result = send_tournament_draft_links(1, 42)
        self.assertIn("1/2", result)
        self._assert_finalized(update_log, request)
        self.assertEqual(finalize.call_count, 2)
        self.assertEqual(
            finalize.call_args_list[0].args[1].error_class, "rate_limit_timeout"
        )

    @patch("events.tournament_tasks.get_match_participants", return_value=PARTICIPANTS)
    @patch(
        "events.tournament_tasks.get_tournament_for_task",
        return_value=TournamentTaskSchema(
            id=1,
            name="Test",
            state="in_progress",
            discord_send_herodraft_link=True,
        ),
    )
    def test_herodraft_links_continue_after_rate_limit_timeout(
        self,
        _tournament: MagicMock,
        _participants: MagicMock,
        _create_log: MagicMock,
        update_log: MagicMock,
        _invite: MagicMock,
        request: MagicMock,
        _claim: MagicMock,
        _mark: MagicMock,
        finalize: MagicMock,
    ) -> None:
        with patch(
            "discordbot.utils._acquire_rate_limit_token", side_effect=self.TOKENS
        ):
            result = send_tournament_herodraft_links(
                1, 99, 10, radiant_name="Alpha", dire_name="Bravo"
            )
        self.assertIn("1/2", result)
        self._assert_finalized(update_log, request)
        self.assertEqual(finalize.call_count, 2)
        self.assertEqual(
            finalize.call_args_list[0].args[1].error_class, "rate_limit_timeout"
        )
