from datetime import time
from functools import partial
from unittest.mock import MagicMock, patch

from django.utils import timezone as tz
from rest_framework.test import APIClient
from structlog.testing import capture_logs

from app.models import CustomUser
from events.constants import EventState, SignupStatus
from events.ledger import SignupActor
from events.models import Event, EventRepeater, EventSignup
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
    ensure_tournament_with_signups,
    reinstate_signup,
    reject_signup,
    restart_event_tournament,
    staff_add_signup,
    sync_event_roster,
    sync_future_events,
    unconfirm_signup,
)
from events.tests.actors import SYSTEM
from events.tests.base import EventTestCase
from tournament.models import Game, Team, Tournament


class RosterTestCase(EventTestCase):
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


@patch("events.services.notify_signup_changed")
@patch("events.services.notify_mark_interested")
class RosterRuleTests(RosterTestCase):
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
        approve_signup(signup, actor=SYSTEM)
        self.assertNotIn(user.pk, self._roster(event))

    def test_approve_in_signups_flag_off_added(self, *_mocks: MagicMock) -> None:
        event = self._event(state=EventState.SIGNUPS_OPEN)
        user = self.make_user()
        signup = self._signup(event, user, SignupStatus.RSVP)
        approve_signup(signup, actor=SYSTEM)
        self.assertIn(user.pk, self._roster(event))

    def test_staff_add_auto_approve_in_roll_call_not_added(
        self, *_mocks: MagicMock
    ) -> None:
        event = self._event(state=EventState.ROLL_CALL)
        user = self.make_user()
        signup = staff_add_signup(event, user, actor=SYSTEM)
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
        cancel_signup(seated_signup, actor=SYSTEM)
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
        unconfirm_signup(signup, actor=SYSTEM)
        self.assertIn(user.pk, self._roster(event))

    def test_unconfirm_in_roll_call_removes_player(self, *_mocks: MagicMock) -> None:
        event = self._event(state=EventState.ROLL_CALL)
        user = self.make_user()
        signup = self._signup(event, user, SignupStatus.CONFIRMED)
        event.tournament.users.add(user)
        unconfirm_signup(signup, actor=SYSTEM)
        self.assertNotIn(user.pk, self._roster(event))

    def test_confirm_adds(self, *_mocks: MagicMock) -> None:
        event = self._event(state=EventState.ROLL_CALL, roll_call_enabled=True)
        user = self.make_user()
        signup = self._signup(event, user, SignupStatus.APPROVED)
        confirm_signup(signup, actor=SYSTEM)
        self.assertIn(user.pk, self._roster(event))

    def test_approve_in_roll_call_keeps_team_member(self, *_mocks: MagicMock) -> None:
        event = self._event(state=EventState.ROLL_CALL)
        captain, member, waiting = self.make_user(), self.make_user(), self.make_user()
        team, game = self._team(event, [captain, member, waiting])
        before = self._team_state(team)

        reinstate_signup(
            self._signup(event, member, SignupStatus.CANCELLED), actor=SYSTEM
        )
        approve_signup(
            self._signup(event, waiting, SignupStatus.WAITLISTED, waitlist_position=1),
            actor=SYSTEM,
        )

        self.assertEqual(self._team_state(team), before)
        self.assertTrue(Game.objects.nocache().filter(pk=game.pk).exists())
        self.assertTrue({member.pk, waiting.pk} <= self._roster(event))

    def test_explicit_removals_drop_team_members(self, *_mocks: MagicMock) -> None:
        actions = {
            "cancel": (SignupStatus.APPROVED, EventState.SIGNUPS_OPEN, cancel_signup),
            "reject": (
                SignupStatus.CONFIRMED,
                EventState.SIGNUPS_OPEN,
                partial(reject_signup, actor=SignupActor.system()),
            ),
            "demote": (
                SignupStatus.APPROVED,
                EventState.SIGNUPS_OPEN,
                demote_to_waitlist,
            ),
            "unconfirm": (
                SignupStatus.CONFIRMED,
                EventState.ROLL_CALL,
                partial(unconfirm_signup, actor=SignupActor.system()),
            ),
        }
        for name, (status, state, action) in actions.items():
            with self.subTest(action=name):
                event = self._event(state=state)
                captain, member = self.make_user(), self.make_user()
                team, _game = self._team(event, [captain, member])
                action(self._signup(event, member, status), actor=SYSTEM)
                self.assertNotIn(member.pk, self._roster(event))
                self.assertNotIn(member.pk, self._team_state(team)[2])

    def test_reject_team_captain_removed(self, *_mocks: MagicMock) -> None:
        event = self._event(state=EventState.SIGNUPS_OPEN)
        captain, member = self.make_user(), self.make_user()
        self._team(event, [captain, member])
        reject_signup(
            self._signup(event, captain, SignupStatus.CONFIRMED), actor=SYSTEM
        )
        self.assertNotIn(captain.pk, self._roster(event))

    def test_cancel_outside_team_removes(self, *_mocks: MagicMock) -> None:
        event = self._event(state=EventState.SIGNUPS_OPEN)
        user = self.make_user()
        signup = self._signup(event, user, SignupStatus.APPROVED)
        event.tournament.users.add(user)
        cancel_signup(signup, actor=SYSTEM)
        self.assertNotIn(user.pk, self._roster(event))


@patch("events.services.notify_signup_changed")
@patch("events.services.notify_mark_interested")
class RosterSyncTests(RosterTestCase):
    def _staff_client(self) -> APIClient:
        client = APIClient()
        client.force_authenticate(user=self.admin)
        return client

    def _approved_and_confirmed(
        self, event: Event, *, on_roster: bool = True
    ) -> tuple[CustomUser, CustomUser]:
        approved, confirmed = self.make_user(), self.make_user()
        self._signup(event, approved, SignupStatus.APPROVED)
        self._signup(event, confirmed, SignupStatus.CONFIRMED)
        if on_roster:
            event.tournament.users.add(approved, confirmed)
        return approved, confirmed

    def test_enter_roll_call_drops_unconfirmed_keeps_confirmed(
        self, *_mocks: MagicMock
    ) -> None:
        event = self._event(state=EventState.SIGNUPS_OPEN)
        approved, confirmed = self._approved_and_confirmed(event)

        resp = self._staff_client().post(f"/api/events/{event.pk}/start_roll_call/")

        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(self._roster(event), {confirmed.pk})
        self.assertEqual(resp.json()["roster_kept_on_team"], [])

    def test_reopen_flag_off_readds_approved(self, *_mocks: MagicMock) -> None:
        event = self._event(state=EventState.ROLL_CALL)
        approved, confirmed = self._approved_and_confirmed(event, on_roster=False)

        resp = self._staff_client().post(f"/api/events/{event.pk}/reopen_signups/")

        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(self._roster(event), {approved.pk, confirmed.pk})

    def test_reopen_flag_on_does_not_readd(self, *_mocks: MagicMock) -> None:
        event = self._event(state=EventState.ROLL_CALL, roll_call_enabled=True)
        _approved, confirmed = self._approved_and_confirmed(event, on_roster=False)

        resp = self._staff_client().post(f"/api/events/{event.pk}/reopen_signups/")

        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(self._roster(event), {confirmed.pk})

    def test_ensure_honours_flag_outside_roll_call(self, *_mocks: MagicMock) -> None:
        event = self._event(state=EventState.SIGNUPS_OPEN, roll_call_enabled=True)
        approved, confirmed = self._approved_and_confirmed(event, on_roster=False)

        result = sync_event_roster(event)

        self.assertEqual(self._roster(event), {confirmed.pk})
        self.assertEqual(result.added, [confirmed])
        ensure_tournament_with_signups(event, RosterPhase.SIGNUPS)
        self.assertNotIn(approved.pk, self._roster(event))

    def test_team_member_survives_roll_call_round_trip(
        self, *_mocks: MagicMock
    ) -> None:
        event = self._event(state=EventState.SIGNUPS_OPEN)
        captain, member = self.make_user(), self.make_user()
        self._signup(event, captain, SignupStatus.CONFIRMED)
        self._signup(event, member, SignupStatus.APPROVED)
        team, game = self._team(event, [captain, member])
        before = self._team_state(team)
        client = self._staff_client()

        with capture_logs() as logs:
            resp = client.post(f"/api/events/{event.pk}/start_roll_call/")
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertIn(member.pk, resp.json()["roster_kept_on_team"])
        self.assertTrue(
            any(
                entry["event"] == "event_roster_sync_skipped_team_member"
                and entry["user_id"] == member.pk
                for entry in logs
            )
        )
        self.assertTrue(
            any(entry["event"] == "event_roster_synced_on_roll_call" for entry in logs)
        )

        resp = client.post(f"/api/events/{event.pk}/reopen_signups/")
        self.assertEqual(resp.status_code, 200, resp.content)

        self.assertEqual(self._team_state(team), before)
        self.assertEqual(before[2], {captain.pk, member.pk})
        self.assertTrue(Game.objects.nocache().filter(pk=game.pk).exists())
        self.assertEqual(self._roster(event), {captain.pk, member.pk})

    def test_flag_patch_resyncs(self, *_mocks: MagicMock) -> None:
        event = self._event(state=EventState.SIGNUPS_OPEN)
        approved, confirmed = self._approved_and_confirmed(event)

        with self.captureOnCommitCallbacks(execute=True):
            resp = self._staff_client().patch(
                f"/api/events/{event.pk}/",
                {"roll_call_enabled": True},
                format="json",
            )

        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(self._roster(event), {confirmed.pk})

    def test_flag_patch_outside_signups_does_not_sync(self, *_mocks: MagicMock) -> None:
        event = self._event(state=EventState.UPCOMING)
        with (
            patch("events.views.sync_event_roster") as sync,
            self.captureOnCommitCallbacks(execute=True),
        ):
            resp = self._staff_client().patch(
                f"/api/events/{event.pk}/",
                {"roll_call_enabled": True},
                format="json",
            )
        self.assertEqual(resp.status_code, 200, resp.content)
        sync.assert_not_called()

    def test_unrelated_patch_does_not_sync(self, *_mocks: MagicMock) -> None:
        event = self._event(state=EventState.SIGNUPS_OPEN)
        with (
            patch("events.views.sync_event_roster") as sync,
            self.captureOnCommitCallbacks(execute=True),
        ):
            resp = self._staff_client().patch(
                f"/api/events/{event.pk}/", {"name": "Renamed"}, format="json"
            )
        self.assertEqual(resp.status_code, 200, resp.content)
        sync.assert_not_called()

    def test_series_cascade_leaves_open_event_roster(self, *_mocks: MagicMock) -> None:
        repeater = EventRepeater.objects.create(
            organization=self.org,
            name="Roster Series",
            day_of_week=1,
            time_of_day=time(20, 0),
            timezone="UTC",
            starts_at=tz.now().date(),
        )
        event = self._event(state=EventState.SIGNUPS_OPEN, event_repeater=repeater)
        approved, confirmed = self._approved_and_confirmed(event)
        repeater.roll_call_enabled = True
        repeater.save(update_fields=["roll_call_enabled"])

        with self.captureOnCommitCallbacks(execute=True):
            touched = sync_future_events(repeater)

        self.assertNotIn(event.pk, {e.pk for e in touched})
        self.assertEqual(self._roster(event), {approved.pk, confirmed.pk})

    def test_event_without_tournament_enter_roll_call(self, *_mocks: MagicMock) -> None:
        event = self.make_event(state=EventState.SIGNUPS_OPEN)
        approved, confirmed = self.make_user(), self.make_user()
        self._signup(event, approved, SignupStatus.APPROVED)
        self._signup(event, confirmed, SignupStatus.CONFIRMED)

        resp = self._staff_client().post(f"/api/events/{event.pk}/start_roll_call/")

        self.assertEqual(resp.status_code, 200, resp.content)
        event.refresh_from_db()
        self.assertIsNotNone(event.tournament_id)
        self.assertEqual(self._roster(event), {confirmed.pk})

    def test_start_from_signups_keeps_approved_with_flag_on(
        self, *_mocks: MagicMock
    ) -> None:
        event = self._event(state=EventState.SIGNUPS_OPEN, roll_call_enabled=True)
        approved, confirmed = self._approved_and_confirmed(event, on_roster=False)

        resp = self._staff_client().post(f"/api/events/{event.pk}/start_tournament/")

        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(self._roster(event), {approved.pk, confirmed.pk})

    def test_restart_unchanged(self, *_mocks: MagicMock) -> None:
        for flag, expected in ((False, 2), (True, 1)):
            event = self._event(state=EventState.ROLL_CALL, roll_call_enabled=flag)
            self._approved_and_confirmed(event, on_roster=False)
            tournament = restart_event_tournament(event)
            event.refresh_from_db()
            self.assertEqual(event.state, EventState.SIGNUPS_OPEN)
            self.assertEqual(tournament.users.count(), expected)
