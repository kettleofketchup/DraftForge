import json
import time
from unittest import mock

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from lobby import services, states
from lobby.models import GameLobbyEvent
from lobby.tests.helpers import (
    LOBBY_SETTINGS,
    envelope,
    lobby_settings,
    make_game,
    post_webhook,
)


@lobby_settings
class WebhookTestBase(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.game = make_game()
        self.row = services.claim_lobby(self.game.pk).game_lobby
        self.row.lobby_id = "lob_1"
        self.row.state = states.PENDING
        self.row.save()
        self.ref = self.row.external_ref
        self.radiant_ref = f"team-{self.game.radiant_team_id}"
        self.dire_ref = f"team-{self.game.dire_team_id}"

    def event(self, seq, event_type, data=None, **kwargs):
        kwargs.setdefault("external_ref", self.ref)
        return envelope(seq, event_type, data, **kwargs)

    def post(self, body, **kwargs):
        with self.captureOnCommitCallbacks(execute=True):
            return post_webhook(self.client, body, **kwargs)


class WebhookAuthTests(WebhookTestBase):
    def test_no_token_is_refused(self):
        resp = self.post(self.event(1, "lobby.created"), token=None)
        self.assertEqual(resp.status_code, 403)
        self.assertFalse(GameLobbyEvent.objects.exists())

    def test_wrong_token_is_refused(self):
        resp = self.post(self.event(1, "lobby.created"), token="wrong")
        self.assertEqual(resp.status_code, 403)

    def test_bad_signature(self):
        resp = self.post(self.event(1, "lobby.created"), secret="whsec_other")
        self.assertEqual(resp.status_code, 401)
        self.assertEqual(resp.json()["code"], "bad_signature")
        self.assertFalse(GameLobbyEvent.objects.exists())

    def test_stale_timestamp(self):
        resp = self.post(
            self.event(1, "lobby.created"), timestamp=int(time.time()) - 301
        )
        self.assertEqual(resp.status_code, 401)

    def test_signature_is_over_raw_bytes(self):
        body = json.dumps(self.event(1, "lobby.created"), indent=3).encode()
        resp = self.post(body)
        self.assertEqual(resp.status_code, 200, resp.content)

    @override_settings(
        **{**LOBBY_SETTINGS, "DOTA_LOBBY_WEBHOOK_SECRETS": ("new", "whsec_test")}
    )
    def test_rotated_secrets(self):
        self.assertEqual(self.post(self.event(1, "lobby.created")).status_code, 200)

    @override_settings(**{**LOBBY_SETTINGS, "DOTA_LOBBY_WEBHOOK_SECRETS": ()})
    def test_no_secret_configured_is_503(self):
        resp = self.post(self.event(1, "lobby.created"))
        self.assertEqual(resp.status_code, 503)
        self.assertEqual(resp.json()["code"], "no_secret")
        self.assertEqual(resp["Retry-After"], "300")

    @override_settings(**{**LOBBY_SETTINGS, "DOTA_LOBBY_ENABLED": False})
    def test_disabled_is_503(self):
        resp = self.post(self.event(1, "lobby.created"))
        self.assertEqual(resp.status_code, 503)
        self.assertEqual(resp.json()["code"], "lobby_disabled")

    def test_malformed_body(self):
        self.assertEqual(self.post(b"not json").status_code, 400)
        self.assertEqual(self.post({"id": "evt_1"}).status_code, 400)


class WebhookOrderingTests(WebhookTestBase):
    def test_applies_and_dedupes(self):
        resp = self.post(self.event(1, "lobby.created", {"league_verified": True}))
        self.assertEqual(resp.json(), {"status": "applied", "last_seq": 1})
        again = self.post(self.event(1, "lobby.created", {"league_verified": True}))
        self.assertEqual(again.status_code, 200)
        self.assertEqual(again.json()["status"], "duplicate")
        self.assertEqual(GameLobbyEvent.objects.count(), 1)
        self.row.refresh_from_db()
        self.assertEqual(self.row.last_seq, 1)
        self.assertTrue(self.row.league_verified)
        self.assertEqual(self.row.state, "waiting")
        self.assertEqual(self.row.bot, "bot1")

    def test_old_seq_under_new_id_is_ignored(self):
        self.post(self.event(1, "lobby.created"))
        resp = self.post(self.event(1, "lobby.created", event_id="evt_other"))
        self.assertEqual(resp.json()["status"], "duplicate")

    @mock.patch("lobby.tasks.backfill_lobby_events.delay")
    def test_gap_is_stored_and_backfilled(self, backfill):
        self.post(self.event(1, "lobby.created"))
        resp = self.post(self.event(3, "lobby.ready", state="ready"))
        self.assertEqual(resp.json(), {"status": "queued", "last_seq": 1})
        backfill.assert_called_once_with(self.row.pk)
        stored = GameLobbyEvent.objects.get(seq=3)
        self.assertIsNone(stored.applied_at)

        resp = self.post(self.event(2, "lobby.player_joined", {"account_id": 7}))
        self.assertEqual(resp.json(), {"status": "applied", "last_seq": 3})
        self.row.refresh_from_db()
        self.assertEqual(self.row.state, "ready")
        self.assertEqual(self.row.players["7"]["status"], "joined")
        self.assertFalse(
            GameLobbyEvent.objects.filter(applied_at__isnull=True).exists()
        )

    def test_unknown_lobby_is_acknowledged(self):
        resp = self.post(
            envelope(1, "lobby.created", lobby_id="lob_x", external_ref="other:5")
        )
        self.assertEqual(resp.json(), {"status": "ignored"})
        resp = self.post(
            envelope(1, "lobby.created", lobby_id="lob_x", external_ref="game:999999")
        )
        self.assertEqual(resp.json(), {"status": "ignored"})
        self.assertFalse(GameLobbyEvent.objects.exists())

    def test_binds_unaccepted_row_by_metadata(self):
        self.row.lobby_id = None
        self.row.state = states.REQUESTED
        self.row.save()
        resp = self.post(
            self.event(
                1,
                "lobby.state_changed",
                {"from": "pending", "to": "creating"},
                lobby_id="lob_new",
                state="creating",
                game_lobby_id=self.row.pk,
            )
        )
        self.assertEqual(resp.json()["status"], "applied")
        self.row.refresh_from_db()
        self.assertEqual((self.row.lobby_id, self.row.state), ("lob_new", "creating"))

    def test_metadata_for_another_game_is_ignored(self):
        self.row.lobby_id = None
        self.row.save()
        other = make_game()
        resp = self.post(
            envelope(
                1,
                "lobby.created",
                lobby_id="lob_new",
                external_ref=f"game:{other.pk}",
                game_lobby_id=self.row.pk,
            )
        )
        self.assertEqual(resp.json(), {"status": "ignored"})


class WebhookGameUpdateTests(WebhookTestBase):
    def started(self, seq=1, match_id="8123456789"):
        return self.event(
            seq,
            "match.started",
            {
                "match_id": match_id,
                "host_seat_strategy": "self_kick",
                "radiant_team_ref": self.radiant_ref,
                "dire_team_ref": self.dire_ref,
            },
            state="in_game",
        )

    @mock.patch("lobby.broadcast.send")
    def test_match_started_sets_gameid_and_live(self, send):
        self.post(self.started())
        self.game.refresh_from_db()
        self.row.refresh_from_db()
        self.assertEqual(self.game.gameid, 8123456789)
        self.assertEqual(self.game.status, "live")
        self.assertEqual(self.row.match_id, 8123456789)
        self.assertEqual(self.row.state, "in_game")
        self.assertIsNotNone(self.row.match_started_at)
        tournament_id, messages = send.call_args.args
        self.assertEqual(tournament_id, self.game.tournament_id)
        self.assertEqual(
            [m["type"] for m in messages], ["lobby.event", "bracket.update"]
        )
        self.assertEqual(messages[0]["match_id"], "8123456789")
        self.assertNotIn("password", json.dumps(messages))

    def test_existing_gameid_is_kept(self):
        self.game.gameid = 555
        self.game.save()
        with self.assertLogs("lobby.events", level="WARNING") as logs:
            self.post(self.started())
        self.assertIn("lobby_gameid_conflict", "".join(logs.output))
        self.game.refresh_from_db()
        self.row.refresh_from_db()
        self.assertEqual(self.game.gameid, 555)
        self.assertEqual(self.game.status, "live")
        self.assertEqual(self.row.match_id, 8123456789)

    def test_completed_game_keeps_status(self):
        self.game.status = "completed"
        self.game.save()
        self.post(self.started())
        self.game.refresh_from_db()
        self.assertEqual(self.game.status, "completed")

    def test_match_ended_is_provisional(self):
        self.post(self.started())
        self.post(
            self.event(
                2,
                "match.ended",
                {
                    "match_id": "8123456789",
                    "outcome": 2,
                    "outcome_name": "radiant_victory",
                    "winner_side": "radiant",
                    "winner_team_ref": self.radiant_ref,
                    "scored": True,
                    "duration_seconds": 2400,
                    "provisional": True,
                    "source": "lobby",
                },
                state="post_game",
            )
        )
        self.game.refresh_from_db()
        self.row.refresh_from_db()
        self.assertIsNone(self.game.winning_team_id)
        self.assertEqual(self.game.status, "live")
        self.assertEqual(self.row.provisional_winner_side, "radiant")
        self.assertEqual(self.row.provisional_winner_team_id, self.game.radiant_team_id)
        self.assertEqual(self.row.provisional_outcome, 2)
        self.assertTrue(self.row.provisional_scored)
        self.assertEqual(self.row.duration_seconds, 2400)

    def test_foreign_team_ref_is_not_trusted(self):
        self.post(self.started())
        self.post(
            self.event(
                2,
                "match.ended",
                {"winner_side": "dire", "winner_team_ref": "team-999999"},
                state="post_game",
            )
        )
        self.row.refresh_from_db()
        self.assertIsNone(self.row.provisional_winner_team_id)

    def test_teams_flipped_updates_sides(self):
        self.post(
            self.event(
                1,
                "lobby.teams_flipped",
                {"radiant_team_ref": self.dire_ref, "dire_team_ref": self.radiant_ref},
            )
        )
        self.row.refresh_from_db()
        self.assertEqual(self.row.radiant_team_id, self.game.dire_team_id)
        self.assertEqual(self.row.dire_team_id, self.game.radiant_team_id)

    def test_terminal_event_ends_row(self):
        self.post(
            self.event(
                1, "lobby.timed_out", {"reason": "pending_timeout"}, state="timed_out"
            )
        )
        self.row.refresh_from_db()
        self.assertTrue(self.row.ended)
        self.assertEqual(
            (self.row.state, self.row.state_reason), ("timed_out", "pending_timeout")
        )

    def test_locally_ended_row_is_not_revived(self):
        services.end_locally(self.row, services.TEAMS_CHANGED)
        self.post(
            self.event(
                1,
                "lobby.state_changed",
                {"from": "pending", "to": "closing"},
                state="closing",
            )
        )
        self.row.refresh_from_db()
        self.assertEqual((self.row.state, self.row.ended), ("closed", True))
        self.assertEqual(self.row.state_reason, services.TEAMS_CHANGED)

    def test_create_failed_records_code(self):
        self.post(
            self.event(
                1,
                "lobby.create_failed",
                {"code": "league_rejected", "message": "no"},
                state="creating",
            )
        )
        self.row.refresh_from_db()
        self.assertEqual(self.row.last_error_code, "league_rejected")

    @override_settings(**LOBBY_SETTINGS)
    @mock.patch("lobby.tasks.send_lobby_info.delay")
    def test_lobby_created_sends_info_when_enabled(self, send_info):
        self.post(self.event(1, "lobby.created"))
        send_info.assert_not_called()
        tournament = self.game.tournament
        tournament.discord_send_lobby_info = True
        tournament.save()
        self.post(self.event(2, "lobby.created", event_id="evt_again"))
        send_info.assert_called_once_with(self.row.pk)
