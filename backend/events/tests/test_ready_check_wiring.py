from unittest import mock

from django.test import override_settings
from rest_framework import status
from rest_framework.response import Response
from rest_framework.test import APIClient

from app.models import CustomUser
from events.constants import (
    ActorRole,
    EventState,
    SignupAction,
    SignupMeans,
    SignupStatus,
)
from events.ledger import SignupActor
from events.models import (
    Event,
    EventSignup,
    ReadyCheck,
    RollCallMode,
    SignupLedgerEntry,
)
from events.ready_check import (
    READY_CHECK_HELD_MESSAGE,
    close_ready_check,
    open_ready_check,
)
from events.ready_check_constants import (
    DROPPED_SIGNUP_MESSAGE,
    ReadyCheckConfirmVia,
    ReadyCheckEntryState,
    ReadyCheckLowCompletionAction,
    ReadyCheckOutcome,
    ReadyCheckPhase,
)
from events.services import create_tournament_for_event
from events.tests.base import EventTestCase
from tournament.models import Team

NOTIFY = "events.discord.dispatch.notify_signup_changed"
SERVICES_NOTIFY = "events.services.notify_signup_changed"
INTERNAL_TOKEN = "test-internal-token"


class WiringTestCase(EventTestCase):
    def setUp(self) -> None:
        for target in (NOTIFY, SERVICES_NOTIFY):
            patcher = mock.patch(target)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.host = self.make_user()
        self.helper = self.make_user()
        self.rc_event = self.make_event(host=self.host)
        self.rc_event.helpers.add(self.helper)
        self.staff_actor = SignupActor(
            user=self.admin, role=ActorRole.STAFF, means=SignupMeans.WEB
        )

    def _client(self, user: CustomUser | None) -> APIClient:
        client = APIClient()
        client.force_authenticate(user=user)
        return client

    def _post(
        self, user: CustomUser | None, path: str, data: dict[str, object] | None = None
    ) -> Response:
        with self.captureOnCommitCallbacks(execute=True):
            return self._client(user).post(path, data or {}, format="json")

    def _event_action(
        self, user: CustomUser | None, action: str, event: Event | None = None
    ) -> Response:
        target = event or self.rc_event
        return self._post(user, f"/api/events/{target.pk}/{action}/")

    def _signup_action(
        self, user: CustomUser | None, signup: EventSignup, action: str
    ) -> Response:
        return self._post(user, f"/api/events/signups/{signup.pk}/{action}/")

    def _signup(
        self,
        status_: str,
        *,
        event: Event | None = None,
        user: CustomUser | None = None,
    ) -> EventSignup:
        return EventSignup.objects.create(
            event=event or self.rc_event, user=user or self.make_user(), status=status_
        )

    def _checks(self, event: Event | None = None) -> list[ReadyCheck]:
        return list(
            ReadyCheck.objects.filter(event=event or self.rc_event).order_by("pk")
        )

    def _state(self, event: Event | None = None) -> str:
        return Event.objects.nocache().get(pk=(event or self.rc_event).pk).state

    def _status(self, signup: EventSignup) -> str:
        return EventSignup.objects.nocache().get(pk=signup.pk).status

    def _open(self, event: Event | None = None) -> ReadyCheck:
        target = event or self.rc_event
        with self.captureOnCommitCallbacks(execute=True):
            check = open_ready_check(target, actor=self.staff_actor).check
        target.refresh_from_db()
        return check


class StartRollCallTests(WiringTestCase):
    def test_host_and_helper_can_start_roll_call(self) -> None:
        for user in (self.host, self.helper):
            with self.subTest(user=user.username):
                event = self.make_event(host=self.host)
                event.helpers.add(self.helper)
                self._signup(SignupStatus.APPROVED, event=event)
                resp = self._event_action(user, "start_roll_call", event)
                self.assertEqual(resp.status_code, 200, resp.content)
                self.assertEqual(self._state(event), EventState.ROLL_CALL)
                (check,) = self._checks(event)
                self.assertEqual(check.phase, ReadyCheckPhase.OPEN)
                self.assertEqual(check.opened_by, user)
                self.assertIn("roster_kept_on_team", resp.json())

    def test_promoter_who_is_not_helper_is_forbidden(self) -> None:
        promoter = self.make_user()
        self.org.promoters.add(promoter)
        resp = self._event_action(promoter, "start_roll_call")
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(self._state(), EventState.SIGNUPS_OPEN)
        self.assertEqual(self._checks(), [])

    def test_unrelated_user_and_other_event_host_are_forbidden(self) -> None:
        other_host = self.make_user()
        self.make_event(host=other_host)
        for user in (self.unrelated_user, other_host):
            with self.subTest(user=user.username):
                resp = self._event_action(user, "start_roll_call")
                self.assertIn(resp.status_code, (403, 404))
        self.assertEqual(self._checks(), [])

    def test_repeat_call_returns_same_payload(self) -> None:
        first = self._event_action(self.admin, "start_roll_call")
        second = self._event_action(self.admin, "start_roll_call")
        self.assertEqual(first.status_code, 200, first.content)
        self.assertEqual(second.status_code, 200, second.content)
        self.assertEqual(set(first.json()), set(second.json()))
        self.assertEqual(len(self._checks()), 1)

    def test_roll_call_without_check_creates_one(self) -> None:
        Event.objects.filter(pk=self.rc_event.pk).update(state=EventState.ROLL_CALL)
        resp = self._event_action(self.admin, "start_roll_call")
        self.assertEqual(resp.status_code, 200, resp.content)
        (check,) = self._checks()
        self.assertEqual(check.phase, ReadyCheckPhase.OPEN)

    def test_teams_made_enters_roll_call_without_check(self) -> None:
        create_tournament_for_event(self.rc_event)
        self.rc_event.refresh_from_db()
        captain = self.make_user()
        Team.objects.create(
            tournament=self.rc_event.tournament, name="Early Team", captain=captain
        )
        resp = self._event_action(self.helper, "start_roll_call")
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(self._state(), EventState.ROLL_CALL)
        self.assertEqual(self._checks(), [])

    def test_from_upcoming_is_400(self) -> None:
        Event.objects.filter(pk=self.rc_event.pk).update(state=EventState.UPCOMING)
        resp = self._event_action(self.admin, "start_roll_call")
        self.assertEqual(resp.status_code, 400, resp.content)
        self.assertEqual(self._checks(), [])


class ReopenSignupsTests(WiringTestCase):
    def test_reopen_cancels_check_and_roll_call_restarts(self) -> None:
        check = self._open()
        resp = self._event_action(self.admin, "reopen_signups")
        self.assertEqual(resp.status_code, 200, resp.content)
        check.refresh_from_db()
        self.assertEqual(check.phase, ReadyCheckPhase.CANCELLED)
        self.assertEqual(self._state(), EventState.SIGNUPS_OPEN)
        transition = SignupLedgerEntry.objects.get(
            event=self.rc_event,
            action=SignupAction.READY_CHECK_TRANSITION,
            correlation_id=f"rc{check.pk}:cancel",
        )
        self.assertEqual(transition.reason, "reopened")
        self.assertEqual(transition.actor_user, self.admin)

        again = self._event_action(self.admin, "start_roll_call")
        self.assertEqual(again.status_code, 200, again.content)
        phases = [c.phase for c in self._checks()]
        self.assertEqual(phases, [ReadyCheckPhase.CANCELLED, ReadyCheckPhase.OPEN])


class StartTournamentTests(WiringTestCase):
    def test_closes_open_manual_check_and_starts_with_confirmed_only(self) -> None:
        event = self.make_event(host=self.host, roll_call_enabled=True)
        confirmed = self._signup(SignupStatus.CONFIRMED, event=event)
        approved = self._signup(SignupStatus.APPROVED, event=event)
        check = self._open(event)
        resp = self._event_action(self.admin, "start_tournament", event)
        self.assertEqual(resp.status_code, 200, resp.content)
        check.refresh_from_db()
        self.assertEqual(check.phase, ReadyCheckPhase.CLOSED)
        self.assertEqual(check.outcome, ReadyCheckOutcome.STAFF_VERIFIED)
        event.refresh_from_db()
        self.assertEqual(event.state, EventState.IN_PROGRESS)
        roster = set(event.tournament.users.values_list("pk", flat=True))
        self.assertIn(confirmed.user_id, roster)
        self.assertNotIn(approved.user_id, roster)
        self.assertEqual(self._status(approved), SignupStatus.APPROVED)

    def test_roll_call_without_check_starts_as_today(self) -> None:
        Event.objects.filter(pk=self.rc_event.pk).update(state=EventState.ROLL_CALL)
        self._signup(SignupStatus.CONFIRMED)
        resp = self._event_action(self.admin, "start_tournament")
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(self._state(), EventState.IN_PROGRESS)
        self.assertEqual(self._checks(), [])

    def test_helper_is_forbidden(self) -> None:
        self._open()
        resp = self._event_action(self.helper, "start_tournament")
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(self._state(), EventState.ROLL_CALL)


@override_settings(READY_CHECK_AUTOMATIC_LIVE=True)
class HeldStartTests(WiringTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.auto_event = self.make_event(
            host=self.host,
            roll_call_enabled=True,
            roll_call_mode=RollCallMode.AUTOMATIC,
            ready_check_low_completion_action=ReadyCheckLowCompletionAction.HOLD_FOR_STAFF,
            ready_check_min_completion_pct=70,
        )
        self.signups = [
            self._signup(SignupStatus.APPROVED, event=self.auto_event) for _ in range(4)
        ]
        self.check = self._open(self.auto_event)

    def _snapshot(self) -> tuple[str, str, int, list[str], set[int]]:
        event = Event.objects.nocache().get(pk=self.auto_event.pk)
        self.check.refresh_from_db()
        roster: set[int] = (
            set(event.tournament.users.values_list("pk", flat=True))
            if event.tournament_id
            else set()
        )
        return (
            event.state,
            self.check.phase,
            SignupLedgerEntry.objects.filter(event=event).count(),
            [self._status(s) for s in self.signups],
            roster,
        )

    def _assert_held_response(self, resp: Response) -> None:
        self.assertEqual(resp.status_code, status.HTTP_409_CONFLICT, resp.content)
        self.assertEqual(
            resp.json(),
            {"code": "ready_check_held", "error": READY_CHECK_HELD_MESSAGE},
        )

    def test_start_holds_and_commits_hold(self) -> None:
        resp = self._event_action(self.admin, "start_tournament", self.auto_event)
        self._assert_held_response(resp)
        self.check.refresh_from_db()
        self.assertEqual(self.check.phase, ReadyCheckPhase.HELD)
        self.assertEqual(self._state(self.auto_event), EventState.ROLL_CALL)
        held = SignupLedgerEntry.objects.filter(
            event=self.auto_event, action=SignupAction.READY_CHECK_HELD
        )
        self.assertEqual(held.count(), 4)
        self.assertTrue(
            all(r.correlation_id == f"rc{self.check.pk}:hold" for r in held)
        )

    def test_already_held_start_changes_nothing(self) -> None:
        with self.captureOnCommitCallbacks(execute=True):
            close_ready_check(self.auto_event, actor=self.staff_actor)
        before = self._snapshot()
        self.assertEqual(before[1], ReadyCheckPhase.HELD)
        resp = self._event_action(self.admin, "start_tournament", self.auto_event)
        self._assert_held_response(resp)
        self.assertEqual(self._snapshot(), before)

    def test_internal_transition_to_in_progress_holds(self) -> None:
        client = APIClient()
        with (
            override_settings(INTERNAL_SERVICE_TOKEN=INTERNAL_TOKEN),
            self.captureOnCommitCallbacks(execute=True),
        ):
            resp = client.post(
                f"/api/internal/events/{self.auto_event.pk}/transition/",
                {"state": EventState.IN_PROGRESS},
                format="json",
                HTTP_X_INTERNAL_TOKEN=INTERNAL_TOKEN,
            )
        self._assert_held_response(resp)
        self.check.refresh_from_db()
        self.assertEqual(self.check.phase, ReadyCheckPhase.HELD)
        self.assertEqual(self._state(self.auto_event), EventState.ROLL_CALL)


class StaffConfirmTests(WiringTestCase):
    def test_open_check_confirms_entry_via_staff(self) -> None:
        signup = self._signup(SignupStatus.APPROVED)
        check = self._open()
        resp = self._signup_action(self.admin, signup, "confirm")
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.json()["status"], SignupStatus.CONFIRMED)
        entry = check.entries.get(signup=signup)
        self.assertEqual(entry.state, ReadyCheckEntryState.CONFIRMED)
        self.assertEqual(entry.confirmed_via, ReadyCheckConfirmVia.STAFF)
        row = SignupLedgerEntry.objects.get(
            signup=signup, action=SignupAction.CONFIRMED
        )
        self.assertEqual(row.correlation_id, f"rc{check.pk}:confirm")
        self.assertEqual(row.actor_user, self.admin)
        self.assertEqual(row.actor_role, ActorRole.STAFF)

    def test_held_check_confirms_entry(self) -> None:
        signup = self._signup(SignupStatus.APPROVED)
        check = self._open()
        ReadyCheck.objects.filter(pk=check.pk).update(phase=ReadyCheckPhase.HELD)
        resp = self._signup_action(self.admin, signup, "confirm")
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(
            check.entries.get(signup=signup).state, ReadyCheckEntryState.CONFIRMED
        )
        self.assertEqual(self._status(signup), SignupStatus.CONFIRMED)

    def test_closed_check_falls_back_with_override(self) -> None:
        signup = self._signup(SignupStatus.APPROVED)
        check = self._open()
        with self.captureOnCommitCallbacks(execute=True):
            close_ready_check(self.rc_event, actor=self.staff_actor)
        check.refresh_from_db()
        self.assertEqual(check.phase, ReadyCheckPhase.CLOSED)
        resp = self._signup_action(self.admin, signup, "confirm")
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(self._status(signup), SignupStatus.CONFIRMED)
        self.assertEqual(
            check.entries.get(signup=signup).state, ReadyCheckEntryState.PENDING
        )
        row = SignupLedgerEntry.objects.get(
            signup=signup, action=SignupAction.CONFIRMED
        )
        self.assertEqual(row.rules_overridden, ["ready_check_closed"])
        self.assertEqual(row.actor_user, self.admin)
        self.assertEqual(row.before["status"], SignupStatus.APPROVED)
        self.assertEqual(row.after["status"], SignupStatus.CONFIRMED)

    def test_no_check_falls_back_to_plain_confirm(self) -> None:
        Event.objects.filter(pk=self.rc_event.pk).update(state=EventState.ROLL_CALL)
        signup = self._signup(SignupStatus.APPROVED)
        resp = self._signup_action(self.admin, signup, "confirm")
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(self._status(signup), SignupStatus.CONFIRMED)
        row = SignupLedgerEntry.objects.get(
            signup=signup, action=SignupAction.CONFIRMED
        )
        self.assertEqual(row.rules_overridden, [])
        self.assertEqual(row.correlation_id, "")

    def test_fallback_still_rejects_non_approved(self) -> None:
        Event.objects.filter(pk=self.rc_event.pk).update(state=EventState.ROLL_CALL)
        signup = self._signup(SignupStatus.RSVP)
        resp = self._signup_action(self.admin, signup, "confirm")
        self.assertEqual(resp.status_code, 400, resp.content)
        self.assertEqual(self._status(signup), SignupStatus.RSVP)
        self.assertFalse(
            SignupLedgerEntry.objects.filter(
                signup=signup, action=SignupAction.CONFIRMED
            ).exists()
        )


@override_settings(INTERNAL_SERVICE_TOKEN=INTERNAL_TOKEN)
class InternalTransitionTests(WiringTestCase):
    def _transition(self, new_state: str) -> Response:
        with self.captureOnCommitCallbacks(execute=True):
            return APIClient().post(
                f"/api/internal/events/{self.rc_event.pk}/transition/",
                {"state": new_state},
                format="json",
                HTTP_X_INTERNAL_TOKEN=INTERNAL_TOKEN,
            )

    def test_into_roll_call_opens_check(self) -> None:
        resp = self._transition(EventState.ROLL_CALL)
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.json()["state"], EventState.ROLL_CALL)
        (check,) = self._checks()
        self.assertEqual(check.phase, ReadyCheckPhase.OPEN)
        self.assertIsNone(check.opened_by)

    def test_roll_call_to_signups_open_cancels(self) -> None:
        check = self._open()
        resp = self._transition(EventState.SIGNUPS_OPEN)
        self.assertEqual(resp.status_code, 200, resp.content)
        check.refresh_from_db()
        self.assertEqual(check.phase, ReadyCheckPhase.CANCELLED)
        self.assertEqual(self._state(), EventState.SIGNUPS_OPEN)

    def test_roll_call_to_cancelled_cancels(self) -> None:
        check = self._open()
        resp = self._transition(EventState.CANCELLED)
        self.assertEqual(resp.status_code, 200, resp.content)
        check.refresh_from_db()
        self.assertEqual(check.phase, ReadyCheckPhase.CANCELLED)

    def test_roll_call_to_in_progress_closes_open_check(self) -> None:
        check = self._open()
        resp = self._transition(EventState.IN_PROGRESS)
        self.assertEqual(resp.status_code, 200, resp.content)
        check.refresh_from_db()
        self.assertEqual(check.phase, ReadyCheckPhase.CLOSED)
        self.assertEqual(self._state(), EventState.IN_PROGRESS)

    def test_roll_call_to_completed_ends_check(self) -> None:
        check = self._open()
        resp = self._transition(EventState.COMPLETED)
        self.assertEqual(resp.status_code, 200, resp.content)
        check.refresh_from_db()
        self.assertEqual(check.phase, ReadyCheckPhase.CANCELLED)

    def test_invalid_transition_still_400(self) -> None:
        Event.objects.filter(pk=self.rc_event.pk).update(state=EventState.UPCOMING)
        resp = self._transition(EventState.ROLL_CALL)
        self.assertEqual(resp.status_code, 400, resp.content)
        self.assertEqual(self._checks(), [])


class HelperStaffEndpointTests(WiringTestCase):
    """The operator role does not reach the other staff endpoints."""

    def test_helper_forbidden_on_staff_endpoints(self) -> None:
        create_tournament_for_event(self.rc_event)
        self._open()
        rsvp = self._signup(SignupStatus.RSVP)
        approved = self._signup(SignupStatus.APPROVED)
        cases: list[tuple[str, Response]] = [
            ("reopen_signups", self._event_action(self.helper, "reopen_signups")),
            ("start_tournament", self._event_action(self.helper, "start_tournament")),
            ("approve", self._signup_action(self.helper, rsvp, "approve")),
            ("reject", self._signup_action(self.helper, rsvp, "reject")),
            ("confirm", self._signup_action(self.helper, approved, "confirm")),
            (
                "conduct_attendance",
                self._client(self.helper).get(
                    f"/api/organizations/{self.org.pk}/conduct/events/"
                    f"{self.rc_event.pk}/attendance/"
                ),
            ),
        ]
        for name, resp in cases:
            with self.subTest(endpoint=name):
                self.assertEqual(resp.status_code, 403, resp.content)
        self.assertEqual(self._state(), EventState.ROLL_CALL)
        self.assertEqual(self._status(rsvp), SignupStatus.RSVP)
        self.assertEqual(self._status(approved), SignupStatus.APPROVED)


class DroppedReinstateTests(WiringTestCase):
    """The owner cannot reinstate a DROPPED signup through the endpoint."""

    def test_owner_reinstate_dropped_returns_400(self) -> None:
        self._open()
        dropped = self._signup(SignupStatus.DROPPED)
        resp = self._event_action(self.admin, "reopen_signups")
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(self._state(), EventState.SIGNUPS_OPEN)

        resp = self._signup_action(dropped.user, dropped, "reinstate")
        self.assertEqual(resp.status_code, 400, resp.content)
        self.assertEqual(resp.json()["error"], DROPPED_SIGNUP_MESSAGE)
        self.assertEqual(self._status(dropped), SignupStatus.DROPPED)

    def test_staff_reinstate_dropped_succeeds(self) -> None:
        self._open()
        dropped = self._signup(SignupStatus.DROPPED)
        self._event_action(self.admin, "reopen_signups")
        resp = self._signup_action(self.admin, dropped, "reinstate")
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertNotEqual(self._status(dropped), SignupStatus.DROPPED)
