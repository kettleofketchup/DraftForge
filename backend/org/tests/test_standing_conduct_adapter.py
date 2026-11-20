from collections.abc import Mapping
from datetime import timedelta

from django.contrib.auth.models import AnonymousUser
from django.test import override_settings
from django.utils import timezone

from app.models import CustomUser
from org.conduct.adapter import CONDUCT
from org.conduct.constants import Outcome
from org.conduct.gate import get_conduct_settings
from org.models import OrgUser
from org.standing import api as standing
from org.standing import registry
from org.standing.periods import parse_period
from org.standing.types import ViewerRoles
from org.tests.test_conduct_api import ConductReadApiBase, base

FEATURE_QUERIES = 1
MEMBERSHIP_QUERIES = 1
SETTINGS_READ_QUERIES = 1
OWN_ROW_QUERIES = 1
IS_STAFF_QUERIES = 2
CAN_VIEW_MEMBERS_QUERIES = 1
SCORING_QUERIES = 1
PROFILE_QUERIES = 1
PRIVATE_STAFF_LEADERBOARD_QUERIES = (
    FEATURE_QUERIES
    + MEMBERSHIP_QUERIES
    + 2 * SETTINGS_READ_QUERIES
    + IS_STAFF_QUERIES
    + CAN_VIEW_MEMBERS_QUERIES
    + SCORING_QUERIES
    + PROFILE_QUERIES
)
PUBLIC_MEMBER_LEADERBOARD_QUERIES = (
    FEATURE_QUERIES
    + MEMBERSHIP_QUERIES
    + 2 * SETTINGS_READ_QUERIES
    + CAN_VIEW_MEMBERS_QUERIES
    + OWN_ROW_QUERIES
    + SCORING_QUERIES
    + PROFILE_QUERIES
)
HISTORY_QUERIES = 1
MEMBER_STANDING_QUERIES = SETTINGS_READ_QUERIES + SCORING_QUERIES + HISTORY_QUERIES

ACCESS_MATRIX: dict[tuple[bool, bool], dict[str, tuple[bool, bool, bool, bool]]] = {
    (False, False): {
        "anon": (False, False, False, False),
        "outsider": (False, False, False, False),
        "member": (True, False, False, True),
        "staff": (True, True, True, False),
        "owner": (True, True, True, False),
        "site_admin": (True, True, True, False),
    },
    (False, True): {
        "anon": (False, False, False, False),
        "outsider": (False, False, False, False),
        "member": (True, False, False, True),
        "staff": (True, True, True, False),
    },
    (True, False): {
        "anon": (True, True, False, False),
        "outsider": (True, True, False, False),
        "member": (True, True, True, True),
        "staff": (True, True, True, False),
        "owner": (True, True, True, False),
        "site_admin": (True, True, True, False),
    },
    (True, True): {
        "anon": (True, True, False, False),
        "outsider": (True, True, False, False),
        "member": (True, True, False, True),
        "staff": (True, True, True, False),
    },
}


class ConductAdapterTest(ConductReadApiBase):
    def viewer(self, role: str) -> CustomUser | AnonymousUser:
        return self.users[role] or AnonymousUser()

    def test_registered_after_contribution(self) -> None:
        self.assertEqual(
            [t.key for t in registry.tracks()], ["contribution", "conduct"]
        )
        self.assertIs(registry.track("conduct"), CONDUCT)

    def test_reopen_reset_fields_include_conduct(self) -> None:
        self.assertEqual(
            standing.reopen_reset_fields(),
            {"contributions_awarded_at": None, "conduct_finalized_at": None},
        )

    def test_access_matrix(self) -> None:
        for (public, members_private), cells in ACCESS_MATRIX.items():
            self.set_public(public)
            self.set_members_private(members_private)
            for role, expected in cells.items():
                with self.subTest(
                    public=public, members_private=members_private, role=role
                ):
                    viewer = self.viewer(role)
                    access = CONDUCT.access(
                        self.org.pk,
                        viewer=viewer,
                        roles=standing.viewer_roles(self.org, viewer),
                    )
                    self.assertEqual(
                        (
                            access.allowed,
                            access.board_open,
                            access.can_view_rows,
                            access.can_view_own,
                        ),
                        expected,
                    )
                    self.assertEqual(access.board_open, public or role in STAFF_ROLES)

    def test_public_board_never_reads_is_staff(self) -> None:
        self.set_public(True)

        def boom() -> bool:
            raise AssertionError("is_staff read on a public board")

        roles = ViewerRoles(is_admin=boom, is_staff=boom, can_view_members=lambda: True)
        access = CONDUCT.access(self.org.pk, viewer=self.users["member"], roles=roles)
        self.assertTrue(access.board_open)

    def test_leaderboard_period_is_current(self) -> None:
        self.add_outcomes(self.org_users["member"], [Outcome.ATTENDED] * 3)
        board = self.board("owner")
        self.assertEqual(board.period, "current")
        self.assertIsNone(board.total)
        self.assertEqual(board.metric.key, "show_rate")

    def board(self, role: str) -> standing.Leaderboard:
        return standing.leaderboard(
            self.org,
            "conduct",
            "show_rate",
            parse_period(self.org, None),
            viewer=self.users[role],
        )

    def test_leaderboard_rows_match_legacy(self) -> None:
        self.add_outcomes(self.org_users["member"], [Outcome.ATTENDED] * 3)
        self.add_outcomes(
            self.org_users["promoter"], [Outcome.ATTENDED, Outcome.NO_SHOW] * 2
        )
        newcomer = self.make_member("conapi_new")
        self.add_outcomes(newcomer, [Outcome.ATTENDED])
        legacy = self.request("owner", "get", f"{base(self.org.pk)}leaderboard/")
        body = legacy.json()
        board = self.board("owner")
        ranked = [r for r in board.rows if r.status == "ranked"]
        new = [r for r in board.rows if r.status == "new"]
        self.assertEqual(board.rows, [*ranked, *new])
        self.assertEqual(
            [(r.org_user_id, r.value, r.sample) for r in ranked],
            [
                (row["member"]["org_user_pk"], row["show_rate"], row["counted_events"])
                for row in body["rows"]
            ],
        )
        self.assertEqual(
            [(r.org_user_id, r.sample) for r in new],
            [
                (row["member"]["org_user_pk"], row["counted_events"])
                for row in body["new_members"]
            ],
        )

    def test_own_row_for_member_without_outcomes(self) -> None:
        self.set_public(True)
        self.add_outcomes(self.org_users["promoter"], [Outcome.ATTENDED] * 3)
        board = self.board("member")
        own = board.own_row
        assert own is not None
        self.assertEqual(own.org_user_id, self.org_users["member"].pk)
        self.assertEqual(own.status, "new")
        self.assertEqual(own.sample, 0)
        legacy = self.request("member", "get", f"{base(self.org.pk)}leaderboard/")
        self.assertEqual(own.value, legacy.json()["own_row"]["show_rate"])

    @override_settings(CACHEOPS_ENABLED=False)
    def test_leaderboard_budget(self) -> None:
        self.add_outcomes(self.org_users["member"], [Outcome.ATTENDED] * 3)
        self.set_public(False)
        get_conduct_settings(self.org)
        with self.assertNumQueries(PRIVATE_STAFF_LEADERBOARD_QUERIES):
            board = self.board("staff")
        self.assertTrue(board.rows_visible)
        self.set_public(True)
        with self.assertNumQueries(PUBLIC_MEMBER_LEADERBOARD_QUERIES):
            board = self.board("member")
        self.assertTrue(board.rows_visible)
        self.assertIsNotNone(board.own_row)

    def seed_history(self) -> OrgUser:
        member = self.org_users["member"]
        older = self.when - timedelta(days=10)
        self.add_outcomes(member, [Outcome.ATTENDED, Outcome.NO_SHOW])
        self.add_outcomes(member, [Outcome.EXCUSED], starts_at=older, reason="sick")
        self.add_outcomes(member, [Outcome.PENDING], starts_at=older, finalized_at=None)
        return member

    def test_member_standing_payload(self) -> None:
        member = self.seed_history()
        for role in ("member", "staff"):
            with self.subTest(role=role):
                viewer = self.users[role]
                block = CONDUCT.member_standing(
                    member,
                    viewer=viewer,
                    roles=standing.viewer_roles(self.org, viewer),
                    now=timezone.now(),
                )
                assert block is not None
                self.assertEqual(
                    set(block), {"show_rate", "status", "counted_events", "history"}
                )
                legacy = self.request(
                    role, "get", f"{base(self.org.pk)}members/{member.pk}/"
                ).json()
                for key in ("show_rate", "status", "counted_events"):
                    self.assertEqual(block[key], legacy[key])
                history = block["history"]
                assert isinstance(history, list)
                self.assertEqual(
                    [_without_weight(item) for item in history],
                    [_without_weight(item) for item in legacy["history"]],
                )

    @override_settings(CACHEOPS_ENABLED=False)
    def test_member_standing_budget(self) -> None:
        member = self.seed_history()
        get_conduct_settings(self.org)
        with self.assertNumQueries(MEMBER_STANDING_QUERIES):
            CONDUCT.member_standing(
                member,
                viewer=self.users["member"],
                roles=ViewerRoles.fixed(False, False, False),
                now=timezone.now(),
            )

    def test_member_standing_viewer_rule(self) -> None:
        member = self.seed_history()
        cases = {
            "member": True,
            "staff": True,
            "owner": True,
            "site_admin": True,
            "promoter": False,
            "outsider": False,
            "anon": False,
        }
        for role, visible in cases.items():
            with self.subTest(role=role):
                viewer = self.viewer(role)
                roles = standing.viewer_roles(self.org, viewer)
                block = CONDUCT.member_standing(
                    member, viewer=viewer, roles=roles, now=timezone.now()
                )
                self.assertEqual(block is not None, visible)
                found = standing.member_standing(member, viewer=viewer, roles=roles)
                self.assertEqual("conduct" in found, visible)


STAFF_ROLES = frozenset({"staff", "owner", "site_admin"})


def _without_weight(item: Mapping[str, object]) -> dict[str, object]:
    return {key: value for key, value in item.items() if key != "weight"}
