"""Team management API (#545)."""

import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from cacheops import invalidate_model
from cacheops.conf import settings as cacheops_settings
from django.core.serializers.json import DjangoJSONEncoder
from django.db import connection, reset_queries, transaction
from django.test import (
    SimpleTestCase,
    TestCase,
    TransactionTestCase,
    override_settings,
)
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from app.draft_state import build_draft_state
from app.exception_handler import exception_handler
from app.functions.tournament import _serialize_tournament
from app.models import (
    CustomUser,
    DraftTeam,
    Game,
    HeroDraft,
    League,
    Organization,
    Team,
    TeamLog,
    TeamLogVia,
    Tournament,
)
from app.serializers import (
    HeroDraftSerializer,
    ManagedTeamSerializer,
    TeamActionRequestSerializer,
    TeamDeputyRequestSerializer,
    TeamLogSerializer,
    TeamRenameRequestSerializer,
    TeamSerializer,
    TeamSerializerSlim,
    TeamSubInRequestSerializer,
    TeamUserActionRequestSerializer,
    UserSerializer,
)
from app.services import team_management
from app.tests.test_draft_state_queries import make_fixture
from app.tests.test_team_management import TeamManagementFixture
from events.overrides import REASON_MAX_LENGTH, OverrideReasonRequired


class TeamActionRequestSerializerTests(TeamManagementFixture, TestCase):
    def user_body(self, **extra: Any) -> dict[str, Any]:
        return {"user_id": self.m1.pk, **extra}

    def test_reason_trimmed(self) -> None:
        body = TeamUserActionRequestSerializer(
            data=self.user_body(reason="  late swap  ")
        )
        self.assertTrue(body.is_valid(), body.errors)
        self.assertEqual(body.validated_data["reason"], "late swap")
        self.assertEqual(body.validated_data["acknowledged_codes"], [])
        self.assertEqual(body.validated_data["user_id"], self.m1)

    def test_missing_blank_whitespace_reason_is_field_error(self) -> None:
        cases: list[dict[str, Any]] = [
            self.user_body(),
            self.user_body(reason=""),
            self.user_body(reason="   "),
            self.user_body(reason=None),
        ]
        for data in cases:
            with self.subTest(data=data):
                body = TeamUserActionRequestSerializer(data=data)
                self.assertFalse(body.is_valid())
                self.assertIn("reason", body.errors)

    def test_reason_too_long_is_field_error(self) -> None:
        long_reason = "x" * (REASON_MAX_LENGTH + 1)
        for codes in ([], ["team_standin_cap"]):
            with self.subTest(codes=codes):
                body = TeamUserActionRequestSerializer(
                    data=self.user_body(reason=long_reason, acknowledged_codes=codes)
                )
                self.assertFalse(body.is_valid())
                self.assertIn("reason", body.errors)

    def test_blank_reason_with_codes_raises_override_reason_required(self) -> None:
        body = TeamUserActionRequestSerializer(
            data=self.user_body(reason=" ", acknowledged_codes=["team_standin_cap"])
        )
        with self.assertRaises(OverrideReasonRequired):
            body.is_valid(raise_exception=True)

    def test_base_serializer_has_reason_and_codes_only(self) -> None:
        body = TeamActionRequestSerializer(
            data={"reason": "r", "acknowledged_codes": ["team_standin_cap"]}
        )
        self.assertTrue(body.is_valid(), body.errors)
        self.assertEqual(
            dict(body.validated_data),
            {"reason": "r", "acknowledged_codes": ["team_standin_cap"]},
        )

    def test_unknown_user_id_is_field_error(self) -> None:
        for user_id in (999999, "abc"):
            with self.subTest(user_id=user_id):
                body = TeamUserActionRequestSerializer(
                    data={"user_id": user_id, "reason": "r"}
                )
                self.assertFalse(body.is_valid())
                self.assertIn("user_id", body.errors)

    def test_acknowledged_codes_must_be_list(self) -> None:
        too_many = [f"code_{i}" for i in range(101)]
        for codes in ("team_standin_cap", too_many):
            with self.subTest(codes=type(codes).__name__):
                body = TeamUserActionRequestSerializer(
                    data=self.user_body(reason="r", acknowledged_codes=codes)
                )
                self.assertFalse(body.is_valid())
                self.assertIn("acknowledged_codes", body.errors)

    def test_deputy_null_allowed_but_required(self) -> None:
        body = TeamDeputyRequestSerializer(data={"user_id": None, "reason": "r"})
        self.assertTrue(body.is_valid(), body.errors)
        self.assertIsNone(body.validated_data["user_id"])

        missing = TeamDeputyRequestSerializer(data={"reason": "r"})
        self.assertFalse(missing.is_valid())
        self.assertIn("user_id", missing.errors)

    def test_sub_in_replacing_optional(self) -> None:
        body = TeamSubInRequestSerializer(
            data={"standin_id": self.o1.pk, "reason": "r"}
        )
        self.assertTrue(body.is_valid(), body.errors)
        self.assertEqual(body.validated_data["standin_id"], self.o1)
        self.assertIsNone(body.validated_data["replacing_id"])

        both = TeamSubInRequestSerializer(
            data={"standin_id": self.o1.pk, "replacing_id": self.m2.pk, "reason": "r"}
        )
        self.assertTrue(both.is_valid(), both.errors)
        self.assertEqual(both.validated_data["replacing_id"], self.m2)

        missing = TeamSubInRequestSerializer(data={"reason": "r"})
        self.assertFalse(missing.is_valid())
        self.assertIn("standin_id", missing.errors)

    def test_rename_blank_name_reaches_service(self) -> None:
        for name in ("", "   ", "  padded  "):
            with self.subTest(name=name):
                body = TeamRenameRequestSerializer(data={"name": name, "reason": "r"})
                self.assertTrue(body.is_valid(), body.errors)
                self.assertEqual(body.validated_data["name"], name)


def _dumps(data: object) -> str:
    return json.dumps(data, cls=DjangoJSONEncoder)


def _count_queries(fn: Callable[[], object]) -> int:
    reset_queries()
    with CaptureQueriesContext(connection) as ctx:
        fn()
    return len(ctx.captured_queries)


TEAM_LOG_KEYS: frozenset[str] = frozenset(
    {
        "id",
        "action",
        "via",
        "actor",
        "target",
        "reason",
        "override_rules",
        "details",
        "team_name",
        "team_id",
        "created_at",
    }
)


class ResponseSerializerTests(TeamManagementFixture, TestCase):
    def test_left_members_are_user_objects(self) -> None:
        self.team.left_members.add(self.m2)
        rows = ManagedTeamSerializer(self.refresh(self.team)).data["left_members"]
        self.assertEqual(rows[0]["pk"], self.m2.pk)
        self.assertIn("username", rows[0])

    def test_leadership_problems_empty_when_healthy(self) -> None:
        data = ManagedTeamSerializer(self.refresh(self.team)).data
        self.assertEqual(data["leadership_problems"], [])

    def test_leadership_problems_ghost_captain(self) -> None:
        team = self.make_ghost_captain(self.team, self.outsider)
        self.assertEqual(
            ManagedTeamSerializer(team).data["leadership_problems"],
            [
                {
                    "field": "captain",
                    "code": "captain_not_member",
                    "message": "Captain must be a member of the team.",
                }
            ],
        )

    def test_leadership_problems_deputy_is_captain(self) -> None:
        team = self.make_deputy_is_captain(self.team)
        rows = ManagedTeamSerializer(team).data["leadership_problems"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["field"], "deputy_captain")
        self.assertEqual(rows[0]["code"], "deputy_is_captain")

    def test_tournament_payload_has_leadership_problems(self) -> None:
        self.make_ghost_captain(self.team, self.outsider)
        resp = APIClient().get(reverse("tournaments-detail", args=[self.tournament.pk]))
        self.assertEqual(resp.status_code, 200)
        teams = {row["pk"]: row for row in resp.json()["teams"]}
        ghost = teams[self.team.pk]
        self.assertEqual(ghost["leadership_problems"][0]["code"], "captain_not_member")
        self.assertIn(self.m1.pk, ghost["members"])
        self.assertEqual(teams[self.other.pk]["leadership_problems"], [])

    def test_unchanged_payloads_have_no_new_keys(self) -> None:
        self.team.left_members.add(self.m2)
        team = self.refresh(self.team)
        self.assertNotIn("leadership_problems", TeamSerializer(team).data)
        self.assertEqual(TeamSerializer(team).data["left_members"], [self.m2.pk])
        self.assertNotIn("leadership_problems", TeamSerializerSlim(team).data)

        # CustomUser has no `teams` attribute, so UserSerializer skips that field.
        user_data = UserSerializer(self.m2).data
        self.assertNotIn("teams", user_data)
        self.assertNotIn("leadership_problems", _dumps(user_data))

        fx = make_fixture(4, "lp4")
        state = build_draft_state(fx.draft.pk, fresh=True)
        self.assertNotIn("leadership_problems", _dumps(state))

        game = Game.objects.create(
            tournament=self.tournament, radiant_team=self.team, dire_team=self.other
        )
        draft = HeroDraft.objects.create(game=game)
        DraftTeam.objects.create(
            draft=draft, tournament_team=self.team, is_first_pick=True
        )
        DraftTeam.objects.create(draft=draft, tournament_team=self.other)
        payload = HeroDraftSerializer(draft).data
        self.assertNotIn("leadership_problems", _dumps(payload))

    def test_team_log_serializer_shape(self) -> None:
        team_management.rename(
            self.team, "New", actor=self.actor, via=TeamLogVia.WEB, reason="typo"
        )
        row = TeamLogSerializer(TeamLog.objects.get(team_snapshot_id=self.team.pk)).data
        self.assertEqual(set(row), TEAM_LOG_KEYS)
        self.assertEqual(row["actor"]["pk"], self.actor.pk)
        self.assertIn("username", row["actor"])
        self.assertEqual(row["team_id"], self.team.pk)
        self.assertEqual(row["reason"], "typo")
        self.assertEqual(row["action"], "rename")
        self.assertEqual(row["via"], "web")
        self.assertIsNone(row["target"])


@override_settings(CACHEOPS_ENABLED=False)
class TournamentLeadershipQueryTests(TeamManagementFixture, TestCase):
    def tournament_with_teams(self, count: int, prefix: str) -> Tournament:
        tournament = Tournament.objects.create(
            name=f"{prefix} cup", date_played=timezone.now(), league=self.league
        )
        for i in range(count):
            captain = self.make_user(f"{prefix}_c{i}")
            member = self.make_user(f"{prefix}_m{i}")
            tournament.users.add(captain, member)
            team = Team.objects.create(
                tournament=tournament, name=f"{prefix} {i}", captain=captain
            )
            team.members.add(captain, member)
        # A ghost captain on the first team exercises the problem path too.
        first = tournament.teams.order_by("pk").first()
        Team.objects.filter(pk=first.pk).update(captain=self.outsider)
        return tournament

    def test_tournament_retrieve_queries_flat(self) -> None:
        small = self.tournament_with_teams(1, "q1")
        large = self.tournament_with_teams(3, "q3")
        client = APIClient()

        def retrieve(t: Tournament) -> None:
            resp = client.get(reverse("tournaments-detail", args=[t.pk]))
            self.assertEqual(resp.status_code, 200)

        retrieve_counts = [
            _count_queries(lambda t=t: retrieve(t)) for t in (small, large)
        ]
        self.assertEqual(retrieve_counts[0], retrieve_counts[1])

        serialize_counts = [
            _count_queries(
                lambda t=t: _serialize_tournament(
                    Tournament.objects.nocache().get(pk=t.pk)
                )
            )
            for t in (small, large)
        ]
        self.assertEqual(serialize_counts[0], serialize_counts[1])
        payload = _serialize_tournament(large)
        self.assertTrue(all("leadership_problems" in t for t in payload["teams"]))


class ExceptionHandlerTests(SimpleTestCase):
    def test_team_management_error_rendered(self) -> None:
        exc = team_management.TeamManagementError("not_member", "X is not on the team.")
        response = exception_handler(exc, {})
        self.assertIsNotNone(response)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.data, {"code": "not_member", "detail": "X is not on the team."}
        )


def action_url(team_pk: int | str, path: str) -> str:
    return f"/api/teams/{team_pk}/{path}/"


@dataclass(frozen=True)
class ActionCase:
    url: str
    prepare: Callable[[Any], dict[str, Any]]


ACTION_CASES: list[ActionCase] = [
    ActionCase("set-captain", lambda t: {"user_id": t.m1.pk, "reason": "matrix check"}),
    ActionCase("set-deputy", lambda t: {"user_id": t.m1.pk, "reason": "matrix check"}),
    ActionCase("rename", lambda t: {"name": "Matrix Name", "reason": "matrix check"}),
]


class TeamApiFixture(TeamManagementFixture):
    def setUp(self) -> None:
        super().setUp()
        self.site_staff = self.make_user("api_site_staff")
        self.site_staff.is_staff = True
        self.site_staff.save()
        self.org_staff = self.make_user("api_org_staff")
        self.org.staff.add(self.org_staff)
        self.league_staff = self.make_user("api_league_staff")
        self.league.staff.add(self.league_staff)
        self.league_admin = self.make_user("api_league_admin")
        self.league.admins.add(self.league_admin)

    def client_for(self, user: CustomUser | None) -> APIClient:
        client = APIClient()
        if user is not None:
            client.force_authenticate(user)
        return client

    def post(
        self,
        path: str,
        body: dict[str, Any],
        user: CustomUser | None = None,
        team_pk: int | str | None = None,
    ) -> Any:
        client = self.client_for(self.site_staff if user is None else user)
        pk = self.team.pk if team_pk is None else team_pk
        return client.post(action_url(pk, path), body, format="json")

    def log_count(self) -> int:
        return TeamLog.objects.filter(team_snapshot_id=self.team.pk).count()

    def other_org_tournament(self) -> Tournament:
        org = Organization.objects.create(name="Elsewhere Org")
        league = League.objects.create(
            organization=org, name="Elsewhere League", steam_league_id=92002
        )
        return Tournament.objects.create(
            name="Elsewhere Cup", date_played=timezone.now(), league=league
        )


class TeamActionPermissionTests(TeamApiFixture, TestCase):
    def test_permission_matrix(self) -> None:
        allowed = {
            "site_staff": self.site_staff,
            "org_staff": self.org_staff,
            "league_staff": self.league_staff,
            "league_admin": self.league_admin,
        }
        denied = {"captain": self.c, "outsider": self.outsider}
        roles: list[tuple[str, CustomUser | None, int]] = [
            *((name, user, 200) for name, user in allowed.items()),
            *((name, user, 403) for name, user in denied.items()),
            ("anonymous", None, 401),
        ]
        for role, user, expected in roles:
            for case in ACTION_CASES:
                with self.subTest(role=role, action=case.url), transaction.atomic():
                    body = case.prepare(self)
                    resp = self.client_for(user).post(
                        action_url(self.team.pk, case.url), body, format="json"
                    )
                    self.assertEqual(resp.status_code, expected, resp.content)
                    if expected == 200:
                        self.assertIs(resp.json()["can_manage_team"], True)
                    elif expected == 403:
                        self.assertEqual(resp.json()["code"], "not_permitted")
                    else:
                        self.assertIn("WWW-Authenticate", resp)
                    transaction.set_rollback(True)

    def test_url_names_reverse(self) -> None:
        for name, path in (
            ("teams-set-captain", "set-captain"),
            ("teams-set-deputy", "set-deputy"),
            ("teams-rename", "rename"),
        ):
            with self.subTest(name=name):
                self.assertEqual(
                    reverse(name, args=[self.team.pk]), action_url(self.team.pk, path)
                )

    def test_tournamentless_team_actions_forbidden_for_site_staff(self) -> None:
        loose = Team.objects.create(tournament=None, name="Loose", captain=self.m1)
        loose.members.add(self.m1)
        resp = self.post(
            "rename", {"name": "Still Loose", "reason": "tidy"}, team_pk=loose.pk
        )
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.json()["code"], "not_permitted")

    def test_legacy_patch_denial_body_unchanged(self) -> None:
        resp = self.client_for(self.outsider).patch(
            f"/api/teams/{self.team.pk}/", {"name": "Nope"}, format="json"
        )
        self.assertEqual(resp.status_code, 403)
        self.assertNotIn("code", resp.json())

    def test_permission_uses_current_tournament(self) -> None:
        Team.objects.filter(pk=self.team.pk).update(
            tournament=self.other_org_tournament()
        )
        before = self.log_count()
        resp = self.post(
            "rename", {"name": "Moved", "reason": "move"}, user=self.league_admin
        )
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.json()["code"], "not_permitted")
        self.assertEqual(self.log_count(), before)


class LeadershipActionTests(TeamApiFixture, TestCase):
    def test_set_captain_happy_path(self) -> None:
        resp = self.post(
            "set-captain", {"user_id": self.m1.pk, "reason": "  late swap  "}
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        data = resp.json()
        self.assertEqual(data["captain"]["pk"], self.m1.pk)
        self.assertIs(data["can_manage_team"], True)
        self.assertIsInstance(data["left_members"], list)
        self.assertEqual(data["leadership_problems"], [])
        log = self.only_log()
        self.assertEqual(log.via, "web")
        self.assertEqual(log.actor_id, self.site_staff.pk)
        self.assertEqual(log.reason, "late swap")

    def test_set_captain_reseats_ghost(self) -> None:
        self.make_ghost_captain(self.team, self.outsider)
        resp = self.post(
            "set-captain", {"user_id": self.outsider.pk, "reason": "reseat"}
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.json()["leadership_problems"], [])

    def test_set_deputy_null_clears(self) -> None:
        resp = self.post("set-deputy", {"user_id": None, "reason": "clear"})
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertIsNone(resp.json()["deputy_captain"])

    def test_rename_blank_is_name_blank(self) -> None:
        for name in ("", "   "):
            with self.subTest(name=name):
                resp = self.post("rename", {"name": name, "reason": "tidy"})
                self.assertEqual(resp.status_code, 400)
                self.assertEqual(resp.json()["code"], "name_blank")
        resp = self.post("rename", {"name": self.team.name, "reason": "tidy"})
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.json()["code"], "name_unchanged")

    def test_missing_reason_400(self) -> None:
        resp = self.post("set-captain", {"user_id": self.m1.pk})
        self.assertEqual(resp.status_code, 400)
        self.assertIn("reason", resp.json())
        self.assertEqual(self.log_count(), 0)

    def test_service_refusal_coded(self) -> None:
        resp = self.post("set-deputy", {"user_id": self.outsider.pk, "reason": "x"})
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.json()["code"], "deputy_not_member")
        self.assertTrue(resp.json()["detail"])
        self.assertEqual(self.log_count(), 0)

    def test_bad_ids(self) -> None:
        for user_id in ("abc", 999999):
            with self.subTest(user_id=user_id):
                resp = self.post("set-captain", {"user_id": user_id, "reason": "x"})
                self.assertEqual(resp.status_code, 400)
                self.assertIn("user_id", resp.json())
        resp = self.post(
            "set-captain", {"user_id": self.m1.pk, "reason": "x"}, team_pk="abc"
        )
        self.assertEqual(resp.status_code, 404)
        resp = self.post("rename", {"name": "Gone", "reason": "x"}, team_pk=999999)
        self.assertEqual(resp.status_code, 404)
        resp = self.post(
            "set-captain", {"user_id": 999999, "reason": "x"}, user=self.outsider
        )
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.json()["code"], "not_permitted")

    def test_staff_acting_on_self(self) -> None:
        self.team.members.add(self.site_staff)
        resp = self.post("set-captain", {"user_id": self.site_staff.pk})
        self.assertEqual(resp.status_code, 400)
        self.assertIn("reason", resp.json())
        resp = self.post("set-captain", {"user_id": self.site_staff.pk, "reason": "me"})
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.json()["captain"]["pk"], self.site_staff.pk)


class CachedPermissionTests(TeamApiFixture, TransactionTestCase):
    def setUp(self) -> None:
        if not cacheops_settings.CACHEOPS_ENABLED:
            self.skipTest("cacheops disabled")
        super().setUp()
        invalidate_model(Team)
        invalidate_model(Tournament)

    def test_permission_ignores_cached_team(self) -> None:
        Team.objects.get(pk=self.team.pk)
        with self.assertNumQueries(0):
            Team.objects.get(pk=self.team.pk)
        elsewhere = self.other_org_tournament()
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE app_team SET tournament_id = %s WHERE id = %s",
                [elsewhere.pk, self.team.pk],
            )
        self.assertEqual(
            Team.objects.get(pk=self.team.pk).tournament_id, self.tournament.pk
        )
        before = self.log_count()
        resp = self.post(
            "rename", {"name": "Moved", "reason": "move"}, user=self.league_admin
        )
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(self.log_count(), before)
