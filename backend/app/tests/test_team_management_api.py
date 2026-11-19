"""Team management API (#545)."""

import json
from collections.abc import Callable
from typing import Any

from django.core.serializers.json import DjangoJSONEncoder
from django.db import connection, reset_queries
from django.test import SimpleTestCase, TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from app.draft_state import build_draft_state
from app.exception_handler import exception_handler
from app.functions.tournament import _serialize_tournament
from app.models import (
    DraftTeam,
    Game,
    HeroDraft,
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
