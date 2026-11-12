from datetime import timedelta
from unittest import mock

from django.test import TestCase, override_settings
from django.utils import timezone

from app.models import GameMode
from discordbot.models import DiscordMessageLog, DiscordTournamentLog
from lobby import services, states, tasks
from lobby.client import DotaLobbyError, DotaLobbyUnavailable
from lobby.models import GameLobby
from lobby.schemas import CreateResult, LobbyEvent, LobbyView
from lobby.tests.helpers import (
    LOBBY_SETTINGS,
    envelope,
    internal_api_bridge,
    lobby_settings,
    lobby_view,
    make_game,
    make_tournament,
    make_user,
)


class Retry(Exception):
    pass


def view(*args, **kwargs):
    return LobbyView.model_validate(lobby_view(*args, **kwargs))


@lobby_settings
class TaskTestBase(TestCase):
    def setUp(self):
        self.game = make_game()
        self.ref = f"game:{self.game.pk}"
        patcher = mock.patch("lobby.tasks.DotaLobbyClient")
        self.client_cls = patcher.start()
        self.addCleanup(patcher.stop)
        self.client = self.client_cls.return_value
        bridge = internal_api_bridge()
        bridge.__enter__()
        self.addCleanup(bridge.__exit__, None, None, None)

    def row(self):
        return GameLobby.objects.get(game=self.game)

    def run_task(self, task, *args, retries=0, **kwargs):
        with (
            mock.patch.object(task, "retry", side_effect=Retry) as retry,
            mock.patch.object(type(task.request), "retries", retries, create=True),
            self.captureOnCommitCallbacks(execute=True),
        ):
            self.retry = retry
            return task.run(*args, **kwargs)


class CreateTaskTests(TaskTestBase):
    def accept(self, replayed=False, **kwargs):
        def create(body):
            row_id = int(body["metadata"]["game_lobby_id"])
            return CreateResult(
                lobby=view(external_ref=self.ref, game_lobby_id=row_id, **kwargs),
                replayed=replayed,
            )

        self.client.create_lobby.side_effect = create

    def test_created(self):
        self.accept()
        self.assertEqual(
            self.run_task(tasks.create_dota_lobby, self.game.pk), "created"
        )
        body = self.client.create_lobby.call_args.args[0]
        row = self.row()
        self.assertEqual(body["password"], row.password)
        self.assertTrue(row.password)
        self.assertEqual(
            {k: v for k, v in body.items() if k != "password"}, row.request
        )
        self.assertEqual((row.lobby_id, row.state), ("lob_1", "pending"))

    def test_resend_is_identical(self):
        self.accept()
        self.run_task(tasks.create_dota_lobby, self.game.pk)
        row = self.row()
        row.lobby_id = None
        row.state = states.REQUESTED
        row.save()
        self.accept(replayed=True)
        self.assertEqual(
            self.run_task(tasks.create_dota_lobby, self.game.pk), "replayed"
        )
        first, second = (c.args[0] for c in self.client.create_lobby.call_args_list)
        self.assertEqual(first, second)

    def test_already_accepted_is_not_sent_again(self):
        self.accept()
        self.run_task(tasks.create_dota_lobby, self.game.pk)
        self.assertEqual(self.run_task(tasks.create_dota_lobby, self.game.pk), "exists")
        self.assertEqual(self.client.create_lobby.call_count, 1)

    def test_retryable_error_retries(self):
        self.client.create_lobby.side_effect = DotaLobbyError(
            "unavailable", status=503, retryable=True
        )
        with self.assertRaises(Retry):
            self.run_task(tasks.create_dota_lobby, self.game.pk)
        self.assertEqual(self.retry.call_args.kwargs["countdown"], 30)
        row = self.row()
        self.assertEqual((row.state, row.last_error_code), ("requested", "unavailable"))
        # The retry holds on to the row it claimed.
        self.assertEqual(self.retry.call_args.kwargs["args"], [self.game.pk])
        self.assertEqual(self.retry.call_args.kwargs["kwargs"]["game_lobby_id"], row.pk)
        # The reconcile task waits for this retry instead of starting another.
        self.assertEqual(
            (row.next_attempt_at - row.last_error_at).total_seconds(),
            30 + services.CREATE_ATTEMPT_LEASE_SECONDS,
        )

    def test_unreachable_retries_until_exhausted(self):
        self.client.create_lobby.side_effect = DotaLobbyUnavailable("Timeout")
        result = self.run_task(tasks.create_dota_lobby, self.game.pk, retries=5)
        self.assertEqual(result, "unreachable")
        self.retry.assert_not_called()
        self.assertEqual(self.row().state, "requested")

    def test_permanent_error(self):
        self.client.create_lobby.side_effect = DotaLobbyError(
            "league_not_held", status=422, detail="no bot holds 17929"
        )
        self.assertEqual(
            self.run_task(tasks.create_dota_lobby, self.game.pk), "league_not_held"
        )
        row = self.row()
        self.assertEqual(
            (row.state, row.ended, row.last_error_code),
            ("error", True, "league_not_held"),
        )
        self.retry.assert_not_called()

    def test_conflict_adopts_own_lobby(self):
        self.client.create_lobby.side_effect = DotaLobbyError("conflict", status=409)

        def holders(**kwargs):
            row = self.row()
            return iter([view("lob_own", external_ref=self.ref, game_lobby_id=row.pk)])

        self.client.list_lobbies.side_effect = holders
        self.assertEqual(
            self.run_task(tasks.create_dota_lobby, self.game.pk), "adopted"
        )
        self.assertEqual(self.row().lobby_id, "lob_own")

    def test_conflict_with_foreign_lobby_is_rejected(self):
        self.client.create_lobby.side_effect = DotaLobbyError("conflict", status=409)
        self.client.list_lobbies.return_value = iter(
            [view("lob_x", external_ref=self.ref)]
        )
        self.assertEqual(
            self.run_task(tasks.create_dota_lobby, self.game.pk), "conflict"
        )
        row = self.row()
        self.assertEqual((row.state, row.last_error_code), ("error", "conflict"))

    def test_conflict_with_earlier_lobby_closes_and_retries(self):
        old = services.claim_lobby(self.game.pk).game_lobby
        old.lobby_id = "lob_old"
        old.save()
        services.end_locally(old, services.TEAMS_CHANGED)
        self.client.create_lobby.side_effect = DotaLobbyError("conflict", status=409)
        self.client.list_lobbies.return_value = iter(
            [
                view(
                    "lob_old",
                    external_ref=self.ref,
                    game_lobby_id=old.pk,
                    state="closing",
                )
            ]
        )
        with self.assertRaises(Retry):
            self.run_task(tasks.create_dota_lobby, self.game.pk)
        self.client.close_lobby.assert_called_once_with("lob_old")
        self.assertEqual(
            self.retry.call_args.kwargs["countdown"], tasks.CONFLICT_RETRY_SECONDS
        )

    def test_retry_of_a_closed_row_does_not_create_a_new_lobby(self):
        # Staff create, every bot is busy, staff close while the task waits
        # to retry: the retry must not bring the lobby back.
        self.client.create_lobby.side_effect = DotaLobbyError(
            "unavailable", status=503, retryable=True
        )
        with self.assertRaises(Retry):
            self.run_task(tasks.create_dota_lobby, self.game.pk, trigger="manual")
        retry_kwargs = self.retry.call_args.kwargs["kwargs"]
        row = self.row()
        with self.captureOnCommitCallbacks(execute=False):
            self.assertTrue(services.close_lobby(row, "closed_by_staff"))
        self.client.create_lobby.reset_mock()
        self.assertEqual(
            self.run_task(
                tasks.create_dota_lobby, self.game.pk, retries=1, **retry_kwargs
            ),
            "lobby_ended",
        )
        self.client.create_lobby.assert_not_called()
        self.assertEqual(GameLobby.objects.filter(game=self.game).count(), 1)

    def test_queued_manual_create_of_a_closed_row_is_not_sent(self):
        with self.captureOnCommitCallbacks(execute=False):
            self.assertTrue(services.queue_create(self.game).ok)
        row = self.row()
        with self.captureOnCommitCallbacks(execute=False):
            services.close_lobby(row, "closed_by_staff")
        self.assertEqual(
            self.run_task(
                tasks.create_dota_lobby,
                self.game.pk,
                trigger="manual",
                game_lobby_id=row.pk,
            ),
            "lobby_ended",
        )
        self.client.create_lobby.assert_not_called()
        self.assertFalse(GameLobby.objects.filter(game=self.game, ended=False).exists())

    def test_not_eligible_is_not_sent(self):
        self.game.radiant_team.members.add(make_user(steam=False))
        self.assertEqual(
            self.run_task(tasks.create_dota_lobby, self.game.pk), "missing_steam_ids"
        )
        self.client.create_lobby.assert_not_called()

    def test_custom_mode_refused(self):
        game = make_game(make_tournament(game_mode=GameMode.CUSTOM))
        self.assertEqual(
            self.run_task(tasks.create_dota_lobby, game.pk), "unsupported_game_mode"
        )
        self.client.create_lobby.assert_not_called()

    def test_accepted_for_ended_row_closes(self):
        def create(body):
            row = self.row()
            services.end_locally(row, services.TEAMS_CHANGED)
            return CreateResult(
                lobby=view(external_ref=self.ref, game_lobby_id=row.pk), replayed=False
            )

        self.client.create_lobby.side_effect = create
        self.client.close_lobby.return_value = view(
            external_ref=self.ref, state="closing"
        )
        self.assertEqual(self.run_task(tasks.create_dota_lobby, self.game.pk), "closed")
        self.client.close_lobby.assert_called_once_with("lob_1")

    @override_settings(**{**LOBBY_SETTINGS, "DOTA_LOBBY_ENABLED": False})
    def test_disabled(self):
        self.assertEqual(
            self.run_task(tasks.create_dota_lobby, self.game.pk), "disabled"
        )
        self.client_cls.assert_not_called()


class ReconcileTests(TaskTestBase):
    def accepted_row(self, **fields):
        row = services.claim_lobby(self.game.pk).game_lobby
        row.lobby_id = "lob_1"
        row.state = fields.pop("state", states.PENDING)
        for k, v in fields.items():
            setattr(row, k, v)
        row.save()
        return row

    @mock.patch("lobby.tasks.create_dota_lobby.delay")
    def test_catches_up_events_and_state(self, create_delay):
        row = self.accepted_row()
        self.client.list_lobbies.return_value = iter(
            [view(external_ref=self.ref, state="waiting", seq=2)]
        )
        self.client.list_events.return_value = iter(
            LobbyEvent.model_validate(e)
            for e in (
                envelope(1, "lobby.created", external_ref=self.ref),
                envelope(
                    2, "lobby.player_joined", {"account_id": 3}, external_ref=self.ref
                ),
            )
        )
        counts = self.run_task(tasks.reconcile_dota_lobbies)
        self.assertEqual((counts["synced"], counts["events"]), (1, 1))
        self.client.list_events.assert_called_once_with("lob_1", after=0)
        row.refresh_from_db()
        self.assertEqual((row.last_seq, row.state), (2, "waiting"))
        self.assertEqual(row.events.filter(source="poll").count(), 2)
        create_delay.assert_not_called()

    def test_lobby_missing_from_list_is_fetched(self):
        self.accepted_row(last_seq=4)
        self.client.list_lobbies.return_value = iter([])
        self.client.get_lobby.return_value = view(
            external_ref=self.ref, state="finished", seq=4
        )
        self.run_task(tasks.reconcile_dota_lobbies)
        self.client.get_lobby.assert_called_once_with("lob_1")
        self.client.list_events.assert_not_called()
        self.assertEqual(GameLobby.objects.get(game=self.game).state, "finished")

    def test_unknown_lobby_is_closed(self):
        self.accepted_row()
        self.client.list_lobbies.return_value = iter([])
        self.client.get_lobby.side_effect = DotaLobbyError("not_found", status=404)
        counts = self.run_task(tasks.reconcile_dota_lobbies)
        self.assertEqual(counts["missing"], 1)
        row = GameLobby.objects.get(game=self.game)
        self.assertEqual((row.state, row.state_reason), ("closed", "not_found"))

    @mock.patch("lobby.tasks.create_dota_lobby.delay")
    def test_resends_old_requested_rows(self, create_delay):
        row = services.claim_lobby(self.game.pk).game_lobby
        GameLobby.objects.filter(pk=row.pk).update(
            created_at=timezone.now() - timedelta(minutes=3)
        )
        fresh = make_game()
        services.claim_lobby(fresh.pk)
        counts = self.run_task(tasks.reconcile_dota_lobbies)
        self.assertEqual(counts["recreated"], 1)
        create_delay.assert_called_once_with(
            self.game.pk, trigger="auto", game_lobby_id=row.pk
        )
        self.client.list_lobbies.assert_not_called()

    @mock.patch("lobby.tasks.create_dota_lobby.delay")
    def test_does_not_resend_while_a_create_is_retrying(self, create_delay):
        self.client.create_lobby.side_effect = DotaLobbyError(
            "unavailable", status=503, retryable=True
        )
        with mock.patch.object(tasks.create_dota_lobby, "retry", side_effect=Retry):
            with self.assertRaises(Retry):
                self.run_task(tasks.create_dota_lobby, self.game.pk, retries=4)
        # Long past the create, but the retry is in 480 s.
        GameLobby.objects.filter(game=self.game).update(
            created_at=timezone.now() - timedelta(minutes=20)
        )
        for _ in range(3):
            counts = self.run_task(tasks.reconcile_dota_lobbies)
            self.assertEqual(counts["recreated"], 0)
        create_delay.assert_not_called()

        GameLobby.objects.filter(game=self.game).update(
            next_attempt_at=timezone.now() - timedelta(seconds=1)
        )
        counts = self.run_task(tasks.reconcile_dota_lobbies)
        self.assertEqual(counts["recreated"], 1)

    @mock.patch("lobby.tasks.create_dota_lobby.delay")
    def test_sweeps_eligible_games(self, create_delay):
        counts = self.run_task(tasks.reconcile_dota_lobbies)
        self.assertEqual(counts["eligible"], 1)
        create_delay.assert_called_once_with(self.game.pk, trigger="auto")

    @mock.patch("lobby.tasks.flip_lobby_sides.delay")
    def test_queues_flip(self, flip_delay):
        self.accepted_row(state=states.WAITING, last_seq=1)
        self.client.list_lobbies.return_value = iter(
            [view(external_ref=self.ref, state="waiting", seq=1)]
        )
        with mock.patch("lobby.services.wants_flip", return_value=True):
            counts = self.run_task(tasks.reconcile_dota_lobbies)
        self.assertEqual(counts["flips"], 1)
        row = GameLobby.objects.get(game=self.game)
        flip_delay.assert_called_once_with(
            row.pk, "lob_1", f"team-{self.game.dire_team_id}"
        )

    def test_dota_lobby_down_skips_round(self):
        self.accepted_row()
        self.client.list_lobbies.side_effect = DotaLobbyUnavailable("ConnectionError")
        self.assertEqual(self.run_task(tasks.reconcile_dota_lobbies), "unreachable")

    @override_settings(**{**LOBBY_SETTINGS, "DOTA_LOBBY_ENABLED": False})
    def test_disabled(self):
        self.assertEqual(self.run_task(tasks.reconcile_dota_lobbies), "disabled")

    def test_backfill(self):
        row = self.accepted_row(last_seq=1)
        self.client.get_lobby.return_value = view(
            external_ref=self.ref, state="ready", seq=2
        )
        self.client.list_events.return_value = iter(
            [
                LobbyEvent.model_validate(
                    envelope(2, "lobby.ready", external_ref=self.ref, state="ready")
                )
            ]
        )
        self.assertEqual(self.run_task(tasks.backfill_lobby_events, row.pk), "events")
        self.client.list_events.assert_called_once_with("lob_1", after=1)
        row.refresh_from_db()
        self.assertEqual((row.last_seq, row.state), (2, "ready"))

    def test_close(self):
        row = self.accepted_row(state=states.WAITING)
        self.client.close_lobby.return_value = view(
            external_ref=self.ref, state="closing"
        )
        self.assertEqual(
            self.run_task(tasks.close_dota_lobby, row.pk, "lob_1"), "closing"
        )
        row.refresh_from_db()
        self.assertEqual(row.state, "closing")

    def test_flip(self):
        row = self.accepted_row(state=states.WAITING)
        radiant = f"team-{self.game.radiant_team_id}"
        dire = f"team-{self.game.dire_team_id}"
        self.client.get_lobby.return_value = view(
            external_ref=self.ref, state="waiting", radiant_ref=radiant, dire_ref=dire
        )
        self.client.flip_teams.return_value = view(
            external_ref=self.ref, state="waiting", radiant_ref=dire, dire_ref=radiant
        )
        self.assertEqual(
            self.run_task(tasks.flip_lobby_sides, row.pk, "lob_1", dire), "flipped"
        )
        row.refresh_from_db()
        self.assertEqual(row.radiant_team_id, self.game.dire_team_id)

        self.client.get_lobby.return_value = self.client.flip_teams.return_value
        self.assertEqual(
            self.run_task(tasks.flip_lobby_sides, row.pk, "lob_1", dire), "already"
        )
        self.assertEqual(self.client.flip_teams.call_count, 1)


class CloseConfirmationTests(TaskTestBase):
    """A lobby DraftForge ended stays `close_pending` until dota_lobby closed it."""

    def claimed_row(self, **fields):
        """A `requested` row whose create body was handed out (lease set)."""
        with self.captureOnCommitCallbacks(execute=False):
            self.assertTrue(services.queue_create(self.game).ok)
        row = self.row()
        row.next_attempt_at = timezone.now() + timedelta(
            seconds=services.CREATE_ATTEMPT_LEASE_SECONDS
        )
        for k, v in fields.items():
            setattr(row, k, v)
        row.save()
        return row

    def close(self, row):
        with (
            mock.patch("lobby.tasks.close_dota_lobby.delay") as close_delay,
            self.captureOnCommitCallbacks(execute=True),
        ):
            self.assertTrue(services.close_lobby(row, "closed_by_staff"))
        row.refresh_from_db()
        return close_delay

    def expire_lease(self, row):
        GameLobby.objects.filter(pk=row.pk).update(
            next_attempt_at=timezone.now() - timedelta(seconds=1)
        )

    def test_row_never_sent_needs_no_close(self):
        with self.captureOnCommitCallbacks(execute=False):
            services.queue_create(self.game)
        row = self.row()
        close_delay = self.close(row)
        self.assertFalse(row.close_pending)
        close_delay.assert_not_called()

    def test_close_confirmed_clears_pending(self):
        row = self.claimed_row(lobby_id="lob_1", state=states.WAITING)
        close_delay = self.close(row)
        self.assertTrue(row.close_pending)
        close_delay.assert_called_once_with(row.pk, "lob_1")
        self.client.close_lobby.return_value = view(
            external_ref=self.ref, state="closing"
        )
        self.assertEqual(
            self.run_task(tasks.close_dota_lobby, row.pk, "lob_1"), "closing"
        )
        row.refresh_from_db()
        self.assertFalse(row.close_pending)
        self.assertEqual(row.state, states.CLOSED)

    def test_failed_close_is_retried_by_reconcile(self):
        # dota_lobby is down (a deploy) when staff press Close: the task gives
        # up, the row stays pending, and the next reconcile closes the lobby.
        row = self.claimed_row(lobby_id="lob_1", state=states.WAITING)
        self.close(row)
        self.client.close_lobby.side_effect = DotaLobbyUnavailable("Timeout")
        self.assertEqual(
            self.run_task(tasks.close_dota_lobby, row.pk, "lob_1", retries=3),
            "unreachable",
        )
        row.refresh_from_db()
        self.assertTrue(row.close_pending)

        self.client.close_lobby.side_effect = None
        self.client.close_lobby.return_value = view(
            external_ref=self.ref, state="closed"
        )
        self.client.list_lobbies.return_value = iter([])
        counts = self.run_task(tasks.reconcile_dota_lobbies)
        self.assertEqual((counts["closes"], counts["errors"]), (1, 0))
        self.client.close_lobby.assert_called_with("lob_1")
        row.refresh_from_db()
        self.assertFalse(row.close_pending)
        self.assertFalse(GameLobby.objects.filter(close_pending=True).exists())

    def test_reconcile_keeps_pending_while_dota_lobby_is_down(self):
        row = self.claimed_row(lobby_id="lob_1", state=states.WAITING)
        self.close(row)
        self.client.list_lobbies.return_value = iter([])
        self.client.close_lobby.side_effect = DotaLobbyUnavailable("Timeout")
        counts = self.run_task(tasks.reconcile_dota_lobbies)
        self.assertEqual((counts["closes"], counts["errors"]), (0, 1))
        row.refresh_from_db()
        self.assertTrue(row.close_pending)

    def test_close_while_disabled_stays_pending(self):
        # Lobbies switched off as a kill switch: the close waits for them to
        # be switched on again, when reconcile closes it.
        row = self.claimed_row(lobby_id="lob_1", state=states.WAITING)
        self.close(row)
        with override_settings(DOTA_LOBBY_ENABLED=False):
            self.assertEqual(
                self.run_task(tasks.close_dota_lobby, row.pk, "lob_1"), "disabled"
            )
        self.client.close_lobby.assert_not_called()
        row.refresh_from_db()
        self.assertTrue(row.close_pending)

    def test_lobby_already_gone_counts_as_closed(self):
        row = self.claimed_row(lobby_id="lob_1", state=states.WAITING)
        self.close(row)
        self.client.close_lobby.side_effect = DotaLobbyError("not_found", status=404)
        self.assertEqual(
            self.run_task(tasks.close_dota_lobby, row.pk, "lob_1"), "not_found"
        )
        row.refresh_from_db()
        self.assertFalse(row.close_pending)

    def test_requested_row_is_closed_by_external_ref(self):
        # The create reached dota_lobby but its answer was lost: the row has
        # no lobby ID. Only the lobby made for this row is closed, not a
        # replacement for the same game.
        row = self.claimed_row()
        close_delay = self.close(row)
        self.assertTrue(row.close_pending)
        close_delay.assert_called_once_with(row.pk, "")
        self.client.list_lobbies.return_value = iter(
            [
                view("lob_new", external_ref=self.ref, game_lobby_id=row.pk + 1),
                view("lob_old", external_ref=self.ref, game_lobby_id=row.pk),
            ]
        )
        self.client.close_lobby.return_value = view(
            "lob_old", external_ref=self.ref, state="closing", game_lobby_id=row.pk
        )
        self.assertEqual(self.run_task(tasks.close_dota_lobby, row.pk, ""), "closing")
        self.client.list_lobbies.assert_called_once_with(
            external_ref=self.ref, active=True
        )
        self.client.close_lobby.assert_called_once_with("lob_old")
        row.refresh_from_db()
        self.assertEqual(row.lobby_id, "lob_old")
        self.assertFalse(row.close_pending)

    def test_requested_row_waits_out_its_create_attempt(self):
        # Nothing in dota_lobby yet, but the create attempt may still land:
        # keep looking until its lease has run out.
        row = self.claimed_row()
        self.close(row)
        self.client.list_lobbies.return_value = iter([])
        self.assertEqual(self.run_task(tasks.close_dota_lobby, row.pk, ""), "waiting")
        row.refresh_from_db()
        self.assertTrue(row.close_pending)
        self.client.close_lobby.assert_not_called()

        self.expire_lease(row)
        self.client.list_lobbies.return_value = iter([])
        counts = self.run_task(tasks.reconcile_dota_lobbies)
        self.assertEqual(counts["closes"], 1)
        row.refresh_from_db()
        self.assertFalse(row.close_pending)


class LobbyInfoTests(TaskTestBase):
    def setUp(self):
        super().setUp()
        tournament = self.game.tournament
        tournament.discord_send_lobby_info = True
        tournament.save()
        self.row = services.claim_lobby(self.game.pk).game_lobby
        self.row.lobby_id = "lob_1"
        self.row.state = states.WAITING
        self.row.save()
        self.client.get_lobby.return_value = view(
            external_ref=self.ref, state="waiting", password="pw-from-lobby"
        )

    @mock.patch("discordbot.utils.sync_send_dm", return_value={"id": "1"})
    def test_sends_dm_with_password_and_logs_without_it(self, send_dm):
        result = self.run_task(tasks.send_lobby_info, self.row.pk)
        self.assertEqual(send_dm.call_count, 10)
        self.assertIn("10/10", result)
        embed = send_dm.call_args.kwargs["embed"]
        self.assertIn("||pw-from-lobby||", str(embed["fields"]))
        self.assertNotIn("tournament_log_id", send_dm.call_args.kwargs)
        log = DiscordTournamentLog.objects.get()
        self.assertEqual(
            (log.notification_type, log.success, log.recipient_count),
            ("lobby_info", True, 10),
        )
        self.assertNotIn("pw-from-lobby", log.message)
        self.assertFalse(DiscordMessageLog.objects.exists())

    @mock.patch("discordbot.utils.sync_send_dm")
    def test_disabled_by_tournament(self, send_dm):
        tournament = self.game.tournament
        tournament.discord_send_lobby_info = False
        tournament.save()
        self.assertEqual(
            self.run_task(tasks.send_lobby_info, self.row.pk), "Config disabled"
        )
        send_dm.assert_not_called()
