from io import StringIO
from typing import Any
from unittest.mock import MagicMock, patch

from django.core.management import call_command
from django.test import TestCase

from app.management.commands import sync_prod_users
from app.models import CustomUser, GameType
from org.models import Organization

USERS_GET = "app.management.commands.sync_prod_users.requests.get"


def fake_response(payload: Any) -> MagicMock:
    response = MagicMock()
    response.json.return_value = payload
    response.raise_for_status.return_value = None
    return response


def prod_user(pk: int, discord_id: str, mmr: int | None = None) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "pk": pk,
        "username": f"prod_{pk}",
        "nickname": f"Nick {pk}",
        "avatar": None,
        "discordId": discord_id,
        "discordNickname": None,
        "steam_account_id": 1000 + pk,
        "positions": {
            "carry": 1,
            "mid": 2,
            "offlane": 3,
            "soft_support": 4,
            "hard_support": 5,
        },
    }
    if mmr is not None:
        entry.update(mmr=mmr, mmr_game_type=GameType.DOTA2)
    return entry


class SyncProdUsersCommandTest(TestCase):
    def run_command(self, payload: list[dict[str, Any]]) -> str:
        out = StringIO()
        with patch(USERS_GET, return_value=fake_response(payload)) as get:
            call_command("sync_prod_users", stdout=out)
        get.assert_called_once()
        self.assertEqual(get.call_args.args[0], sync_prod_users.PROD_API_URL)
        return out.getvalue()

    def test_creates_new_user_from_prod_payload(self) -> None:
        payload = [
            {
                **prod_user(11, "d11"),
                "mmr": 4000,
                "is_staff": True,
                "is_superuser": False,
            }
        ]

        output = self.run_command(payload)

        self.assertNotIn("Skipped", output)
        user = CustomUser.objects.get(discordId="d11")
        self.assertEqual(user.username, "prod_11")
        self.assertEqual(user.nickname, "Nick 11")
        self.assertEqual(user.steam_account_id, 1011)
        self.assertTrue(user.is_staff)
        self.assertEqual(user.positions.offlane, 3)

    def test_org_owner_is_kept_and_updated_in_place(self) -> None:
        owner = CustomUser.objects.create(username="local_owner", discordId="d11")
        org = Organization.objects.create(name="Owned Org", owner=owner)
        CustomUser.objects.create(username="stale", discordId="d99")

        output = self.run_command([prod_user(11, "d11"), prod_user(12, "d12")])

        self.assertNotIn("Skipped", output)
        org.refresh_from_db()
        self.assertEqual(org.owner_id, owner.pk)
        owner.refresh_from_db()
        self.assertEqual(owner.username, "prod_11")
        self.assertEqual(owner.steam_account_id, 1011)
        self.assertEqual(owner.positions.offlane, 3)
        self.assertEqual(CustomUser.objects.filter(discordId="d11").count(), 1)
        self.assertTrue(CustomUser.objects.filter(discordId="d12").exists())
        self.assertFalse(CustomUser.objects.filter(discordId="d99").exists())

    def test_failed_user_does_not_roll_back_the_rest(self) -> None:
        clash = {**prod_user(12, "d12"), "username": "prod_11"}

        output = self.run_command([prod_user(11, "d11"), clash, prod_user(13, "d13")])

        self.assertIn("Skipped user prod_11", output)
        self.assertEqual(
            set(CustomUser.objects.values_list("discordId", flat=True)),
            {"d11", "d13"},
        )
