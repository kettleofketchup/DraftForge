"""lobby.client against canned dota_lobby responses (requests.Session.request mocked)."""

import json
from unittest.mock import MagicMock, patch

import requests
from django.test import SimpleTestCase
from structlog.testing import capture_logs

from lobby.client import (
    CONNECT_TIMEOUT_SECONDS,
    DotaLobbyClient,
    DotaLobbyError,
    DotaLobbyNotConfigured,
    DotaLobbyUnavailable,
)

BASE = "http://dota-lobby.test:8080"
API_KEY = "test-api-key-not-real"
PASSWORD = "abcdefghijkl"


def _lobby(**overrides):
    lobby = {
        "id": "lob_01JC9Z7Q8W5X2M3N4P5R6S7T8V",
        "external_ref": "game:42",
        "state": "pending",
        "state_reason": None,
        "seq": 1,
        "bot": None,
        "gc_lobby_id": None,
        "league_id": 17929,
        "league_node_id": None,
        "league_verified": None,
        "name": "Spring Cup R1: Ravens vs Owls",
        "game_mode": "cm",
        "region": None,
        "tv_delay_seconds": None,
        "visibility": "public",
        "allow_cheats": False,
        "launch": "manual",
        "ready_check": False,
        "allow_short_handed": False,
        "kick_strangers": True,
        "admins": None,
        "host_seat": {"strategy": None, "confirmed": False, "team": None},
        "teams": {
            "radiant": {
                "team_ref": "team:1",
                "name": "Ravens",
                "players": [
                    {
                        "account_id": 11111111,
                        "steam_id": "76561197971376839",
                        "captain": True,
                        "status": "pending",
                        "seat": None,
                        "ready": False,
                        "invites_sent": 0,
                        "last_invite_at": None,
                        "invite_confirmed": False,
                    }
                ],
            },
            "dire": {"team_ref": "team:2", "name": "Owls", "players": None},
        },
        "strangers": None,
        "pending_invites": None,
        "match": {
            "match_id": None,
            "outcome": None,
            "outcome_name": None,
            "winner_side": None,
            "winner_team_ref": None,
            "scored": None,
            "duration_seconds": None,
            "started_at": None,
            "ended_at": None,
        },
        "launch_attempts": 0,
        "metadata": {"draftforge_game": "42"},
        "created_at": "2026-11-09T12:00:00Z",
        "updated_at": "2026-11-09T12:00:00Z",
        "expires_at": None,
        "ended_at": None,
        "a_field_from_a_newer_server": {"ignored": True},
    }
    lobby.update(overrides)
    return lobby


def _event(seq, type_="lobby.state_changed"):
    return {
        "id": f"evt_{seq:026d}",
        "type": type_,
        "seq": seq,
        "occurred_at": "2026-11-09T12:00:00Z",
        "lobby": {
            "id": "lob_1",
            "external_ref": "game:42",
            "state": "waiting",
            "bot": "bot1",
            "gc_lobby_id": "27110133250527232",
            "league_id": None,
            "metadata": {},
        },
        "data": {"from": "creating", "to": "waiting"},
    }


def _resp(status, body=None, *, content_type="application/json", headers=None):
    resp = MagicMock(spec=requests.Response)
    resp.status_code = status
    resp.reason = {502: "Bad Gateway"}.get(status, "")
    resp.headers = {"Content-Type": content_type, **(headers or {})}
    if isinstance(body, (dict, list)):
        resp.json.return_value = body
        resp.text = json.dumps(body)
    else:
        resp.json.side_effect = ValueError("not json")
        resp.text = body or ""
    return resp


def _problem(status, code, *, retryable=False, detail="", errors=None, headers=None):
    body = {
        "status": status,
        "title": "Problem",
        "detail": detail,
        "code": code,
        "retryable": retryable,
    }
    if errors is not None:
        body["errors"] = errors
    return _resp(status, body, content_type="application/problem+json", headers=headers)


class ClientTestBase(SimpleTestCase):
    def setUp(self):
        patcher = patch.object(requests.Session, "request")
        self.request = patcher.start()
        self.addCleanup(patcher.stop)
        self.sleeps = []
        self.client = DotaLobbyClient(
            BASE, API_KEY, 5, sleep=self.sleeps.append, backoff=(1, 3)
        )

    def call(self, n=-1):
        args, kwargs = self.request.call_args_list[n]
        return args[0], args[1], kwargs


class ClientConfigTests(SimpleTestCase):
    def test_not_configured_without_url(self):
        with patch.dict("os.environ", {"DOTA_LOBBY_URL": ""}):
            with self.assertRaises(DotaLobbyNotConfigured) as ctx:
                DotaLobbyClient()
        self.assertEqual(ctx.exception.code, "not_configured")
        self.assertFalse(ctx.exception.retryable)

    def test_reads_environment(self):
        env = {
            "DOTA_LOBBY_URL": "http://svc:8080/v1/",
            "DOTA_LOBBY_API_KEY": API_KEY,
            "DOTA_LOBBY_TIMEOUT_SECONDS": "7.5",
        }
        with patch.dict("os.environ", env):
            client = DotaLobbyClient()
        self.assertEqual(client.base_url, "http://svc:8080")
        self.assertEqual(client.timeout, 7.5)
        self.assertEqual(client.session.headers["X-API-Key"], API_KEY)
        self.assertEqual(client.session.headers["Accept"], "application/json")
        self.assertTrue(client.session.headers["User-Agent"].startswith("draftforge"))

    def test_no_api_key_header_when_unset(self):
        client = DotaLobbyClient(BASE, "")
        self.assertNotIn("X-API-Key", client.session.headers)


class CreateLobbyTests(ClientTestBase):
    BODY = {"external_ref": "game:42", "name": "x", "teams": {}, "password": PASSWORD}

    def test_accepted(self):
        self.request.return_value = _resp(202, _lobby(password=PASSWORD))
        result = self.client.create_lobby(self.BODY)

        method, url, kwargs = self.call()
        self.assertEqual((method, url), ("POST", f"{BASE}/v1/lobbies"))
        self.assertEqual(kwargs["json"], self.BODY)
        # (connect, read): connecting is capped, reading uses the setting.
        self.assertEqual(kwargs["timeout"], (CONNECT_TIMEOUT_SECONDS, 5))
        self.assertFalse(result.replayed)
        self.assertEqual(result.lobby.id, "lob_01JC9Z7Q8W5X2M3N4P5R6S7T8V")
        self.assertEqual(result.lobby.password.get_secret_value(), PASSWORD)
        self.assertNotIn(PASSWORD, repr(result))

    def test_short_timeout_also_caps_connect(self):
        client = DotaLobbyClient(BASE, API_KEY, timeout=1)
        self.request.return_value = _resp(202, _lobby(password=PASSWORD))
        client.create_lobby(self.BODY)
        self.assertEqual(self.call()[2]["timeout"], (1, 1))

    def test_replayed(self):
        self.request.return_value = _resp(200, _lobby(password=PASSWORD))
        self.assertTrue(self.client.create_lobby(self.BODY).replayed)

    def test_null_lists_become_empty(self):
        self.request.return_value = _resp(202, _lobby())
        lobby = self.client.create_lobby(self.BODY).lobby
        self.assertEqual(lobby.teams.dire.players, [])
        self.assertEqual(lobby.admins, [])
        self.assertEqual(lobby.strangers, [])
        self.assertEqual(lobby.pending_invites, [])
        self.assertEqual(lobby.teams.radiant.players[0].account_id, 11111111)
        self.assertIsNone(lobby.password)

    def test_conflict_is_permanent(self):
        self.request.return_value = _problem(
            409, "conflict", detail="external_ref game:42 is in use"
        )
        with self.assertRaises(DotaLobbyError) as ctx:
            self.client.create_lobby(self.BODY)
        err = ctx.exception
        self.assertEqual(
            (err.status, err.code, err.retryable), (409, "conflict", False)
        )
        self.assertEqual(err.detail, "external_ref game:42 is in use")
        self.assertEqual(self.request.call_count, 1)
        self.assertEqual(self.sleeps, [])

    def test_validation_errors(self):
        errors = [
            {
                "message": "expected account_id or steam_id",
                "location": "body.teams.radiant.players[0]",
                "value": {},
            }
        ]
        self.request.return_value = _problem(422, "invalid_request", errors=errors)
        with self.assertRaises(DotaLobbyError) as ctx:
            self.client.create_lobby(self.BODY)
        err = ctx.exception
        self.assertEqual((err.status, err.code), (422, "invalid_request"))
        self.assertEqual(len(err.errors), 1)
        self.assertEqual(err.errors[0].location, "body.teams.radiant.players[0]")
        self.assertEqual(err.errors[0].message, "expected account_id or steam_id")

    def test_league_not_held(self):
        self.request.return_value = _problem(422, "league_not_held")
        with self.assertRaises(DotaLobbyError) as ctx:
            self.client.create_lobby(self.BODY)
        self.assertEqual(ctx.exception.code, "league_not_held")
        self.assertFalse(ctx.exception.retryable)
        self.assertEqual(self.request.call_count, 1)

    def test_unavailable_retried_then_succeeds(self):
        self.request.side_effect = [
            _problem(503, "unavailable", retryable=True),
            _resp(202, _lobby()),
        ]
        result = self.client.create_lobby(self.BODY)
        self.assertEqual(result.lobby.state, "pending")
        self.assertEqual(self.request.call_count, 2)
        self.assertEqual(self.sleeps, [1])
        # The retry sends the identical body, so dota_lobby can answer 200.
        self.assertEqual(self.call(0)[2]["json"], self.call(1)[2]["json"])

    def test_gc_timeout_retries_exhausted(self):
        self.request.return_value = _problem(504, "gc_timeout", retryable=True)
        with self.assertRaises(DotaLobbyError) as ctx:
            self.client.create_lobby(self.BODY)
        self.assertEqual(ctx.exception.code, "gc_timeout")
        self.assertTrue(ctx.exception.retryable)
        self.assertEqual(self.request.call_count, 3)
        self.assertEqual(self.sleeps, [1, 3])

    def test_retryable_flag_comes_from_server_not_status(self):
        # A 503 problem that says it is not retryable is not retried.
        self.request.return_value = _problem(503, "unavailable", retryable=False)
        with self.assertRaises(DotaLobbyError):
            self.client.create_lobby(self.BODY)
        self.assertEqual(self.request.call_count, 1)

    def test_non_json_bad_gateway(self):
        self.request.return_value = _resp(
            502, "<html>Bad Gateway</html>", content_type="text/html"
        )
        with self.assertRaises(DotaLobbyError) as ctx:
            self.client.create_lobby(self.BODY)
        err = ctx.exception
        self.assertEqual((err.status, err.code, err.retryable), (502, "http_502", True))
        self.assertEqual(self.request.call_count, 3)

    def test_non_problem_client_error(self):
        self.request.return_value = _resp(404, "nope", content_type="text/plain")
        with self.assertRaises(DotaLobbyError) as ctx:
            self.client.get_lobby("lob_1")
        self.assertEqual(
            (ctx.exception.code, ctx.exception.retryable), ("http_404", False)
        )

    def test_malformed_problem_errors_are_dropped(self):
        self.request.return_value = _problem(
            422,
            "invalid_request",
            errors=[
                {"message": {"x": 1}, "location": "body.name"},
                "not an object",
                {"message": "name is required", "location": "body.name"},
            ],
        )
        with self.assertRaises(DotaLobbyError) as ctx:
            self.client.create_lobby({"external_ref": "game:1"})
        err = ctx.exception
        self.assertEqual((err.status, err.code), (422, "invalid_request"))
        self.assertEqual([e.message for e in err.errors], ["name is required"])

    def test_non_list_problem_errors_ignored(self):
        self.request.return_value = _problem(422, "invalid_request", errors={"a": 1})
        with self.assertRaises(DotaLobbyError) as ctx:
            self.client.create_lobby({"external_ref": "game:1"})
        self.assertEqual(ctx.exception.errors, [])

    def test_redirects_not_followed(self):
        # Following one would re-send X-API-Key to the redirect's host.
        self.request.return_value = _resp(
            301, None, content_type="text/html", headers={"Location": "https://x/"}
        )
        with self.assertRaises(DotaLobbyError) as ctx:
            self.client.create_lobby({"external_ref": "game:1"})
        err = ctx.exception
        self.assertEqual(
            (err.status, err.code, err.retryable), (301, "http_301", False)
        )
        self.assertEqual(self.request.call_count, 1)
        self.assertIs(self.call()[2]["allow_redirects"], False)

    def test_timeout_is_unreachable(self):
        self.request.side_effect = requests.Timeout("read timed out")
        with self.assertRaises(DotaLobbyUnavailable) as ctx:
            self.client.create_lobby(self.BODY)
        self.assertEqual(ctx.exception.code, "unreachable")
        self.assertTrue(ctx.exception.retryable)
        self.assertEqual(self.request.call_count, 3)

    def test_connection_error_then_success(self):
        self.request.side_effect = [
            requests.ConnectionError("refused"),
            _resp(202, _lobby()),
        ]
        self.assertFalse(self.client.create_lobby(self.BODY).replayed)

    def test_other_request_errors_not_retried(self):
        self.request.side_effect = requests.exceptions.InvalidURL("bad")
        with self.assertRaises(DotaLobbyError) as ctx:
            self.client.create_lobby(self.BODY)
        self.assertEqual(ctx.exception.code, "request_failed")
        self.assertEqual(self.request.call_count, 1)

    def test_invalid_success_body(self):
        self.request.return_value = _resp(202, {"id": 5})
        with self.assertRaises(DotaLobbyError) as ctx:
            self.client.create_lobby(self.BODY)
        self.assertEqual(ctx.exception.code, "invalid_response")

    def test_password_and_api_key_never_logged(self):
        self.request.side_effect = [
            _problem(503, "unavailable", retryable=True, detail="bot busy"),
            _problem(409, "conflict", detail="in use"),
        ]
        with capture_logs() as logs, self.assertRaises(DotaLobbyError):
            self.client.create_lobby(self.BODY)
        self.assertEqual(len(logs), 2)
        for entry in logs:
            self.assertEqual(entry["event"], "dota_lobby_request_failed")
            self.assertEqual((entry["system"], entry["subsystem"]), ("lobby", "client"))
        self.assertEqual(logs[0]["log_level"], "info")
        self.assertTrue(logs[0]["will_retry"])
        self.assertEqual(logs[1]["log_level"], "warning")
        self.assertEqual(logs[1]["code"], "conflict")
        dumped = repr(logs)
        self.assertNotIn(PASSWORD, dumped)
        self.assertNotIn(API_KEY, dumped)


class LobbyOperationTests(ClientTestBase):
    def test_get_lobby_quotes_id(self):
        self.request.return_value = _resp(200, _lobby(password=PASSWORD))
        lobby = self.client.get_lobby("lob_1/../x")
        self.assertEqual(self.call()[1], f"{BASE}/v1/lobbies/lob_1%2F..%2Fx")
        self.assertEqual(lobby.password.get_secret_value(), PASSWORD)

    def test_close_lobby(self):
        self.request.return_value = _resp(202, _lobby(state="closing"))
        lobby = self.client.close_lobby("lob_1")
        self.assertEqual(self.call()[:2], ("DELETE", f"{BASE}/v1/lobbies/lob_1"))
        self.assertEqual(lobby.state, "closing")
        self.assertFalse(lobby.ended)

    def test_ended(self):
        self.request.return_value = _resp(200, _lobby(state="timed_out"))
        self.assertTrue(self.client.get_lobby("lob_1").ended)

    def test_launch_is_not_retried(self):
        self.request.return_value = _problem(504, "gc_timeout", retryable=True)
        with self.assertRaises(DotaLobbyError):
            self.client.launch_lobby("lob_1", force=True)
        self.assertEqual(self.request.call_count, 1)
        self.assertEqual(self.call()[2]["json"], {"force": True})

    def test_launch_not_ready(self):
        self.request.return_value = _problem(409, "not_ready")
        with self.assertRaises(DotaLobbyError) as ctx:
            self.client.launch_lobby("lob_1")
        self.assertEqual(ctx.exception.code, "not_ready")
        self.assertEqual(self.call()[2]["json"], {})

    def test_flip_is_not_retried(self):
        self.request.side_effect = requests.Timeout()
        with self.assertRaises(DotaLobbyUnavailable):
            self.client.flip_teams("lob_1")
        self.assertEqual(self.request.call_count, 1)
        self.assertEqual(self.call()[1], f"{BASE}/v1/lobbies/lob_1/teams/flip")

    def test_invite_missing(self):
        self.request.return_value = _resp(
            200,
            {
                "invited": [11111111],
                "skipped": [{"account_id": 2, "reason": "in_lobby"}],
            },
        )
        result = self.client.invite("lob_1", missing=True)
        self.assertEqual(self.call()[2]["json"], {"missing": True})
        self.assertEqual(result.invited, [11111111])
        self.assertEqual(result.skipped[0].reason, "in_lobby")

    def test_invite_is_not_retried(self):
        # The bot may have sent the invites before the gateway timed out; a
        # repeat would hit the resend cooldown and report 429 instead.
        self.request.return_value = _problem(504, "gc_timeout", retryable=True)
        with self.assertRaises(DotaLobbyError) as ctx:
            self.client.invite("lob_1", missing=True)
        self.assertEqual(ctx.exception.code, "gc_timeout")
        self.assertEqual(self.request.call_count, 1)
        self.assertEqual(self.sleeps, [])

    def test_invite_null_lists(self):
        self.request.return_value = _resp(200, {"invited": None, "skipped": None})
        result = self.client.invite("lob_1", players=[3])
        self.assertEqual(self.call()[2]["json"], {"players": [3]})
        self.assertEqual((result.invited, result.skipped), ([], []))

    def test_invite_needs_players_or_missing(self):
        with self.assertRaises(ValueError):
            self.client.invite("lob_1")

    def test_invite_limited_carries_retry_after(self):
        self.request.return_value = _problem(
            429, "invite_limited", headers={"Retry-After": "42"}
        )
        with self.assertRaises(DotaLobbyError) as ctx:
            self.client.invite("lob_1", players=[1])
        err = ctx.exception
        self.assertEqual(
            (err.status, err.code, err.retry_after), (429, "invite_limited", 42)
        )
        self.assertFalse(err.retryable)
        self.assertEqual(self.request.call_count, 1)

    def test_get_league(self):
        self.request.return_value = _resp(
            200,
            {
                "league_id": 17929,
                "name": "DTX",
                "bots": None,
                "holders": None,
                "holders_total": 2,
                "holders_free": 1,
            },
        )
        league = self.client.get_league(17929)
        self.assertEqual(self.call()[1], f"{BASE}/v1/leagues/17929")
        self.assertEqual((league.holders_total, league.holders_free), (2, 1))


class PaginationTests(ClientTestBase):
    def test_list_lobbies_follows_cursor(self):
        self.request.side_effect = [
            _resp(
                200,
                {
                    "lobbies": [_lobby(id="lob_a"), _lobby(id="lob_b")],
                    "next_cursor": "c1",
                },
            ),
            _resp(200, {"lobbies": [_lobby(id="lob_c")], "next_cursor": None}),
        ]
        ids = [
            lobby.id
            for lobby in self.client.list_lobbies(
                external_ref="game:42", active=True, state=["waiting", "ready"]
            )
        ]
        self.assertEqual(ids, ["lob_a", "lob_b", "lob_c"])
        first, second = self.call(0)[2]["params"], self.call(1)[2]["params"]
        self.assertEqual(
            first,
            {
                "limit": 200,
                "external_ref": "game:42",
                "active": "true",
                "state": "waiting,ready",
            },
        )
        self.assertNotIn("cursor", first)
        self.assertEqual(second["cursor"], "c1")

    def test_list_lobbies_null_page(self):
        self.request.return_value = _resp(200, {"lobbies": None, "next_cursor": None})
        self.assertEqual(list(self.client.list_lobbies()), [])

    def test_list_events_follows_next_after(self):
        self.request.side_effect = [
            _resp(
                200,
                {"events": [_event(1), _event(2, "match.started")], "next_after": 2},
            ),
            _resp(200, {"events": [_event(3)], "next_after": 3}),
            _resp(200, {"events": None, "next_after": 3}),
        ]
        events = list(self.client.list_events("lob_1", after=0))
        self.assertEqual([e.seq for e in events], [1, 2, 3])
        self.assertEqual(events[1].type, "match.started")
        self.assertEqual(events[0].lobby.gc_lobby_id, "27110133250527232")
        self.assertEqual(
            [self.call(n)[2]["params"]["after"] for n in range(3)], [0, 2, 3]
        )

    def test_list_events_stops_when_server_does_not_advance(self):
        self.request.return_value = _resp(200, {"events": [_event(5)], "next_after": 5})
        events = list(self.client.list_events("lob_1", after=5))
        self.assertEqual(len(events), 1)
        self.assertEqual(self.request.call_count, 1)


def _bot(**overrides):
    bot = {
        "name": "sim_bot_1",
        "username": "sim_login_1",
        "state": "gc_ready",
        "ready": True,
        "reason": None,
        "last_error": "steam_logon_failed",
        "last_error_message": "boom",
        "since": "2026-11-24T10:00:00Z",
        "steam_id": "76561197960265729",
        "limited": True,
        "lobby_stale": False,
        "token_expires_at": "2026-12-24T10:00:00Z",
        "renew_blocked": None,
        "attempt": 0,
        "gc_queue_position": None,
        "ready_since": "2026-11-24T10:00:00Z",
        "leagues": None,
        "lobby": None,
    }
    bot.update(overrides)
    return bot


class BotAccessClientTests(ClientTestBase):
    def test_list_bots_drops_username_and_nulls(self):
        self.request.return_value = _resp(
            200, {"bots": [_bot(), _bot(name="sim_bot_2", lobby="lob_x", leagues=[7])]}
        )
        bots = self.client.list_bots()
        method, url, _ = self.call()
        self.assertEqual((method, url), ("GET", f"{BASE}/v1/bots"))
        first, second = bots
        self.assertFalse(hasattr(first, "username"))
        self.assertFalse(hasattr(first, "last_error"))
        self.assertFalse(hasattr(first, "token_expires_at"))
        self.assertEqual(first.leagues, [])
        self.assertEqual(first.steam_id, "76561197960265729")
        self.assertIsNone(first.lobby)
        self.assertEqual((second.lobby, second.leagues), ("lob_x", [7]))

    def test_list_bots_null_list(self):
        self.request.return_value = _resp(200, {"bots": None, "simulation": True})
        self.assertEqual(self.client.list_bots(), [])

    def test_list_bots_not_retried_on_unreachable(self):
        self.request.side_effect = requests.ConnectionError
        with self.assertRaises(DotaLobbyUnavailable):
            self.client.list_bots()
        self.assertEqual(self.request.call_count, 1)
        self.assertEqual(self.sleeps, [])

    def test_get_league_parses_holders_and_bots(self):
        self.request.return_value = _resp(
            200,
            {
                "league_id": 17929,
                "name": "DTX",
                "holders": [
                    {
                        "bot": "sim_bot_1",
                        "source": "gc",
                        "verified": True,
                        "first_seen_at": None,
                        "refreshed_at": "2026-11-24T10:00:00Z",
                        "bot_state": "gc_ready",
                        "ready": True,
                        "lobby_id": None,
                    }
                ],
                "bots": [{"name": "sim_bot_1", "stale": True}],
                "holders_total": 1,
                "holders_free": 1,
            },
        )
        league = self.client.get_league(17929, retry=False)
        holder = league.holders[0]
        self.assertEqual(
            (holder.bot, holder.source, holder.verified), ("sim_bot_1", "gc", True)
        )
        self.assertEqual(holder.refreshed_at.year, 2026)
        self.assertEqual(
            (league.bots[0].name, league.bots[0].stale), ("sim_bot_1", True)
        )

    def test_get_league_null_holders(self):
        self.request.return_value = _resp(
            200, {"league_id": 1, "holders": None, "bots": None}
        )
        league = self.client.get_league(1)
        self.assertEqual((league.holders, league.bots), ([], []))

    def test_get_league_retry_false(self):
        self.request.side_effect = requests.ConnectionError
        with self.assertRaises(DotaLobbyUnavailable):
            self.client.get_league(1, retry=False)
        self.assertEqual(self.request.call_count, 1)

    def test_get_bot_leagues_quotes_name(self):
        self.request.return_value = _resp(
            200,
            {
                "bot": "a/b",
                "leagues": [
                    {
                        "league_id": 17929,
                        "name": None,
                        "source": "gc",
                        "verified": True,
                        "first_seen_at": None,
                        "refreshed_at": "2026-11-24T10:00:00Z",
                        "stale": False,
                    }
                ],
                "refresh": {
                    "ok_at": "2026-11-24T10:00:00Z",
                    "error": "gc timeout",
                    "error_at": None,
                },
                "changes": None,
            },
        )
        result = self.client.get_bot_leagues("a/b")
        method, url, _ = self.call()
        self.assertEqual(method, "GET")
        self.assertTrue(url.endswith("/v1/bots/a%2Fb/leagues"), url)
        self.assertEqual(result.refresh.ok_at.year, 2026)
        self.assertFalse(hasattr(result.refresh, "error"))
        self.assertEqual(result.leagues[0].league_id, 17929)

    def test_get_bot_leagues_null_refresh_fields(self):
        self.request.return_value = _resp(
            200, {"bot": "sim_bot_1", "leagues": None, "refresh": {"ok_at": None}}
        )
        result = self.client.get_bot_leagues("sim_bot_1")
        self.assertEqual(result.leagues, [])
        self.assertIsNone(result.refresh.ok_at)

    def test_get_bot_leagues_timeout_override(self):
        self.request.return_value = _resp(200, {"bot": "sim_bot_1", "leagues": []})
        self.client.get_bot_leagues("sim_bot_1", timeout=4.0)
        self.assertEqual(self.call()[2]["timeout"][1], 4.0)

    def test_get_bot_leagues_not_retried(self):
        self.request.return_value = _problem(503, "unavailable", retryable=True)
        with self.assertRaises(DotaLobbyError):
            self.client.get_bot_leagues("sim_bot_1")
        self.assertEqual(self.request.call_count, 1)

    def test_get_bot_leagues_failure_log_redacts_name(self):
        self.request.return_value = _problem(
            404, "not_found", detail='no bot named "sim_bot_1"'
        )
        with capture_logs() as logs, self.assertRaises(DotaLobbyError):
            self.client.get_bot_leagues("sim_bot_1")
        failed = [e for e in logs if e["event"] == "dota_lobby_request_failed"]
        self.assertEqual(len(failed), 1)
        self.assertEqual(failed[0]["http_path"], "/v1/bots/{name}/leagues")
        self.assertNotIn("sim_bot_1", repr(logs))

    def test_refresh_leagues_uses_long_timeout(self):
        self.request.return_value = _resp(
            200,
            {
                "results": [
                    {"bot": "sim_bot_1", "status": "ok", "error": None, "leagues": [1]},
                    {
                        "bot": "sim_bot_2",
                        "status": "not_ready",
                        "error": None,
                        "leagues": None,
                    },
                ]
            },
        )
        result = self.client.refresh_leagues()
        method, url, kwargs = self.call()
        self.assertEqual((method, url), ("POST", f"{BASE}/v1/leagues/refresh"))
        self.assertEqual(kwargs["json"], {})
        self.assertEqual(kwargs["timeout"], (CONNECT_TIMEOUT_SECONDS, 20.0))
        self.assertEqual(
            [(r.bot, r.status) for r in result.results],
            [("sim_bot_1", "ok"), ("sim_bot_2", "not_ready")],
        )

    def test_refresh_leagues_keeps_longer_configured_timeout(self):
        client = DotaLobbyClient(BASE, API_KEY, 30)
        self.request.return_value = _resp(200, {"results": None})
        self.assertEqual(client.refresh_leagues().results, [])
        self.assertEqual(self.call()[2]["timeout"], (CONNECT_TIMEOUT_SECONDS, 30.0))

    def test_refresh_leagues_not_retried(self):
        self.request.return_value = _problem(503, "unavailable", retryable=True)
        with self.assertRaises(DotaLobbyError):
            self.client.refresh_leagues()
        self.assertEqual(self.request.call_count, 1)

    def test_refresh_leagues_409_raises_invalid_state(self):
        self.request.return_value = _problem(409, "invalid_state")
        with self.assertRaises(DotaLobbyError) as ctx:
            self.client.refresh_leagues()
        self.assertEqual(
            (ctx.exception.code, ctx.exception.status), ("invalid_state", 409)
        )

    def test_default_timeout_unchanged(self):
        self.request.return_value = _resp(200, {"bots": []})
        self.client.list_bots()
        self.assertEqual(self.call()[2]["timeout"], (CONNECT_TIMEOUT_SECONDS, 5))
