"""User-facing lobby API: api/games/<game_pk>/lobby/ (lobby.views)."""

from unittest import mock

from django.core.cache.backends.locmem import LocMemCache
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from app.models import DotaLobbyMode, GameMode, League, Organization
from events.models import Event
from lobby import services, states
from lobby.client import DotaLobbyError, DotaLobbyUnavailable
from lobby.models import GameLobby
from lobby.schemas import InviteResult, LobbyView
from lobby.tests.helpers import (
    lobby_settings,
    lobby_view,
    make_game,
    make_tournament,
    make_user,
)
from lobby.views import LobbyActionThrottle

PRIVATE_KEYS = {"password", "players", "last_error_detail", "name", "bot"}


def _url(game_pk: int, action: str = "") -> str:
    return f"/api/games/{game_pk}/lobby/{action}"


class LobbyViewTestCase(TestCase):
    def setUp(self):
        self.tournament = make_tournament(dota_lobby_mode=DotaLobbyMode.MANUAL)
        self.game = make_game(self.tournament)
        self.staff = make_user()
        self.staff.is_staff = True
        self.staff.save()
        self.player = self.game.radiant_team.members.exclude(
            pk=self.game.radiant_team.captain_id
        ).first()
        self.outsider = make_user()
        self.client = APIClient()

    def as_user(self, user):
        self.client.force_authenticate(user=user)
        return self.client

    def make_lobby(self, state=states.WAITING, lobby_id="lob_1"):
        row = services.claim_lobby(self.game.pk, trigger="manual").game_lobby
        row.lobby_id = lobby_id
        row.state = state
        row.save()
        return row


@lobby_settings
class LobbyReadTests(LobbyViewTestCase):
    def test_anonymous_is_refused(self):
        resp = APIClient().get(_url(self.game.pk))
        self.assertIn(resp.status_code, (401, 403))

    def test_no_lobby_yet(self):
        resp = self.as_user(self.outsider).get(_url(self.game.pk))
        self.assertEqual(resp.status_code, 200)
        self.assertIsNone(resp.data["lobby"])
        self.assertTrue(resp.data["enabled"])
        self.assertFalse(resp.data["can_manage"])
        self.assertNotIn("eligibility", resp.data)
        self.assertNotIn("players", resp.data)

    def test_staff_sees_eligibility_and_roster_before_a_lobby(self):
        self.game.dire_team.members.add(make_user(steam=False))
        resp = self.as_user(self.staff).get(_url(self.game.pk))
        self.assertTrue(resp.data["can_manage"])
        self.assertEqual(resp.data["eligibility"]["code"], "missing_steam_ids")
        missing = resp.data["eligibility"]["details"]["players"]
        self.assertEqual(len(missing), 1)
        self.assertIn("name", missing[0])
        self.assertEqual(len(resp.data["players"]), 11)

    def test_other_user_gets_public_fields_only(self):
        row = self.make_lobby()
        row.match_id = 8_000_000_001
        row.provisional_winner_side = "radiant"
        row.save()
        resp = self.as_user(self.outsider).get(_url(self.game.pk))
        lobby = resp.data["lobby"]
        self.assertEqual(lobby["state"], states.WAITING)
        self.assertEqual(lobby["match_id"], "8000000001")
        self.assertEqual(lobby["provisional_winner_side"], "radiant")
        self.assertFalse(PRIVATE_KEYS & set(lobby))
        self.assertTrue(row.password)
        self.assertNotIn(row.password, str(resp.content))

    def test_rostered_player_sees_password_and_invites(self):
        row = self.make_lobby()
        account = str(self.player.steam_account_id)
        row.players = {account: {"status": "invited", "invites_sent": 1}}
        row.save()
        resp = self.as_user(self.player).get(_url(self.game.pk))
        lobby = resp.data["lobby"]
        self.assertTrue(resp.data["is_player"])
        self.assertFalse(resp.data["can_manage"])
        self.assertEqual(lobby["password"], row.password)
        self.assertEqual(lobby["name"], row.request["name"])
        mine = next(p for p in lobby["players"] if p["user_id"] == self.player.pk)
        self.assertEqual(mine["status"], "invited")
        self.assertEqual(mine["invites_sent"], 1)
        self.assertEqual(mine["side"], "radiant")
        self.assertEqual(len(lobby["players"]), 10)

    def test_captain_counts_as_rostered(self):
        self.make_lobby()
        captain = self.game.dire_team.captain
        resp = self.as_user(captain).get(_url(self.game.pk))
        self.assertIsNotNone(resp.data["lobby"]["password"])

    def test_staff_sees_password_and_error_detail(self):
        row = self.make_lobby()
        row.last_error_code = "league_not_held"
        row.last_error_detail = "no bot holds league 1"
        row.save()
        resp = self.as_user(self.staff).get(_url(self.game.pk))
        lobby = resp.data["lobby"]
        self.assertEqual(lobby["password"], row.password)
        self.assertEqual(lobby["last_error_code"], "league_not_held")
        self.assertEqual(lobby["last_error_detail"], "no bot holds league 1")
        self.assertEqual(resp.data["eligibility"]["code"], "active_lobby_exists")

    def _league_tournament(self):
        owner = make_user()
        org = Organization.objects.create(name="Lobby Org", owner=owner)
        league = League.objects.create(name="Lobby League", organization=org)
        self.tournament.league = league
        self.tournament.save()
        return org, league

    def test_league_staff_outside_the_org_manage_without_the_password(self):
        # The password is event-wide: a tournament editor who is only league
        # staff must not read it from the lobby panel.
        _, league = self._league_tournament()
        league_staff = make_user()
        league.staff.add(league_staff)
        self.make_lobby()
        resp = self.as_user(league_staff).get(_url(self.game.pk))
        self.assertTrue(resp.data["can_manage"])
        self.assertIsNone(resp.data["lobby"]["password"])
        self.assertNotIn(self.tournament.dota_lobby_password, str(resp.content))

    def test_org_staff_of_the_league_org_see_the_password(self):
        org, _ = self._league_tournament()
        org_staff = make_user()
        org.staff.add(org_staff)
        row = self.make_lobby()
        resp = self.as_user(org_staff).get(_url(self.game.pk))
        self.assertTrue(resp.data["can_manage"])
        self.assertEqual(resp.data["lobby"]["password"], row.password)

    def test_org_staff_of_the_source_event_see_the_password(self):
        _, league = self._league_tournament()
        event_owner = make_user()
        event_org = Organization.objects.create(name="Event Org", owner=event_owner)
        Event.objects.create(
            organization=event_org,
            name="Night 4",
            scheduled_at=timezone.now(),
            tournament=self.tournament,
            created_by=event_owner,
        )
        # Org staff of the event's organization who also edit the league.
        both = make_user()
        event_org.staff.add(both)
        league.staff.add(both)
        row = self.make_lobby()
        resp = self.as_user(both).get(_url(self.game.pk))
        self.assertEqual(resp.data["lobby"]["password"], row.password)
        # League org staff who are not staff of the event's organization.
        league_org_staff = make_user()
        league.organization.staff.add(league_org_staff)
        resp = self.as_user(league_org_staff).get(_url(self.game.pk))
        self.assertTrue(resp.data["can_manage"])
        self.assertIsNone(resp.data["lobby"]["password"])

    def test_rostered_league_staff_still_see_the_password(self):
        _, league = self._league_tournament()
        league.staff.add(self.player)
        row = self.make_lobby()
        resp = self.as_user(self.player).get(_url(self.game.pk))
        self.assertEqual(resp.data["lobby"]["password"], row.password)

    def test_ended_lobby_is_shown_without_password(self):
        row = self.make_lobby(state=states.TIMED_OUT)
        resp = self.as_user(self.staff).get(_url(self.game.pk))
        self.assertEqual(resp.data["lobby"]["id"], row.pk)
        self.assertTrue(resp.data["lobby"]["ended"])
        self.assertIsNone(resp.data["lobby"]["password"])

    def test_disabled_when_tournament_mode_off(self):
        self.tournament.dota_lobby_mode = DotaLobbyMode.OFF
        self.tournament.save()
        resp = self.as_user(self.staff).get(_url(self.game.pk))
        self.assertFalse(resp.data["enabled"])
        self.assertEqual(resp.data["eligibility"]["code"], "lobby_mode_off")

    def test_unknown_game_is_404(self):
        resp = self.as_user(self.staff).get(_url(999_999))
        self.assertEqual(resp.status_code, 404)


@lobby_settings
@mock.patch("lobby.tasks.close_dota_lobby.delay")
@mock.patch("lobby.tasks.create_dota_lobby.delay")
class LobbyCreateCloseTests(LobbyViewTestCase):
    def test_staff_create_queues_task(self, create_delay, close_delay):
        with self.captureOnCommitCallbacks(execute=True):
            resp = self.as_user(self.staff).post(_url(self.game.pk), {}, format="json")
        self.assertEqual(resp.status_code, 202)
        # The row exists before the task runs, so staff can close it at once.
        row = GameLobby.objects.get(game=self.game)
        self.assertEqual((row.state, row.trigger), (states.REQUESTED, "manual"))
        self.assertEqual(row.requested_by, self.staff)
        create_delay.assert_called_once_with(
            self.game.pk,
            trigger="manual",
            user_id=self.staff.pk,
            allow_missing=False,
            game_lobby_id=row.pk,
        )

    def test_close_right_after_create_closes_the_queued_row(
        self, create_delay, close_delay
    ):
        client = self.as_user(self.staff)
        with self.captureOnCommitCallbacks(execute=True):
            client.post(_url(self.game.pk), {}, format="json")
        with self.captureOnCommitCallbacks(execute=True):
            resp = client.delete(_url(self.game.pk))
        self.assertEqual(resp.status_code, 200)
        row = GameLobby.objects.get(game=self.game)
        self.assertEqual((row.state, row.state_reason), ("closed", "closed_by_staff"))

    def test_non_staff_cannot_create(self, create_delay, close_delay):
        for user in (self.player, self.outsider):
            resp = self.as_user(user).post(_url(self.game.pk), {}, format="json")
            self.assertEqual(resp.status_code, 403)
        create_delay.assert_not_called()

    def test_missing_steam_ids_refused_unless_allowed(self, create_delay, close_delay):
        self.game.dire_team.members.add(make_user(steam=False))
        client = self.as_user(self.staff)
        resp = client.post(_url(self.game.pk), {}, format="json")
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.data["code"], "missing_steam_ids")
        self.assertEqual(len(resp.data["eligibility"]["details"]["players"]), 1)
        with self.captureOnCommitCallbacks(execute=True):
            resp = client.post(
                _url(self.game.pk), {"allow_missing": True}, format="json"
            )
        self.assertEqual(resp.status_code, 202)
        self.assertTrue(create_delay.call_args.kwargs["allow_missing"])

    def test_custom_game_mode_refused(self, create_delay, close_delay):
        self.tournament.game_mode = GameMode.CUSTOM
        self.tournament.save()
        resp = self.as_user(self.staff).post(_url(self.game.pk), {}, format="json")
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.data["code"], "unsupported_game_mode")

    def test_active_lobby_conflicts_without_replace(self, create_delay, close_delay):
        self.make_lobby()
        resp = self.as_user(self.staff).post(_url(self.game.pk), {}, format="json")
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(resp.data["code"], "active_lobby_exists")

    def test_replace_closes_pregame_lobby_and_requests_new(
        self, create_delay, close_delay
    ):
        row = self.make_lobby(state=states.READY)
        with self.captureOnCommitCallbacks(execute=True):
            resp = self.as_user(self.staff).post(
                _url(self.game.pk), {"replace": True}, format="json"
            )
        self.assertEqual(resp.status_code, 202)
        self.assertTrue(resp.data["replaced"])
        row.refresh_from_db()
        self.assertEqual(row.state, states.CLOSED)
        self.assertEqual(row.state_reason, "replaced")
        close_delay.assert_called_once_with(row.pk, "lob_1")
        create_delay.assert_called_once()

    def test_recreated_lobby_uses_the_tournament_password(
        self, create_delay, close_delay
    ):
        # One password per event/tournament: a recreated lobby keeps it until
        # staff change or regenerate the event password.
        self.make_lobby(state=states.WAITING)
        player = self.as_user(self.player)
        old = player.get(_url(self.game.pk)).data["lobby"]["password"]
        self.assertEqual(old, self.tournament.dota_lobby_password)
        with self.captureOnCommitCallbacks(execute=True):
            resp = self.as_user(self.staff).post(
                _url(self.game.pk), {"replace": True}, format="json"
            )
        self.assertEqual(resp.status_code, 202)
        lobby = self.as_user(self.player).get(_url(self.game.pk)).data["lobby"]
        self.assertEqual(lobby["state"], states.REQUESTED)
        self.assertEqual(lobby["password"], old)

    def test_changed_password_applies_to_the_next_lobby_only(
        self, create_delay, close_delay
    ):
        first = self.make_lobby(state=states.WAITING)
        old = first.password
        self.tournament.dota_lobby_password = "new-event-pw"
        self.tournament.save()
        with self.captureOnCommitCallbacks(execute=True):
            resp = self.as_user(self.staff).post(
                _url(self.game.pk), {"replace": True}, format="json"
            )
        self.assertEqual(resp.status_code, 202)
        first.refresh_from_db()
        self.assertEqual(first.password, old)
        lobby = self.as_user(self.player).get(_url(self.game.pk)).data["lobby"]
        self.assertEqual(lobby["password"], "new-event-pw")

    def test_replace_refused_once_match_started(self, create_delay, close_delay):
        row = self.make_lobby(state=states.IN_GAME)
        resp = self.as_user(self.staff).post(
            _url(self.game.pk), {"replace": True}, format="json"
        )
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(resp.data["code"], "lobby_in_progress")
        row.refresh_from_db()
        self.assertEqual(row.state, states.IN_GAME)
        close_delay.assert_not_called()

    def test_failed_replace_keeps_the_old_lobby(self, create_delay, close_delay):
        row = self.make_lobby(state=states.WAITING)
        self.game.dire_team.members.add(make_user(steam=False))
        with self.captureOnCommitCallbacks(execute=True):
            resp = self.as_user(self.staff).post(
                _url(self.game.pk), {"replace": True}, format="json"
            )
        self.assertEqual(resp.status_code, 400)
        row.refresh_from_db()
        self.assertEqual(row.state, states.WAITING)
        close_delay.assert_not_called()
        create_delay.assert_not_called()

    def test_retry_after_timeout(self, create_delay, close_delay):
        self.make_lobby(state=states.TIMED_OUT)
        with self.captureOnCommitCallbacks(execute=True):
            resp = self.as_user(self.staff).post(_url(self.game.pk), {}, format="json")
        self.assertEqual(resp.status_code, 202)
        self.assertFalse(resp.data["replaced"])
        create_delay.assert_called_once()

    def test_no_retry_after_a_played_match(self, create_delay, close_delay):
        row = self.make_lobby(state=states.FINISHED)
        row.provisional_scored = True
        row.save()
        client = self.as_user(self.staff)
        self.assertEqual(
            client.get(_url(self.game.pk)).data["eligibility"]["code"],
            "lobby_match_played",
        )
        with self.captureOnCommitCallbacks(execute=True):
            resp = client.post(_url(self.game.pk), {}, format="json")
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.data["code"], "lobby_match_played")
        self.assertEqual(GameLobby.objects.filter(game=self.game).count(), 1)
        create_delay.assert_not_called()

    def test_replay_after_a_played_match(self, create_delay, close_delay):
        row = self.make_lobby(state=states.FINISHED)
        row.provisional_scored = True
        row.save()
        with self.captureOnCommitCallbacks(execute=True):
            resp = self.as_user(self.staff).post(
                _url(self.game.pk), {"replay": True}, format="json"
            )
        self.assertEqual(resp.status_code, 202)
        self.assertEqual(GameLobby.objects.filter(game=self.game).count(), 2)
        create_delay.assert_called_once()

    def test_staff_close(self, create_delay, close_delay):
        row = self.make_lobby()
        with self.captureOnCommitCallbacks(execute=True):
            resp = self.as_user(self.staff).delete(_url(self.game.pk))
        self.assertEqual(resp.status_code, 200)
        row.refresh_from_db()
        self.assertEqual(row.state, states.CLOSED)
        self.assertEqual(row.state_reason, "closed_by_staff")
        close_delay.assert_called_once_with(row.pk, "lob_1")
        self.assertEqual(resp.data["lobby"]["state"], states.CLOSED)

    def test_close_refused_in_game_and_without_lobby(self, create_delay, close_delay):
        client = self.as_user(self.staff)
        self.assertEqual(client.delete(_url(self.game.pk)).status_code, 404)
        self.make_lobby(state=states.IN_GAME)
        resp = client.delete(_url(self.game.pk))
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(resp.data["code"], "lobby_in_progress")

    def test_non_staff_cannot_close(self, create_delay, close_delay):
        self.make_lobby()
        resp = self.as_user(self.player).delete(_url(self.game.pk))
        self.assertEqual(resp.status_code, 403)


@lobby_settings
@mock.patch("lobby.views.DotaLobbyClient")
class LobbyInviteTests(LobbyViewTestCase):
    def test_staff_invites_missing(self, client_cls):
        self.make_lobby()
        client_cls.return_value.invite.return_value = InviteResult(invited=[1, 2])
        resp = self.as_user(self.staff).post(
            _url(self.game.pk, "invite/"), {"missing": True}, format="json"
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["invited"], [1, 2])
        client_cls.return_value.invite.assert_called_once_with(
            "lob_1", players=None, missing=True
        )

    def test_staff_invites_given_players(self, client_cls):
        self.make_lobby()
        client_cls.return_value.invite.return_value = InviteResult(invited=[7])
        resp = self.as_user(self.staff).post(
            _url(self.game.pk, "invite/"), {"players": [7]}, format="json"
        )
        self.assertEqual(resp.status_code, 200)
        client_cls.return_value.invite.assert_called_once_with(
            "lob_1", players=[7], missing=False
        )

    def test_staff_must_name_players(self, client_cls):
        self.make_lobby()
        resp = self.as_user(self.staff).post(
            _url(self.game.pk, "invite/"), {"players": ["x"]}, format="json"
        )
        self.assertEqual(resp.status_code, 400)
        client_cls.return_value.invite.assert_not_called()

    def test_player_can_only_invite_themselves(self, client_cls):
        self.make_lobby()
        client_cls.return_value.invite.return_value = InviteResult()
        resp = self.as_user(self.player).post(
            _url(self.game.pk, "invite/"),
            {"missing": True, "players": [1, 2, 3]},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        client_cls.return_value.invite.assert_called_once_with(
            "lob_1", players=[self.player.steam_account_id], missing=False
        )

    def test_outsider_cannot_invite(self, client_cls):
        self.make_lobby()
        resp = self.as_user(self.outsider).post(
            _url(self.game.pk, "invite/"), {}, format="json"
        )
        self.assertEqual(resp.status_code, 403)
        client_cls.return_value.invite.assert_not_called()

    def test_lobby_not_accepted_yet(self, client_cls):
        self.make_lobby(state=states.REQUESTED, lobby_id=None)
        resp = self.as_user(self.staff).post(
            _url(self.game.pk, "invite/"), {"missing": True}, format="json"
        )
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(resp.data["code"], "lobby_not_created")

    def test_invite_limited_keeps_retry_after(self, client_cls):
        self.make_lobby()
        client_cls.return_value.invite.side_effect = DotaLobbyError(
            "invite_limited", status=429, detail="cooldown", retry_after=30
        )
        resp = self.as_user(self.player).post(
            _url(self.game.pk, "invite/"), {}, format="json"
        )
        self.assertEqual(resp.status_code, 429)
        self.assertEqual(resp["Retry-After"], "30")
        self.assertEqual(resp.data["code"], "invite_limited")
        self.assertFalse(resp.data["retryable"])

    def test_upstream_errors_are_mapped(self, client_cls):
        self.make_lobby()
        cases = [
            (DotaLobbyError("unavailable", status=503, retryable=True), 503),
            (DotaLobbyError("gc_timeout", status=504, retryable=True), 504),
            (DotaLobbyError("invalid_state", status=409), 409),
            (DotaLobbyUnavailable("timed out"), 503),
            (DotaLobbyError("unauthorized", status=401), 502),
            (DotaLobbyError("http_500", status=500), 502),
        ]
        for exc, expected in cases:
            with self.subTest(code=exc.code):
                client_cls.return_value.invite.side_effect = exc
                resp = self.as_user(self.staff).post(
                    _url(self.game.pk, "invite/"), {"missing": True}, format="json"
                )
                self.assertEqual(resp.status_code, expected)
                self.assertEqual(resp.data["code"], exc.code)
                self.assertEqual(resp.data["retryable"], exc.retryable)


@lobby_settings
@mock.patch("lobby.views.DotaLobbyClient")
class LobbyActionThrottleTests(LobbyViewTestCase):
    """Invite and launch block a web worker on dota_lobby: limit them per user."""

    def setUp(self):
        super().setUp()
        # The test settings use a dummy cache, which never throttles.
        cache = LocMemCache("lobby-throttle-test", {})
        cache.clear()
        patcher = mock.patch.object(LobbyActionThrottle, "cache", cache)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_player_invites_are_limited(self, client_cls):
        self.make_lobby()
        client_cls.return_value.invite.return_value = InviteResult(invited=[1])
        client = self.as_user(self.player)
        for _ in range(12):
            resp = client.post(_url(self.game.pk, "invite/"), {}, format="json")
            self.assertEqual(resp.status_code, 200)
        resp = client.post(_url(self.game.pk, "invite/"), {}, format="json")
        self.assertEqual(resp.status_code, 429)
        self.assertEqual(resp.data["code"], "rate_limited")
        self.assertTrue(resp.data["retryable"])
        self.assertGreater(int(resp["Retry-After"]), 0)
        self.assertEqual(client_cls.return_value.invite.call_count, 12)

        # Another player has their own budget.
        other = self.game.dire_team.captain
        resp = self.as_user(other).post(
            _url(self.game.pk, "invite/"), {}, format="json"
        )
        self.assertEqual(resp.status_code, 200)

    def test_launch_has_its_own_budget(self, client_cls):
        self.make_lobby(state=states.READY)
        client_cls.return_value.invite.return_value = InviteResult(invited=[1])
        client_cls.return_value.launch_lobby.side_effect = DotaLobbyError(
            "not_ready", status=409
        )
        client = self.as_user(self.staff)
        for _ in range(12):
            client.post(_url(self.game.pk, "invite/"), {"missing": True}, format="json")
        resp = client.post(_url(self.game.pk, "launch/"), {}, format="json")
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(resp.data["code"], "not_ready")


@lobby_settings
@mock.patch("lobby.views.DotaLobbyClient")
class LobbyLaunchTests(LobbyViewTestCase):
    def test_staff_launch_applies_snapshot(self, client_cls):
        row = self.make_lobby(state=states.READY)
        client_cls.return_value.launch_lobby.return_value = LobbyView.model_validate(
            lobby_view(
                "lob_1",
                external_ref=row.external_ref,
                state=states.LAUNCHING,
                seq=5,
                launch_attempts=1,
            )
        )
        resp = self.as_user(self.staff).post(
            _url(self.game.pk, "launch/"), {"force": True}, format="json"
        )
        self.assertEqual(resp.status_code, 200)
        client_cls.return_value.launch_lobby.assert_called_once_with(
            "lob_1", force=True
        )
        row.refresh_from_db()
        self.assertEqual(row.state, states.LAUNCHING)
        self.assertEqual(resp.data["lobby"]["state"], states.LAUNCHING)

    def test_not_ready_passes_through(self, client_cls):
        self.make_lobby(state=states.WAITING)
        client_cls.return_value.launch_lobby.side_effect = DotaLobbyError(
            "not_ready", status=409, detail="2 players not ready"
        )
        resp = self.as_user(self.staff).post(
            _url(self.game.pk, "launch/"), {}, format="json"
        )
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(resp.data["code"], "not_ready")
        self.assertEqual(resp.data["error"], "2 players not ready")

    def test_player_cannot_launch(self, client_cls):
        self.make_lobby()
        resp = self.as_user(self.player).post(
            _url(self.game.pk, "launch/"), {}, format="json"
        )
        self.assertEqual(resp.status_code, 403)
        client_cls.return_value.launch_lobby.assert_not_called()


class LobbyDisabledTests(LobbyViewTestCase):
    """Outside lobby_settings DOTA_LOBBY_ENABLED is off."""

    @mock.patch("lobby.views.DotaLobbyClient")
    def test_actions_refused_while_disabled(self, client_cls):
        GameLobby.objects.create(
            game=self.game,
            external_ref=f"game:{self.game.pk}",
            lobby_id="lob_1",
            state=states.WAITING,
        )
        client = self.as_user(self.staff)
        resp = client.get(_url(self.game.pk))
        self.assertFalse(resp.data["enabled"])
        resp = client.post(_url(self.game.pk, "launch/"), {}, format="json")
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.data["code"], "lobby_disabled")
        client_cls.assert_not_called()


@lobby_settings
class BracketLobbyStateTests(LobbyViewTestCase):
    def test_bracket_includes_latest_lobby_state(self):
        resp = APIClient().get(f"/api/bracket/tournaments/{self.tournament.pk}/")
        self.assertEqual(resp.status_code, 200)
        match = next(m for m in resp.data["matches"] if m["pk"] == self.game.pk)
        self.assertIsNone(match["lobby_state"])

        old = self.make_lobby(state=states.TIMED_OUT)
        self.assertTrue(old.ended)
        self.make_lobby(state=states.WAITING, lobby_id="lob_2")
        resp = APIClient().get(f"/api/bracket/tournaments/{self.tournament.pk}/")
        match = next(m for m in resp.data["matches"] if m["pk"] == self.game.pk)
        self.assertEqual(match["lobby_state"], states.WAITING)
        self.assertNotIn("password", str(resp.content))


class TournamentLobbyFieldsTests(LobbyViewTestCase):
    def test_serializer_exposes_lobby_fields(self):
        resp = APIClient().get(f"/api/tournaments/{self.tournament.pk}/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["dota_lobby_mode"], DotaLobbyMode.MANUAL)
        self.assertEqual(resp.data["dota_lobby_launch"], "manual")
        self.assertEqual(resp.data["dota_lobby_region"], "")
        self.assertFalse(resp.data["discord_send_lobby_info"])
        self.assertEqual(resp.data["game_mode"], GameMode.CAPTAINS_MODE)
        self.assertIn("lobby_steam_league_id", resp.data)

    def test_staff_can_change_lobby_settings_but_not_game_mode(self):
        resp = self.as_user(self.staff).patch(
            f"/api/tournaments/{self.tournament.pk}/",
            {
                "dota_lobby_mode": "auto",
                "dota_lobby_launch": "auto",
                "dota_lobby_region": "europe",
                "discord_send_lobby_info": True,
                "game_mode": "turbo",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 200, resp.data)
        self.tournament.refresh_from_db()
        self.assertEqual(self.tournament.dota_lobby_mode, DotaLobbyMode.AUTO)
        self.assertEqual(self.tournament.dota_lobby_launch, "auto")
        self.assertEqual(self.tournament.dota_lobby_region, "europe")
        self.assertTrue(self.tournament.discord_send_lobby_info)
        self.assertEqual(self.tournament.game_mode, GameMode.CAPTAINS_MODE)

    def test_invalid_mode_rejected(self):
        resp = self.as_user(self.staff).patch(
            f"/api/tournaments/{self.tournament.pk}/",
            {"dota_lobby_mode": "sometimes"},
            format="json",
        )
        self.assertEqual(resp.status_code, 400)
