import itertools
from typing import Any

from django.test import TestCase, TransactionTestCase
from django.utils import timezone
from rest_framework.response import Response
from rest_framework.test import APIClient

from app.models import CustomUser, Organization, OrgLog, PositionsModel, Tournament
from common.game import GameType
from events.models import Event
from events.services import create_tournament_for_event
from org.models import OrgUser, OrgUserGameMmr
from tests.populate.utils import ensure_org_user
from user.tests.test_cacheops_integration import _redis_reachable

_discord_ids = itertools.count(920_000_000_000_000_000)


def _make_user(name: str) -> CustomUser:
    return CustomUser.objects.create(
        username=name,
        discordId=str(next(_discord_ids)),
        positions=PositionsModel.objects.create(),
    )


def _rows(org_user: OrgUser) -> dict[int, int]:
    return dict(
        OrgUserGameMmr.objects.filter(org_user=org_user).values_list("game_type", "mmr")
    )


class PatchFixtures:
    client: APIClient
    owner: CustomUser
    org: Organization
    member: CustomUser
    org_user: OrgUser

    def build(self) -> None:
        self.owner = _make_user("pg_owner")
        self.org = Organization.objects.create(name="Patch Game Org", owner=self.owner)
        self.member = _make_user("pg_member")
        self.org_user = ensure_org_user(
            self.member, self.org, mmr=4000, game_mmrs={GameType.DEADLOCK: 2500}
        )
        OrgUser.objects.filter(pk=self.org_user.pk).update(
            has_active_dota_mmr=False, dota_mmr_last_verified=None
        )
        self.client = APIClient()
        self.client.force_authenticate(self.owner)

    def url(self, query: str = "") -> str:
        return f"/api/organizations/{self.org.pk}/users/{self.org_user.pk}/{query}"

    def patch(self, body: Any, query: str = "") -> Response:
        return self.client.patch(self.url(query), body, format="json")

    def flags(self) -> tuple[bool, object]:
        ou = OrgUser.objects.get(pk=self.org_user.pk)
        return ou.has_active_dota_mmr, ou.dota_mmr_last_verified

    def deadlock_tournament(self) -> Tournament:
        event = Event.objects.create(
            name="Patch DL Night",
            organization=self.org,
            scheduled_at=timezone.now(),
            timezone="UTC",
            created_by=self.owner,
            tournament_name="Patch DL Cup",
            game_type=GameType.DEADLOCK,
        )
        tournament = create_tournament_for_event(event)
        assert tournament.league_id is None
        tournament.users.add(self.member)
        return tournament


class OrgUserPatchGameMmrsTests(PatchFixtures, TestCase):
    def setUp(self) -> None:
        self.build()

    def test_patch_deadlock_only_leaves_dota(self) -> None:
        response = self.patch({"game_mmrs": {"2": 3000}})

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["game_mmrs"]["2"], 3000)
        self.assertEqual(_rows(self.org_user), {1: 4000, 2: 3000})
        self.assertEqual(self.flags(), (False, None))
        logs = OrgLog.objects.filter(organization=self.org, action="set_mmr")
        self.assertEqual(logs.count(), 1)
        log = logs.get()
        self.assertEqual(
            log.details,
            {"game_type": 2, "mmr": 3000, "source": "org_user_patch"},
        )
        self.assertEqual(log.target_user, self.member)
        self.assertEqual(log.actor, self.owner)

    def test_patch_clear_deletes_row(self) -> None:
        response = self.patch({"game_mmrs": {"2": None}})

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["game_mmrs"]["2"], 0)
        self.assertEqual(_rows(self.org_user), {1: 4000})

    def test_patch_dota_zero_sets_flags(self) -> None:
        response = self.patch({"game_mmrs": {"1": 0}})

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(_rows(self.org_user), {2: 2500})
        active, verified = self.flags()
        self.assertTrue(active)
        self.assertIsNotNone(verified)

    def test_patch_bare_mmr_writes_dota(self) -> None:
        response = self.patch({"mmr": 4100})

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(_rows(self.org_user), {1: 4100, 2: 2500})
        self.assertEqual(
            OrgUser.objects.values_list("mmr", flat=True).get(pk=self.org_user.pk),
            4100,
        )

    def test_patch_legacy_mmr_with_game(self) -> None:
        response = self.patch({"mmr": 3000, "mmr_game_type": 2})

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(_rows(self.org_user), {1: 4000, 2: 3000})
        self.assertEqual(self.flags(), (False, None))

    def test_patch_legacy_dota_mmr_sets_flags(self) -> None:
        response = self.patch({"mmr": 6500, "mmr_game_type": 1})

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(_rows(self.org_user), {1: 6500, 2: 2500})
        self.assertTrue(self.flags()[0])

    def test_patch_conflict_400(self) -> None:
        response = self.patch(
            {"mmr": 3000, "mmr_game_type": 2, "game_mmrs": {"2": 2000}}
        )

        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(_rows(self.org_user), {1: 4000, 2: 2500})

    def test_patch_same_value_mmr_and_game_mmrs_ok(self) -> None:
        response = self.patch(
            {"mmr": 3000, "mmr_game_type": 2, "game_mmrs": {"2": 3000, "1": 4100}}
        )

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(_rows(self.org_user), {1: 4100, 2: 3000})
        self.assertEqual(
            OrgLog.objects.filter(organization=self.org, action="set_mmr").count(), 2
        )

    def test_patch_deadlock_roundtrip_cannot_touch_dota(self) -> None:
        tournament = self.deadlock_tournament()
        payload = self.client.get(f"/api/tournaments/{tournament.pk}/").json()
        entry = payload["_users"][str(self.member.pk)]
        self.assertEqual((entry["mmr"], entry["mmr_game_type"]), (2500, 2))

        response = self.patch(
            {"mmr": entry["mmr"] + 100, "mmr_game_type": entry["mmr_game_type"]}
        )

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(_rows(self.org_user), {1: 4000, 2: 2600})

    def test_patch_response_context_game(self) -> None:
        response = self.patch({"game_mmrs": {"2": 3100}}, query="?game_type=2")

        self.assertEqual(response.status_code, 200, response.content)
        data = response.json()
        self.assertEqual((data["mmr"], data["mmr_game_type"]), (3100, 2))
        self.assertEqual(data["game_mmrs"], {"1": 4000, "2": 3100})

    def test_patch_response_defaults_to_dota(self) -> None:
        response = self.patch({"game_mmrs": {"2": 3100}})

        data = response.json()
        self.assertEqual((data["mmr"], data["mmr_game_type"]), (4000, 1))

    def test_patch_rejects_malformed(self) -> None:
        bodies: list[Any] = [
            {"game_mmrs": {"1": True}},
            {"game_mmrs": {"1": "4200"}},
            {"game_mmrs": {"1": 4200.5}},
            {"game_mmrs": {"abc": 1}},
            {"game_mmrs": {"\u00b2": 1}},
            {"game_mmrs": {"\u0662": 1}},
            {"game_mmrs": {"-1": 1}},
            {"game_mmrs": {"99": 1}},
            {"game_mmrs": {"1": 20001}},
            {"game_mmrs": {"1": -1}},
            {"game_mmrs": []},
            {"game_mmrs": "x"},
            {"mmr": "4200", "mmr_game_type": 1},
            {"mmr": 4200, "mmr_game_type": 99},
            {"mmr": 4200, "mmr_game_type": True},
            {"mmr": 4200, "mmr_game_type": "1"},
        ]
        for body in bodies:
            with self.subTest(body=body):
                response = self.patch(body)
                self.assertEqual(response.status_code, 400, response.content)
                self.assertIn("error", response.json())
                self.assertEqual(_rows(self.org_user), {1: 4000, 2: 2500})
                self.assertEqual(self.flags(), (False, None))
                self.assertFalse(
                    OrgLog.objects.filter(
                        organization=self.org, action="set_mmr"
                    ).exists()
                )

    def test_patch_unchanged_game_not_logged(self) -> None:
        response = self.patch({"game_mmrs": {"1": 4000, "2": 2500}})

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(_rows(self.org_user), {1: 4000, 2: 2500})
        self.assertFalse(
            OrgLog.objects.filter(organization=self.org, action="set_mmr").exists()
        )
        active, verified = self.flags()
        self.assertTrue(active)
        self.assertIsNotNone(verified)

    def test_patch_logs_only_changed_games(self) -> None:
        response = self.patch({"game_mmrs": {"1": 4000, "2": 2600}})

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(_rows(self.org_user), {1: 4000, 2: 2600})
        logs = OrgLog.objects.filter(organization=self.org, action="set_mmr")
        self.assertEqual(
            [log.details["game_type"] for log in logs], [GameType.DEADLOCK]
        )

    def test_patch_unchanged_deadlock_clear_of_missing_row(self) -> None:
        OrgUserGameMmr.objects.filter(
            org_user=self.org_user, game_type=GameType.DEADLOCK
        ).delete()
        response = self.patch({"game_mmrs": {"2": None}})

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(self.flags(), (False, None))
        self.assertFalse(
            OrgLog.objects.filter(organization=self.org, action="set_mmr").exists()
        )

    def test_patch_no_change_400(self) -> None:
        response = self.patch({})

        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(response.json(), {"error": "No valid fields to update"})

    def test_patch_empty_game_mmrs_is_no_change(self) -> None:
        response = self.patch({"game_mmrs": {}})

        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(response.json(), {"error": "No valid fields to update"})


class OrgUserPatchCacheTests(PatchFixtures, TransactionTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls._redis_ok = _redis_reachable()

    def setUp(self) -> None:
        if not self._redis_ok:
            self.fail("Cacheops Redis not reachable: cache tests cannot run")
        self.build()

    def _entry(self, tournament: Tournament) -> dict[str, Any]:
        response = self.client.get(f"/api/tournaments/{tournament.pk}/")
        self.assertEqual(response.status_code, 200)
        return response.json()["_users"][str(self.member.pk)]

    def test_patch_busts_tournament_detail(self) -> None:
        tournament = self.deadlock_tournament()
        self.assertEqual(self._entry(tournament)["mmr"], 2500)

        response = self.patch({"game_mmrs": {"2": 3300}})
        self.assertEqual(response.status_code, 200, response.content)

        self.assertEqual(self._entry(tournament)["mmr"], 3300)
