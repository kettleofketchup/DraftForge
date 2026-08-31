"""Regression tests for the populate helpers' unique-column allocation.

A fresh populate creates ~100 mock users, each needing a UNIQUE
steam_account_id. Drawing that id at random without checking made the whole
run abort on a birthday collision — CI hit it on the herodraft job once a
models.py edit busted the test-db image hash and every job fell back to
`just db::populate::fresh`.
"""

from unittest.mock import patch

from django.test import TestCase

from app.models import CustomUser
from tests.populate.utils import create_user, unused_steam_account_id


def _member(discord_id: str, username: str) -> dict:
    return {
        "user": {
            "id": discord_id,
            "username": username,
            "avatar": None,
            "discriminator": "0",
            "global_name": username.title(),
        },
        "nick": None,
        "joined_at": "2024-01-01T00:00:00.000000+00:00",
    }


class UnusedSteamAccountIdTests(TestCase):
    def test_skips_ids_already_held(self) -> None:
        CustomUser.objects.create_user(
            username="holder", password="x", steam_account_id=4242
        )

        # First two draws collide with the existing row; the third is free.
        with patch(
            "tests.populate.utils.random.randint", side_effect=[4242, 4242, 99]
        ):
            self.assertEqual(unused_steam_account_id(), 99)

    def test_returns_first_free_draw(self) -> None:
        with patch("tests.populate.utils.random.randint", return_value=7):
            self.assertEqual(unused_steam_account_id(), 7)


def _draws(steam_ids: list[int]):
    """randint side effect: serve the steam ids in order, 0 for anything else.

    create_user also draws mmr and five position ratings; only the steam id
    draws matter here, and they are the ones bounded by 1..1_000_000.
    """
    queue = list(steam_ids)

    def _side_effect(low: int, high: int) -> int:
        if (low, high) == (1, 1_000_000):
            return queue.pop(0)
        return low

    return _side_effect


class CreateUserSteamIdTests(TestCase):
    def test_colliding_draw_does_not_abort_creation(self) -> None:
        first = create_user(_member("200000000000000001", "alpha"))
        self.assertIsNotNone(first.steam_account_id)

        # Force the next user's first draw onto the id alpha already holds.
        # Pre-fix this raised IntegrityError and killed the populate run.
        draws = [first.steam_account_id, first.steam_account_id + 1]
        with patch("tests.populate.utils.random.randint", side_effect=_draws(draws)):
            second = create_user(_member("200000000000000002", "beta"))

        self.assertEqual(second.steam_account_id, first.steam_account_id + 1)
        self.assertEqual(CustomUser.objects.filter(steam_account_id=None).count(), 0)
