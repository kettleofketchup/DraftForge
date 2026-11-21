"""Team API writes keep the captain and deputy inside the member set (#571)."""

import itertools
from io import StringIO
from typing import Any

from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone
from rest_framework.response import Response
from rest_framework.test import APIClient

from app.models import (
    CustomUser,
    Game,
    PositionsModel,
    Team,
    TeamLog,
    TeamLogAction,
    TeamLogVia,
    Tournament,
)
from app.serializers import TeamSerializer
from app.services.team_leadership import teams_with_leadership_problems
from app.services.team_signals import TeamRosterChange, team_roster_changed
from app.tests.test_team_management import TeamManagementFixture
from draft.models import Draft, DraftEvent, DraftRound, TeamDraftState

_discord_ids = itertools.count(571000)


def _user(name: str) -> CustomUser:
    return CustomUser.objects.create(
        username=name,
        discordId=str(next(_discord_ids)),
        positions=PositionsModel.objects.create(),
    )


class TeamLeadershipApiTests(TestCase):
    def setUp(self):
        self.staff = CustomUser.objects.create_user(
            username="team_staff", password="x", is_staff=True
        )
        self.client = APIClient()
        self.client.force_authenticate(self.staff)
        self.tournament = Tournament.objects.create(
            name="Leadership Cup",
            tournament_type="single_elimination",
            date_played=timezone.now(),
        )
        self.a = _user("lead_a")
        self.b = _user("lead_b")
        self.c = _user("lead_c")
        self.outsider = _user("lead_outsider")
        self.tournament.users.set([self.a, self.b, self.c, self.outsider])
        self.team = Team.objects.create(tournament=self.tournament, name="Leaders")
        self.team.members.set([self.a, self.b, self.c])
        self.team.captain = self.a
        self.team.save(update_fields=["captain"])

    def _patch(self, data: dict):
        return self.client.patch(f"/api/teams/{self.team.pk}/", data, format="json")

    def test_patch_captain_non_member_rejected(self):
        response = self._patch({"captain_id": self.outsider.pk})

        self.assertEqual(response.status_code, 400, response.data)
        self.assertEqual(
            [str(m) for m in response.data["captain_id"]],
            ["Captain must be a member of the team."],
        )
        self.team.refresh_from_db()
        self.assertEqual(self.team.captain, self.a)

    def test_patch_deputy_non_member_rejected(self):
        response = self._patch({"deputy_captain_id": self.outsider.pk})

        self.assertEqual(response.status_code, 400, response.data)
        self.assertEqual(
            [str(m) for m in response.data["deputy_captain_id"]],
            ["Deputy captain must be a member of the team."],
        )

    def test_patch_deputy_equal_to_captain_rejected(self):
        response = self._patch({"deputy_captain_id": self.a.pk})

        self.assertEqual(response.status_code, 400, response.data)
        self.assertEqual(
            [str(m) for m in response.data["deputy_captain_id"]],
            ["Deputy captain cannot be the same as captain."],
        )

    def test_patch_members_and_captain_together_accepted(self):
        response = self._patch(
            {"member_ids": [self.a.pk, self.b.pk], "captain_id": self.b.pk}
        )

        self.assertEqual(response.status_code, 200, response.data)
        self.team.refresh_from_db()
        self.assertEqual(self.team.captain, self.b)

    def test_patch_captain_outside_new_members_rejected(self):
        response = self._patch({"member_ids": [self.b.pk], "captain_id": self.a.pk})

        self.assertEqual(response.status_code, 400, response.data)
        self.assertIn("captain_id", response.data)
        self.assertEqual(self.team.members.count(), 3)

    def test_patch_members_dropping_captain_promotes_remaining_member(self):
        response = self._patch({"member_ids": [self.b.pk]})

        self.assertEqual(response.status_code, 200, response.data)
        self.team.refresh_from_db()
        self.assertEqual(self.team.captain, self.b)

    def test_post_with_captain_in_members_created(self):
        response = self.client.post(
            "/api/teams/",
            {
                "name": "New Team",
                "tournament_id": self.tournament.pk,
                "member_ids": [self.b.pk, self.c.pk],
                "captain_id": self.b.pk,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201, response.data)

    def test_post_with_captain_outside_members_rejected(self):
        response = self.client.post(
            "/api/teams/",
            {
                "name": "Bad Team",
                "tournament_id": self.tournament.pk,
                "member_ids": [self.c.pk],
                "captain_id": self.b.pk,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400, response.data)
        self.assertIn("captain_id", response.data)
        self.assertFalse(Team.objects.filter(name="Bad Team").exists())


class TeamLeadershipMessagesTests(TestCase):
    def setUp(self):
        self.tournament = Tournament.objects.create(
            name="Messages Cup",
            tournament_type="single_elimination",
            date_played=timezone.now(),
        )
        self.a = _user("msg_a")
        self.b = _user("msg_b")
        self.outsider = _user("msg_outsider")
        self.team = Team.objects.create(tournament=self.tournament, name="Msg")
        self.team.members.set([self.a, self.b])

    def _serializer_errors(self, data: dict) -> dict[str, list[str]]:
        serializer = TeamSerializer(self.team, data=data, partial=True)
        self.assertFalse(serializer.is_valid())
        return {k: [str(m) for m in v] for k, v in serializer.errors.items()}

    def _clean_errors(self) -> dict[str, list[str]]:
        with self.assertRaises(ValidationError) as ctx:
            self.team.full_clean()
        return ctx.exception.message_dict

    def test_captain_non_member_same_message(self):
        serializer_errors = self._serializer_errors({"captain_id": self.outsider.pk})
        self.team.captain = self.outsider

        self.assertEqual(
            serializer_errors["captain_id"], self._clean_errors()["captain"]
        )

    def test_deputy_non_member_same_message(self):
        serializer_errors = self._serializer_errors(
            {"deputy_captain_id": self.outsider.pk}
        )
        self.team.deputy_captain = self.outsider

        self.assertEqual(
            serializer_errors["deputy_captain_id"],
            self._clean_errors()["deputy_captain"],
        )

    def test_deputy_is_captain_same_message(self):
        serializer_errors = self._serializer_errors(
            {"captain_id": self.a.pk, "deputy_captain_id": self.a.pk}
        )
        self.team.captain = self.a
        self.team.deputy_captain = self.a

        self.assertEqual(
            serializer_errors["deputy_captain_id"],
            self._clean_errors()["deputy_captain"],
        )

    def test_leadership_errors_is_pure(self):
        self.assertEqual(
            Team.leadership_errors({1, 2}, 3, 2),
            {"captain": "Captain must be a member of the team."},
        )
        self.assertEqual(
            Team.leadership_errors({1, 2}, 3, 4, check_captain=False),
            {"deputy_captain": "Deputy captain must be a member of the team."},
        )
        self.assertEqual(
            Team.leadership_errors({1}, 1, 1),
            {"deputy_captain": "Deputy captain cannot be the same as captain."},
        )
        self.assertEqual(Team.leadership_errors(set(), None, None), {})


class TeamLeadershipAuditTests(TestCase):
    def setUp(self):
        self.tournament = Tournament.objects.create(
            name="Audit Cup",
            tournament_type="single_elimination",
            date_played=timezone.now(),
        )
        self.a = _user("audit_a")
        self.b = _user("audit_b")
        self.outsider = _user("audit_outsider")
        self.good = self._team("Good", captain=self.a, deputy=self.b)
        self.no_captain = self._team("NoCaptain", captain=self.outsider)
        self.no_deputy = self._team("NoDeputy", captain=self.a, deputy=self.outsider)
        self.same = self._team("Same", captain=self.a, deputy=self.a)

    def _team(
        self, name: str, *, captain: CustomUser, deputy: CustomUser | None = None
    ) -> Team:
        team = Team.objects.create(tournament=self.tournament, name=name)
        team.members.set([self.a, self.b])
        Team.objects.filter(pk=team.pk).update(captain=captain, deputy_captain=deputy)
        return team

    def _snapshot(self) -> list[tuple]:
        return [
            (
                t.pk,
                t.captain_id,
                t.deputy_captain_id,
                tuple(sorted(t.members.values_list("pk", flat=True))),
            )
            for t in Team.objects.nocache().order_by("pk")
        ]

    def test_predicate_lists_each_problem(self):
        rows = [
            (team.pk, problem) for team, problem in teams_with_leadership_problems()
        ]

        self.assertEqual(
            rows,
            [
                (self.no_captain.pk, "captain_not_member"),
                (self.no_deputy.pk, "deputy_not_member"),
                (self.same.pk, "deputy_is_captain"),
            ],
        )

    def test_predicate_accepts_queryset(self):
        rows = teams_with_leadership_problems(Team.objects.filter(pk=self.good.pk))

        self.assertEqual(rows, [])

    def test_command_reports_and_changes_nothing(self):
        before = self._snapshot()
        out = StringIO()

        call_command("audit_team_leadership", stdout=out)

        self.assertEqual(self._snapshot(), before)
        output = out.getvalue()
        self.assertIn(
            f"team={self.no_captain.pk} tournament={self.tournament.pk} problem=captain_not_member",
            output,
        )
        self.assertIn(
            f"team={self.same.pk} tournament={self.tournament.pk} problem=deputy_is_captain",
            output,
        )
        self.assertNotIn(f"team={self.good.pk} ", output)


class TeamLegacyPatchTests(TeamManagementFixture, TestCase):
    """Legacy PATCH applies rosters safely, audits, and follows captain changes (#544)."""

    def setUp(self) -> None:
        super().setUp()
        self.staff = CustomUser.objects.create_user(
            username="legacy_staff", password="x", is_staff=True
        )
        self.client = APIClient()
        self.client.force_authenticate(self.staff)
        self.n1 = self.make_user("legacy_n1")
        self.n2 = self.make_user("legacy_n2")
        self.tournament.users.add(self.n1, self.n2)

    def _patch(self, data: dict[str, Any], team: Team | None = None) -> Response:
        pk = (team or self.team).pk
        return self.client.patch(f"/api/teams/{pk}/", data, format="json")

    def _legacy_rows(self) -> list[TeamLog]:
        return list(
            TeamLog.objects.filter(action=TeamLogAction.LEGACY_PATCH).order_by("pk")
        )

    def _round_captains(self) -> dict[int, int | None]:
        return dict(DraftRound.objects.nocache().values_list("pk", "captain_id"))

    def _make_rounds(self) -> tuple[DraftRound, DraftRound]:
        draft = Draft.objects.create(
            tournament=self.tournament,
            state=TeamDraftState.DRAFTING,
            draft_style="snake",
        )
        own = DraftRound.objects.create(draft=draft, captain=self.c, pick_number=1)
        other = DraftRound.objects.create(draft=draft, captain=self.o1, pick_number=2)
        return own, other

    def _reference(self, team: Team | None = None) -> None:
        Game.objects.create(tournament=self.tournament, radiant_team=team or self.team)

    def test_patch_writes_legacy_row(self) -> None:
        response = self._patch({"name": "Renamed"})

        self.assertEqual(response.status_code, 200, response.data)
        rows = self._legacy_rows()
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row.team_id, self.team.pk)
        self.assertEqual(row.via, TeamLogVia.WEB)
        self.assertEqual(row.actor_id, self.staff.pk)
        self.assertEqual(row.reason, "")
        self.assertEqual(row.event_id, self.event.pk)
        self.assertEqual(row.details["fields_changed"], ["name"])
        self.assertEqual(row.details["before"]["name"], "Rostered")
        self.assertEqual(row.details["after"]["name"], "Renamed")

    def test_noop_patch_writes_none(self) -> None:
        response = self._patch({"name": "Rostered", "draft_order": 4})

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(self._legacy_rows(), [])

    def test_patch_non_member_captain_400(self) -> None:
        response = self._patch({"captain_id": self.outsider.pk})

        self.assertEqual(response.status_code, 400, response.data)
        self.assertIn("captain_id", response.data)
        self.assertFalse(TeamLog.objects.exists())

    def test_patch_captain_change_moves_team_rounds(self) -> None:
        own, other = self._make_rounds()

        response = self._patch({"captain_id": self.m1.pk})

        self.assertEqual(response.status_code, 200, response.data)
        captains = self._round_captains()
        self.assertEqual(captains[own.pk], self.m1.pk)
        self.assertEqual(captains[other.pk], self.o1.pk)
        row = self._legacy_rows()[0]
        self.assertEqual(row.details["draft_rounds_updated"], 1)
        self.assertEqual(row.details["fields_changed"], ["captain_id"])

    def test_patch_dropping_captain_moves_rounds_to_successor(self) -> None:
        own, _ = self._make_rounds()

        response = self._patch({"member_ids": [self.d.pk, self.m1.pk, self.m2.pk]})

        self.assertEqual(response.status_code, 200, response.data)
        team = self.refresh(self.team)
        self.assertEqual(team.captain_id, self.d.pk)
        self.assertEqual(self._round_captains()[own.pk], self.d.pk)
        rows = list(TeamLog.objects.all())
        self.assertEqual([r.action for r in rows], [TeamLogAction.LEGACY_PATCH])
        self.assertEqual(
            rows[0].details["fields_changed"],
            ["captain_id", "deputy_captain_id", "member_ids"],
        )
        self.assertEqual(
            DraftEvent.objects.filter(
                draft=own.draft, event_type="team_changed"
            ).count(),
            1,
        )

    def _assert_swapped(self, response: Response) -> None:
        self.assertEqual(response.status_code, 200, response.data)
        team = self.refresh(self.team)
        self.assertEqual(
            set(team.members.nocache().values_list("pk", flat=True)),
            {self.n1.pk, self.n2.pk},
        )
        self.assertEqual(team.captain_id, self.n1.pk)
        self.assertIsNone(team.deputy_captain_id)
        rows = list(TeamLog.objects.all())
        self.assertEqual([r.action for r in rows], [TeamLogAction.LEGACY_PATCH])
        self.assertEqual(rows[0].team_id, self.team.pk)

    def test_full_swap_unreferenced_team_kept(self) -> None:
        response = self._patch(
            {"member_ids": [self.n1.pk, self.n2.pk], "captain_id": self.n1.pk}
        )

        self._assert_swapped(response)

    def test_full_swap_referenced_team_kept(self) -> None:
        self._reference()

        response = self._patch(
            {"member_ids": [self.n1.pk, self.n2.pk], "captain_id": self.n1.pk}
        )

        self._assert_swapped(response)

    def test_empty_referenced_team_400(self) -> None:
        self._reference()

        response = self._patch({"member_ids": []})

        self.assertEqual(response.status_code, 400, response.data)
        self.assertEqual(
            [str(m) for m in response.data["member_ids"]],
            [
                "This team is used by bracket games or hero drafts; "
                "remove it from those first."
            ],
        )
        self.assertEqual(self.refresh(self.team).members.nocache().count(), 4)
        self.assertFalse(TeamLog.objects.exists())

    def test_empty_unreferenced_team_deleted_cleanly(self) -> None:
        old_pk = self.team.pk

        response = self._patch({"member_ids": [], "dropin_member_ids": [self.n1.pk]})

        self.assertEqual(response.status_code, 204)
        self.assertEqual(response.content, b"")
        self.assertFalse(Team.objects.nocache().filter(pk=old_pk).exists())
        rows = list(TeamLog.objects.all())
        self.assertEqual([r.action for r in rows], [TeamLogAction.LEGACY_PATCH])
        row = rows[0]
        self.assertIsNone(row.team_id)
        self.assertEqual(row.team_snapshot_id, old_pk)
        self.assertEqual(row.team_name, "Rostered")
        self.assertTrue(row.details["team_deleted"])
        self.assertIsNone(row.details["after"])
        self.assertEqual(row.details["fields_changed"], ["dropin_ids", "member_ids"])

    def test_name_only_patch_on_empty_kept_team_ok(self) -> None:
        self._reference()
        self.team.members.clear()
        self.assertTrue(Team.objects.nocache().filter(pk=self.team.pk).exists())

        response = self._patch({"name": "Still Here"})

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(self.refresh(self.team).name, "Still Here")

    def test_post_create_team_still_works(self) -> None:
        response = self.client.post(
            "/api/teams/",
            {
                "name": "Fresh",
                "tournament_id": self.tournament.pk,
                "member_ids": [self.n1.pk, self.n2.pk],
                "captain_id": self.n1.pk,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201, response.data)
        self.assertTrue(Team.objects.filter(name="Fresh").exists())

    def _capture_signal(self) -> list[TeamRosterChange]:
        changes: list[TeamRosterChange] = []

        def receiver(sender: type, change: TeamRosterChange, **kwargs: Any) -> None:
            changes.append(change)

        team_roster_changed.connect(receiver, sender=Team, weak=False)
        self.addCleanup(team_roster_changed.disconnect, receiver, sender=Team)
        return changes

    def test_patch_sends_roster_signal_on_member_change(self) -> None:
        changes = self._capture_signal()
        members = [self.c.pk, self.d.pk, self.m1.pk, self.m2.pk, self.n1.pk]

        with self.captureOnCommitCallbacks(execute=True):
            response = self._patch({"member_ids": members})

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(len(changes), 1)
        sent = changes[0]
        self.assertEqual(sent.action, TeamLogAction.LEGACY_PATCH)
        self.assertEqual(sent.log_id, self._legacy_rows()[0].pk)
        self.assertEqual(sent.after["member_ids"], sorted(members))

    def test_name_only_patch_sends_roster_signal(self) -> None:
        changes = self._capture_signal()

        with self.captureOnCommitCallbacks(execute=True):
            response = self._patch({"name": "Renamed"})

        self.assertEqual(response.status_code, 200, response.data)
        rows = self._legacy_rows()
        self.assertEqual(len(rows), 1)
        self.assertEqual([c.log_id for c in changes], [rows[0].pk])
        self.assertEqual(changes[0].after["name"], "Renamed")

    def test_rename_patch_snapshot_uses_new_name(self) -> None:
        response = self._patch({"name": "Renamed"})

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(self._legacy_rows()[0].team_name, "Renamed")

    def test_tournament_move_snapshot_uses_new_tournament(self) -> None:
        moved = Tournament.objects.create(
            name="Moved Cup", date_played=timezone.now(), league=self.tournament.league
        )

        response = self._patch({"tournament_id": moved.pk})

        self.assertEqual(response.status_code, 200, response.data)
        row = self._legacy_rows()[0]
        self.assertEqual(row.tournament_id, moved.pk)
        self.assertEqual(row.details["fields_changed"], ["tournament_id"])
        self.assertEqual(row.details["before_tournament_id"], self.tournament.pk)
