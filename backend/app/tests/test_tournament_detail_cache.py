"""GET /api/tournaments/<pk>/ never caches a payload a concurrent commit made stale."""

from collections.abc import Callable
from unittest.mock import patch

from django.test import TransactionTestCase
from rest_framework.response import Response
from rest_framework.test import APIClient

from app import views_main
from app.models import Team
from app.tests.teamdraft_fixtures import TimedDraftFixture
from user.tests.test_cacheops_integration import _redis_reachable


class TournamentDetailStaleWriteTests(TransactionTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls._redis_ok = _redis_reachable()

    def setUp(self) -> None:
        if not self._redis_ok:
            self.skipTest("Cacheops Redis not reachable")
        tick = patch("app.tasks.draft_tick.start_tick_broadcaster", return_value=True)
        tick.start()
        self.addCleanup(tick.stop)
        self.fx = TimedDraftFixture(prefix="tdcache")
        self.reader = APIClient()
        self.reader.force_authenticate(self.fx.staff)
        self.captain = APIClient()
        self.captain.force_authenticate(self.fx.captains[0])

    def detail(self) -> Response:
        return self.reader.get(f"/api/tournaments/{self.fx.tournament.pk}/")

    def ready_flag(self, data: dict) -> bool:
        team = next(t for t in data["teams"] if t["pk"] == self.fx.teams[0].pk)
        return team["draft_is_ready"]

    def test_ready_committed_mid_read_is_not_cached_stale(self) -> None:
        original: Callable[..., dict] = views_main._build_users_dict
        fired: list[bool] = []

        def commit_ready_mid_read(*args: object, **kwargs: object) -> dict:
            if not fired:
                fired.append(True)
                response = self.captain.post(
                    f"/api/draft/{self.fx.draft.pk}/ready/", {"ready": True}, format="json"
                )
                self.assertEqual(response.status_code, 200)
            return original(*args, **kwargs)

        with patch.object(views_main, "_build_users_dict", commit_ready_mid_read):
            racing = self.detail()
        self.assertEqual(fired, [True])
        self.assertFalse(self.ready_flag(racing.data))
        self.assertTrue(
            Team.objects.nocache().get(pk=self.fx.teams[0].pk).draft_is_ready
        )

        self.assertTrue(self.ready_flag(self.detail().data))

    def test_member_nickname_edit_evicts_cached_detail(self) -> None:
        member = self.fx.captains[0]
        self.assertEqual(self.detail().status_code, 200)

        editor = APIClient()
        editor.force_authenticate(member)
        response = editor.patch(
            "/api/users/me/profile/base/", {"nickname": "Renamed"}, format="json"
        )
        self.assertEqual(response.status_code, 200)

        users = self.detail().data["_users"]
        self.assertEqual(users[member.pk]["nickname"], "Renamed")
