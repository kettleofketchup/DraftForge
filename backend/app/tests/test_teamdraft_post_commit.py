"""Post-commit hook failures on team-draft actions (pick, undo, ready, start, pause, resume)."""

from contextlib import ExitStack
from unittest.mock import MagicMock, patch

from django.test import TransactionTestCase
from rest_framework.response import Response
from rest_framework.test import APIClient
from structlog.testing import capture_logs

from app.models import CustomUser, Draft, DraftRound, Team, TeamDraftState
from app.tests.teamdraft_fixtures import TimedDraftFixture


class PostCommitFailureTests(TransactionTestCase):
    """A post-commit hook failure never turns a committed action into an error."""

    def setUp(self) -> None:
        draft_tick_patch = patch(
            "app.tasks.draft_tick.start_tick_broadcaster", return_value=True
        )
        draft_tick_patch.start()
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

    def failing_broadcast(self) -> tuple[list[dict], MagicMock]:
        stack = ExitStack()
        self.addCleanup(stack.close)
        stack.enter_context(
            patch(
                "app.broadcast.broadcast_event", side_effect=RuntimeError("layer down")
            )
        )
        invalidate = stack.enter_context(
            patch("app.cache_utils._cacheops_invalidate_obj")
        )
        logs = stack.enter_context(capture_logs())
        return logs, invalidate

    def assert_logged_failure(self, logs: list[dict], fx: TimedDraftFixture) -> None:
        failures = [e for e in logs if e["event"] == "broadcast_after_commit_failed"]
        self.assertTrue(failures, [e["event"] for e in logs])
        self.assertEqual(failures[0]["system"], "websocket")
        self.assertEqual(failures[0]["subsystem"], "broadcast")
        self.assertEqual(failures[0]["draft_id"], fx.draft.pk)
        self.assertEqual(failures[0]["error"], "layer down")

    def test_pick_is_201_and_saved_when_broadcast_raises(self) -> None:
        fx = TimedDraftFixture(prefix="pcpick")
        fx.start()
        rnd = fx.round(1)
        player = fx.players[0]
        logs, invalidate = self.failing_broadcast()
        response = fx.pick(rnd, fx.staff, player)
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(
            DraftRound.objects.nocache().get(pk=rnd.pk).choice_id, player.pk
        )
        self.assertEqual(response.data["draft"]["draft_rounds"][0]["choice"], player.pk)
        self.assert_logged_failure(logs, fx)
        invalidate.assert_called()

    def test_undo_is_200_and_saved_when_broadcast_raises(self) -> None:
        fx = TimedDraftFixture(prefix="pcundo")
        fx.start()
        fx.pick(fx.round(1), fx.staff, fx.players[0])
        logs, invalidate = self.failing_broadcast()
        response = fx.undo(fx.staff)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertIsNone(fx.round(1).choice_id)
        self.assert_logged_failure(logs, fx)
        invalidate.assert_called()

    def test_ready_is_200_and_saved_when_broadcast_raises(self) -> None:
        fx = TimedDraftFixture(prefix="pcready")
        logs, invalidate = self.failing_broadcast()
        response = self.post(fx, fx.captains[0], "ready", {"ready": True})
        self.assertEqual(response.status_code, 200, response.content)
        self.assertTrue(Team.objects.nocache().get(pk=fx.teams[0].pk).draft_is_ready)
        self.assert_logged_failure(logs, fx)
        invalidate.assert_called()

    def test_start_pause_resume_are_200_and_saved_when_broadcast_raises(self) -> None:
        fx = TimedDraftFixture(prefix="pcspr")
        logs, _ = self.failing_broadcast()
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
