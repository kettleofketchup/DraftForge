from unittest.mock import MagicMock, patch

from structlog.testing import capture_logs

from app.models import CustomUser, Game, Team, Tournament
from events.constants import EventState, SignupStatus
from events.models import Event, EventSignup
from events.roster import (
    RosterPhase,
    joins_roster,
    roster_phase,
    roster_statuses,
    team_bound_user_pks,
)
from events.services import (
    approve_signup,
    cancel_signup,
    confirm_signup,
    create_tournament_for_event,
    demote_to_waitlist,
    reinstate_signup,
    reject_signup,
    staff_add_signup,
    unconfirm_signup,
)
from events.tests.base import EventTestCase


@patch("events.services.notify_signup_changed")
@patch("events.services.notify_mark_interested")
class RosterRuleTests(EventTestCase):
    def _event(
        self, *, state: str, roll_call_enabled: bool = False, **extra: object
    ) -> Event:
        event = self.make_event(
            state=state, roll_call_enabled=roll_call_enabled, **extra
        )
        create_tournament_for_event(event)
        event.refresh_from_db()
        return event

    def _signup(
        self, event: Event, user: CustomUser, status: str, **extra: object
    ) -> EventSignup:
        return EventSignup.objects.create(
            event=event, user=user, status=status, **extra
        )

    def _roster(self, event: Event) -> set[int]:
        tournament = Tournament.objects.nocache().get(pk=event.tournament_id)
        return set(tournament.users.values_list("pk", flat=True))

    def _team(self, event: Event, members: list[CustomUser]) -> tuple[Team, Game]:
        tournament = event.tournament
        tournament.users.add(*members)
        team = Team.objects.create(
            tournament=tournament, name="Roster Team", captain=members[0]
        )
        team.members.add(*members)
        game = Game.objects.create(tournament=tournament, radiant_team=team)
        return team, game

    def _team_state(self, team: Team) -> tuple[int, int | None, set[int]]:
        fresh = Team.objects.nocache().get(pk=team.pk)
        return (
            fresh.pk,
            fresh.captain_id,
            set(fresh.members.values_list("pk", flat=True)),
        )

    def test_statuses_per_phase(self, *_mocks: MagicMock) -> None:
        both = frozenset({SignupStatus.APPROVED, SignupStatus.CONFIRMED})
        confirmed = frozenset({SignupStatus.CONFIRMED})
        flag_off = self.make_event(roll_call_enabled=False)
        flag_on = self.make_event(roll_call_enabled=True)

        self.assertEqual(roster_statuses(flag_off, RosterPhase.SIGNUPS), both)
        self.assertEqual(roster_statuses(flag_on, RosterPhase.SIGNUPS), confirmed)
        for event in (flag_off, flag_on):
            self.assertEqual(roster_statuses(event, RosterPhase.ROLL_CALL), confirmed)
            self.assertEqual(
                roster_statuses(event, RosterPhase.START_FROM_SIGNUPS), both
            )

    def test_phase_follows_state(self, *_mocks: MagicMock) -> None:
        roll_call = self.make_event(state=EventState.ROLL_CALL)
        signups = self.make_event(state=EventState.SIGNUPS_OPEN)
        self.assertEqual(roster_phase(roll_call), RosterPhase.ROLL_CALL)
        self.assertEqual(roster_phase(signups), RosterPhase.SIGNUPS)
        self.assertFalse(joins_roster(roll_call, SignupStatus.APPROVED))
        self.assertTrue(joins_roster(signups, SignupStatus.APPROVED))
        self.assertFalse(joins_roster(signups, SignupStatus.WAITLISTED))

    def test_team_bound_user_pks(self, *_mocks: MagicMock) -> None:
        event = self._event(state=EventState.SIGNUPS_OPEN)
        member, deputy, outsider = self.make_user(), self.make_user(), self.make_user()
        team, _game = self._team(event, [member])
        team.deputy_captain = deputy
        team.save(update_fields=["deputy_captain"])
        self.assertEqual(team_bound_user_pks(event.tournament), {member.pk, deputy.pk})
        self.assertNotIn(outsider.pk, team_bound_user_pks(event.tournament))

    def test_approve_in_roll_call_flag_off_not_added(self, *_mocks: MagicMock) -> None:
        event = self._event(state=EventState.ROLL_CALL)
        user = self.make_user()
        signup = self._signup(event, user, SignupStatus.RSVP)
        approve_signup(signup)
        self.assertNotIn(user.pk, self._roster(event))

    def test_approve_in_signups_flag_off_added(self, *_mocks: MagicMock) -> None:
        event = self._event(state=EventState.SIGNUPS_OPEN)
        user = self.make_user()
        signup = self._signup(event, user, SignupStatus.RSVP)
        approve_signup(signup)
        self.assertIn(user.pk, self._roster(event))

    def test_staff_add_auto_approve_in_roll_call_not_added(
        self, *_mocks: MagicMock
    ) -> None:
        event = self._event(state=EventState.ROLL_CALL)
        user = self.make_user()
        signup = staff_add_signup(event, user)
        self.assertEqual(signup.status, SignupStatus.APPROVED)
        self.assertNotIn(user.pk, self._roster(event))

    def test_promotion_in_roll_call_not_added(self, *_mocks: MagicMock) -> None:
        event = self._event(state=EventState.ROLL_CALL, max_players=1)
        seated, waiting = self.make_user(), self.make_user()
        seated_signup = self._signup(event, seated, SignupStatus.CONFIRMED)
        event.tournament.users.add(seated)
        waiting_signup = self._signup(
            event, waiting, SignupStatus.WAITLISTED, waitlist_position=1
        )
        cancel_signup(seated_signup)
        waiting_signup.refresh_from_db()
        self.assertEqual(waiting_signup.status, SignupStatus.APPROVED)
        self.assertNotIn(waiting.pk, self._roster(event))

    def test_unconfirm_in_signups_flag_off_keeps_player(
        self, *_mocks: MagicMock
    ) -> None:
        event = self._event(state=EventState.SIGNUPS_OPEN)
        user = self.make_user()
        signup = self._signup(event, user, SignupStatus.CONFIRMED)
        event.tournament.users.add(user)
        unconfirm_signup(signup)
        self.assertIn(user.pk, self._roster(event))

    def test_unconfirm_in_roll_call_removes_player(self, *_mocks: MagicMock) -> None:
        event = self._event(state=EventState.ROLL_CALL)
        user = self.make_user()
        signup = self._signup(event, user, SignupStatus.CONFIRMED)
        event.tournament.users.add(user)
        unconfirm_signup(signup)
        self.assertNotIn(user.pk, self._roster(event))

    def test_confirm_adds(self, *_mocks: MagicMock) -> None:
        event = self._event(state=EventState.ROLL_CALL, roll_call_enabled=True)
        user = self.make_user()
        signup = self._signup(event, user, SignupStatus.APPROVED)
        confirm_signup(signup)
        self.assertIn(user.pk, self._roster(event))

    def test_approve_in_roll_call_keeps_team_member(self, *_mocks: MagicMock) -> None:
        event = self._event(state=EventState.ROLL_CALL)
        captain, member = self.make_user(), self.make_user()
        team, game = self._team(event, [captain, member])
        before = self._team_state(team)
        signup = self._signup(event, member, SignupStatus.CANCELLED)

        reinstate_signup(signup)
        demote_to_waitlist(signup)
        approve_signup(signup)

        self.assertEqual(self._team_state(team), before)
        self.assertTrue(Game.objects.nocache().filter(pk=game.pk).exists())
        self.assertIn(member.pk, self._roster(event))

    def test_cancel_team_member_not_removed(self, *_mocks: MagicMock) -> None:
        event = self._event(state=EventState.SIGNUPS_OPEN)
        captain, member = self.make_user(), self.make_user()
        team, game = self._team(event, [captain, member])
        before = self._team_state(team)
        signup = self._signup(event, member, SignupStatus.APPROVED)

        with capture_logs() as logs:
            cancel_signup(signup)

        self.assertEqual(self._team_state(team), before)
        self.assertTrue(Game.objects.nocache().filter(pk=game.pk).exists())
        self.assertIn(member.pk, self._roster(event))
        skipped = [
            entry
            for entry in logs
            if entry["event"] == "event_roster_sync_skipped_team_member"
        ]
        self.assertEqual(len(skipped), 1)
        self.assertEqual(skipped[0]["user_id"], member.pk)

    def test_reject_team_captain_not_removed(self, *_mocks: MagicMock) -> None:
        event = self._event(state=EventState.SIGNUPS_OPEN)
        captain, member = self.make_user(), self.make_user()
        team, _game = self._team(event, [captain, member])
        before = self._team_state(team)
        reject_signup(self._signup(event, captain, SignupStatus.CONFIRMED))
        self.assertEqual(self._team_state(team), before)
        self.assertIn(captain.pk, self._roster(event))

    def test_cancel_outside_team_removes(self, *_mocks: MagicMock) -> None:
        event = self._event(state=EventState.SIGNUPS_OPEN)
        user = self.make_user()
        signup = self._signup(event, user, SignupStatus.APPROVED)
        event.tournament.users.add(user)
        cancel_signup(signup)
        self.assertNotIn(user.pk, self._roster(event))
