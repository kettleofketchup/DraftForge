"""Staff roster service: pipeline, invariant, audit rows and the first four actions."""

from datetime import timedelta
from typing import Any
from unittest.mock import patch

from django.db.models import F
from django.test import TestCase, TransactionTestCase
from django.utils import timezone
from rest_framework.test import APIClient

from app.models import CustomUser
from draft.models import (
    Draft,
    DraftEvent,
    DraftRound,
    DraftTeam,
    HeroDraft,
    HeroDraftState,
    TeamDraftState,
)
from draft.serializers.hero import HeroDraftSerializer
from draft.services.hero_state import herodraft_state_queryset
from events.eligibility import UNMET_LABELS, Unmet, unmet_codes
from events.models import Event
from events.overrides import (
    REASON_MAX_LENGTH,
    OverrideReasonRequired,
    OverrideRequired,
)
from league.models import League, LeagueUser
from org.models import Organization, OrgSettings, OrgUser
from org.models_profiles import PlayerDotaProfile
from org.settings_constants import StaffOverridePolicy
from org.settings_service import get_org_settings
from tests.populate.utils import ensure_org_user
from tournament.models import Game, Team, TeamLog, Tournament
from tournament.models.team import LeadershipProblem
from tournament.models.team_log import TeamLogAction, TeamLogVia
from tournament.serializers.draft import users_remaining_pks
from tournament.services import team_management
from tournament.services.team_management import (
    DEFAULT_MAX_STANDINS,
    TeamChange,
    TeamManagementError,
    _apply,
    add_standin,
    mark_dropout,
    other_team_user_ids,
    remove_standin,
    rename,
    restore_member,
    set_captain,
    set_deputy,
    standin_cap,
    sub_in,
)
from tournament.services.team_signals import TeamRosterChange, team_roster_changed
from tournament.state import tournament_state_queryset
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
        ensure_org_user(user, self.org, mmr=3000)
        return user

    def gate_event(self) -> CustomUser:
        Event.objects.filter(pk=self.event.pk).update(
            require_steam_id=True, min_mmr=5000
        )
        user = self.make_user("roster_low")
        profile = PlayerDotaProfile.objects.create(
            org_user=OrgUser.objects.get(user=user, organization=self.org)
        )
        profile.declare_rank("active")
        profile.mmr = 3000
        profile.save()
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

    def test_rename_needs_no_reason(self) -> None:
        rename(self.team, "New", actor=self.actor, via=TeamLogVia.WEB)
        self.assertEqual(self.refresh(self.team).name, "New")
        self.assertEqual(self.only_log().reason, "")

    def test_reason_over_limit_refused(self) -> None:
        with self.assertRaises(TeamManagementError) as ctx:
            set_deputy(
                self.team,
                self.m1,
                actor=self.actor,
                via=TeamLogVia.WEB,
                reason="r" * (REASON_MAX_LENGTH + 1),
            )
        self.assertEqual(ctx.exception.code, "reason_too_long")
        self.assertEqual(self.refresh(self.team).deputy_captain_id, self.d.pk)
        set_deputy(
            self.team,
            self.m1,
            actor=self.actor,
            via=TeamLogVia.WEB,
            reason="r" * REASON_MAX_LENGTH,
        )

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
        self.assertEqual(other_team_user_ids(self.team), {self.o1.pk, self.outsider.pk})

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


class SetCaptainTests(TeamManagementFixture, TestCase):
    def captain(self, user: CustomUser, **kwargs: Any) -> TeamChange:
        kwargs.setdefault("reason", "r")
        return set_captain(
            self.team, user, actor=self.actor, via=TeamLogVia.WEB, **kwargs
        )

    def test_set_captain_member(self) -> None:
        change = self.captain(self.m1)

        team = self.refresh(self.team)
        self.assertEqual(team.captain_id, self.m1.pk)
        self.assertEqual(team.deputy_captain_id, self.d.pk)
        self.assertIn(self.c.pk, self.member_pks(team))
        row = self.only_log()
        self.assertEqual(row.pk, change.log.pk)
        self.assertEqual(row.action, TeamLogAction.SET_CAPTAIN)
        self.assertEqual(row.target_user_id, self.m1.pk)
        self.assertEqual(row.details["before"]["captain_id"], self.c.pk)
        self.assertEqual(row.details["after"]["captain_id"], self.m1.pk)
        self.assertEqual(row.details["draft_rounds_updated"], 0)
        self.assertTrue(row.details["presence_reset"])
        self.assertNotIn("added_to_tournament", row.details)

    def test_set_captain_requires_reason(self) -> None:
        with self.assertRaises(TeamManagementError) as ctx:
            self.captain(self.m1, reason="")
        self.assertEqual(ctx.exception.code, "reason_required")
        self.assertEqual(self.refresh(self.team).captain_id, self.c.pk)

    def test_set_captain_deputy_clears_deputy(self) -> None:
        self.captain(self.d)

        team = self.refresh(self.team)
        self.assertEqual(team.captain_id, self.d.pk)
        self.assertIsNone(team.deputy_captain_id)
        self.assertEqual(_problems(team), {})

    def test_set_captain_standin_moves_into_members(self) -> None:
        standin = CustomUser.objects.create_user(username="roster_s", password="t")
        self.team.dropin_members.add(standin)

        self.captain(standin)

        team = self.refresh(self.team)
        self.assertEqual(team.captain_id, standin.pk)
        self.assertIn(standin.pk, self.member_pks(team))
        self.assertIn(self.c.pk, self.member_pks(team))
        self.assertFalse(team.dropin_members.nocache().filter(pk=standin.pk).exists())
        self.assertTrue(self.tournament.users.filter(pk=standin.pk).exists())
        details = self.only_log().details
        self.assertTrue(details["added_to_tournament"])
        self.assertTrue(details["org_user_created"])
        self.assertTrue(details["league_user_created"])
        self.assertTrue(
            LeagueUser.objects.filter(user=standin, league=self.league).exists()
        )

    def test_set_captain_same_refused(self) -> None:
        with self.assertRaises(TeamManagementError) as ctx:
            self.captain(self.c)
        self.assertEqual(ctx.exception.code, "already_captain")
        self.assertFalse(TeamLog.objects.exists())

    def test_set_captain_non_member_refused(self) -> None:
        with self.assertRaises(TeamManagementError) as ctx:
            self.captain(self.outsider)
        self.assertEqual(ctx.exception.code, "captain_not_member")
        self.assertFalse(TeamLog.objects.exists())

    def test_reseat_ghost_captain(self) -> None:
        team = self.drop_member_silently(self.team, self.c)
        self.assertIn("captain", _problems(team))

        change = self.captain(self.c)

        team = self.refresh(self.team)
        self.assertEqual(team.captain_id, self.c.pk)
        self.assertIn(self.c.pk, self.member_pks(team))
        self.assertEqual(_problems(team), {})
        self.assertNotIn("draft_rounds_updated", change.log.details)

    def test_reseat_from_left_members(self) -> None:
        self.drop_member_silently(self.team, self.c)
        self.team.left_members.add(self.c)

        self.captain(self.c)

        team = self.refresh(self.team)
        self.assertIn(self.c.pk, self.member_pks(team))
        self.assertFalse(team.left_members.nocache().filter(pk=self.c.pk).exists())

    def test_reseat_refused_when_on_other_team(self) -> None:
        self.drop_member_silently(self.team, self.c)
        Team.members.through.objects.create(
            team_id=self.other.pk, customuser_id=self.c.pk
        )

        with self.assertRaises(TeamManagementError) as ctx:
            self.captain(self.c)
        self.assertEqual(ctx.exception.code, "on_other_team")
        self.assertNotIn(self.c.pk, self.member_pks(self.team))

    def test_repair_ghost_captain_and_deputy_stepwise(self) -> None:
        team = self.make_ghost_captain(self.team, self.outsider)
        team = self.make_ghost_deputy(team, self.o1)
        self.assertEqual(set(_problems(team)), {"captain", "deputy_captain"})

        set_deputy(team, None, actor=self.actor, via=TeamLogVia.WEB, reason="r")
        self.assertEqual(set(_problems(self.team)), {"captain"})
        self.captain(self.m1)

        self.assertEqual(_problems(self.team), {})
        self.assertEqual(self.refresh(self.team).captain_id, self.m1.pk)


class CaptainDraftFollowUpTests(TeamManagementFixture, TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.p1 = self.make_user("roster_p1")
        self.p2 = self.make_user("roster_p2")
        self.tournament.users.add(self.p1, self.p2)

    def make_draft(self, state: str, style: str = "snake") -> Draft:
        return Draft.objects.create(
            tournament=self.tournament, state=state, draft_style=style
        )

    def captain(self, user: CustomUser) -> TeamChange:
        return set_captain(
            self.team, user, actor=self.actor, via=TeamLogVia.WEB, reason="r"
        )

    def make_herodraft(self, state: str = HeroDraftState.DRAFTING) -> HeroDraft:
        game = Game.objects.create(tournament=self.tournament)
        herodraft = HeroDraft.objects.create(game=game, state=state)
        DraftTeam.objects.create(draft=herodraft, tournament_team=self.team)
        DraftTeam.objects.create(draft=herodraft, tournament_team=self.other)
        return herodraft

    def test_team_rounds_follow(self) -> None:
        draft = self.make_draft(TeamDraftState.DRAFTING)
        picked = DraftRound.objects.create(
            draft=draft, captain=self.c, pick_number=1, choice=self.p1
        )
        open_a = DraftRound.objects.create(draft=draft, captain=self.c, pick_number=3)
        open_b = DraftRound.objects.create(draft=draft, captain=self.c, pick_number=5)
        other = DraftRound.objects.create(draft=draft, captain=self.o1, pick_number=2)

        change = self.captain(self.m1)

        captains = dict(DraftRound.objects.nocache().values_list("pk", "captain_id"))
        self.assertEqual(captains[picked.pk], self.m1.pk)
        self.assertEqual(captains[open_a.pk], self.m1.pk)
        self.assertEqual(captains[open_b.pk], self.m1.pk)
        self.assertEqual(captains[other.pk], self.o1.pk)
        self.assertEqual(change.log.details["draft_rounds_updated"], 3)
        self.assertEqual(change.log.details["draft_picked_rounds_updated"], 1)

    def test_picked_rounds_keep_their_team(self) -> None:
        draft = self.make_draft(TeamDraftState.DRAFTING)
        picked = DraftRound.objects.create(
            draft=draft, captain=self.c, pick_number=1, choice=self.p1
        )

        self.captain(self.m1)

        fresh = DraftRound.objects.nocache().get(pk=picked.pk)
        self.assertEqual(fresh.team, self.team)

    def test_undo_old_captain_pick_after_captain_change(self) -> None:
        draft = self.make_draft(TeamDraftState.DRAFTING)
        DraftRound.objects.create(
            draft=draft, captain=self.o1, pick_number=1, choice=self.p2
        )
        last = DraftRound.objects.create(
            draft=draft, captain=self.c, pick_number=2, choice=self.p1
        )
        self.other.members.add(self.p2)
        self.team.members.add(self.p1)
        self.captain(self.m1)
        staff = CustomUser.objects.create_superuser(
            username="roster_admin", password="test"
        )
        client = APIClient()
        client.force_authenticate(staff)

        with self.captureOnCommitCallbacks(execute=True):
            response = client.post(
                "/api/tournaments/undo-pick", {"draft_pk": draft.pk}, format="json"
            )

        self.assertEqual(response.status_code, 200, response.content)
        self.assertNotIn(self.p1.pk, self.member_pks(self.team))
        fresh = DraftRound.objects.nocache().get(pk=last.pk)
        self.assertIsNone(fresh.choice_id)
        self.assertEqual(fresh.captain_id, self.m1.pk)
        self.assertEqual(fresh.team, self.team)
        event = DraftEvent.objects.get(draft=draft, event_type="pick_undone")
        self.assertEqual(event.payload["team_id"], self.team.pk)
        remaining = Draft.objects.nocache().get(pk=draft.pk).users_remaining
        self.assertIn(self.p1.pk, set(remaining.values_list("pk", flat=True)))

    def test_shuffle_null_rounds_untouched(self) -> None:
        draft = self.make_draft(TeamDraftState.DRAFTING, style="shuffle")
        null_rounds = [
            DraftRound.objects.create(draft=draft, captain=None, pick_number=n)
            for n in (1, 2, 3)
        ]
        Team.objects.filter(pk=self.team.pk).update(captain=None)

        change = self.captain(self.m1)

        self.assertEqual(
            set(
                DraftRound.objects.nocache()
                .filter(pk__in=[r.pk for r in null_rounds])
                .values_list("captain_id", flat=True)
            ),
            {None},
        )
        self.assertEqual(change.log.details["draft_rounds_updated"], 0)
        self.assertEqual(
            change.log.details["draft_rounds_skipped_reason"], "no_previous_captain"
        )

    def test_old_captain_not_in_pool(self) -> None:
        draft = self.make_draft(TeamDraftState.DRAFTING)
        DraftRound.objects.create(draft=draft, captain=self.c, pick_number=1)

        self.captain(self.m1)

        fresh = Draft.objects.nocache().get(pk=draft.pk)
        remaining = set(fresh.users_remaining.values_list("pk", flat=True))
        self.assertNotIn(self.c.pk, remaining)
        self.assertEqual(remaining, {self.p1.pk, self.p2.pk})
        state = tournament_state_queryset(fresh=True).get(pk=self.tournament.pk)
        pool = users_remaining_pks(state.draft)
        self.assertNotIn(self.c.pk, pool)
        self.assertEqual(set(pool), {self.p1.pk, self.p2.pk})

    def test_standin_not_in_pool(self) -> None:
        draft = self.make_draft(TeamDraftState.DRAFTING)
        DraftRound.objects.create(draft=draft, captain=self.c, pick_number=1)

        add_standin(self.team, self.p1, actor=None, via=TeamLogVia.WEB, reason="r")

        fresh = Draft.objects.nocache().get(pk=draft.pk)
        remaining = set(fresh.users_remaining.values_list("pk", flat=True))
        self.assertEqual(remaining, {self.p2.pk})
        state = tournament_state_queryset(fresh=True).get(pk=self.tournament.pk)
        self.assertEqual(set(users_remaining_pks(state.draft)), {self.p2.pk})

    def test_presence_reset_and_pending_emits(self) -> None:
        draft = self.make_draft(TeamDraftState.PENDING)
        Team.objects.filter(pk=self.team.pk).update(
            draft_is_ready=True, draft_is_connected=True, draft_has_connected=True
        )

        self.captain(self.m1)

        team = self.refresh(self.team)
        self.assertFalse(team.draft_is_ready)
        self.assertFalse(team.draft_is_connected)
        self.assertFalse(team.draft_has_connected)
        event = DraftEvent.objects.get(draft=draft, event_type="team_changed")
        self.assertEqual(
            event.payload,
            {"team_id": self.team.pk, "team_name": "Rostered", "pick_number": None},
        )
        self.assertEqual(event.actor_id, self.actor.pk)

    def test_completed_draft_emits_nothing(self) -> None:
        draft = self.make_draft(TeamDraftState.COMPLETED)

        self.captain(self.m1)

        self.assertFalse(DraftEvent.objects.filter(draft=draft).exists())

    def test_waiting_herodraft_ready_reset(self) -> None:
        herodraft = self.make_herodraft(HeroDraftState.WAITING_FOR_CAPTAINS)
        DraftTeam.objects.filter(draft=herodraft).update(
            is_ready=True, is_connected=True
        )

        with patch.object(team_management, "broadcast_herodraft_state"):
            with self.captureOnCommitCallbacks(execute=True):
                self.captain(self.m1)

        flags = {
            dt.tournament_team_id: (dt.is_ready, dt.is_connected)
            for dt in DraftTeam.objects.nocache().filter(draft=herodraft)
        }
        self.assertEqual(flags[self.team.pk], (False, False))
        self.assertEqual(flags[self.other.pk], (True, True))
        self.assertEqual(
            HeroDraft.objects.nocache().get(pk=herodraft.pk).state,
            HeroDraftState.WAITING_FOR_CAPTAINS,
        )

    def test_drafting_herodraft_keeps_connected(self) -> None:
        herodraft = self.make_herodraft(HeroDraftState.DRAFTING)
        DraftTeam.objects.filter(draft=herodraft).update(
            is_ready=True, is_connected=True
        )

        with patch.object(team_management, "broadcast_herodraft_state"):
            with self.captureOnCommitCallbacks(execute=True):
                self.captain(self.m1)

        own = DraftTeam.objects.nocache().get(
            draft=herodraft, tournament_team=self.team
        )
        self.assertTrue(own.is_connected)

    def test_live_herodrafts_broadcast_each(self) -> None:
        first = self.make_herodraft()
        second = self.make_herodraft(HeroDraftState.WAITING_FOR_CAPTAINS)
        self.make_herodraft(HeroDraftState.COMPLETED)
        self.make_herodraft(HeroDraftState.ABANDONED)

        refresh = patch.object(
            team_management,
            "_refresh_herodrafts",
            wraps=team_management._refresh_herodrafts,
        )
        order: list[str] = []
        with (
            refresh as refresh_spy,
            patch.object(team_management, "broadcast_herodraft_state") as spy,
            patch.object(team_management, "invalidate_obj") as invalidate,
        ):
            spy.side_effect = lambda *a, **k: order.append("broadcast")
            invalidate.side_effect = lambda *a, **k: order.append("invalidate")
            with self.captureOnCommitCallbacks(execute=True):
                self.captain(self.m1)
                spy.assert_not_called()

        refresh_spy.assert_called_once()
        # team + 2 drafts + 4 draft teams, all before any broadcast
        self.assertEqual(order, ["invalidate"] * 7 + ["broadcast"] * 2)
        self.assertEqual(
            sorted(call.args[0].pk for call in spy.call_args_list),
            sorted([first.pk, second.pk]),
        )
        self.assertEqual(
            {call.args[1] for call in spy.call_args_list}, {"team_changed"}
        )


class HeroDraftCaptainCacheTests(TeamManagementFixture, TransactionTestCase):
    def setUp(self) -> None:
        if not _redis_reachable():
            self.skipTest("Cacheops Redis not reachable")
        super().setUp()
        game = Game.objects.create(tournament=self.tournament)
        self.herodraft = HeroDraft.objects.create(
            game=game, state=HeroDraftState.DRAFTING
        )
        DraftTeam.objects.create(draft=self.herodraft, tournament_team=self.team)

    def captain_pk(self) -> int:
        draft = herodraft_state_queryset().get(id=self.herodraft.pk)
        return HeroDraftSerializer(draft).data["draft_teams"][0]["captain"]["pk"]

    def test_herodraft_read_shows_new_captain(self) -> None:
        self.assertEqual(self.captain_pk(), self.c.pk)

        with patch.object(team_management, "broadcast_herodraft_state"):
            set_captain(
                self.team, self.m1, actor=self.actor, via=TeamLogVia.WEB, reason="r"
            )

        self.assertEqual(self.captain_pk(), self.m1.pk)


class DropoutTests(TeamManagementFixture, TestCase):
    def dropout(self, user: CustomUser, **kwargs: Any) -> TeamChange:
        kwargs.setdefault("reason", "r")
        return mark_dropout(
            self.team, user, actor=self.actor, via=TeamLogVia.WEB, **kwargs
        )

    def left_pks(self, team: Team) -> set[int]:
        return set(
            self.refresh(team).left_members.nocache().values_list("pk", flat=True)
        )

    def test_dropout_member(self) -> None:
        change = self.dropout(self.m1)

        team = self.refresh(self.team)
        self.assertNotIn(self.m1.pk, self.member_pks(team))
        self.assertIn(self.m1.pk, self.left_pks(team))
        self.assertEqual(team.captain_id, self.c.pk)
        self.assertEqual(team.deputy_captain_id, self.d.pk)
        self.assertTrue(self.tournament.users.filter(pk=self.m1.pk).exists())
        row = self.only_log()
        self.assertEqual(row.pk, change.log.pk)
        self.assertEqual(row.action, TeamLogAction.MARK_DROPOUT)
        self.assertEqual(row.target_user_id, self.m1.pk)
        self.assertEqual(row.details["succession"], "unchanged")
        self.assertIn(self.m1.pk, row.details["before"]["member_ids"])
        self.assertNotIn(self.m1.pk, row.details["after"]["member_ids"])

    def test_dropout_requires_reason(self) -> None:
        with self.assertRaises(TeamManagementError) as ctx:
            self.dropout(self.m1, reason="")
        self.assertEqual(ctx.exception.code, "reason_required")
        self.assertIn(self.m1.pk, self.member_pks(self.team))

    def test_self_dropout_needs_no_reason(self) -> None:
        mark_dropout(self.team, self.m1, actor=self.m1, via=TeamLogVia.WEB)
        self.assertNotIn(self.m1.pk, self.member_pks(self.team))

    def test_dropout_non_member_refused(self) -> None:
        with self.assertRaises(TeamManagementError) as ctx:
            self.dropout(self.outsider)
        self.assertEqual(ctx.exception.code, "not_member")
        self.assertFalse(TeamLog.objects.exists())

    def test_dropout_last_member_refused(self) -> None:
        with self.assertRaises(TeamManagementError) as ctx:
            mark_dropout(
                self.other, self.o1, actor=self.actor, via=TeamLogVia.WEB, reason="r"
            )
        self.assertEqual(ctx.exception.code, "last_member")
        other = self.refresh(self.other)
        self.assertEqual(self.member_pks(other), {self.o1.pk})
        self.assertEqual(other.captain_id, self.o1.pk)
        self.assertFalse(TeamLog.objects.exists())

    def test_dropout_deputy_clears_deputy(self) -> None:
        change = self.dropout(self.d)

        team = self.refresh(self.team)
        self.assertIsNone(team.deputy_captain_id)
        self.assertEqual(team.captain_id, self.c.pk)
        self.assertIn(self.d.pk, self.left_pks(team))
        self.assertEqual(change.log.details["succession"], "deputy_cleared")
        self.assertEqual(_problems(team), {})

    def test_dropout_captain_uses_deputy(self) -> None:
        draft = Draft.objects.create(
            tournament=self.tournament,
            state=TeamDraftState.DRAFTING,
            draft_style="snake",
        )
        open_round = DraftRound.objects.create(
            draft=draft, captain=self.c, pick_number=1
        )

        change = self.dropout(self.c)

        team = self.refresh(self.team)
        self.assertEqual(team.captain_id, self.d.pk)
        self.assertIsNone(team.deputy_captain_id)
        self.assertIn(self.c.pk, self.left_pks(team))
        self.assertEqual(
            DraftRound.objects.nocache().get(pk=open_round.pk).captain_id, self.d.pk
        )
        details = change.log.details
        self.assertEqual(details["succession"], "deputy")
        self.assertEqual(details["draft_rounds_updated"], 1)
        self.assertNotIn("added_to_tournament", details)
        self.assertEqual(_problems(team), {})

    def test_dropout_captain_mmr_successor_added_to_tournament(self) -> None:
        Team.objects.filter(pk=self.team.pk).update(deputy_captain=None)
        high = CustomUser.objects.create_user(username="roster_high", password="t")
        ensure_org_user(high, self.org, mmr=9000)
        self.team.members.add(high)
        ensure_org_user(self.c, self.org, mmr=12000)
        self.assertFalse(self.tournament.users.filter(pk=high.pk).exists())

        change = self.dropout(self.c)

        team = self.refresh(self.team)
        self.assertEqual(team.captain_id, high.pk)
        self.assertTrue(self.tournament.users.filter(pk=high.pk).exists())
        self.assertTrue(self.tournament.users.filter(pk=self.c.pk).exists())
        details = change.log.details
        self.assertEqual(details["succession"], "org_mmr")
        self.assertTrue(details["added_to_tournament"])

    def test_dropout_does_not_fire_signal_rows(self) -> None:
        draft = Draft.objects.create(
            tournament=self.tournament,
            state=TeamDraftState.DRAFTING,
            draft_style="snake",
        )
        DraftRound.objects.create(draft=draft, captain=self.c, pick_number=1)
        DraftRound.objects.create(draft=draft, captain=self.c, pick_number=3)

        follow = patch.object(
            team_management,
            "follow_captain",
            wraps=team_management.follow_captain,
        )
        with follow as spy:
            change = self.dropout(self.c)

        spy.assert_called_once()
        self.assertEqual(TeamLog.objects.count(), 1)
        self.assertEqual(self.only_log().pk, change.log.pk)
        self.assertEqual(change.log.details["draft_rounds_updated"], 2)
        self.assertEqual(
            DraftEvent.objects.filter(draft=draft, event_type="team_changed").count(),
            1,
        )

    def test_dropout_on_ghost_captain_team(self) -> None:
        team = self.make_ghost_captain(self.team, self.outsider)

        mark_dropout(team, self.m1, actor=self.actor, via=TeamLogVia.WEB, reason="r")

        self.assertEqual(
            _problems(self.team), {"captain": LeadershipProblem.CAPTAIN_NOT_MEMBER}
        )

    def test_dropout_captain_repairs_deputy_is_captain(self) -> None:
        self.make_deputy_is_captain(self.team)

        change = self.dropout(self.c)

        team = self.refresh(self.team)
        self.assertNotEqual(team.captain_id, self.c.pk)
        self.assertIn(team.captain_id, self.member_pks(team))
        self.assertIsNone(team.deputy_captain_id)
        self.assertEqual(change.log.details["succession"], "org_mmr")
        self.assertEqual(_problems(team), {})


class SubInTests(TeamManagementFixture, TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.standin = self.make_user("roster_standin")
        self.team.dropin_members.add(self.standin)

    def sub(
        self, standin: CustomUser, replacing: CustomUser | None = None, **kwargs: Any
    ) -> TeamChange:
        kwargs.setdefault("reason", "r")
        return sub_in(
            self.team,
            standin,
            replacing,
            actor=self.actor,
            via=TeamLogVia.WEB,
            **kwargs,
        )

    def test_sub_in_grows_roster(self) -> None:
        change = self.sub(self.standin)

        team = self.refresh(self.team)
        self.assertEqual(
            self.member_pks(team),
            {self.c.pk, self.d.pk, self.m1.pk, self.m2.pk, self.standin.pk},
        )
        self.assertFalse(
            team.dropin_members.nocache().filter(pk=self.standin.pk).exists()
        )
        row = self.only_log()
        self.assertEqual(row.pk, change.log.pk)
        self.assertEqual(row.action, TeamLogAction.SUB_IN)
        self.assertEqual(row.target_user_id, self.standin.pk)
        self.assertIsNone(row.details["replacing_user_id"])
        self.assertNotIn("succession", row.details)

    def test_sub_in_replacing_member(self) -> None:
        change = self.sub(self.standin, self.m1)

        team = self.refresh(self.team)
        self.assertIn(self.standin.pk, self.member_pks(team))
        self.assertNotIn(self.m1.pk, self.member_pks(team))
        self.assertTrue(team.left_members.nocache().filter(pk=self.m1.pk).exists())
        details = self.only_log().details
        self.assertEqual(details["replacing_user_id"], self.m1.pk)
        self.assertEqual(details["succession"], "unchanged")
        self.assertEqual(change.log.target_user_id, self.standin.pk)

    def test_sub_in_replacing_captain(self) -> None:
        draft = Draft.objects.create(
            tournament=self.tournament,
            state=TeamDraftState.DRAFTING,
            draft_style="snake",
        )
        open_round = DraftRound.objects.create(
            draft=draft, captain=self.c, pick_number=1
        )

        change = self.sub(self.standin, self.c)

        team = self.refresh(self.team)
        self.assertEqual(team.captain_id, self.d.pk)
        self.assertIsNone(team.deputy_captain_id)
        self.assertIn(self.standin.pk, self.member_pks(team))
        self.assertTrue(team.left_members.nocache().filter(pk=self.c.pk).exists())
        self.assertEqual(
            DraftRound.objects.nocache().get(pk=open_round.pk).captain_id, self.d.pk
        )
        details = change.log.details
        self.assertEqual(details["succession"], "deputy")
        self.assertEqual(details["replacing_user_id"], self.c.pk)
        self.assertEqual(TeamLog.objects.count(), 1)
        self.assertEqual(_problems(team), {})

    def test_sub_in_replacing_last_member(self) -> None:
        self.other.dropin_members.add(self.outsider)

        sub_in(
            self.other,
            self.outsider,
            self.o1,
            actor=self.actor,
            via=TeamLogVia.WEB,
            reason="r",
        )

        other = self.refresh(self.other)
        self.assertEqual(self.member_pks(other), {self.outsider.pk})
        self.assertEqual(other.captain_id, self.outsider.pk)
        self.assertTrue(self.tournament.users.filter(pk=self.outsider.pk).exists())

    def test_sub_in_non_standin_refused(self) -> None:
        with self.assertRaises(TeamManagementError) as ctx:
            self.sub(self.outsider)
        self.assertEqual(ctx.exception.code, "not_standin")
        self.assertIn("add them as a stand-in first", ctx.exception.message)
        self.assertFalse(TeamLog.objects.exists())

    def test_sub_in_replacing_non_member_refused(self) -> None:
        with self.assertRaises(TeamManagementError) as ctx:
            self.sub(self.standin, self.outsider)
        self.assertEqual(ctx.exception.code, "replacing_not_member")
        team = self.refresh(self.team)
        self.assertTrue(
            team.dropin_members.nocache().filter(pk=self.standin.pk).exists()
        )
        self.assertFalse(TeamLog.objects.exists())

    def test_sub_in_reason_covers_replaced_player(self) -> None:
        with self.assertRaises(TeamManagementError) as ctx:
            sub_in(
                self.team,
                self.standin,
                self.m1,
                actor=self.standin,
                via=TeamLogVia.WEB,
            )
        self.assertEqual(ctx.exception.code, "reason_required")


class AddStandinTests(TeamManagementFixture, TestCase):
    def add(self, user: CustomUser, **kwargs: Any) -> TeamChange:
        kwargs.setdefault("reason", "r")
        return add_standin(
            self.team, user, actor=self.actor, via=TeamLogVia.WEB, **kwargs
        )

    def fill_standins(self) -> None:
        for i in range(DEFAULT_MAX_STANDINS):
            self.team.dropin_members.add(self.make_user(f"roster_s{i}"))

    def test_add_standin(self) -> None:
        change = self.add(self.outsider)

        team = self.refresh(self.team)
        self.assertTrue(team.dropin_members.filter(pk=self.outsider.pk).exists())
        self.assertNotIn(self.outsider.pk, self.member_pks(team))
        self.assertFalse(self.tournament.users.filter(pk=self.outsider.pk).exists())
        row = self.only_log()
        self.assertEqual(change.log, row)
        self.assertEqual(change.overridden, [])
        self.assertEqual(row.action, TeamLogAction.ADD_STANDIN)
        self.assertEqual(row.target_user_id, self.outsider.pk)
        self.assertEqual(row.override_rules, [])
        self.assertNotIn("violations", row.details)
        self.assertEqual(row.details["before"]["dropin_ids"], [])
        self.assertEqual(row.details["after"]["dropin_ids"], [self.outsider.pk])

    def test_add_standin_already_on_team_refused(self) -> None:
        self.team.dropin_members.add(self.o1)
        self.team.left_members.add(self.outsider)
        Team.members.through.objects.filter(
            team_id=self.other.pk, customuser_id=self.o1.pk
        ).delete()
        for user in (self.m1, self.o1, self.outsider):
            with self.subTest(user=user.username):
                with self.assertRaises(TeamManagementError) as ctx:
                    self.add(user)
                self.assertEqual(ctx.exception.code, "already_on_team")
        self.assertFalse(TeamLog.objects.exists())

    def test_add_standin_on_other_team_refused(self) -> None:
        self.other.dropin_members.add(self.outsider)
        for user in (self.o1, self.outsider):
            with self.subTest(user=user.username):
                with self.assertRaises(TeamManagementError) as ctx:
                    self.add(user)
                self.assertEqual(ctx.exception.code, "on_other_team")
        self.assertFalse(self.refresh(self.team).dropin_members.nocache().exists())

    def test_add_standin_self_needs_no_reason(self) -> None:
        add_standin(self.team, self.outsider, actor=self.outsider, via=TeamLogVia.WEB)
        self.assertEqual(self.only_log().reason, "")

    def test_add_standin_reason_required(self) -> None:
        with self.assertRaises(TeamManagementError) as ctx:
            self.add(self.outsider, reason="")
        self.assertEqual(ctx.exception.code, "reason_required")

    def test_third_standin_requires_override(self) -> None:
        self.fill_standins()
        with self.assertRaises(OverrideRequired) as ctx:
            self.add(self.outsider)
        violations = ctx.exception.violations
        self.assertEqual([v.code for v in violations], ["team_standin_cap"])
        self.assertEqual(violations[0].category, "team")
        self.assertEqual(violations[0].rule, "override-warning")
        self.assertIn(str(DEFAULT_MAX_STANDINS), violations[0].message)
        team = self.refresh(self.team)
        self.assertEqual(team.dropin_members.count(), DEFAULT_MAX_STANDINS)
        self.assertFalse(TeamLog.objects.exists())

    def test_cap_comes_from_standin_cap(self) -> None:
        with patch.object(team_management, "standin_cap", return_value=0):
            with self.assertRaises(OverrideRequired) as ctx:
                self.add(self.outsider)
        self.assertEqual(
            [v.code for v in ctx.exception.violations], ["team_standin_cap"]
        )

    def test_override_acknowledged_with_reason(self) -> None:
        self.fill_standins()

        change = self.add(
            self.outsider,
            reason="league allows a third tonight",
            acknowledged_codes=["team_standin_cap"],
        )

        self.assertEqual(change.overridden, ["team_standin_cap"])
        team = self.refresh(self.team)
        self.assertEqual(team.dropin_members.count(), DEFAULT_MAX_STANDINS + 1)
        row = self.only_log()
        self.assertEqual(row.override_rules, ["team_standin_cap"])
        self.assertEqual(row.reason, "league allows a third tonight")
        self.assertEqual(
            [v["code"] for v in row.details["violations"]], ["team_standin_cap"]
        )
        self.assertEqual(row.details["violations"][0]["category"], "team")

    def test_override_without_reason(self) -> None:
        self.fill_standins()
        with self.assertRaises(OverrideReasonRequired):
            add_standin(
                self.team,
                self.outsider,
                actor=self.outsider,
                via=TeamLogVia.WEB,
                acknowledged_codes=["team_standin_cap"],
            )
        self.assertEqual(
            self.refresh(self.team).dropin_members.count(), DEFAULT_MAX_STANDINS
        )
        self.assertFalse(TeamLog.objects.exists())

    def test_silent_policy_still_raises(self) -> None:
        settings = get_org_settings(self.org)
        OrgSettings.objects.filter(pk=settings.pk).update(
            staff_override_policy=StaffOverridePolicy.SILENT
        )
        self.fill_standins()

        with patch.object(
            team_management, "check_overrides", wraps=team_management.check_overrides
        ) as spy:
            with self.assertRaises(OverrideRequired):
                self.add(self.outsider)

        passed = spy.call_args.kwargs["org_settings"]
        self.assertIsInstance(passed, OrgSettings)
        self.assertEqual(passed.pk, settings.pk)
        self.assertEqual(passed.staff_override_policy, StaffOverridePolicy.SILENT)

    def test_eligibility_violations_from_source_event(self) -> None:
        user = self.gate_event()
        event = Event.objects.get(pk=self.event.pk)
        expected = unmet_codes(event, user)
        self.assertIn("below_min_mmr", expected)
        self.assertIn("steam_id_missing", expected)

        with self.assertRaises(OverrideRequired) as ctx:
            self.add(user)

        violations = ctx.exception.violations
        self.assertCountEqual([v.code for v in violations], expected)
        for v in violations:
            self.assertEqual(v.category, "eligibility")
            self.assertEqual(v.rule, "staff-override")
            self.assertEqual(v.message, UNMET_LABELS[Unmet(v.code)])
        self.assertFalse(TeamLog.objects.exists())

    def test_eligibility_override_recorded(self) -> None:
        user = self.gate_event()
        codes = unmet_codes(Event.objects.get(pk=self.event.pk), user)

        change = self.add(user, reason="verified by staff", acknowledged_codes=codes)

        self.assertCountEqual(change.overridden, codes)
        row = self.only_log()
        self.assertCountEqual(row.override_rules, codes)
        self.assertCountEqual([v["code"] for v in row.details["violations"]], codes)

    def test_no_source_event_no_eligibility_check(self) -> None:
        user = self.gate_event()
        Event.objects.filter(pk=self.event.pk).update(tournament=None)

        change = self.add(user)

        self.assertEqual(change.overridden, [])
        self.assertTrue(
            self.refresh(self.team).dropin_members.filter(pk=user.pk).exists()
        )

    def test_standin_cap_default(self) -> None:
        Event.objects.filter(pk=self.event.pk).update(tournament=None)
        self.assertEqual(standin_cap(self.team), DEFAULT_MAX_STANDINS)
        self.fill_standins()
        with self.assertRaises(OverrideRequired) as ctx:
            self.add(self.outsider)
        self.assertEqual(
            [v.code for v in ctx.exception.violations], ["team_standin_cap"]
        )


class DraftBookkeepingTests(TeamManagementFixture, TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.p1 = self.make_user("roster_p1")
        self.p2 = self.make_user("roster_p2")
        self.tournament.users.add(self.p1, self.p2)
        self.draft = Draft.objects.create(
            tournament=self.tournament,
            state=TeamDraftState.DRAFTING,
            draft_style="snake",
        )
        staff = CustomUser.objects.create_superuser(
            username="roster_admin", password="test"
        )
        self.client = APIClient()
        self.client.force_authenticate(staff)

    def pick(self, captain: CustomUser, player: CustomUser, number: int) -> DraftRound:
        draft_round = DraftRound.objects.create(
            draft=self.draft, captain=captain, pick_number=number, choice=player
        )
        Team.objects.get(captain=captain, tournament=self.tournament).members.add(
            player
        )
        return draft_round

    def undo(self) -> Any:
        with self.captureOnCommitCallbacks(execute=True):
            return self.client.post(
                "/api/tournaments/undo-pick", {"draft_pk": self.draft.pk}, format="json"
            )

    def pool(self) -> set[int]:
        fresh = Draft.objects.nocache().get(pk=self.draft.pk)
        remaining = set(fresh.users_remaining.values_list("pk", flat=True))
        state = tournament_state_queryset(fresh=True).get(pk=self.tournament.pk)
        self.assertEqual(set(users_remaining_pks(state.draft)), remaining)
        return remaining

    def test_dropout_not_in_pool(self) -> None:
        DraftRound.objects.create(draft=self.draft, captain=self.c, pick_number=1)

        mark_dropout(
            self.team, self.m1, actor=self.actor, via=TeamLogVia.WEB, reason="r"
        )

        self.assertNotIn(self.m1.pk, self.pool())

    def test_dropped_out_captain_not_in_pool(self) -> None:
        DraftRound.objects.create(draft=self.draft, captain=self.c, pick_number=1)

        mark_dropout(
            self.team, self.c, actor=self.actor, via=TeamLogVia.WEB, reason="r"
        )

        self.assertNotIn(self.c.pk, self.pool())

    def test_undo_pick_of_new_captain_refused(self) -> None:
        last = self.pick(self.c, self.p1, 1)
        set_captain(
            self.team, self.p1, actor=self.actor, via=TeamLogVia.WEB, reason="r"
        )

        response = self.undo()

        self.assertEqual(response.status_code, 409, response.content)
        self.assertEqual(response.json()["code"], "pick_is_captain")
        team = self.refresh(self.team)
        self.assertEqual(team.captain_id, self.p1.pk)
        self.assertIn(self.p1.pk, self.member_pks(team))
        self.assertEqual(
            DraftRound.objects.nocache().get(pk=last.pk).choice_id, self.p1.pk
        )
        self.assertFalse(
            TeamLog.objects.filter(action=TeamLogAction.SYSTEM_SUCCESSION).exists()
        )

    def test_undo_pick_of_dropout_clears_dropout(self) -> None:
        last = self.pick(self.c, self.p1, 1)
        mark_dropout(
            self.team, self.p1, actor=self.actor, via=TeamLogVia.WEB, reason="r"
        )
        self.assertNotIn(self.p1.pk, self.pool())

        response = self.undo()

        self.assertEqual(response.status_code, 200, response.content)
        team = self.refresh(self.team)
        self.assertFalse(team.left_members.nocache().filter(pk=self.p1.pk).exists())
        self.assertIsNone(DraftRound.objects.nocache().get(pk=last.pk).choice_id)
        self.assertIn(self.p1.pk, self.pool())

    def test_rounds_stay_when_old_captain_leads_another_team(self) -> None:
        Team.objects.filter(pk=self.other.pk).update(captain=self.c)
        draft_round = DraftRound.objects.create(
            draft=self.draft, captain=self.c, pick_number=1
        )

        change = set_captain(
            self.team, self.m1, actor=self.actor, via=TeamLogVia.WEB, reason="r"
        )

        self.assertEqual(
            DraftRound.objects.nocache().get(pk=draft_round.pk).captain_id, self.c.pk
        )
        self.assertEqual(change.log.details["draft_rounds_updated"], 0)
        self.assertEqual(
            change.log.details["draft_rounds_skipped_reason"],
            "old_captain_leads_other_team",
        )

    def test_rebuild_with_rounds_refused_after_staff_changes(self) -> None:
        self.pick(self.c, self.p1, 1)
        add_standin(
            self.team, self.p2, actor=self.actor, via=TeamLogVia.WEB, reason="r"
        )

        response = self.client.post(
            "/api/tournaments/draft-rebuild",
            {"tournament_pk": self.tournament.pk},
            format="json",
        )

        self.assertEqual(response.status_code, 409, response.content)
        self.assertEqual(response.json()["code"], "team_changes_logged")
        team = self.refresh(self.team)
        self.assertTrue(team.dropin_members.nocache().filter(pk=self.p2.pk).exists())
        self.assertIn(self.m1.pk, self.member_pks(team))

    def test_rebuild_skips_dropped_out_picks(self) -> None:
        self.pick(self.c, self.p1, 1)
        self.team.members.remove(self.p1)
        self.team.left_members.add(self.p1)

        self.draft.rebuild_teams()

        self.assertNotIn(self.p1.pk, self.member_pks(self.team))


class ReseatGhostDeputyTests(TeamManagementFixture, TestCase):
    def test_reseat_ghost_captain_who_is_also_deputy(self) -> None:
        team = self.drop_member_silently(self.team, self.c)
        Team.objects.filter(pk=team.pk).update(deputy_captain=self.c)

        change = set_captain(
            self.team, self.c, actor=self.actor, via=TeamLogVia.WEB, reason="r"
        )

        team = self.refresh(self.team)
        self.assertEqual(team.captain_id, self.c.pk)
        self.assertIsNone(team.deputy_captain_id)
        self.assertIn(self.c.pk, self.member_pks(team))
        self.assertEqual(_problems(team), {})
        self.assertIsNone(change.log.details["after"]["deputy_captain_id"])


class SubInTournamentUserTests(TeamManagementFixture, TestCase):
    def test_sub_in_adds_standin_to_tournament(self) -> None:
        standin = self.make_user("roster_sub")
        self.team.dropin_members.add(standin)

        change = sub_in(
            self.team, standin, actor=self.actor, via=TeamLogVia.WEB, reason="r"
        )

        self.assertTrue(self.tournament.users.filter(pk=standin.pk).exists())
        self.assertTrue(change.log.details["added_to_tournament"])
        self.assertTrue(
            LeagueUser.objects.filter(user=standin, league=self.league).exists()
        )
        self.assertTrue(change.log.details["league_user_created"])
        self.assertFalse(change.log.details["org_user_created"])

    def test_sub_in_existing_tournament_user_not_flagged(self) -> None:
        standin = self.make_user("roster_sub2")
        self.tournament.users.add(standin)
        self.team.dropin_members.add(standin)

        change = sub_in(
            self.team, standin, actor=self.actor, via=TeamLogVia.WEB, reason="r"
        )

        self.assertNotIn("added_to_tournament", change.log.details)


class TournamentCacheTests(TeamManagementFixture, TransactionTestCase):
    def setUp(self) -> None:
        if not _redis_reachable():
            self.skipTest("Cacheops Redis not reachable")
        super().setUp()

    def roster(self, client: APIClient) -> dict[str, Any]:
        data = client.get(f"/api/tournaments/{self.tournament.pk}/").json()
        return next(t for t in data["teams"] if t["pk"] == self.team.pk)

    def pks(self, entries: list[Any]) -> set[int]:
        return {e["pk"] if isinstance(e, dict) else e for e in entries}

    def test_dropout_visible_through_tournament_cache(self) -> None:
        client = APIClient()
        self.assertIn(self.m1.pk, self.pks(self.roster(client)["members"]))

        mark_dropout(
            self.team, self.m1, actor=self.actor, via=TeamLogVia.WEB, reason="r"
        )

        team = self.roster(client)
        self.assertNotIn(self.m1.pk, self.pks(team["members"]))
        self.assertIn(self.m1.pk, self.pks(team["left_members"]))

    def test_standin_visible_through_tournament_cache(self) -> None:
        client = APIClient()
        self.assertEqual(self.pks(self.roster(client)["dropin_members"]), set())

        add_standin(
            self.team, self.outsider, actor=self.actor, via=TeamLogVia.WEB, reason="r"
        )

        self.assertEqual(
            self.pks(self.roster(client)["dropin_members"]), {self.outsider.pk}
        )
