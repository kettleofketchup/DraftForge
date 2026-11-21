"""Committed Discord avatars for the real test users."""

import ast
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.test import TestCase, override_settings

import tests.populate.avatars as avatars_module
import tests.populate.utils as populate_utils
from app.models import CustomUser
from tests.data.discord_avatars import DISCORD_AVATARS
from tests.data.users import ADMIN_USER, TOURNAMENT_USERS
from tests.populate.avatars import (
    AvatarFetchError,
    real_test_discord_ids,
    refresh_committed_avatars,
    render_avatars_module,
)
from tests.populate.users import populate_test_auth_users
from tests.populate.utils import (
    REAL_TOURNAMENT_USERS,
    fetch_discord_avatars_for_users,
    get_or_create_demo_user,
)


def _no_network(*args: object, **kwargs: object) -> None:
    raise AssertionError("populate reached the network")


@override_settings(DEBUG=True, DISCORD_BOT_TOKEN=None)
@patch("requests.sessions.Session.request", _no_network)
class CommittedAvatarPopulateTest(TestCase):
    def setUp(self) -> None:
        patcher = patch.object(populate_utils, "_discord_avatar_cache", None)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_auth_users_get_committed_avatar(self) -> None:
        populate_test_auth_users()
        admin = CustomUser.objects.get(pk=ADMIN_USER.pk)
        self.assertIsNotNone(ADMIN_USER.avatar)
        self.assertEqual(admin.avatar, ADMIN_USER.avatar)

    def test_demo_user_gets_committed_avatar(self) -> None:
        username = "clarexlauda"
        user = get_or_create_demo_user(username, REAL_TOURNAMENT_USERS[username])
        self.assertEqual(user.avatar, TOURNAMENT_USERS[username].avatar)
        self.assertEqual(
            CustomUser.objects.get(pk=user.pk).avatar,
            DISCORD_AVATARS[TOURNAMENT_USERS[username].discord_id or ""],
        )

    def test_live_fetch_without_avatar_keeps_committed_hash(self) -> None:
        username = "heffdawgz"
        user = get_or_create_demo_user(username, REAL_TOURNAMENT_USERS[username])
        with patch.object(populate_utils, "_discord_avatar_cache", {"1": "other"}):
            fetch_discord_avatars_for_users([user])
        self.assertEqual(
            CustomUser.objects.get(pk=user.pk).avatar, TOURNAMENT_USERS[username].avatar
        )


class RefreshAvatarsTest(TestCase):
    def test_real_ids_skip_synthetic_test_users(self) -> None:
        ids = real_test_discord_ids()
        self.assertIn(ADMIN_USER.discord_id, ids)
        self.assertIn(TOURNAMENT_USERS["tornope"].discord_id, ids)
        self.assertFalse([i for i in ids if "000000" in i])

    def test_committed_ids_are_real_test_users(self) -> None:
        self.assertLessEqual(set(DISCORD_AVATARS), set(real_test_discord_ids()))

    def test_rendered_module_round_trips(self) -> None:
        for mapping in ({"20": "b", "3": "a_c"}, {}):
            assign = ast.parse(render_avatars_module(mapping)).body[-1]
            assert isinstance(assign, ast.AnnAssign) and assign.value is not None
            self.assertEqual(ast.literal_eval(assign.value), mapping)

    def test_failed_fetch_keeps_committed_hash(self) -> None:
        kept = next(iter(DISCORD_AVATARS))

        def fake_fetch(session: object, discord_id: str, token: str) -> str | None:
            if discord_id == kept:
                raise AvatarFetchError("boom")
            return None

        with TemporaryDirectory() as tmp:
            out = Path(tmp) / "discord_avatars.py"
            with (
                patch.object(avatars_module, "fetch_avatar_hash", fake_fetch),
                patch.object(avatars_module, "AVATARS_FILE", out),
            ):
                avatars, missing, failed = refresh_committed_avatars("token")
            self.assertEqual(out.read_text(), render_avatars_module(avatars))
        self.assertEqual(avatars, {kept: DISCORD_AVATARS[kept]})
        self.assertEqual(failed, [kept])
        self.assertNotIn(kept, missing)
