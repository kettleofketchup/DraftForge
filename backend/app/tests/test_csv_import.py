"""Tests for CSV import endpoints."""

from typing import Any

from django.test import TestCase, TransactionTestCase
from django.utils import timezone
from rest_framework.test import APIClient

from app.models import CustomUser, GameType, PositionsModel
from events.models import Event
from events.services import create_tournament_for_event
from org.mmr import org_mmr_for
from org.models import Organization, OrgUser, OrgUserGameMmr
from tests.populate.utils import ensure_org_user
from user.tests.test_cacheops_integration import _redis_reachable


class OrgCSVImportTest(TestCase):
    """Test POST /api/organizations/{id}/import-csv/"""

    def setUp(self):
        pos = PositionsModel.objects.create()
        self.admin = CustomUser.objects.create_user(
            username="admin", password="pass", positions=pos
        )
        self.org = Organization.objects.create(name="Test Org", owner=self.admin)
        self.org.admins.add(self.admin)
        self.client = APIClient()
        self.client.force_authenticate(self.admin)
        self.url = f"/api/organizations/{self.org.pk}/import-csv/"

    def test_import_creates_org_user_by_steam_id(self):
        """Row with steam_friend_id matching existing user creates OrgUser."""
        pos = PositionsModel.objects.create()
        user = CustomUser.objects.create_user(
            username="steamuser",
            password="pass",
            positions=pos,
            steamid=76561198012345678,
        )
        resp = self.client.post(
            self.url,
            {"rows": [{"steam_friend_id": "76561198012345678", "mmr": 5000}]},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["summary"]["added"], 1)
        OrgUser.objects.get(user=user, organization=self.org)
        self.assertEqual(org_mmr_for(self.org.pk, user.pk, GameType.DOTA2), 5000)

    def test_import_creates_stub_user_when_no_match(self):
        """Row with unknown steam_friend_id creates a stub user + OrgUser."""
        resp = self.client.post(
            self.url,
            {"rows": [{"steam_friend_id": "76561198099999999", "mmr": 3000}]},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["summary"]["created"], 1)
        self.assertEqual(resp.data["summary"]["added"], 1)
        user = CustomUser.objects.get(steamid=76561198099999999)
        OrgUser.objects.get(user=user, organization=self.org)
        self.assertEqual(org_mmr_for(self.org.pk, user.pk, GameType.DOTA2), 3000)

    def test_import_by_discord_id(self):
        """Row with discord_id matching existing user creates OrgUser."""
        pos = PositionsModel.objects.create()
        user = CustomUser.objects.create_user(
            username="discorduser",
            password="pass",
            positions=pos,
            discordId="123456789012345678",
        )
        resp = self.client.post(
            self.url,
            {"rows": [{"discord_id": "123456789012345678", "mmr": 4000}]},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["summary"]["added"], 1)
        OrgUser.objects.get(user=user, organization=self.org)
        self.assertEqual(org_mmr_for(self.org.pk, user.pk, GameType.DOTA2), 4000)

    def test_import_skips_existing_member(self):
        """Row matching a user already in the org is skipped."""
        pos = PositionsModel.objects.create()
        user = CustomUser.objects.create_user(
            username="existing",
            password="pass",
            positions=pos,
            steamid=76561198011111111,
        )
        ensure_org_user(user, self.org, mmr=1000)
        resp = self.client.post(
            self.url,
            {"rows": [{"steam_friend_id": "76561198011111111", "mmr": 2000}]},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["summary"]["skipped"], 1)
        # MMR should NOT be updated for skipped users
        OrgUser.objects.get(user=user, organization=self.org)
        self.assertEqual(org_mmr_for(self.org.pk, user.pk, GameType.DOTA2), 1000)

    def test_import_row_with_no_identifier_errors(self):
        """Row without steam_friend_id or discord_id reports error."""
        resp = self.client.post(self.url, {"rows": [{"mmr": 5000}]}, format="json")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["summary"]["errors"], 1)
        self.assertIn("No identifier", resp.data["results"][0]["reason"])

    def test_import_conflict_detection(self):
        """Row with steam + discord where existing user has different discord is an error."""
        pos = PositionsModel.objects.create()
        CustomUser.objects.create_user(
            username="conflictuser",
            password="pass",
            positions=pos,
            steamid=76561198022222222,
            discordId="999999999999999999",
        )
        resp = self.client.post(
            self.url,
            {
                "rows": [
                    {
                        "steam_friend_id": "76561198022222222",
                        "discord_id": "111111111111111111",
                        "mmr": 4000,
                    }
                ]
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["summary"]["errors"], 1)
        self.assertEqual(resp.data["summary"]["added"], 0)
        result = resp.data["results"][0]
        self.assertEqual(result["status"], "error")
        self.assertIn("different Discord account", result["reason"])
        self.assertIn("conflict_users", result)

    def _conflict_reason(self, row: dict) -> str:
        resp = self.client.post(self.url, {"rows": [row]}, format="json")
        self.assertEqual(resp.status_code, 200)
        result = resp.data["results"][0]
        self.assertEqual(result["status"], "error")
        return result["reason"]

    def test_conflict_names_use_discord_global_name(self) -> None:
        pos = PositionsModel.objects.create()
        CustomUser.objects.create_user(
            username="steamside",
            password="pass",
            positions=pos,
            steamid=76561198033333333,
            discordNickname="Gwaihir",
        )
        CustomUser.objects.create_user(
            username="discordside",
            password="pass",
            positions=PositionsModel.objects.create(),
            discordId="222222222222222222",
            discordNickname="Windlord",
        )
        reason = self._conflict_reason(
            {
                "steam_friend_id": "76561198033333333",
                "discord_id": "222222222222222222",
            }
        )
        self.assertEqual(
            reason,
            "Steam ID and Discord ID belong to different users: "
            "Gwaihir (Steam) vs Windlord (Discord)",
        )

    def test_linked_conflict_names_use_discord_global_name(self) -> None:
        CustomUser.objects.create_user(
            username="linked",
            password="pass",
            positions=PositionsModel.objects.create(),
            steamid=76561198044444444,
            discordId="333333333333333333",
            discordNickname="Landroval",
        )
        reason = self._conflict_reason(
            {
                "steam_friend_id": "76561198044444444",
                "discord_id": "444444444444444444",
            }
        )
        self.assertEqual(
            reason, "Landroval is already linked to a different Discord account"
        )

    def test_conflict_name_falls_back_to_user_pk(self) -> None:
        nameless = CustomUser.objects.create(
            username=None, steamid=76561198055555555, discordId="555555555555555555"
        )
        reason = self._conflict_reason(
            {
                "steam_friend_id": "76561198055555555",
                "discord_id": "666666666666666666",
            }
        )
        self.assertEqual(
            reason,
            f"User {nameless.pk} is already linked to a different Discord account",
        )

    def test_import_update_mmr_for_existing_member(self):
        """update_mmr=True updates MMR for existing org members."""
        pos = PositionsModel.objects.create()
        user = CustomUser.objects.create_user(
            username="existing",
            password="pass",
            positions=pos,
            steamid=76561198011111111,
        )
        ensure_org_user(user, self.org, mmr=1000)
        resp = self.client.post(
            self.url,
            {
                "rows": [{"steam_friend_id": "76561198011111111", "mmr": 5000}],
                "update_mmr": True,
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["summary"]["updated"], 1)
        self.assertEqual(resp.data["summary"]["skipped"], 0)
        result = resp.data["results"][0]
        self.assertEqual(result["status"], "updated")
        OrgUser.objects.get(user=user, organization=self.org)
        self.assertEqual(org_mmr_for(self.org.pk, user.pk, GameType.DOTA2), 5000)

    def test_import_update_mmr_false_skips(self):
        """update_mmr=False (default) skips existing members without updating MMR."""
        pos = PositionsModel.objects.create()
        user = CustomUser.objects.create_user(
            username="existing",
            password="pass",
            positions=pos,
            steamid=76561198011111111,
        )
        ensure_org_user(user, self.org, mmr=1000)
        resp = self.client.post(
            self.url,
            {
                "rows": [{"steam_friend_id": "76561198011111111", "mmr": 5000}],
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["summary"]["skipped"], 1)
        self.assertEqual(resp.data["summary"]["updated"], 0)
        OrgUser.objects.get(user=user, organization=self.org)
        self.assertEqual(
            org_mmr_for(self.org.pk, user.pk, GameType.DOTA2), 1000
        )  # Unchanged

    def test_import_requires_staff_access(self):
        """Non-staff/non-admin user gets 403."""
        pos = PositionsModel.objects.create()
        nonadmin = CustomUser.objects.create_user(
            username="nonadmin", password="pass", positions=pos
        )
        client = APIClient()
        client.force_authenticate(nonadmin)
        resp = client.post(
            self.url,
            {"rows": [{"steam_friend_id": "76561198099999999"}]},
            format="json",
        )
        self.assertEqual(resp.status_code, 403)

    def test_import_allowed_for_staff(self):
        """Org staff (not admin) can import."""
        pos = PositionsModel.objects.create()
        staff_user = CustomUser.objects.create_user(
            username="staff", password="pass", positions=pos
        )
        self.org.staff.add(staff_user)
        client = APIClient()
        client.force_authenticate(staff_user)
        resp = client.post(
            self.url,
            {"rows": [{"steam_friend_id": "76561198099999999", "mmr": 3000}]},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["summary"]["created"], 1)

    def test_import_rejects_too_many_rows(self):
        """More than MAX_ROWS returns 400."""
        rows = [{"steam_friend_id": str(76561198000000000 + i)} for i in range(501)]
        resp = self.client.post(self.url, {"rows": rows}, format="json")
        self.assertEqual(resp.status_code, 400)

    def test_import_rejects_non_list_rows(self):
        """Non-list rows returns 400."""
        resp = self.client.post(self.url, {"rows": "not a list"}, format="json")
        self.assertEqual(resp.status_code, 400)

    def test_import_empty_rows(self):
        """Empty rows list returns empty summary."""
        resp = self.client.post(self.url, {"rows": []}, format="json")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["summary"]["added"], 0)

    def test_import_creates_stub_user_from_discord_id_only(self):
        """Row with only discord_id and no match creates a stub user."""
        resp = self.client.post(
            self.url,
            {"rows": [{"discord_id": "555555555555555555", "mmr": 2500}]},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["summary"]["created"], 1)
        user = CustomUser.objects.get(discordId="555555555555555555")
        self.assertIsNotNone(user)
        OrgUser.objects.get(user=user, organization=self.org)
        self.assertEqual(org_mmr_for(self.org.pk, user.pk, GameType.DOTA2), 2500)

    def test_import_name_sets_nickname_on_new_stub(self):
        """CSV row with name sets nickname on newly created stub user."""
        resp = self.client.post(
            self.url,
            {"rows": [{"steam_friend_id": "76561198099999999", "name": "PlayerOne"}]},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["summary"]["created"], 1)
        user = CustomUser.objects.get(steamid=76561198099999999)
        self.assertEqual(user.nickname, "PlayerOne")

    def test_import_name_sets_nickname_on_existing_user_without_nickname(self):
        """CSV row with name sets nickname on existing user if nickname is empty."""
        pos = PositionsModel.objects.create()
        user = CustomUser.objects.create_user(
            username="nonickname",
            password="pass",
            positions=pos,
            steamid=76561198011111111,
        )
        self.assertFalse(user.nickname)  # no nickname set
        resp = self.client.post(
            self.url,
            {"rows": [{"steam_friend_id": "76561198011111111", "name": "GivenName"}]},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        user.refresh_from_db()
        self.assertEqual(user.nickname, "GivenName")


class OrgCSVImportDotaRowTest(TestCase):
    def setUp(self) -> None:
        self.admin = CustomUser.objects.create_user(
            username="row_admin", password="pass"
        )
        self.org = Organization.objects.create(name="Row Org", owner=self.admin)
        self.org.admins.add(self.admin)
        self.client = APIClient()
        self.client.force_authenticate(self.admin)
        self.url = f"/api/organizations/{self.org.pk}/import-csv/"
        self.user = CustomUser.objects.create_user(
            username="row_member", password="pass", steamid=76561198011111112
        )
        self.org_user = ensure_org_user(self.user, self.org, mmr=1000)

    def post(self, mmr: int) -> dict:
        resp = self.client.post(
            self.url,
            {
                "rows": [{"steam_friend_id": "76561198011111112", "mmr": mmr}],
                "update_mmr": True,
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        return resp.data

    def test_update_mmr_writes_dota_row(self) -> None:
        data = self.post(5000)
        self.assertEqual(data["summary"]["updated"], 1)
        self.assertEqual(
            OrgUserGameMmr.objects.get(
                org_user=self.org_user, game_type=GameType.DOTA2
            ).mmr,
            5000,
        )

    def test_update_mmr_out_of_range_is_row_error(self) -> None:
        data = self.post(25000)
        self.assertEqual(data["summary"]["errors"], 1)
        self.assertEqual(data["results"][0]["status"], "error")
        self.assertEqual(
            OrgUserGameMmr.objects.get(
                org_user=self.org_user, game_type=GameType.DOTA2
            ).mmr,
            1000,
        )


class OrgCSVImportGameTypeFixtures:
    client: APIClient
    admin: CustomUser
    org: Organization
    url: str
    member: CustomUser
    org_user: OrgUser

    STEAM_ID = 76561198011111113

    def build(self) -> None:
        self.admin = CustomUser.objects.create_user(
            username="gt_admin", password="pass"
        )
        self.org = Organization.objects.create(name="GT Org", owner=self.admin)
        self.org.admins.add(self.admin)
        self.client = APIClient()
        self.client.force_authenticate(self.admin)
        self.url = f"/api/organizations/{self.org.pk}/import-csv/"
        self.member = CustomUser.objects.create_user(
            username="gt_member", password="pass", steamid=self.STEAM_ID
        )
        self.org_user = ensure_org_user(
            self.member, self.org, mmr=1000, game_mmrs={GameType.DEADLOCK: 700}
        )

    def post(self, rows: list[dict[str, Any]], **extra: Any) -> Any:
        return self.client.post(
            self.url, {"rows": rows, "update_mmr": True, **extra}, format="json"
        )

    def rows_for(self, org_user: OrgUser) -> dict[int, int]:
        return dict(
            OrgUserGameMmr.objects.nocache()
            .filter(org_user=org_user)
            .values_list("game_type", "mmr")
        )


class OrgCSVImportGameTypeTest(OrgCSVImportGameTypeFixtures, TestCase):
    def setUp(self) -> None:
        self.build()

    def test_org_import_game_type_deadlock(self) -> None:
        resp = self.post(
            [
                {"steam_friend_id": str(self.STEAM_ID), "mmr": 2600},
                {"steam_friend_id": "76561198011111199", "mmr": 1800},
            ],
            game_type=2,
        )

        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.data["summary"]["updated"], 1)
        self.assertEqual(resp.data["summary"]["added"], 1)
        self.assertEqual(
            resp.data["results"][0]["reason"], "Deadlock MMR updated to 2600"
        )
        self.assertEqual(
            self.rows_for(self.org_user),
            {GameType.DOTA2: 1000, GameType.DEADLOCK: 2600},
        )
        new_ou = OrgUser.objects.get(
            user__steamid=76561198011111199, organization=self.org
        )
        self.assertEqual(self.rows_for(new_ou), {GameType.DEADLOCK: 1800})

    def test_org_import_default_dota(self) -> None:
        resp = self.post([{"steam_friend_id": str(self.STEAM_ID), "mmr": 4100}])

        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(
            resp.data["results"][0]["reason"], "Dota 2 MMR updated to 4100"
        )
        self.assertEqual(
            self.rows_for(self.org_user),
            {GameType.DOTA2: 4100, GameType.DEADLOCK: 700},
        )

    def test_org_import_out_of_range_row_error(self) -> None:
        resp = self.post(
            [
                {"steam_friend_id": str(self.STEAM_ID), "mmr": 25000},
                {"steam_friend_id": "76561198011111198", "mmr": 25000},
                {"steam_friend_id": "76561198011111197", "mmr": 3000},
            ],
            game_type=2,
        )

        self.assertEqual(resp.status_code, 200, resp.content)
        statuses = [r["status"] for r in resp.data["results"]]
        self.assertEqual(statuses, ["error", "error", "added"])
        self.assertEqual(
            self.rows_for(self.org_user),
            {GameType.DOTA2: 1000, GameType.DEADLOCK: 700},
        )
        self.assertFalse(
            OrgUser.objects.filter(user__steamid=76561198011111198).exists()
        )
        added = OrgUser.objects.get(user__steamid=76561198011111197)
        self.assertEqual(self.rows_for(added), {GameType.DEADLOCK: 3000})

    def test_org_import_invalid_game_type_400(self) -> None:
        for game_type in (99, "2", True, 0):
            with self.subTest(game_type=game_type):
                resp = self.post(
                    [{"steam_friend_id": str(self.STEAM_ID), "mmr": 2600}],
                    game_type=game_type,
                )
                self.assertEqual(resp.status_code, 400, resp.content)
                self.assertIn("error", resp.data)
        self.assertEqual(
            self.rows_for(self.org_user),
            {GameType.DOTA2: 1000, GameType.DEADLOCK: 700},
        )

    def test_org_import_messy_cells(self) -> None:
        cases: list[tuple[Any, str, int]] = [
            ("4,200", "error", 1000),
            (" 4200 ", "updated", 4200),
            ("4k", "error", 4200),
            ("", "skipped", 4200),
            ("-1", "error", 4200),
        ]
        for cell, status, dota in cases:
            with self.subTest(cell=cell):
                resp = self.post([{"steam_friend_id": str(self.STEAM_ID), "mmr": cell}])
                self.assertEqual(resp.status_code, 200, resp.content)
                self.assertEqual(resp.data["results"][0]["status"], status)
                self.assertEqual(self.rows_for(self.org_user)[GameType.DOTA2], dota)

    def test_org_import_new_member_negative_is_row_error(self) -> None:
        resp = self.post([{"steam_friend_id": "76561198011111196", "mmr": "-1"}])

        self.assertEqual(resp.data["results"][0]["status"], "error")
        self.assertFalse(
            OrgUser.objects.filter(user__steamid=76561198011111196).exists()
        )

    def test_org_import_without_update_mmr_leaves_existing(self) -> None:
        resp = self.client.post(
            self.url,
            {
                "rows": [{"steam_friend_id": str(self.STEAM_ID), "mmr": 2600}],
                "game_type": 2,
            },
            format="json",
        )

        self.assertEqual(resp.data["results"][0]["status"], "skipped")
        self.assertEqual(self.rows_for(self.org_user)[GameType.DEADLOCK], 700)

    def test_org_import_without_update_mmr_seeds_only_new_members(self) -> None:
        resp = self.client.post(
            self.url,
            {
                "rows": [
                    {"steam_friend_id": str(self.STEAM_ID), "mmr": 2600},
                    {"steam_friend_id": "76561198011111195", "mmr": 3100},
                ],
            },
            format="json",
        )

        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(
            [r["status"] for r in resp.data["results"]], ["skipped", "added"]
        )
        self.assertEqual(
            self.rows_for(self.org_user),
            {GameType.DOTA2: 1000, GameType.DEADLOCK: 700},
        )
        added = OrgUser.objects.get(user__steamid=76561198011111195)
        self.assertEqual(self.rows_for(added), {GameType.DOTA2: 3100})


class OrgCSVImportCacheTest(OrgCSVImportGameTypeFixtures, TransactionTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls._redis_ok = _redis_reachable()

    def setUp(self) -> None:
        if not self._redis_ok:
            self.fail("Cacheops Redis not reachable: cache tests cannot run")
        self.build()

    def test_org_import_invalidates_cache(self) -> None:
        event = Event.objects.create(
            name="CSV DL Night",
            organization=self.org,
            scheduled_at=timezone.now(),
            timezone="UTC",
            created_by=self.admin,
            tournament_name="CSV DL Cup",
            game_type=GameType.DEADLOCK,
        )
        tournament = create_tournament_for_event(event)
        self.assertIsNone(tournament.league_id)
        tournament.users.add(self.member)
        detail = f"/api/tournaments/{tournament.pk}/"

        def mmr() -> int:
            return self.client.get(detail).json()["_users"][str(self.member.pk)]["mmr"]

        self.assertEqual(mmr(), 700)

        resp = self.post(
            [{"steam_friend_id": str(self.STEAM_ID), "mmr": 2900}], game_type=2
        )
        self.assertEqual(resp.status_code, 200, resp.content)

        self.assertEqual(mmr(), 2900)
