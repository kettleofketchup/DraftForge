"""Post-commit hook failures on team-draft actions (pick, undo, ready, start, pause, resume)."""

from contextlib import ExitStack
from unittest.mock import patch

from django.db import transaction
from django.test import TransactionTestCase
from redis.exceptions import ResponseError
from rest_framework.response import Response
from rest_framework.test import APIClient
from structlog.testing import capture_logs

from app import broadcast
from app.models import CustomUser, Draft, DraftRound, Team, TeamDraftState
from app.tests.teamdraft_fixtures import TimedDraftFixture

BROADCAST_CALL_SITES: tuple[str, ...] = (
    "app.functions.teamdraft",
    "app.functions.draft_picks",
    "app.functions.shuffle_draft",
)


class HookSentinel:
    """Queues an on_commit hook right behind every guarded broadcast hook."""

    def __init__(self) -> None:
        self.registered = 0
        self.ran = 0

    def register(self, event: object) -> None:
        broadcast.broadcast_event_after_commit(event)
        self.registered += 1
        transaction.on_commit(self.run)

    def run(self) -> None:
        self.ran += 1


class PostCommitFailureTests(TransactionTestCase):
    """A post-commit hook failure never turns a committed action into an error."""

    def setUp(self) -> None:
        draft_tick_patch = patch(
            "app.tasks.draft_tick.start_tick_broadcaster", return_value=True
        )
        self.tick_start = draft_tick_patch.start()
        self.addCleanup(draft_tick_patch.stop)
        self.client = APIClient()

    def post(
        self,
        fx: TimedDraftFixture,
        user: CustomUser,
        path: str,
        body: dict | None = None,
    ) -> Response:
        self.client.force_authenticate(user)
        return self.client.post(
            f"/api/draft/{fx.draft.pk}/{path}/", body or {}, format="json"
        )

    def failing_broadcast(self) -> tuple[list[dict], HookSentinel]:
        stack = ExitStack()
        self.addCleanup(stack.close)
        stack.enter_context(
            patch(
                "app.broadcast.broadcast_event", side_effect=RuntimeError("layer down")
            )
        )
        sentinel = HookSentinel()
        for site in BROADCAST_CALL_SITES:
            stack.enter_context(
                patch(f"{site}.broadcast_event_after_commit", sentinel.register)
            )
        self.tick_start.reset_mock()
        logs = stack.enter_context(capture_logs())
        return logs, sentinel

    def assert_later_hooks_ran(self, sentinel: HookSentinel) -> None:
        self.assertGreater(sentinel.registered, 0)
        self.assertEqual(sentinel.ran, sentinel.registered)

    def assert_logged_failure(self, logs: list[dict], fx: TimedDraftFixture) -> None:
        failures = [e for e in logs if e["event"] == "broadcast_after_commit_failed"]
        self.assertTrue(failures, [e["event"] for e in logs])
        self.assertEqual(failures[0]["system"], "websocket")
        self.assertEqual(failures[0]["subsystem"], "broadcast")
        self.assertEqual(failures[0]["draft_id"], fx.draft.pk)
        self.assertEqual(failures[0]["error"], "layer down")
        self.assertIs(failures[0]["exc_info"], True)

    def test_pick_is_201_and_saved_when_broadcast_raises(self) -> None:
        fx = TimedDraftFixture(prefix="pcpick")
        fx.start()
        rnd = fx.round(1)
        player = fx.players[0]
        logs, sentinel = self.failing_broadcast()
        response = fx.pick(rnd, fx.staff, player)
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(
            DraftRound.objects.nocache().get(pk=rnd.pk).choice_id, player.pk
        )
        self.assertEqual(response.data["draft"]["draft_rounds"][0]["choice"], player.pk)
        self.assert_logged_failure(logs, fx)
        self.assert_later_hooks_ran(sentinel)

    def test_undo_is_200_and_saved_when_broadcast_raises(self) -> None:
        fx = TimedDraftFixture(prefix="pcundo")
        fx.start()
        fx.pick(fx.round(1), fx.staff, fx.players[0])
        logs, sentinel = self.failing_broadcast()
        response = fx.undo(fx.staff)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertIsNone(fx.round(1).choice_id)
        self.assert_logged_failure(logs, fx)
        self.assert_later_hooks_ran(sentinel)
        self.tick_start.assert_called_once()

    def test_ready_is_200_and_saved_when_broadcast_raises(self) -> None:
        fx = TimedDraftFixture(prefix="pcready")
        logs, sentinel = self.failing_broadcast()
        response = self.post(fx, fx.captains[0], "ready", {"ready": True})
        self.assertEqual(response.status_code, 200, response.content)
        self.assertTrue(Team.objects.nocache().get(pk=fx.teams[0].pk).draft_is_ready)
        self.assert_logged_failure(logs, fx)
        self.assert_later_hooks_ran(sentinel)

    def test_start_pause_resume_are_200_and_saved_when_broadcast_raises(self) -> None:
        fx = TimedDraftFixture(prefix="pcspr")
        logs, sentinel = self.failing_broadcast()
        for path, state in (
            ("start", TeamDraftState.DRAFTING),
            ("pause", TeamDraftState.PAUSED),
            ("resume", TeamDraftState.RESUMING),
        ):
            with self.subTest(path=path):
                response = self.post(fx, fx.staff, path)
                self.assertEqual(response.status_code, 200, response.content)
                self.assertEqual(
                    Draft.objects.nocache().get(pk=fx.draft.pk).state, state
                )
                self.assertEqual(response.data["draft"]["state"], state)
        self.assert_logged_failure(logs, fx)
        self.assert_later_hooks_ran(sentinel)
        # start and resume queue the tick start behind their broadcasts
        self.assertEqual(self.tick_start.call_count, 2)

    def test_resume_is_200_when_the_tick_start_raises(self) -> None:
        fx = TimedDraftFixture(prefix="pctick")
        fx.start()
        self.post(fx, fx.staff, "pause")
        with (
            patch(
                "app.tasks.draft_tick.start_tick_broadcaster",
                side_effect=ConnectionError("redis down"),
            ),
            capture_logs() as logs,
        ):
            response = self.post(fx, fx.staff, "resume")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(
            Draft.objects.nocache().get(pk=fx.draft.pk).state, TeamDraftState.RESUMING
        )
        failures = [e for e in logs if e["event"] == "tick_start_after_commit_failed"]
        self.assertTrue(failures, [e["event"] for e in logs])
        self.assertEqual(failures[0]["error"], "redis down")
        self.assertEqual(failures[0]["system"], "teamdraft")
        self.assertEqual(failures[0]["subsystem"], "timer")
        self.assertIs(failures[0]["exc_info"], True)

    def test_ready_is_200_and_broadcasts_when_invalidation_raises(self) -> None:
        fx = TimedDraftFixture(prefix="pcinv")
        with (
            patch(
                "app.cache_utils._cacheops_invalidate_obj",
                side_effect=ResponseError("MISCONF"),
            ),
            patch("app.broadcast.broadcast_event") as broadcast_mock,
            capture_logs() as logs,
        ):
            response = self.post(fx, fx.captains[0], "ready", {"ready": True})
        self.assertEqual(response.status_code, 200, response.content)
        self.assertTrue(Team.objects.nocache().get(pk=fx.teams[0].pk).draft_is_ready)
        broadcast_mock.assert_called_once()
        failures = [
            e for e in logs if e["event"] == "cache_invalidate_after_commit_failed"
        ]
        self.assertTrue(failures, [e["event"] for e in logs])
        self.assertEqual(failures[0]["system"], "cache")
        self.assertEqual(failures[0]["subsystem"], "invalidate")
        self.assertEqual(failures[0]["error"], "MISCONF")
        self.assertIs(failures[0]["exc_info"], True)
