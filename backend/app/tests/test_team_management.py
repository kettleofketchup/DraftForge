"""Staff roster service: pipeline, invariant, audit rows and the first four actions."""

from datetime import timedelta
from typing import Any
from unittest.mock import patch

from django.db.models import F
from django.test import TestCase, TransactionTestCase
from django.utils import timezone
from rest_framework.test import APIClient

from app.models import (
    CustomUser,
    LeadershipProblem,
    League,
    Organization,
    Team,
    TeamLog,
    TeamLogAction,
    TeamLogVia,
    Tournament,
)
from app.services import team_management
from app.services.team_management import (
    DEFAULT_MAX_STANDINS,
    TeamChange,
    TeamManagementError,
    _apply,
    _other_team_user_ids,
    remove_standin,
    rename,
    restore_member,
    set_deputy,
    standin_cap,
)
from app.services.team_signals import TeamRosterChange, team_roster_changed
from events.models import Event
from org.models import OrgUser
from user.tests.test_cacheops_integration import _redis_reachable


def _problems(team: Team) -> dict[str, LeadershipProblem]:
    fresh = Team.objects.nocache().get(pk=team.pk)
    member_pks = set(fresh.members.nocache().values_list("pk", flat=True))
    return Team.leadership_problems(
        member_pks, fresh.captain_id, fresh.deputy_captain_id
    )


class TeamManagementFixture:
    def setUp(self) -> None:
        super().setUp()
        self.org = Organization.objects.create(name="Roster Org")
        self.league = League.objects.create(
            organization=self.org, name="Roster League", steam_league_id=92001
        )
        self.tournament = Tournament.objects.create(
            name="Roster Cup", date_played=timezone.now(), league=self.league
        )
        self.actor = self.make_user("roster_staff")
        self.start = timezone.now() + timedelta(days=1)
        self.event = Event.objects.create(
            organization=self.org,
            name="Roster Night",
            scheduled_at=self.start,
            ends_at=self.start + timedelta(hours=3),
            created_by=self.actor,
            tournament=self.tournament,
        )
        self.c = self.make_user("roster_c")
        self.d = self.make_user("roster_d")
        self.m1 = self.make_user("roster_m1")
        self.m2 = self.make_user("roster_m2")
        self.o1 = self.make_user("roster_o1")
        self.outsider = self.make_user("roster_outsider")
        self.tournament.users.add(self.c, self.d, self.m1, self.m2, self.o1)
        self.team = Team.objects.create(
            tournament=self.tournament, name="Rostered", captain=self.c
        )
        self.team.members.add(self.c, self.d, self.m1, self.m2)
        self.team.deputy_captain = self.d
        self.team.save()
        self.other = Team.objects.create(
            tournament=self.tournament, name="Others", captain=self.o1
        )
        self.other.members.add(self.o1)

    def make_user(self, username: str) -> CustomUser:
        user = CustomUser.objects.create_user(username=username, password="test")
        OrgUser.objects.create(user=user, organization=self.org, mmr=3000)
        return user

    def refresh(self, team: Team) -> Team:
        return Team.objects.nocache().get(pk=team.pk)

    def make_ghost_captain(self, team: Team, outsider: CustomUser) -> Team:
        assert not team.members.nocache().filter(pk=outsider.pk).exists()
        Team.objects.filter(pk=team.pk).update(captain=outsider)
        team = self.refresh(team)
        assert _problems(team).get("captain") == LeadershipProblem.CAPTAIN_NOT_MEMBER
        return team

    def make_ghost_deputy(self, team: Team, outsider: CustomUser) -> Team:
        assert not team.members.nocache().filter(pk=outsider.pk).exists()
        Team.objects.filter(pk=team.pk).update(deputy_captain=outsider)
        team = self.refresh(team)
        assert (
            _problems(team).get("deputy_captain") == LeadershipProblem.DEPUTY_NOT_MEMBER
        )
        return team

    def make_deputy_is_captain(self, team: Team) -> Team:
        Team.objects.filter(pk=team.pk).update(deputy_captain=F("captain"))
        team = self.refresh(team)
        assert (
            _problems(team).get("deputy_captain") == LeadershipProblem.DEPUTY_IS_CAPTAIN
        )
        return team

    def drop_member_silently(self, team: Team, user: CustomUser) -> Team:
        Team.members.through.objects.filter(
            team_id=team.pk, customuser_id=user.pk
        ).delete()
        team = self.refresh(team)
        if user.pk in (team.captain_id, team.deputy_captain_id):
            assert _problems(team)
        return team

    def only_log(self) -> TeamLog:
        rows = list(TeamLog.objects.filter(team_snapshot_id=self.team.pk))
        self.assertEqual(len(rows), 1)
        return rows[0]

    def member_pks(self, team: Team) -> set[int]:
        return set(self.refresh(team).members.nocache().values_list("pk", flat=True))


class FixtureHelperTests(TeamManagementFixture, TestCase):
    def test_helpers_produce_problems(self) -> None:
        team = self.make_deputy_is_captain(self.team)
        self.assertEqual(team.deputy_captain_id, self.c.pk)
        Team.objects.filter(pk=team.pk).update(deputy_captain=None)
        team = self.make_ghost_captain(team, self.outsider)
        team = self.make_ghost_deputy(team, self.o1)
        self.assertEqual(
            _problems(team),
            {
                "captain": LeadershipProblem.CAPTAIN_NOT_MEMBER,
                "deputy_captain": LeadershipProblem.DEPUTY_NOT_MEMBER,
            },
        )
        self.assertEqual(TeamLog.objects.count(), 0)

    def test_drop_member_silently_skips_succession(self) -> None:
        team = self.drop_member_silently(self.team, self.c)
        self.assertEqual(team.captain_id, self.c.pk)
        self.assertEqual(
            _problems(team)["captain"], LeadershipProblem.CAPTAIN_NOT_MEMBER
        )


class RenameTests(TeamManagementFixture, TestCase):
    def test_rename_writes_one_log(self) -> None:
        change = rename(
            self.team,
            "  Renamed  ",
            actor=self.actor,
            via=TeamLogVia.WEB,
            reason="typo",
        )
        self.assertIsInstance(change, TeamChange)
        self.assertEqual(change.overridden, [])
        self.assertEqual(self.refresh(self.team).name, "Renamed")
        row = self.only_log()
        self.assertEqual(row.pk, change.log.pk)
        self.assertEqual(row.action, TeamLogAction.RENAME)
        self.assertEqual(row.via, TeamLogVia.WEB)
        self.assertEqual(row.actor_id, self.actor.pk)
        self.assertEqual(row.reason, "typo")
        self.assertEqual(row.team_id, self.team.pk)
        self.assertEqual(row.tournament_id, self.tournament.pk)
        self.assertEqual(row.event_id, self.event.pk)
        self.assertEqual(row.organization_id, self.org.pk)
        self.assertEqual(row.occasion_at, self.event.ends_at)
        self.assertEqual(row.team_name, "Renamed")
        self.assertEqual(row.details["before"]["name"], "Rostered")
        self.assertEqual(row.details["after"]["name"], "Renamed")
        self.assertEqual(
            row.details["after"]["member_ids"],
            sorted([self.c.pk, self.d.pk, self.m1.pk, self.m2.pk]),
        )

    def test_rename_requires_reason(self) -> None:
        with self.assertRaises(TeamManagementError) as ctx:
            rename(self.team, "New", actor=self.actor, via=TeamLogVia.WEB)
        self.assertEqual(ctx.exception.code, "reason_required")
        self.assertEqual(self.refresh(self.team).name, "Rostered")

    def test_rename_blank_refused(self) -> None:
        with self.assertRaises(TeamManagementError) as ctx:
            rename(self.team, "   ", actor=self.actor, via=TeamLogVia.WEB, reason="x")
        self.assertEqual(ctx.exception.code, "name_blank")

    def test_rename_same_refused(self) -> None:
        with self.assertRaises(TeamManagementError) as ctx:
            rename(
                self.team,
                " Rostered ",
                actor=self.actor,
                via=TeamLogVia.WEB,
                reason="x",
            )
        self.assertEqual(ctx.exception.code, "name_unchanged")

    def test_rename_256_chars_refused(self) -> None:
        with self.assertRaises(TeamManagementError) as ctx:
            rename(
                self.team, "n" * 256, actor=self.actor, via=TeamLogVia.WEB, reason="x"
            )
        self.assertEqual(ctx.exception.code, "name_too_long")
        rename(self.team, "n" * 255, actor=self.actor, via=TeamLogVia.WEB, reason="x")

    def test_refusal_writes_no_log(self) -> None:
        for name in ("", "Rostered", "n" * 256):
            with self.assertRaises(TeamManagementError):
                rename(
                    self.team, name, actor=self.actor, via=TeamLogVia.WEB, reason="x"
                )
        self.assertEqual(TeamLog.objects.count(), 0)

    def test_system_via_needs_no_reason(self) -> None:
        rename(self.team, "Auto", actor=None, via=TeamLogVia.SYSTEM)
        self.assertEqual(self.only_log().via, TeamLogVia.SYSTEM)

    def test_rename_on_ghost_captain_team_succeeds(self) -> None:
        team = self.make_ghost_captain(self.team, self.outsider)
        before = _problems(team)

        rename(team, "Still Ghosted", actor=self.actor, via=TeamLogVia.WEB, reason="x")

        self.assertEqual(self.refresh(team).name, "Still Ghosted")
        self.assertEqual(_problems(team), before)

    def test_org_settings_reach_check_overrides(self) -> None:
        with patch.object(
            team_management, "check_overrides", wraps=team_management.check_overrides
        ) as spy:
            rename(self.team, "Spied", actor=self.actor, via=TeamLogVia.WEB, reason="x")
        settings = spy.call_args.kwargs["org_settings"]
        self.assertIsNotNone(settings)
        self.assertEqual(settings.organization_id, self.org.pk)


class SetDeputyTests(TeamManagementFixture, TestCase):
    def test_set_deputy_member(self) -> None:
        set_deputy(self.team, self.m1, actor=self.actor, via=TeamLogVia.WEB, reason="r")
        self.assertEqual(self.refresh(self.team).deputy_captain_id, self.m1.pk)
        row = self.only_log()
        self.assertEqual(row.action, TeamLogAction.SET_DEPUTY)
        self.assertEqual(row.target_user_id, self.m1.pk)
        self.assertEqual(row.details["before"]["deputy_captain_id"], self.d.pk)
        self.assertEqual(row.details["after"]["deputy_captain_id"], self.m1.pk)

    def test_set_deputy_none_requires_reason(self) -> None:
        with self.assertRaises(TeamManagementError) as ctx:
            set_deputy(self.team, None, actor=self.actor, via=TeamLogVia.WEB)
        self.assertEqual(ctx.exception.code, "reason_required")
        self.assertEqual(self.refresh(self.team).deputy_captain_id, self.d.pk)

    def test_set_deputy_none_targets_outgoing(self) -> None:
        set_deputy(self.team, None, actor=self.actor, via=TeamLogVia.WEB, reason="r")
        self.assertIsNone(self.refresh(self.team).deputy_captain_id)
        self.assertEqual(self.only_log().target_user_id, self.d.pk)

    def test_set_deputy_none_without_deputy_refused(self) -> None:
        Team.objects.filter(pk=self.team.pk).update(deputy_captain=None)
        with self.assertRaises(TeamManagementError) as ctx:
            set_deputy(
                self.team, None, actor=self.actor, via=TeamLogVia.WEB, reason="r"
            )
        self.assertEqual(ctx.exception.code, "no_deputy")

    def test_set_deputy_captain_refused(self) -> None:
        with self.assertRaises(TeamManagementError) as ctx:
            set_deputy(
                self.team, self.c, actor=self.actor, via=TeamLogVia.WEB, reason="r"
            )
        self.assertEqual(ctx.exception.code, "deputy_is_captain")

    def test_set_deputy_already_refused(self) -> None:
        with self.assertRaises(TeamManagementError) as ctx:
            set_deputy(
                self.team, self.d, actor=self.actor, via=TeamLogVia.WEB, reason="r"
            )
        self.assertEqual(ctx.exception.code, "already_deputy")
        self.assertIn("already", ctx.exception.message)

    def test_set_deputy_standin_refused(self) -> None:
        self.team.dropin_members.add(self.outsider)
        with self.assertRaises(TeamManagementError) as ctx:
            set_deputy(
                self.team,
                self.outsider,
                actor=self.actor,
                via=TeamLogVia.WEB,
                reason="r",
            )
        self.assertEqual(ctx.exception.code, "deputy_is_standin")
        self.assertIn("sub them in first", ctx.exception.message)

    def test_set_deputy_non_member_refused(self) -> None:
        with self.assertRaises(TeamManagementError) as ctx:
            set_deputy(
                self.team,
                self.outsider,
                actor=self.actor,
                via=TeamLogVia.WEB,
                reason="r",
            )
        self.assertEqual(ctx.exception.code, "deputy_not_member")
        self.assertEqual(TeamLog.objects.count(), 0)

    def test_self_action_without_reason_ok(self) -> None:
        set_deputy(self.team, None, actor=self.d, via=TeamLogVia.WEB)
        row = self.only_log()
        self.assertEqual(row.actor_id, self.d.pk)
        self.assertEqual(row.reason, "")

    def test_deputy_is_captain_fixed_by_clearing(self) -> None:
        team = self.make_deputy_is_captain(self.team)

        set_deputy(team, None, actor=self.actor, via=TeamLogVia.WEB, reason="fix")

        self.assertEqual(_problems(team), {})
        self.assertEqual(self.only_log().target_user_id, self.c.pk)

    def test_ghost_deputy_replaced_by_member(self) -> None:
        team = self.make_ghost_deputy(self.team, self.outsider)

        set_deputy(team, self.m2, actor=self.actor, via=TeamLogVia.WEB, reason="fix")

        self.assertEqual(_problems(team), {})

    def test_set_deputy_on_ghost_captain_team(self) -> None:
        team = self.make_ghost_captain(self.team, self.outsider)

        set_deputy(team, self.m1, actor=self.actor, via=TeamLogVia.WEB, reason="r")

        self.assertEqual(
            _problems(team), {"captain": LeadershipProblem.CAPTAIN_NOT_MEMBER}
        )


class StandinAndRestoreTests(TeamManagementFixture, TestCase):
    def test_remove_standin(self) -> None:
        self.team.dropin_members.add(self.outsider)

        remove_standin(
            self.team, self.outsider, actor=self.actor, via=TeamLogVia.WEB, reason="r"
        )

        self.assertFalse(
            self.refresh(self.team).dropin_members.filter(pk=self.outsider.pk).exists()
        )
        row = self.only_log()
        self.assertEqual(row.action, TeamLogAction.REMOVE_STANDIN)
        self.assertEqual(row.target_user_id, self.outsider.pk)
        self.assertEqual(row.details["before"]["dropin_ids"], [self.outsider.pk])
        self.assertEqual(row.details["after"]["dropin_ids"], [])

    def test_remove_standin_not_standin_refused(self) -> None:
        with self.assertRaises(TeamManagementError) as ctx:
            remove_standin(
                self.team, self.m1, actor=self.actor, via=TeamLogVia.WEB, reason="r"
            )
        self.assertEqual(ctx.exception.code, "not_standin")
        self.assertIn(self.m1.pk, self.member_pks(self.team))

    def test_remove_standin_self_needs_no_reason(self) -> None:
        self.team.dropin_members.add(self.outsider)
        remove_standin(
            self.team, self.outsider, actor=self.outsider, via=TeamLogVia.WEB
        )
        self.assertEqual(self.only_log().reason, "")

    def test_restore_member(self) -> None:
        self.team.left_members.add(self.outsider)
        tournament_users = set(self.tournament.users.values_list("pk", flat=True))

        restore_member(
            self.team, self.outsider, actor=self.actor, via=TeamLogVia.WEB, reason="r"
        )

        team = self.refresh(self.team)
        self.assertIn(self.outsider.pk, self.member_pks(team))
        self.assertFalse(team.left_members.filter(pk=self.outsider.pk).exists())
        self.assertEqual(
            set(self.tournament.users.values_list("pk", flat=True)), tournament_users
        )
        row = self.only_log()
        self.assertEqual(row.action, TeamLogAction.RESTORE_MEMBER)
        self.assertEqual(row.details["before"]["left_ids"], [self.outsider.pk])
        self.assertEqual(row.details["after"]["left_ids"], [])

    def test_restore_member_on_other_team_refused(self) -> None:
        self.team.left_members.add(self.o1)
        with self.assertRaises(TeamManagementError) as ctx:
            restore_member(
                self.team, self.o1, actor=self.actor, via=TeamLogVia.WEB, reason="r"
            )
        self.assertEqual(ctx.exception.code, "on_other_team")
        self.assertNotIn(self.o1.pk, self.member_pks(self.team))

    def test_restore_member_standin_elsewhere_refused(self) -> None:
        self.team.left_members.add(self.outsider)
        self.other.dropin_members.add(self.outsider)
        with self.assertRaises(TeamManagementError) as ctx:
            restore_member(
                self.team,
                self.outsider,
                actor=self.actor,
                via=TeamLogVia.WEB,
                reason="r",
            )
        self.assertEqual(ctx.exception.code, "on_other_team")

    def test_restore_member_not_left_refused(self) -> None:
        with self.assertRaises(TeamManagementError) as ctx:
            restore_member(
                self.team,
                self.outsider,
                actor=self.actor,
                via=TeamLogVia.WEB,
                reason="r",
            )
        self.assertEqual(ctx.exception.code, "not_dropout")

    def test_other_team_user_ids(self) -> None:
        self.other.dropin_members.add(self.outsider)
        self.team.dropin_members.add(self.m2)
        self.assertEqual(
            _other_team_user_ids(self.team), {self.o1.pk, self.outsider.pk}
        )

    def test_standin_cap_default(self) -> None:
        self.assertEqual(standin_cap(self.team), DEFAULT_MAX_STANDINS)
        self.assertEqual(DEFAULT_MAX_STANDINS, 2)


class InvariantTests(TeamManagementFixture, TestCase):
    def run_apply(
        self, team: Team, mutate: Any, touched: tuple[str, ...] = ()
    ) -> TeamChange:
        return _apply(
            team,
            TeamLogAction.RENAME,
            actor=self.actor,
            via=TeamLogVia.WEB,
            reason="r",
            acknowledged_codes=(),
            target_user=lambda t: None,
            affected_users=lambda t: [],
            validate=lambda t: [],
            mutate=mutate,
            touched=touched,
        )

    def test_invariant_rolls_back_new_problem(self) -> None:
        def mutate(team: Team) -> dict[str, Any]:
            team.name = "Broken"
            team.deputy_captain = team.captain
            team.save()
            return {}

        with self.assertRaises(TeamManagementError) as ctx:
            self.run_apply(self.team, mutate)
        self.assertEqual(ctx.exception.code, "leadership_invariant")
        team = self.refresh(self.team)
        self.assertEqual(team.deputy_captain_id, self.d.pk)
        self.assertEqual(team.name, "Rostered")
        self.assertEqual(TeamLog.objects.count(), 0)

    def test_invariant_problem_kind_change_refused(self) -> None:
        team = self.make_ghost_deputy(self.team, self.outsider)

        def mutate(locked: Team) -> dict[str, Any]:
            locked.deputy_captain = locked.captain
            locked.save()
            return {}

        with self.assertRaises(TeamManagementError) as ctx:
            self.run_apply(team, mutate)
        self.assertEqual(ctx.exception.code, "leadership_invariant")
        self.assertEqual(self.refresh(team).deputy_captain_id, self.outsider.pk)

    def test_invariant_touched_key_must_be_clean(self) -> None:
        team = self.make_ghost_deputy(self.team, self.outsider)

        def mutate(locked: Team) -> dict[str, Any]:
            locked.name = "Touched"
            locked.save()
            return {}

        with self.assertRaises(TeamManagementError) as ctx:
            self.run_apply(team, mutate, touched=("deputy_captain",))
        self.assertEqual(ctx.exception.code, "leadership_invariant")
        self.assertEqual(self.refresh(team).name, "Rostered")

    def test_existing_problem_kept_is_allowed(self) -> None:
        team = self.make_ghost_deputy(self.team, self.outsider)

        def mutate(locked: Team) -> dict[str, Any]:
            locked.name = "Kept"
            locked.save()
            return {}

        self.run_apply(team, mutate)
        self.assertEqual(self.refresh(team).name, "Kept")


class RosterSignalTests(TeamManagementFixture, TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.changes: list[TeamRosterChange] = []

        def receiver(sender: type, change: TeamRosterChange, **kwargs: Any) -> None:
            self.changes.append(change)

        self.receiver = receiver
        team_roster_changed.connect(receiver, sender=Team, weak=False)
        self.addCleanup(team_roster_changed.disconnect, receiver, sender=Team)

    def test_signal_sent_on_commit(self) -> None:
        with self.captureOnCommitCallbacks(execute=True):
            change = rename(
                self.team, "Signalled", actor=self.actor, via=TeamLogVia.WEB, reason="r"
            )
            self.assertEqual(self.changes, [])
        self.assertEqual(len(self.changes), 1)
        sent = self.changes[0]
        self.assertEqual(sent.action, "rename")
        self.assertEqual(sent.log_id, change.log.pk)
        self.assertEqual(sent.team_id, self.team.pk)
        self.assertEqual(sent.event_id, self.event.pk)
        self.assertEqual(sent.before["name"], "Rostered")
        self.assertEqual(sent.after["name"], "Signalled")

    def test_refusal_sends_nothing(self) -> None:
        with self.captureOnCommitCallbacks(execute=True):
            with self.assertRaises(TeamManagementError):
                rename(self.team, "", actor=self.actor, via=TeamLogVia.WEB, reason="r")
        self.assertEqual(self.changes, [])


class TeamManagementCacheTests(TeamManagementFixture, TransactionTestCase):
    def setUp(self) -> None:
        if not _redis_reachable():
            self.skipTest("Cacheops Redis not reachable")
        super().setUp()

    def test_rename_visible_through_team_view_cache(self) -> None:
        client = APIClient()
        url = f"/api/teams/{self.team.pk}/"
        self.assertEqual(client.get(url).json()["name"], "Rostered")

        rename(self.team, "Fresh", actor=self.actor, via=TeamLogVia.WEB, reason="r")

        self.assertEqual(client.get(url).json()["name"], "Fresh")
