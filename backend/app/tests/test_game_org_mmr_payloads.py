import itertools
import json
from collections.abc import Callable

from cacheops.conf import settings as cacheops_settings
from cacheops.signals import cache_read
from django.db import connection
from django.test import TestCase, TransactionTestCase
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from app.functions.tournament import _serialize_tournament
from app.models import (
    CustomUser,
    League,
    PositionsModel,
    ProfileClaimRequest,
    Team,
    Tournament,
)
from app.schemas import TournamentUserSchema
from app.serializers import UserSerializer
from app.tests.test_game_org_mmr_drafts import GameOrgMmrFixtures
from common.game import GameType
from draft.models import Draft
from draft.services.team_state import build_draft_state
from draft.tests.team_fixtures import mid_draft_fixture
from org.mmr import game_mmrs_prefetch, set_org_mmr
from org.models import Organization, OrgUser
from org.serializers import OrgUserSerializer
from tests.populate.utils import ensure_org_user

_discord_ids = itertools.count(910_000_000_000_000_000)


def _make_user(name: str) -> CustomUser:
    return CustomUser.objects.create(
        username=name,
        discordId=str(next(_discord_ids)),
        positions=PositionsModel.objects.create(),
    )


class NumericDiscordFixtures(GameOrgMmrFixtures):
    def member(self, name: str, dota: int, deadlock: int) -> CustomUser:
        user = _make_user(name)
        ensure_org_user(
            user, self.org, mmr=dota, game_mmrs={GameType.DEADLOCK: deadlock}
        )
        return user


def _map_queries(ctx: CaptureQueriesContext) -> list[str]:
    return [
        q["sql"]
        for q in ctx.captured_queries
        if 'FROM "org_orgusergamemmr"' in q["sql"]
        and '"org_orgusergamemmr"."game_type" =' in q["sql"]
    ]


def _count(fn: Callable[[], object]) -> int:
    with CaptureQueriesContext(connection) as ctx:
        fn()
    return len(ctx.captured_queries)


class OrgUsersEndpointTests(TestCase):
    def setUp(self) -> None:
        self.owner = _make_user("ou_owner")
        self.org = Organization.objects.create(name="OU Org", owner=self.owner)
        self.client = APIClient()
        self.client.force_authenticate(self.owner)

    def _rows(self, org: Organization | None = None) -> dict[int, dict]:
        org = org or self.org
        response = self.client.get(f"/api/organizations/{org.pk}/users/")
        self.assertEqual(response.status_code, 200, response.content)
        return {row["pk"]: row for row in response.json()}

    def _add_members(self, start: int, count: int) -> None:
        for i in range(start, start + count):
            ensure_org_user(
                _make_user(f"ou_m{i}"),
                self.org,
                mmr=1000 + i,
                game_mmrs={GameType.DEADLOCK: 2000 + i},
            )

    def test_org_users_endpoint_shape(self) -> None:
        rated = _make_user("ou_rated")
        ensure_org_user(rated, self.org, mmr=4000, game_mmrs={GameType.DEADLOCK: 2500})
        blank = _make_user("ou_blank")
        ensure_org_user(blank, self.org)

        rows = self._rows()

        self.assertEqual(rows[rated.pk]["mmr"], 4000)
        self.assertEqual(rows[rated.pk]["mmr_game_type"], 1)
        self.assertEqual(rows[rated.pk]["game_mmrs"], {"1": 4000, "2": 2500})
        self.assertEqual(rows[blank.pk]["mmr"], 0)
        self.assertEqual(rows[blank.pk]["game_mmrs"], {"1": 0, "2": 0})

    def test_org_users_endpoint_constant_queries(self) -> None:
        self._add_members(0, 2)
        url = f"/api/organizations/{self.org.pk}/users/"
        two = _count(lambda: self.client.get(url))
        self._add_members(2, 4)
        six = _count(lambda: self.client.get(url))
        self.assertEqual(len(self._rows()), 6)
        self.assertEqual(two, six)

    def test_org_users_other_org_value_absent(self) -> None:
        other = Organization.objects.create(name="OU Other", owner=self.owner)
        user = _make_user("ou_both")
        ensure_org_user(user, self.org, mmr=4000, game_mmrs={GameType.DEADLOCK: 1111})
        ensure_org_user(user, other, mmr=3000, game_mmrs={GameType.DEADLOCK: 2222})

        self.assertEqual(self._rows()[user.pk]["game_mmrs"], {"1": 4000, "2": 1111})
        self.assertEqual(
            self._rows(other)[user.pk]["game_mmrs"], {"1": 3000, "2": 2222}
        )


class OrgUserSerializerContextTests(TestCase):
    def setUp(self) -> None:
        self.org = Organization.objects.create(name="Ctx Org")
        ensure_org_user(
            _make_user("ctx_u"),
            self.org,
            mmr=4100,
            game_mmrs={GameType.DEADLOCK: 2600},
        )
        self.org_user = OrgUser.objects.prefetch_related(
            game_mmrs_prefetch(fresh=False)
        ).get(organization=self.org)

    def test_org_user_serializer_context_game(self) -> None:
        deadlock = OrgUserSerializer(
            self.org_user, context={"game_type": GameType.DEADLOCK}
        ).data
        self.assertEqual((deadlock["mmr"], deadlock["mmr_game_type"]), (2600, 2))
        default = OrgUserSerializer(self.org_user).data
        self.assertEqual((default["mmr"], default["mmr_game_type"]), (4100, 1))
        self.assertNotIn("game_mmrs", default)

    def test_game_mmrs_only_when_requested(self) -> None:
        data = OrgUserSerializer(
            self.org_user, context={"include_game_mmrs": True}
        ).data
        self.assertEqual(data["game_mmrs"], {"1": 4100, "2": 2600})


class PublicPayloadGameTests(NumericDiscordFixtures, TestCase):
    def setUp(self) -> None:
        self.build_orgs()
        self.cap = self.member("pp_cap", 4000, 2500)
        self.mate = self.member("pp_mate", 3000, 1500)
        self.client = APIClient()
        self.payloads: dict[int, dict[str, object]] = {}
        for tournament in (self.dota_tournament, self.dl_tournament):
            tournament.users.add(self.cap, self.mate)
            team = self.team(tournament, f"pp {tournament.pk}", self.cap, [self.mate])
            draft = Draft.objects.get_or_create(tournament=tournament)[0]
            self.payloads[tournament.game_type] = {
                "tournament": self._get(f"/api/tournaments/{tournament.pk}/"),
                "team": self._get(f"/api/teams/{team.pk}/"),
                "draft": self._get(f"/api/drafts/{draft.pk}/"),
            }

    def _get(self, url: str) -> dict:
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    def _check(self, game: int, cap_mmr: int, mate_mmr: int) -> None:
        payloads = self.payloads[game]
        for name in ("tournament", "draft"):
            with self.subTest(payload=name):
                users = payloads[name]["_users"]
                self.assertEqual(users[str(self.cap.pk)]["mmr"], cap_mmr)
                self.assertEqual(users[str(self.cap.pk)]["mmr_game_type"], game)
                self.assertEqual(users[str(self.mate.pk)]["mmr"], mate_mmr)
                schema = TournamentUserSchema.model_validate(users[str(self.cap.pk)])
                self.assertEqual(schema.mmr_game_type, game)
        team = payloads["team"]
        self.assertEqual(team["captain"]["mmr"], cap_mmr)
        self.assertEqual(team["captain"]["mmr_game_type"], game)
        self.assertEqual(
            {m["pk"]: m["mmr"] for m in team["members"]},
            {self.cap.pk: cap_mmr, self.mate.pk: mate_mmr},
        )
        self.assertEqual(team["total_mmr"], cap_mmr + mate_mmr)
        for name, payload in payloads.items():
            with self.subTest(no_game_mmrs=name):
                self.assertNotIn("game_mmrs", json.dumps(payload))

    def test_tournament_payload_resolves_deadlock(self) -> None:
        self._check(GameType.DEADLOCK, 2500, 1500)

    def test_dota_tournament_payload_unchanged(self) -> None:
        self._check(GameType.DOTA2, 4000, 3000)


class TeamTotalsQueryTests(NumericDiscordFixtures, TestCase):
    def setUp(self) -> None:
        self.build_orgs()
        self.staff = CustomUser.objects.create_user(
            username="tt_staff", password="x", is_staff=True
        )
        self.client = APIClient()
        self.client.force_authenticate(self.staff)
        self.seq = 0

    def _add_team(self, tournament: Tournament, size: int) -> Team:
        self.seq += 1
        users = [
            self.member(f"tt_{self.seq}_{i}", 1000 + i, 3000 + i) for i in range(size)
        ]
        return self.team(tournament, f"tt team {self.seq}", users[0], users[1:])

    def _list(self) -> tuple[int, list[str], dict[int, int]]:
        with CaptureQueriesContext(connection) as ctx:
            response = self.client.get("/api/teams/")
        self.assertEqual(response.status_code, 200, response.content)
        totals = {row["pk"]: row["total_mmr"] for row in response.json()}
        return len(ctx.captured_queries), _map_queries(ctx), totals

    def test_team_list_total_mmr_constant_queries(self) -> None:
        small = [
            self._add_team(self.dota_tournament, 2),
            self._add_team(self.dl_tournament, 2),
        ]
        small_count, small_maps, small_totals = self._list()
        self.assertEqual(small_totals[small[0].pk], 1000 + 1001)
        self.assertEqual(small_totals[small[1].pk], 3000 + 3001)
        Team.objects.all().delete()

        large = [
            self._add_team(self.dota_tournament, 5),
            self._add_team(self.dl_tournament, 5),
        ]
        large_count, large_maps, large_totals = self._list()
        self.assertEqual(large_totals[large[0].pk], sum(range(1000, 1005)))
        self.assertEqual(large_totals[large[1].pk], sum(range(3000, 3005)))

        # One rating map per (org, game), whatever the team or member count.
        self.assertEqual(len(small_maps), 2)
        self.assertEqual(len(large_maps), 2)
        self.assertEqual(small_count, large_count)

    def test_team_list_map_queries_do_not_grow_with_teams(self) -> None:
        for _ in range(2):
            self._add_team(self.dota_tournament, 3)
            self._add_team(self.dl_tournament, 3)
        _, two_each, _ = self._list()
        for _ in range(2):
            self._add_team(self.dota_tournament, 3)
            self._add_team(self.dl_tournament, 3)
        _, four_each, totals = self._list()
        self.assertEqual(len(totals), 8)
        self.assertEqual((len(two_each), len(four_each)), (2, 2))


class UserSerializerTeamsTests(NumericDiscordFixtures, TestCase):
    # CustomUser has no `teams` relation (Team.members is `teams_as_member`), so
    # UserSerializer.teams is skipped by DRF and never computes team totals.
    def test_user_serializer_runs_no_rating_queries(self) -> None:
        self.build_orgs()
        player = self.member("us_player", 4000, 2000)
        self.team(self.dota_tournament, "us dota", player)
        self.team(self.dl_tournament, "us dl", player)
        user = CustomUser.objects.get(pk=player.pk)
        with CaptureQueriesContext(connection) as ctx:
            data = UserSerializer(user).data
        self.assertNotIn("teams", data)
        self.assertEqual(
            [q for q in ctx.captured_queries if "org_orgusergamemmr" in q["sql"]], []
        )


class ClaimRequestPayloadTests(TestCase):
    # One OrgUserGameMmr query per row.
    LIST_QUERIES_THREE_ROWS: int = 21

    def setUp(self) -> None:
        self.owner = _make_user("cl_owner")
        self.org = Organization.objects.create(name="Claim Org", owner=self.owner)
        self.org.admins.add(self.owner)
        self.client = APIClient()
        self.client.force_authenticate(self.owner)
        self.targets: list[CustomUser] = []
        for i in range(3):
            target = CustomUser.objects.create(username=f"cl_target{i}")
            ensure_org_user(
                target,
                self.org,
                mmr=4000 + i,
                game_mmrs={GameType.DEADLOCK: 2000 + i},
            )
            ProfileClaimRequest.objects.create(
                claimer=_make_user(f"cl_claimer{i}"),
                target_user=target,
                organization=self.org,
            )
            self.targets.append(target)

    def test_claim_request_target_game_mmrs(self) -> None:
        with self.assertNumQueries(self.LIST_QUERIES_THREE_ROWS):
            response = self.client.get(
                "/api/claim-requests/", {"organization": self.org.pk}
            )
        self.assertEqual(response.status_code, 200, response.content)
        rows = {row["target_user"]: row for row in response.json()}
        for i, target in enumerate(self.targets):
            self.assertEqual(rows[target.pk]["target_mmr"], 4000 + i)
            self.assertEqual(
                rows[target.pk]["target_game_mmrs"],
                {"1": 4000 + i, "2": 2000 + i},
            )


class OrgUserPatchResponseTests(TestCase):
    def setUp(self) -> None:
        self.owner = _make_user("pr_owner")
        self.org = Organization.objects.create(name="Patch Org", owner=self.owner)
        self.org_user = ensure_org_user(
            _make_user("pr_member"),
            self.org,
            mmr=4000,
            game_mmrs={GameType.DEADLOCK: 2500},
        )
        self.client = APIClient()
        self.client.force_authenticate(self.owner)

    def test_org_user_patch_response_is_post_write(self) -> None:
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.patch(
                f"/api/organizations/{self.org.pk}/users/{self.org_user.pk}/",
                {"game_mmrs": {"1": 6500}},
                format="json",
            )
        self.assertEqual(response.status_code, 200, response.content)
        data = response.json()
        self.assertEqual(data["mmr"], 6500)
        self.assertEqual(data["mmr_game_type"], 1)
        self.assertEqual(data["game_mmrs"], {"1": 6500, "2": 2500})


class DeadlockFreshReadTests(TransactionTestCase):
    def setUp(self) -> None:
        self.assertTrue(
            cacheops_settings.CACHEOPS_ENABLED,
            "cacheops disabled: fresh-read test cannot run",
        )

    def cached_reads(self, fn: Callable[[], object]) -> list[str]:
        reads: list[str] = []

        def record(sender: type | None, func: object = None, **kwargs: object) -> None:
            reads.append(getattr(sender, "__name__", None) or repr(func))

        cache_read.connect(record)
        try:
            fn()
        finally:
            cache_read.disconnect(record)
        return reads

    def test_fresh_payload_no_cached_reads_deadlock(self) -> None:
        fx = mid_draft_fixture(4, "frdl")
        Tournament.objects.filter(pk=fx.tournament.pk).update(
            game_type=GameType.DEADLOCK
        )
        fx.tournament.refresh_from_db()
        league: League = fx.tournament.league
        captain = fx.captains[0]
        org_user = OrgUser.objects.get(user=captain, organization=league.organization)
        set_org_mmr(org_user, GameType.DEADLOCK, 3456, mark_verified=False)
        build_draft_state(fx.draft.pk, fresh=False)

        states: list[dict] = []

        def serialize_all() -> None:
            states.append(build_draft_state(fx.draft.pk, fresh=True))
            _serialize_tournament(fx.tournament)

        self.assertEqual(self.cached_reads(serialize_all), [])
        entry = states[0]["_users"][str(captain.pk)]
        self.assertEqual(entry["mmr"], 3456)
        self.assertEqual(entry["mmr_game_type"], GameType.DEADLOCK)
        other = states[0]["_users"][str(fx.captains[1].pk)]
        self.assertEqual((other["mmr"], other["mmr_game_type"]), (0, 2))
