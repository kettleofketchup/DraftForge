"""Team management API (#545)."""

import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from unittest.mock import patch

from cacheops import invalidate_model
from cacheops.conf import settings as cacheops_settings
from django.core.serializers.json import DjangoJSONEncoder
from django.db import connection, reset_queries, transaction
from django.db.models import QuerySet
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
from structlog.testing import capture_logs

from app.exception_handler import exception_handler
from app.functions.tournament import serialize_tournament
from app.models import (
    CustomUser,
    Game,
    Team,
    TeamLog,
    TeamLogAction,
    TeamLogVia,
    Tournament,
)
from app.serializers import (
    ManagedTeamSerializer,
    TeamActionRequestSerializer,
    TeamDeputyRequestSerializer,
    TeamLogSerializer,
    TeamRenameRequestSerializer,
    TeamReplaceCaptainRequestSerializer,
    TeamSerializer,
    TeamSerializerSlim,
    TeamSubInRequestSerializer,
    TeamUserActionRequestSerializer,
    UserSerializer,
)
from app.services import team_management
from app.services.team_audit import log_snapshot_fields
from app.services.team_references import team_references, team_usage
from app.services.team_signals import TeamRosterChange, team_roster_changed
from app.tests.test_team_management import TeamManagementFixture, eliminate
from app.views_main import TeamView
from draft.models import DraftTeam, HeroDraft
from draft.serializers.hero import HeroDraftSerializer
from draft.services.team_state import build_draft_state
from draft.tests.team_fixtures import mid_draft_fixture
from events.models import EventTeam
from events.overrides import REASON_MAX_LENGTH, OverrideReasonRequired
from league.models import League
from org.models import Organization
from user.tests.test_cacheops_integration import _redis_reachable


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

        fx = mid_draft_fixture(4, "lp4")
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
                lambda t=t: serialize_tournament(
                    Tournament.objects.nocache().get(pk=t.pk)
                )
            )
            for t in (small, large)
        ]
        self.assertEqual(serialize_counts[0], serialize_counts[1])
        payload = serialize_tournament(large)
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


def prepare_restore(t: Any) -> dict[str, Any]:
    team_management.mark_dropout(
        t.team, t.m1, actor=t.actor, via=TeamLogVia.WEB, reason="prep"
    )
    return {"user_id": t.m1.pk, "reason": "matrix check"}


def prepare_standins_remove(t: Any) -> dict[str, Any]:
    team_management.add_standin(
        t.team, t.outsider, actor=t.actor, via=TeamLogVia.WEB, reason="prep"
    )
    return {"user_id": t.outsider.pk, "reason": "matrix check"}


def prepare_sub_in(t: Any) -> dict[str, Any]:
    team_management.add_standin(
        t.team, t.outsider, actor=t.actor, via=TeamLogVia.WEB, reason="prep"
    )
    return {
        "standin_id": t.outsider.pk,
        "replacing_id": t.m2.pk,
        "reason": "matrix check",
    }


def prepare_replace_captain(t: Any) -> dict[str, Any]:
    return {"user_id": t.m1.pk, "reason": "matrix check"}


ACTION_CASES: list[ActionCase] = [
    ActionCase("set-captain", lambda t: {"user_id": t.m1.pk, "reason": "matrix check"}),
    ActionCase("set-deputy", lambda t: {"user_id": t.m1.pk, "reason": "matrix check"}),
    ActionCase("rename", lambda t: {"name": "Matrix Name", "reason": "matrix check"}),
    ActionCase("dropout", lambda t: {"user_id": t.m1.pk, "reason": "matrix check"}),
    ActionCase("restore", prepare_restore),
    ActionCase(
        "standins", lambda t: {"user_id": t.outsider.pk, "reason": "matrix check"}
    ),
    ActionCase("standins/remove", prepare_standins_remove),
    ActionCase("sub-in", prepare_sub_in),
    ActionCase("replace-captain", prepare_replace_captain),
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
        for case in ACTION_CASES:
            with self.subTest(action=case.url), transaction.atomic():
                body = case.prepare(self)
                del body["reason"]
                before = self.log_count()
                resp = self.post(case.url, body)
                self.assertEqual(resp.status_code, 400, resp.content)
                self.assertEqual(resp.json(), {"reason": ["This field is required."]})
                self.assertEqual(self.log_count(), before)
                transaction.set_rollback(True)

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


class RosterActionTests(TeamApiFixture, TestCase):
    def user_ids(self, rows: list[dict[str, Any]]) -> list[int]:
        return [row["pk"] for row in rows]

    def logs(self) -> list[TeamLog]:
        return list(
            TeamLog.objects.filter(team_snapshot_id=self.team.pk).order_by("pk")
        )

    def assert_logged(self, resp: Any, reason: str) -> TeamLog:
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertIs(resp.json()["can_manage_team"], True)
        log = self.logs()[-1]
        self.assertEqual(log.via, "web")
        self.assertEqual(log.actor_id, self.site_staff.pk)
        self.assertEqual(log.reason, reason)
        return log

    def test_url_names_reverse(self) -> None:
        for name, path in (
            ("teams-dropout", "dropout"),
            ("teams-restore", "restore"),
            ("teams-standins", "standins"),
            ("teams-standins-remove", "standins/remove"),
            ("teams-sub-in", "sub-in"),
            ("teams-replace-captain", "replace-captain"),
        ):
            with self.subTest(name=name):
                self.assertEqual(
                    reverse(name, args=[self.team.pk]), action_url(self.team.pk, path)
                )

    def test_dropout_and_restore(self) -> None:
        resp = self.post("dropout", {"user_id": self.m1.pk, "reason": "no show"})
        self.assert_logged(resp, "no show")
        data = resp.json()
        self.assertIn(self.m1.pk, self.user_ids(data["left_members"]))
        self.assertIn("username", data["left_members"][0])
        self.assertNotIn(self.m1.pk, self.user_ids(data["members"]))

        resp = self.post("restore", {"user_id": self.m1.pk, "reason": "back"})
        self.assert_logged(resp, "back")
        data = resp.json()
        self.assertEqual(data["left_members"], [])
        self.assertIn(self.m1.pk, self.user_ids(data["members"]))
        self.assertEqual(self.log_count(), 2)

    def test_standins_add_and_remove(self) -> None:
        resp = self.post("standins", {"user_id": self.outsider.pk, "reason": "cover"})
        self.assert_logged(resp, "cover")
        self.assertIn(self.outsider.pk, self.user_ids(resp.json()["dropin_members"]))

        resp = self.post(
            "standins/remove", {"user_id": self.outsider.pk, "reason": "not needed"}
        )
        self.assert_logged(resp, "not needed")
        self.assertEqual(resp.json()["dropin_members"], [])
        self.assertEqual(self.log_count(), 2)

    def test_sub_in_swaps(self) -> None:
        self.post("standins", {"user_id": self.outsider.pk, "reason": "cover"})
        resp = self.post(
            "sub-in",
            {
                "standin_id": self.outsider.pk,
                "replacing_id": self.m2.pk,
                "reason": "swap",
            },
        )
        self.assert_logged(resp, "swap")
        data = resp.json()
        self.assertIn(self.outsider.pk, self.user_ids(data["members"]))
        self.assertNotIn(self.m2.pk, self.user_ids(data["members"]))
        self.assertIn(self.m2.pk, self.user_ids(data["left_members"]))
        self.assertEqual(data["dropin_members"], [])

    def test_dropout_last_member_refused(self) -> None:
        before = TeamLog.objects.count()
        resp = self.post(
            "dropout", {"user_id": self.o1.pk, "reason": "gone"}, team_pk=self.other.pk
        )
        self.assertEqual(resp.status_code, 400, resp.content)
        self.assertEqual(resp.json()["code"], "last_member")
        self.assertEqual(TeamLog.objects.count(), before)
        self.assertTrue(Team.objects.filter(pk=self.other.pk).exists())

    def fill_two_standins(self) -> None:
        for name in ("api_s0", "api_s1"):
            user = self.make_user(name)
            resp = self.post("standins", {"user_id": user.pk, "reason": "fill"})
            self.assertEqual(resp.status_code, 200, resp.content)

    def test_standin_cap_override_sequence(self) -> None:
        self.fill_two_standins()
        body = {"user_id": self.outsider.pk, "reason": "third stand-in"}

        resp = self.post("standins", {**body, "acknowledged_codes": []})
        self.assertEqual(resp.status_code, 409, resp.content)
        data = resp.json()
        self.assertEqual(data["code"], "override_required")
        self.assertEqual(data["violations"][0]["code"], "team_standin_cap")
        self.assertEqual(data["violations"][0]["rule"], "override-warning")
        self.assertEqual(self.log_count(), 2)

        resp = self.post(
            "standins", {**body, "acknowledged_codes": ["team_standin_cap"]}
        )
        log = self.assert_logged(resp, "third stand-in")
        self.assertIn("team_standin_cap", log.override_rules)
        self.assertEqual(self.log_count(), 3)

    def test_override_retry_blank_reason(self) -> None:
        self.fill_two_standins()
        resp = self.post(
            "standins",
            {
                "user_id": self.outsider.pk,
                "reason": " ",
                "acknowledged_codes": ["team_standin_cap"],
            },
        )
        self.assertEqual(resp.status_code, 400, resp.content)
        self.assertEqual(resp.json()["code"], "override_reason_required")
        self.assertEqual(self.log_count(), 2)

    def test_unraised_ack_codes_ignored(self) -> None:
        resp = self.post(
            "standins",
            {
                "user_id": self.outsider.pk,
                "reason": "cover",
                "acknowledged_codes": ["something_else"],
            },
        )
        log = self.assert_logged(resp, "cover")
        self.assertEqual(log.override_rules, [])

    def test_malformed_acknowledged_codes(self) -> None:
        resp = self.post(
            "standins",
            {
                "user_id": self.outsider.pk,
                "reason": "cover",
                "acknowledged_codes": "team_standin_cap",
            },
        )
        self.assertEqual(resp.status_code, 400, resp.content)
        self.assertIn("acknowledged_codes", resp.json())
        self.assertEqual(self.log_count(), 0)

    def test_eligibility_409(self) -> None:
        user = self.gate_event()
        resp = self.post("standins", {"user_id": user.pk, "reason": "gated"})
        self.assertEqual(resp.status_code, 409, resp.content)
        data = resp.json()
        self.assertEqual(data["code"], "override_required")
        codes = [v["code"] for v in data["violations"]]
        self.assertIn("below_min_mmr", codes)
        self.assertIn("steam_id_missing", codes)
        self.assertEqual(self.log_count(), 0)

    def test_double_submit(self) -> None:
        body = {"user_id": self.outsider.pk, "reason": "cover"}
        self.assertEqual(self.post("standins", body).status_code, 200)
        resp = self.post("standins", body)
        self.assertEqual(resp.status_code, 400, resp.content)
        self.assertEqual(resp.json()["code"], "already_on_team")
        self.assertEqual(
            TeamLog.objects.filter(
                team_snapshot_id=self.team.pk, target_user=self.outsider
            ).count(),
            1,
        )


class CachedPermissionTests(TeamApiFixture, TransactionTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls._redis_ok = _redis_reachable()

    def setUp(self) -> None:
        if not cacheops_settings.CACHEOPS_ENABLED:
            self.skipTest("cacheops disabled")
        if not self._redis_ok:
            self.skipTest("Cacheops Redis not reachable")
        super().setUp()
        for model in (Team, Tournament):
            invalidate_model(model)
            self.addCleanup(invalidate_model, model)

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
        self.assertEqual(resp.json()["code"], "not_permitted")
        self.assertEqual(self.log_count(), before)


class ReplaceCaptainApiTests(TeamApiFixture, TestCase):
    def user_ids(self, rows: list[dict[str, Any]]) -> list[int]:
        return [row["pk"] for row in rows]

    def replace(
        self, user: CustomUser, staff: CustomUser | None = None, **extra: Any
    ) -> Any:
        body = {"user_id": user.pk, "reason": "takeover", **extra}
        return self.post("replace-captain", body, user=staff)

    def replace_logs(self) -> list[TeamLog]:
        return list(
            TeamLog.objects.filter(
                team_snapshot_id=self.team.pk, action=TeamLogAction.REPLACE_CAPTAIN
            ).order_by("pk")
        )

    def test_serializer_defaults_mark_outgoing_dropout(self) -> None:
        body = TeamReplaceCaptainRequestSerializer(
            data={"user_id": self.m1.pk, "reason": "r"}
        )
        self.assertTrue(body.is_valid(), body.errors)
        self.assertIs(body.validated_data["mark_outgoing_dropout"], True)
        self.assertEqual(body.validated_data["user_id"], self.m1)

    def test_200_body_has_new_captain_left_members_other_teams(self) -> None:
        resp = self.replace(self.m1)
        self.assertEqual(resp.status_code, 200, resp.content)
        data = resp.json()
        self.assertEqual(data["captain"]["pk"], self.m1.pk)
        self.assertIn(self.c.pk, self.user_ids(data["left_members"]))
        self.assertIs(data["can_manage_team"], True)
        self.assertEqual(
            data["other_teams"],
            [
                {
                    "pk": self.other.pk,
                    "name": "Others",
                    "placement": None,
                    "member_pks": [self.o1.pk],
                    "dropin_pks": [],
                }
            ],
        )
        log = self.replace_logs()[-1]
        self.assertEqual(log.via, "web")
        self.assertEqual(log.actor_id, self.site_staff.pk)
        self.assertEqual(log.reason, "takeover")

    def test_default_marks_outgoing_dropout(self) -> None:
        data = self.replace(self.m1).json()
        self.assertNotIn(self.c.pk, self.user_ids(data["members"]))
        self.assertIn(self.c.pk, self.user_ids(data["left_members"]))

    def test_false_keeps_outgoing_member(self) -> None:
        resp = self.replace(self.m1, mark_outgoing_dropout=False)
        self.assertEqual(resp.status_code, 200, resp.content)
        data = resp.json()
        self.assertEqual(data["captain"]["pk"], self.m1.pk)
        self.assertIn(self.c.pk, self.user_ids(data["members"]))
        self.assertEqual(data["left_members"], [])

    def test_eliminated_team_captain_takes_over(self) -> None:
        eliminate(self.other, 3)
        resp = self.replace(self.o1)
        self.assertEqual(resp.status_code, 200, resp.content)
        data = resp.json()
        self.assertEqual(data["captain"]["pk"], self.o1.pk)
        self.assertEqual(data["other_teams"][0]["placement"], 3)
        other = Team.objects.nocache().get(pk=self.other.pk)
        self.assertEqual(other.captain_id, self.o1.pk)
        self.assertTrue(other.members.filter(pk=self.o1.pk).exists())

    def test_on_other_team_400(self) -> None:
        resp = self.replace(self.o1)
        self.assertEqual(resp.status_code, 400, resp.content)
        data = resp.json()
        self.assertEqual(data["code"], "on_other_team")
        self.assertIn("Others", data["detail"])
        self.assertEqual(self.log_count(), 0)
        self.assertEqual(
            Team.objects.nocache().get(pk=self.team.pk).captain_id, self.c.pk
        )

    def test_missing_reason_400(self) -> None:
        for reason in (None, "", "  "):
            with self.subTest(reason=reason):
                body: dict[str, Any] = {"user_id": self.m1.pk}
                if reason is not None:
                    body["reason"] = reason
                resp = self.post("replace-captain", body)
                self.assertEqual(resp.status_code, 400, resp.content)
                self.assertIn("reason", resp.json())
        self.assertEqual(self.log_count(), 0)

    def test_unknown_user_400(self) -> None:
        resp = self.post("replace-captain", {"user_id": 999999, "reason": "r"})
        self.assertEqual(resp.status_code, 400, resp.content)
        self.assertIn("user_id", resp.json())

    def test_non_bool_flag_400(self) -> None:
        resp = self.replace(self.m1, mark_outgoing_dropout="maybe")
        self.assertEqual(resp.status_code, 400, resp.content)
        self.assertIn("mark_outgoing_dropout", resp.json())
        self.assertEqual(self.log_count(), 0)

    def test_eligibility_409_then_acknowledged_200(self) -> None:
        user = self.gate_event()
        resp = self.replace(user)
        self.assertEqual(resp.status_code, 409, resp.content)
        data = resp.json()
        self.assertEqual(data["code"], "override_required")
        codes = [v["code"] for v in data["violations"]]
        self.assertIn("below_min_mmr", codes)
        self.assertEqual(self.log_count(), 0)

        resp = self.replace(user, acknowledged_codes=codes)
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.json()["captain"]["pk"], user.pk)
        log = self.replace_logs()[-1]
        self.assertIn("below_min_mmr", log.override_rules)

    def test_double_submit_same_user_already_captain(self) -> None:
        self.assertEqual(self.replace(self.m1).status_code, 200)
        resp = self.replace(self.m1)
        self.assertEqual(resp.status_code, 400, resp.content)
        self.assertEqual(resp.json()["code"], "already_captain")
        self.assertEqual(len(self.replace_logs()), 1)

    def test_two_staff_different_candidates(self) -> None:
        first = self.replace(self.m1, staff=self.site_staff)
        self.assertEqual(first.status_code, 200, first.content)
        second = self.replace(self.m2, staff=self.org_staff)
        self.assertEqual(second.status_code, 200, second.content)

        team = Team.objects.nocache().get(pk=self.team.pk)
        self.assertEqual(team.captain_id, self.m2.pk)
        left = set(team.left_members.values_list("pk", flat=True))
        self.assertEqual(left, {self.c.pk, self.m1.pk})
        members = set(team.members.values_list("pk", flat=True))
        self.assertIn(self.m2.pk, members)
        self.assertNotIn(self.m1.pk, members)
        logs = self.replace_logs()
        self.assertEqual(len(logs), 2)
        self.assertEqual(logs[0].details["replacing_user_id"], self.c.pk)
        self.assertEqual(logs[1].details["replacing_user_id"], self.m1.pk)
        self.assertEqual(logs[1].actor_id, self.org_staff.pk)


class CanManageTeamTests(TeamApiFixture, TestCase):
    def detail(self, user: CustomUser | None, team: Team | None = None) -> Any:
        pk = (self.team if team is None else team).pk
        resp = self.client_for(user).get(f"/api/teams/{pk}/")
        self.assertEqual(resp.status_code, 200, resp.content)
        return resp.json()

    def test_staff_true_random_false(self) -> None:
        self.assertIs(self.detail(self.league_admin)["can_manage_team"], True)
        self.assertIs(self.detail(self.site_staff)["can_manage_team"], True)
        self.assertIs(self.detail(self.outsider)["can_manage_team"], False)
        self.assertIs(self.detail(self.c)["can_manage_team"], False)
        self.assertIs(self.detail(None)["can_manage_team"], False)

    def test_tournamentless_team(self) -> None:
        loose = Team.objects.create(name="Loose", captain=self.o1)
        loose.members.add(self.o1)
        self.assertIs(self.detail(self.outsider, loose)["can_manage_team"], False)
        self.assertIs(self.detail(self.site_staff, loose)["can_manage_team"], False)

    def test_detail_after_action_has_new_roster_and_own_flag(self) -> None:
        self.detail(self.outsider)
        resp = self.post("set-captain", {"user_id": self.m1.pk, "reason": "swap"})
        self.assertEqual(resp.status_code, 200, resp.content)
        staff_view = self.detail(self.league_staff)
        self.assertEqual(staff_view["captain"]["pk"], self.m1.pk)
        self.assertIs(staff_view["can_manage_team"], True)
        outsider_view = self.detail(self.outsider)
        self.assertEqual(outsider_view["captain"]["pk"], self.m1.pk)
        self.assertIs(outsider_view["can_manage_team"], False)

    def test_retrieve_has_managed_fields(self) -> None:
        self.team.left_members.add(self.m2)
        data = self.detail(self.outsider)
        self.assertEqual(data["leadership_problems"], [])
        self.assertEqual(data["left_members"][0]["pk"], self.m2.pk)

    def test_manager_gets_scope_fields(self) -> None:
        self.other.dropin_members.add(self.outsider)
        data = self.detail(self.league_admin)
        self.assertEqual(data["organization_pk"], self.org.pk)
        self.assertEqual(data["league_pk"], self.league.pk)
        self.assertEqual(
            data["other_team_user_pks"], sorted([self.o1.pk, self.outsider.pk])
        )

    def test_viewer_gets_no_scope_fields(self) -> None:
        for user in (self.outsider, None):
            data = self.detail(user)
            for key in ("organization_pk", "league_pk", "other_team_user_pks"):
                self.assertNotIn(key, data)

    def test_scope_fields_fresh_after_other_team_changes(self) -> None:
        self.detail(self.league_admin)
        self.other.members.add(self.outsider)
        data = self.detail(self.league_admin)
        self.assertIn(self.outsider.pk, data["other_team_user_pks"])

    def test_action_response_has_scope_fields(self) -> None:
        resp = self.post("set-captain", {"user_id": self.m1.pk, "reason": "swap"})
        self.assertEqual(resp.status_code, 200, resp.content)
        data = resp.json()
        self.assertEqual(data["organization_pk"], self.org.pk)
        self.assertEqual(data["other_team_user_pks"], [self.o1.pk])

    def test_other_team_user_pks_excludes_placed_team(self) -> None:
        live = Team.objects.create(tournament=self.tournament, name="Live")
        live.members.add(self.outsider)
        self.other.dropin_members.add(self.m1)
        eliminate(self.other, 4)
        data = self.detail(self.league_admin)
        self.assertEqual(data["other_team_user_pks"], [self.outsider.pk])

    def test_other_teams_lists_live_and_placed_with_placement(self) -> None:
        zulu = Team.objects.create(tournament=self.tournament, name="Zulu")
        bravo = Team.objects.create(tournament=self.tournament, name="Bravo")
        charlie = Team.objects.create(tournament=self.tournament, name="Charlie")
        apex = Team.objects.create(tournament=self.tournament, name="Apex")
        zulu.members.add(self.outsider)
        bravo.dropin_members.add(self.m1)
        bravo.left_members.add(self.m2)
        eliminate(zulu, 2)
        eliminate(bravo, 2)
        eliminate(charlie, 1)
        elsewhere = Team.objects.create(
            tournament=self.other_org_tournament(), name="Aaa Elsewhere"
        )
        elsewhere.members.add(self.o1)

        rows = self.detail(self.league_admin)["other_teams"]
        self.assertEqual(
            [r["name"] for r in rows], ["Apex", "Others", "Charlie", "Bravo", "Zulu"]
        )
        by_name = {r["name"]: r for r in rows}
        self.assertEqual(
            by_name["Others"],
            {
                "pk": self.other.pk,
                "name": "Others",
                "placement": None,
                "member_pks": [self.o1.pk],
                "dropin_pks": [],
            },
        )
        self.assertEqual(by_name["Apex"]["pk"], apex.pk)
        self.assertEqual(by_name["Charlie"]["placement"], 1)
        self.assertEqual(by_name["Zulu"]["placement"], 2)
        self.assertEqual(by_name["Zulu"]["member_pks"], [self.outsider.pk])
        self.assertEqual(by_name["Bravo"]["member_pks"], [])
        self.assertEqual(by_name["Bravo"]["dropin_pks"], [self.m1.pk])

    def test_other_teams_absent_for_non_staff(self) -> None:
        for user in (self.outsider, self.c, None):
            with self.subTest(user=user):
                self.assertNotIn("other_teams", self.detail(user))


class CanManageTeamCacheTests(TeamApiFixture, TransactionTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls._redis_ok = _redis_reachable()

    def setUp(self) -> None:
        if not cacheops_settings.CACHEOPS_ENABLED:
            self.skipTest("cacheops disabled")
        if not self._redis_ok:
            self.skipTest("Cacheops Redis not reachable")
        super().setUp()
        invalidate_model(Team)
        self.addCleanup(invalidate_model, Team)

    def test_flag_is_per_viewer_on_cache_hit(self) -> None:
        url = f"/api/teams/{self.team.pk}/"
        with patch.object(
            ManagedTeamSerializer,
            "to_representation",
            autospec=True,
            side_effect=ManagedTeamSerializer.to_representation,
        ) as spy:
            flags = [
                self.client_for(user).get(url).json()["can_manage_team"]
                for user in (self.site_staff, self.outsider, None)
            ]
        self.assertEqual(flags, [True, False, False])
        self.assertEqual(spy.call_count, 1)


class TeamHistoryTests(TeamApiFixture, TestCase):
    def history(
        self,
        user: CustomUser | None = None,
        team_pk: int | str | None = None,
        query: str = "",
    ) -> Any:
        client = self.client_for(self.site_staff if user is None else user)
        pk = self.team.pk if team_pk is None else team_pk
        return client.get(f"/api/teams/{pk}/history/{query}")

    def rename_to(self, name: str) -> None:
        resp = self.post("rename", {"name": name, "reason": f"to {name}"})
        self.assertEqual(resp.status_code, 200, resp.content)

    def actions(self, resp: Any) -> list[str]:
        self.assertEqual(resp.status_code, 200, resp.content)
        return [row["action"] for row in resp.json()["results"]]

    def org_staff_of(self, tournament: Tournament) -> CustomUser:
        user = self.make_user(f"history_staff_{tournament.pk}")
        tournament.league.organization.staff.add(user)
        return user

    def test_url_name_reverses(self) -> None:
        self.assertEqual(
            reverse("teams-history", args=[self.team.pk]),
            action_url(self.team.pk, "history"),
        )

    def test_permission_matrix(self) -> None:
        self.rename_to("Matrix")
        roles: list[tuple[str, CustomUser | None, int]] = [
            ("site_staff", self.site_staff, 200),
            ("org_staff", self.org_staff, 200),
            ("league_staff", self.league_staff, 200),
            ("league_admin", self.league_admin, 200),
            ("captain", self.c, 403),
            ("outsider", self.outsider, 403),
        ]
        for role, user, expected in roles:
            with self.subTest(role=role):
                resp = self.history(user)
                self.assertEqual(resp.status_code, expected, resp.content)
                if expected == 403:
                    self.assertEqual(resp.json()["code"], "not_permitted")
        resp = APIClient().get(action_url(self.team.pk, "history"))
        self.assertEqual(resp.status_code, 401)
        self.assertIn("WWW-Authenticate", resp)

    def test_newest_first_and_paginated(self) -> None:
        for name in ("First", "Second", "Third"):
            self.rename_to(name)
        resp = self.history(query="?page_size=2")
        self.assertEqual(resp.status_code, 200, resp.content)
        data = resp.json()
        self.assertEqual(data["count"], 3)
        self.assertEqual(len(data["results"]), 2)
        self.assertIsNotNone(data["next"])
        latest = data["results"][0]
        self.assertEqual(latest["team_name"], "Third")
        self.assertEqual(latest["reason"], "to Third")
        self.assertEqual(latest["actor"]["pk"], self.site_staff.pk)
        self.assertEqual(latest["team_id"], self.team.pk)

    def test_default_page_size_is_25(self) -> None:
        self.bulk_logs(30)
        data = self.history().json()
        self.assertEqual(data["count"], 30)
        self.assertEqual(len(data["results"]), 25)

    def bulk_logs(self, n: int) -> None:
        snapshot = log_snapshot_fields(self.team)
        TeamLog.objects.bulk_create(
            TeamLog(
                **snapshot,
                team=self.team,
                action=TeamLogAction.RENAME,
                via=TeamLogVia.WEB,
                actor=self.actor,
            )
            for _ in range(n)
        )

    def test_page_edges(self) -> None:
        self.bulk_logs(101)
        resp = self.history(query="?page_size=1000")
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.json()["count"], 101)
        self.assertEqual(len(resp.json()["results"]), 100)
        self.assertEqual(self.history(query="?page=99").status_code, 404)

    def test_non_numeric_pk_404(self) -> None:
        self.assertEqual(self.history(team_pk="abc").status_code, 404)

    def test_unknown_team_404(self) -> None:
        self.assertEqual(self.history(team_pk=999999).status_code, 404)

    def test_unknown_team_403_for_non_staff(self) -> None:
        for user in (self.outsider, self.league_admin):
            with self.subTest(user=user.username):
                resp = self.history(user, team_pk=999999)
                self.assertEqual(resp.status_code, 403, resp.content)
                self.assertEqual(resp.json()["code"], "not_permitted")

    def test_event_team_rows_excluded(self) -> None:
        self.rename_to("Visible")
        event_team = EventTeam.objects.create(
            event=self.event, name="Event Side", captain=self.c
        )
        TeamLog.objects.create(
            **log_snapshot_fields(self.team),
            event_team=event_team,
            action=TeamLogAction.RENAME,
            via=TeamLogVia.WEB,
            reason="event team row",
        )
        resp = self.history()
        self.assertEqual(self.actions(resp), ["rename"])
        self.assertEqual(resp.json()["results"][0]["reason"], "to Visible")

    def test_survives_deletion(self) -> None:
        self.rename_to("Doomed")
        Team.objects.filter(pk=self.team.pk).delete()
        for user in (self.site_staff, self.org_staff, self.league_admin):
            with self.subTest(user=user.username):
                self.assertEqual(self.actions(self.history(user)), ["rename"])
        resp = self.history(self.outsider)
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.json()["code"], "not_permitted")

    def test_orphan_org_scope(self) -> None:
        self.rename_to("Orphan")
        Team.objects.filter(pk=self.team.pk).delete()
        Tournament.objects.filter(pk=self.tournament.pk).delete()
        self.assertEqual(self.actions(self.history(self.org_staff)), ["rename"])
        self.assertEqual(self.actions(self.history(self.site_staff)), ["rename"])
        for user in (self.outsider, self.league_admin):
            with self.subTest(user=user.username):
                resp = self.history(user)
                self.assertEqual(resp.status_code, 403)
                self.assertEqual(resp.json()["code"], "not_permitted")

    def test_orphan_without_org_is_site_staff_only(self) -> None:
        self.bulk_logs(1)
        TeamLog.objects.filter(team_snapshot_id=self.team.pk).update(
            tournament_id=None, organization_id=None, team=None
        )
        Team.objects.filter(pk=self.team.pk).delete()
        self.assertEqual(self.actions(self.history()), ["rename"])
        self.assertEqual(self.history(self.org_staff).status_code, 403)

    def test_tournamentless_live_team(self) -> None:
        loose = Team.objects.create(tournament=None, name="Loose", captain=self.m1)
        resp = self.history(team_pk=loose.pk)
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.json()["count"], 0)
        for user in (self.outsider, self.org_staff):
            with self.subTest(user=user.username):
                resp = self.history(user, team_pk=loose.pk)
                self.assertEqual(resp.status_code, 403)
                self.assertEqual(resp.json()["code"], "not_permitted")

    def test_live_team_without_rows_is_empty_page(self) -> None:
        resp = self.history(self.league_admin)
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.json()["count"], 0)

    def test_cross_org_move(self) -> None:
        self.rename_to("Before Move")
        elsewhere = self.other_org_tournament()
        resp = self.client_for(self.site_staff).patch(
            f"/api/teams/{self.team.pk}/",
            {"tournament_id": elsewhere.pk},
            format="json",
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        self.rename_to("After Move")
        new_staff = self.org_staff_of(elsewhere)
        self.assertEqual(
            self.actions(self.history(new_staff)), ["rename", "legacy_patch"]
        )
        old = self.history(self.org_staff)
        self.assertEqual(self.actions(old), ["rename"])
        self.assertEqual(old.json()["results"][0]["team_name"], "Before Move")
        self.assertEqual(
            self.actions(self.history()), ["rename", "legacy_patch", "rename"]
        )

    def test_queries_flat(self) -> None:
        def count(n: int) -> int:
            TeamLog.objects.all().delete()
            self.bulk_logs(n)
            TeamLog.objects.filter(team_snapshot_id=self.team.pk).update(
                target_user=self.m1
            )
            client = self.client_for(self.league_admin)
            url = action_url(self.team.pk, "history")
            with CaptureQueriesContext(connection) as ctx:
                self.assertEqual(client.get(url).status_code, 200)
            return len(ctx.captured_queries)

        self.assertEqual(count(1), count(6))


class LegacyDeleteTests(TeamApiFixture, TestCase):
    def delete(self, user: CustomUser | None = None) -> Any:
        client = self.client_for(self.site_staff if user is None else user)
        return client.delete(f"/api/teams/{self.team.pk}/")

    def deleted_rows(self) -> QuerySet[TeamLog]:
        return TeamLog.objects.filter(
            team_snapshot_id=self.team.pk, action=TeamLogAction.TEAM_DELETED
        )

    def test_referenced_team_refused(self) -> None:
        game = Game.objects.create(tournament=self.tournament, radiant_team=self.team)
        resp = self.delete()
        self.assertEqual(resp.status_code, 409, resp.content)
        body = resp.json()
        self.assertEqual(body["code"], "team_in_use")
        self.assertIn("1 game", body["detail"])
        self.assertEqual(body["usage"], team_usage([self.team]))
        self.assertIsInstance(body["usage"][0]["count"], int)
        self.assertIsInstance(body["usage"][0]["teams"][0]["pk"], int)
        self.assertTrue(Team.objects.nocache().filter(pk=self.team.pk).exists())
        self.assertTrue(Game.objects.nocache().filter(pk=game.pk).exists())
        self.assertFalse(self.deleted_rows().exists())

    def test_unreferenced_team_deleted_and_audited(self) -> None:
        pk = self.team.pk
        resp = self.delete()
        self.assertEqual(resp.status_code, 204, resp.content)
        self.assertFalse(Team.objects.nocache().filter(pk=pk).exists())
        rows = list(TeamLog.objects.filter(team_snapshot_id=pk))
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row.action, TeamLogAction.TEAM_DELETED)
        self.assertEqual(row.via, TeamLogVia.WEB)
        self.assertEqual(row.actor, self.site_staff)
        self.assertIsNone(row.team_id)
        self.assertEqual(row.team_name, "Rostered")
        self.assertEqual(row.tournament_id, self.tournament.pk)
        self.assertEqual(
            row.details["before"]["member_ids"],
            sorted([self.c.pk, self.d.pk, self.m1.pk, self.m2.pk]),
        )
        self.assertEqual(row.details["before"]["captain_id"], self.c.pk)

    def test_delete_sends_roster_changed(self) -> None:
        pk = self.team.pk
        changes: list[TeamRosterChange] = []

        def receiver(sender: type[Team], change: TeamRosterChange, **_: Any) -> None:
            changes.append(change)

        team_roster_changed.connect(receiver, sender=Team, weak=False)
        self.addCleanup(team_roster_changed.disconnect, receiver, sender=Team)
        with self.captureOnCommitCallbacks(execute=True):
            resp = self.delete()
        self.assertEqual(resp.status_code, 204, resp.content)
        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0].action, TeamLogAction.TEAM_DELETED)
        self.assertEqual(changes[0].team_id, pk)
        self.assertEqual(changes[0].tournament_id, self.tournament.pk)
        self.assertEqual(changes[0].actor_id, self.site_staff.pk)
        row = self.deleted_rows().get()
        self.assertEqual(changes[0].log_id, row.pk)

    def test_refused_delete_sends_nothing(self) -> None:
        Game.objects.create(tournament=self.tournament, dire_team=self.team)
        changes: list[TeamRosterChange] = []

        def receiver(sender: type[Team], change: TeamRosterChange, **_: Any) -> None:
            changes.append(change)

        team_roster_changed.connect(receiver, sender=Team, weak=False)
        self.addCleanup(team_roster_changed.disconnect, receiver, sender=Team)
        with self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(self.delete().status_code, 409)
        self.assertEqual(changes, [])

    def test_history_after_guarded_delete(self) -> None:
        self.assertEqual(self.delete().status_code, 204)
        resp = self.client_for(self.org_staff).get(action_url(self.team.pk, "history"))
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.json()["results"][0]["action"], "team_deleted")

    def test_delete_denial_body_unchanged(self) -> None:
        resp = self.delete(self.outsider)
        self.assertEqual(resp.status_code, 403, resp.content)
        self.assertNotIn("code", resp.json())
        self.assertIn("detail", resp.json())
        self.assertTrue(Team.objects.nocache().filter(pk=self.team.pk).exists())
        self.assertFalse(self.deleted_rows().exists())

    def test_unknown_team_404(self) -> None:
        resp = self.client_for(self.site_staff).delete("/api/teams/999999/")
        self.assertEqual(resp.status_code, 404)

    def stale_get_object(self) -> Any:
        stale = Team.objects.nocache().get(pk=self.team.pk)
        return patch.object(TeamView, "get_object", return_value=stale)

    def test_team_gone_before_lock_404(self) -> None:
        with self.stale_get_object():
            Team.objects.nocache().filter(pk=self.team.pk).delete()
            resp = self.delete()
        self.assertEqual(resp.status_code, 404, resp.content)
        self.assertFalse(self.deleted_rows().exists())

    def test_permission_rechecked_under_lock(self) -> None:
        with self.stale_get_object():
            Team.objects.nocache().filter(pk=self.team.pk).update(
                tournament=self.other_org_tournament()
            )
            resp = self.delete(self.org_staff)
        self.assertEqual(resp.status_code, 403, resp.content)
        self.assertTrue(Team.objects.nocache().filter(pk=self.team.pk).exists())
        self.assertFalse(self.deleted_rows().exists())

    def test_delete_logged(self) -> None:
        pk = self.team.pk
        with capture_logs() as logs:
            self.assertEqual(self.delete().status_code, 204)
        events = [e for e in logs if e["event"] == "team_deleted"]
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["system"], "tournament")
        self.assertEqual(events[0]["subsystem"], "teams")
        self.assertEqual(events[0]["team_id"], pk)
        self.assertEqual(events[0]["tournament_id"], self.tournament.pk)
        self.assertEqual(events[0]["actor_id"], self.site_staff.pk)

    def test_refusal_logged(self) -> None:
        Game.objects.create(tournament=self.tournament, radiant_team=self.team)
        with capture_logs() as logs:
            self.assertEqual(self.delete().status_code, 409)
        events = [e for e in logs if e["event"] == "team_delete_refused"]
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["log_level"], "warning")
        self.assertEqual(events[0]["system"], "tournament")
        self.assertEqual(events[0]["subsystem"], "teams")
        self.assertEqual(events[0]["team_id"], self.team.pk)
        self.assertEqual(events[0]["references"], team_references([self.team]))


class TeamUsageTests(TeamApiFixture, TestCase):
    def usage(self, user: CustomUser | None = None) -> Any:
        client = self.client_for(self.site_staff if user is None else user)
        return client.get(action_url(self.team.pk, "usage"))

    def test_url_name_reverses(self) -> None:
        self.assertEqual(
            reverse("teams-usage", args=[self.team.pk]),
            action_url(self.team.pk, "usage"),
        )

    def test_unused_team(self) -> None:
        resp = self.usage()
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.json(), {"in_use": False, "detail": None, "usage": []})

    def test_used_team_matches_delete_refusal(self) -> None:
        Game.objects.create(tournament=self.tournament, radiant_team=self.team)
        resp = self.usage()
        self.assertEqual(resp.status_code, 200, resp.content)
        body = resp.json()
        self.assertIs(body["in_use"], True)
        self.assertIn("1 game", body["detail"])
        self.assertEqual(body["usage"], team_usage([self.team]))
        refusal = self.client_for(self.site_staff).delete(f"/api/teams/{self.team.pk}/")
        self.assertEqual(refusal.json()["detail"], body["detail"])

    def test_writes_nothing(self) -> None:
        before = TeamLog.objects.count()
        self.assertEqual(self.usage().status_code, 200)
        self.assertEqual(TeamLog.objects.count(), before)
        self.assertTrue(Team.objects.nocache().filter(pk=self.team.pk).exists())

    def test_permissions(self) -> None:
        self.assertEqual(self.usage(self.league_admin).status_code, 200)
        for user in (self.c, self.outsider):
            with self.subTest(user=user.username):
                resp = self.usage(user)
                self.assertEqual(resp.status_code, 403, resp.content)
                self.assertEqual(resp.json()["code"], "not_permitted")
        resp = APIClient().get(action_url(self.team.pk, "usage"))
        self.assertEqual(resp.status_code, 401)


class TeamPatchPlacementGuardTests(TeamApiFixture, TestCase):
    def patch(self, team: Team, body: dict[str, Any]) -> Any:
        return self.client_for(self.site_staff).patch(
            f"/api/teams/{team.pk}/", body, format="json"
        )

    def take_over(self) -> None:
        eliminate(self.other, 4)
        team_management.replace_captain(
            self.team, self.o1, actor=self.actor, via=TeamLogVia.WEB, reason="r"
        )

    def legacy_rows(self, team: Team) -> int:
        return TeamLog.objects.filter(
            team_snapshot_id=team.pk, action=TeamLogAction.LEGACY_PATCH
        ).count()

    def test_patch_placement_null_after_takeover_409(self) -> None:
        self.take_over()

        resp = self.patch(self.other, {"placement": None})

        self.assertEqual(resp.status_code, 409, resp.content)
        body = resp.json()
        self.assertEqual(body["code"], "roster_conflict")
        self.assertEqual(
            body["details"], {"team_id": self.other.pk, "user_ids": [self.o1.pk]}
        )
        self.assertIn(self.o1.username, body["error"])
        self.assertEqual(Team.objects.nocache().get(pk=self.other.pk).placement, 4)
        self.assertEqual(self.legacy_rows(self.other), 0)

    def test_patch_placement_null_without_conflict_ok(self) -> None:
        eliminate(self.other, 4)

        resp = self.patch(self.other, {"placement": None})

        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertIsNone(Team.objects.nocache().get(pk=self.other.pk).placement)

    def test_patch_other_fields_unaffected(self) -> None:
        self.take_over()

        resp = self.patch(self.other, {"name": "Renamed Others"})
        self.assertEqual(resp.status_code, 200, resp.content)

        resp = self.patch(self.other, {"placement": 3})
        self.assertEqual(resp.status_code, 200, resp.content)

        other = Team.objects.nocache().get(pk=self.other.pk)
        self.assertEqual(other.name, "Renamed Others")
        self.assertEqual(other.placement, 3)
