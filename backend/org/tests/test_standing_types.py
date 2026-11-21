import dataclasses

from django.test import SimpleTestCase

from org.standing.cache import StandingCache, memo
from org.standing.errors import FeatureLocked, UnknownMetric, UnknownTrack
from org.standing.types import (
    EMPTY_OUTPUT,
    HasUserId,
    HookResult,
    Leaderboard,
    Metric,
    OutputKeys,
    TrackAccess,
    TrackOutput,
)


class HookResultTests(SimpleTestCase):
    def test_hook_result_unions_in_order(self) -> None:
        r = HookResult(
            by_track={
                "contribution": TrackOutput(
                    orglog={"awarded": 2}, log={"awarded": True}
                ),
                "conduct": TrackOutput(orglog={"attendance_reopened": 1}),
            }
        )
        self.assertEqual(
            list(r.orglog_details().items()),
            [("awarded", 2), ("attendance_reopened", 1)],
        )
        self.assertEqual(r.log_fields(), {"awarded": True})

    def test_empty_hook_result(self) -> None:
        self.assertEqual(HookResult().orglog_details(), {})
        self.assertEqual(HookResult().log_fields(), {})
        self.assertEqual(EMPTY_OUTPUT, TrackOutput())

    def test_output_keys_keep_declared_order(self) -> None:
        keys = OutputKeys(orglog=("revoked",), log=("awarded", "created"))
        self.assertEqual(keys.log, ("awarded", "created"))
        self.assertEqual(OutputKeys().orglog, ())


class TypesShapeTests(SimpleTestCase):
    def test_dataclasses_are_frozen(self) -> None:
        access = TrackAccess(can_view_rows=True, can_view_own=False)
        with self.assertRaises(dataclasses.FrozenInstanceError):
            access.can_view_rows = False  # type: ignore[misc]

    def test_leaderboard_carries_rows_visible(self) -> None:
        metric = Metric(key="points", label="Points", format="int", periodic=True)
        board = Leaderboard(
            track="contribution",
            metric=metric,
            period="all",
            rows=[],
            total=0,
            own_row=None,
            rows_visible=False,
        )
        self.assertFalse(board.rows_visible)

    def test_has_user_id_is_runtime_checkable(self) -> None:
        class Row:
            user_id = 7

        self.assertIsInstance(Row(), HasUserId)
        self.assertNotIsInstance(object(), HasUserId)


class ErrorTests(SimpleTestCase):
    def test_lookup_errors_are_value_errors(self) -> None:
        self.assertTrue(issubclass(UnknownTrack, ValueError))
        self.assertTrue(issubclass(UnknownMetric, ValueError))

    def test_feature_locked_carries_track(self) -> None:
        self.assertEqual(FeatureLocked("contribution").track, "contribution")


class MemoTests(SimpleTestCase):
    def test_memo_computes_once(self) -> None:
        cache = StandingCache()
        calls: list[str] = []

        def compute() -> int:
            calls.append("x")
            return len(calls)

        self.assertEqual(memo(cache, "contribution", "scores", compute), 1)
        self.assertEqual(memo(cache, "contribution", "scores", compute), 1)
        self.assertEqual(len(calls), 1)
        self.assertEqual(memo(cache, "conduct", "scores", compute), 2)
        self.assertEqual(len(calls), 2)

    def test_caches_are_independent(self) -> None:
        memo(StandingCache(), "contribution", "scores", lambda: 1)
        self.assertEqual(memo(StandingCache(), "contribution", "scores", lambda: 2), 2)
