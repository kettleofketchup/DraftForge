from collections.abc import Callable
from datetime import timedelta
from typing import Any
from unittest import mock

from django.test import override_settings
from django.urls import reverse
from django.utils import timezone as tz
from rest_framework.response import Response
from rest_framework.test import APIClient

from app.models import CustomUser
from app.redis_client import set_client_for_tests
from events import ledger
from events.constants import (
    ActorRole,
    EventState,
    SignupAction,
    SignupMeans,
    SignupStatus,
    StaffReasonPolicy,
)
from events.ledger import PLACEMENT_ACTIONS, SignupActor
from events.models import (
    Event,
    EventSignup,
    ReadyCheck,
    ReadyCheckEntry,
    RollCallMode,
    SignupLedgerEntry,
)
from events.overrides import REASON_MAX_LENGTH, StaffReasonRequired
from events.ready_check import close_ready_check, confirm_ready, open_ready_check
from events.ready_check_constants import (
    DROPPED_SIGNUP_MESSAGE,
    ReadyCheckConfirmVia,
    ReadyCheckEntryState,
    ReadyCheckPhase,
)
from events.services import approve_signup
from events.tests.base import EventTestCase
from events.tests.test_signup_post_lock import FakeRedis
from org.models import OrgUser

REASON_REQUIRED: dict[str, str] = {"error": "reason_required"}
VOICE_GUILD = "200000000000000494"
VOICE_CHANNEL = "100000000000000494"

SIGNUP_URL_NAMES: dict[str, str] = {
    "approve": "event-signup-approve",
    "reject": "event-signup-reject",
    "confirm": "event-signup-confirm",
    "unconfirm": "event-signup-unconfirm",
    "demote": "event-signup-demote",
    "cancel_signup": "event-signup-cancel-signup",
    "reinstate": "event-signup-reinstate",
}

# (case, endpoint, starting status, ledger action, placement)
MATRIX: list[tuple[str, str, str | None, SignupAction, bool]] = [
    ("admin_signup", "admin_signup", None, SignupAction.STAFF_ADDED, True),
    (
        "approve_waitlisted",
        "approve",
        SignupStatus.WAITLISTED,
        SignupAction.APPROVED,
        True,
    ),
    ("approve_rsvp", "approve", SignupStatus.RSVP, SignupAction.APPROVED, False),
    (
        "approve_pending",
        "approve",
        SignupStatus.PENDING_APPROVAL,
        SignupAction.APPROVED,
        False,
    ),
    (
        "reject",
        "reject",
        SignupStatus.PENDING_APPROVAL,
        SignupAction.REJECTED,
        False,
    ),
    (
        "cancel",
        "cancel_signup",
        SignupStatus.APPROVED,
        SignupAction.WITHDREW,
        False,
    ),
    (
        "unconfirm",
        "unconfirm",
        SignupStatus.CONFIRMED,
        SignupAction.UNCONFIRMED,
        False,
    ),
    ("demote", "demote", SignupStatus.APPROVED, SignupAction.DEMOTED, True),
    (
        "reinstate",
        "reinstate",
        SignupStatus.CANCELLED,
        SignupAction.REINSTATED,
        True,
    ),
]

REASONS: list[str | None] = [None, "   ", "  sub for no-show  "]


class StaffReasonPolicyTestBase(EventTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.client = APIClient()
        self.current_event: Event | None = None

    def make_event(
        self, policy: str = StaffReasonPolicy.OPTIONAL, **overrides: object
    ) -> Event:
        event = super().make_event(staff_reason_policy=policy, **overrides)
        self.current_event = event
        return event

    def signup(
        self, user: CustomUser, status: str, *, event: Event | None = None
    ) -> EventSignup:
        target = event or self.current_event
        assert target is not None
        return EventSignup.objects.create(event=target, user=user, status=status)

    def post(self, path: str, body: dict[str, Any], *, as_user: CustomUser) -> Response:
        self.client.force_authenticate(as_user)
        return self.client.post(path, body, format="json")

    def signup_url(self, endpoint: str, signup: EventSignup) -> str:
        return reverse(SIGNUP_URL_NAMES[endpoint], args=[signup.pk])

    def admin_signup_url(self, event: Event) -> str:
        return f"/api/events/{event.pk}/admin-signup/"

    def last_entry(self, signup: EventSignup) -> SignupLedgerEntry | None:
        return (
            SignupLedgerEntry.objects.filter(signup=signup)
            .exclude(action=SignupAction.BACKFILLED)
            .order_by("pk")
            .last()
        )

    def ledger_count(self, event: Event) -> int:
        return SignupLedgerEntry.objects.filter(event=event).count()

    def body(self, reason: str | None, **extra: Any) -> dict[str, Any]:
        data: dict[str, Any] = dict(extra)
        if reason is not None:
            data["reason"] = reason
        return data


@mock.patch("events.services.notify_signup_changed")
class StaffSignupActionsReasonTest(StaffReasonPolicyTestBase):
    def _run(
        self, endpoint: str, start: str | None, reason: str | None
    ) -> tuple[Response, EventSignup | None, CustomUser]:
        assert self.current_event is not None
        member = self.make_user()
        if endpoint == "admin_signup":
            response = self.post(
                self.admin_signup_url(self.current_event),
                self.body(reason, user_id=member.pk),
                as_user=self.admin,
            )
            return response, None, member
        assert start is not None
        signup = self.signup(member, start)
        response = self.post(
            self.signup_url(endpoint, signup), self.body(reason), as_user=self.admin
        )
        return response, signup, member

    def test_matrix(self, _notify: Any) -> None:
        for policy in StaffReasonPolicy.values:
            event = self.make_event(policy)
            for case, endpoint, start, action, placement in MATRIX:
                for reason in REASONS:
                    with self.subTest(policy=policy, case=case, reason=reason):
                        before_rows = self.ledger_count(event)
                        response, signup, member = self._run(endpoint, start, reason)
                        refused = not (reason or "").strip() and (
                            policy == StaffReasonPolicy.ALL_STAFF_CHANGES
                            or (policy == StaffReasonPolicy.PLACEMENTS and placement)
                        )
                        if refused:
                            self.assertEqual(response.status_code, 400)
                            self.assertEqual(response.json(), REASON_REQUIRED)
                            self.assertEqual(self.ledger_count(event), before_rows)
                            if signup is None:
                                self.assertFalse(
                                    EventSignup.objects.filter(
                                        event=event, user=member
                                    ).exists()
                                )
                            else:
                                signup.refresh_from_db()
                                self.assertEqual(signup.status, start)
                            continue
                        self.assertIn(
                            response.status_code, (200, 201), response.content
                        )
                        if signup is None:
                            signup = EventSignup.objects.get(event=event, user=member)
                        entry = SignupLedgerEntry.objects.filter(
                            signup=signup, action=action
                        ).last()
                        assert entry is not None
                        self.assertEqual(
                            entry.reason,
                            "sub for no-show" if (reason or "").strip() else "",
                        )

    def test_optional_records_given_reason(self, _notify: Any) -> None:
        self.make_event(StaffReasonPolicy.OPTIONAL)
        signup = self.signup(self.make_user(), SignupStatus.APPROVED)
        response = self.post(
            self.signup_url("demote", signup),
            {"reason": "late twice"},
            as_user=self.admin,
        )
        self.assertEqual(response.status_code, 200, response.content)
        entry = self.last_entry(signup)
        assert entry is not None
        self.assertEqual(entry.action, SignupAction.DEMOTED)
        self.assertEqual(entry.reason, "late twice")

    def test_member_self_cancel_and_reinstate_exempt(self, _notify: Any) -> None:
        self.make_event(StaffReasonPolicy.ALL_STAFF_CHANGES)
        member = self.make_user()
        signup = self.signup(member, SignupStatus.APPROVED)
        cancelled = self.post(
            self.signup_url("cancel_signup", signup), {}, as_user=member
        )
        self.assertEqual(cancelled.status_code, 200, cancelled.content)
        reinstated = self.post(self.signup_url("reinstate", signup), {}, as_user=member)
        self.assertEqual(reinstated.status_code, 200, reinstated.content)

    def test_staff_self_cancel_and_reinstate_exempt(self, _notify: Any) -> None:
        self.make_event(StaffReasonPolicy.ALL_STAFF_CHANGES)
        signup = self.signup(self.admin, SignupStatus.APPROVED)
        cancelled = self.post(
            self.signup_url("cancel_signup", signup), {}, as_user=self.admin
        )
        self.assertEqual(cancelled.status_code, 200, cancelled.content)
        reinstated = self.post(
            self.signup_url("reinstate", signup), {}, as_user=self.admin
        )
        self.assertEqual(reinstated.status_code, 200, reinstated.content)
        entry = self.last_entry(signup)
        assert entry is not None
        self.assertEqual(entry.action, SignupAction.VOIDED_WITHDRAWAL)
        self.assertEqual(entry.actor_role, ActorRole.MEMBER)
        assert entry.after is not None
        self.assertIs(entry.after["extra"]["staff_power"], True)

    def test_reason_too_long(self, _notify: Any) -> None:
        self.make_event(StaffReasonPolicy.ALL_STAFF_CHANGES)
        signup = self.signup(self.make_user(), SignupStatus.APPROVED)
        too_long = self.post(
            self.signup_url("demote", signup),
            {"reason": "x" * (REASON_MAX_LENGTH + 1)},
            as_user=self.admin,
        )
        self.assertEqual(too_long.status_code, 400)
        self.assertIn("reason", too_long.json())
        signup.refresh_from_db()
        self.assertEqual(signup.status, SignupStatus.APPROVED)

        at_limit = "y" * REASON_MAX_LENGTH
        ok = self.post(
            self.signup_url("demote", signup),
            {"reason": f"  {at_limit}  "},
            as_user=self.admin,
        )
        self.assertEqual(ok.status_code, 200, ok.content)
        entry = self.last_entry(signup)
        assert entry is not None
        self.assertEqual(entry.reason, at_limit)

    def test_non_staff_gets_403(self, _notify: Any) -> None:
        self.make_event(StaffReasonPolicy.ALL_STAFF_CHANGES)
        signup = self.signup(self.make_user(), SignupStatus.APPROVED)
        response = self.post(
            self.signup_url("demote", signup),
            {"reason": "because"},
            as_user=self.unrelated_user,
        )
        self.assertEqual(response.status_code, 403)

    def test_validation_before_policy(self, _notify: Any) -> None:
        cases: list[tuple[str, str, str]] = [
            ("approve", SignupStatus.APPROVED, "Cannot approve signup in 'approved'"),
            ("reject", SignupStatus.REJECTED, "Cannot reject signup in 'rejected'"),
            ("demote", SignupStatus.WAITLISTED, "Cannot demote signup in 'waitlisted'"),
            ("unconfirm", SignupStatus.APPROVED, "Only confirmed signups"),
            (
                "cancel_signup",
                SignupStatus.CANCELLED,
                "Cannot cancel signup in 'cancelled'",
            ),
            ("reinstate", SignupStatus.APPROVED, "Only cancelled signups"),
        ]
        event = self.make_event(StaffReasonPolicy.ALL_STAFF_CHANGES)
        for endpoint, start, message in cases:
            with self.subTest(endpoint=endpoint):
                signup = self.signup(self.make_user(), start)
                rows = self.ledger_count(event)
                response = self.post(
                    self.signup_url(endpoint, signup), {}, as_user=self.admin
                )
                self.assertEqual(response.status_code, 400)
                self.assertIn(message, response.json()["error"])
                self.assertEqual(self.ledger_count(event), rows)
                signup.refresh_from_db()
                self.assertEqual(signup.status, start)

        admin_cases: list[tuple[str, str]] = [
            (SignupStatus.APPROVED, "User has already signed up for this event."),
            (SignupStatus.DROPPED, DROPPED_SIGNUP_MESSAGE),
        ]
        for policy in (
            StaffReasonPolicy.ALL_STAFF_CHANGES,
            StaffReasonPolicy.PLACEMENTS,
        ):
            event = self.make_event(policy)
            for start, message in admin_cases:
                with self.subTest(policy=policy, admin_signup=start):
                    member = self.make_user()
                    self.signup(member, start)
                    rows = self.ledger_count(event)
                    response = self.post(
                        self.admin_signup_url(event),
                        {"user_id": member.pk},
                        as_user=self.admin,
                    )
                    self.assertEqual(response.status_code, 400)
                    self.assertEqual(response.json(), {"error": message})
                    self.assertEqual(self.ledger_count(event), rows)

    def test_roll_call_admin_add_reason_only_on_staff_added(self, _notify: Any) -> None:
        event = self.make_event(StaffReasonPolicy.PLACEMENTS)
        staff_actor = SignupActor(
            user=self.admin, role=ActorRole.STAFF, means=SignupMeans.WEB
        )
        self.signup(self.make_user(), SignupStatus.APPROVED)
        with self.captureOnCommitCallbacks(execute=True):
            open_ready_check(event, actor=staff_actor)
        event.refresh_from_db()
        self.assertEqual(event.state, EventState.ROLL_CALL)

        member = self.make_user()
        response = self.post(
            self.admin_signup_url(event),
            {"user_id": member.pk, "reason": "late sub"},
            as_user=self.admin,
        )
        self.assertEqual(response.status_code, 201, response.content)
        signup = EventSignup.objects.get(event=event, user=member)
        rows = {
            e.action: e.reason for e in SignupLedgerEntry.objects.filter(signup=signup)
        }
        self.assertEqual(rows[SignupAction.STAFF_ADDED], "late sub")
        self.assertEqual(
            rows[SignupAction.READY_CHECK_ASKED], "ready_check_late_enrolment"
        )

    def test_reject_cascade_promoted_row_is_system(self, _notify: Any) -> None:
        self.make_event(StaffReasonPolicy.ALL_STAFF_CHANGES, max_players=1)
        seated = self.signup(self.make_user(), SignupStatus.APPROVED)
        waiting = self.signup(self.make_user(), SignupStatus.WAITLISTED)
        response = self.post(
            self.signup_url("reject", seated),
            {"reason": "no-show last week"},
            as_user=self.admin,
        )
        self.assertEqual(response.status_code, 200, response.content)
        rejected = self.last_entry(seated)
        assert rejected is not None
        self.assertEqual(rejected.reason, "no-show last week")
        promoted = SignupLedgerEntry.objects.get(
            signup=waiting, action=SignupAction.PROMOTED
        )
        self.assertEqual(promoted.actor_role, ActorRole.SYSTEM)
        self.assertEqual(promoted.reason, "")

    def test_placement_set_extension_point(self, _notify: Any) -> None:
        self.make_event(StaffReasonPolicy.PLACEMENTS)
        first = self.signup(self.make_user(), SignupStatus.PENDING_APPROVAL)
        passed = self.post(self.signup_url("reject", first), {}, as_user=self.admin)
        self.assertEqual(passed.status_code, 200, passed.content)

        second = self.signup(self.make_user(), SignupStatus.PENDING_APPROVAL)
        with mock.patch(
            "events.ledger.PLACEMENT_ACTIONS",
            PLACEMENT_ACTIONS | {SignupAction.REJECTED},
        ):
            refused = self.post(
                self.signup_url("reject", second), {}, as_user=self.admin
            )
        self.assertEqual(refused.status_code, 400)
        self.assertEqual(refused.json(), REASON_REQUIRED)

    def test_approve_classifies_from_reread_status(self, _notify: Any) -> None:
        self.make_event(StaffReasonPolicy.PLACEMENTS)
        stale = self.signup(self.make_user(), SignupStatus.RSVP)
        EventSignup.objects.filter(pk=stale.pk).update(status=SignupStatus.WAITLISTED)
        actor = SignupActor(
            user=self.admin, role=ActorRole.STAFF, means=SignupMeans.WEB
        )
        with self.assertRaises(StaffReasonRequired):
            approve_signup(stale, actor=actor)
        self.assertEqual(
            EventSignup.objects.get(pk=stale.pk).status, SignupStatus.WAITLISTED
        )

    def test_refusal_writes_no_mmr(self, _notify: Any) -> None:
        event = self.make_event(StaffReasonPolicy.PLACEMENTS)
        member = self.make_user()
        org_user = OrgUser.objects.get(user=member, organization=self.org)
        before = {
            f.attname: getattr(org_user, f.attname)
            for f in OrgUser._meta.concrete_fields
        }
        signup = self.signup(member, SignupStatus.WAITLISTED)
        rows = self.ledger_count(event)
        response = self.post(
            self.signup_url("approve", signup), {"mmr": 4321}, as_user=self.admin
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), REASON_REQUIRED)
        org_user.refresh_from_db()
        after = {
            f.attname: getattr(org_user, f.attname)
            for f in OrgUser._meta.concrete_fields
        }
        self.assertEqual(after, before)
        self.assertEqual(self.ledger_count(event), rows)


@override_settings(READY_CHECK_AUTOMATIC_LIVE=True)
class ConfirmReasonThreadingTest(StaffReasonPolicyTestBase):
    def setUp(self) -> None:
        super().setUp()
        for target in (
            "events.services.notify_signup_changed",
            "events.discord.dispatch.notify_signup_changed",
        ):
            patcher = mock.patch(target)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.staff_actor = SignupActor(
            user=self.admin, role=ActorRole.STAFF, means=SignupMeans.WEB
        )

    def _open(self, event: Event) -> ReadyCheck:
        with self.captureOnCommitCallbacks(execute=True):
            check = open_ready_check(event, actor=self.staff_actor).check
        event.refresh_from_db()
        assert check is not None
        return check

    def _close(self, event: Event) -> ReadyCheck:
        with self.captureOnCommitCallbacks(execute=True):
            result = close_ready_check(event, actor=self.staff_actor)
        assert result.check is not None
        self.assertEqual(result.check.phase, ReadyCheckPhase.CLOSED)
        return result.check

    def _confirmed_row(self, signup: EventSignup) -> SignupLedgerEntry:
        return SignupLedgerEntry.objects.get(
            signup=signup, action=SignupAction.CONFIRMED
        )

    def _rc_confirm(
        self, event: Event, user: CustomUser, reason: str | None
    ) -> Response:
        return self.post(
            f"/api/events/{event.pk}/ready-check/confirm/",
            self.body(reason, user_id=user.pk),
            as_user=self.admin,
        )

    def _live_setup(self) -> tuple[Event, EventSignup]:
        event = self.make_event(StaffReasonPolicy.ALL_STAFF_CHANGES)
        signup = self.signup(self.make_user(), SignupStatus.APPROVED)
        self._open(event)
        return event, signup

    def _closed_setup(self) -> tuple[Event, EventSignup]:
        event, signup = self._live_setup()
        self._close(event)
        return event, signup

    def _fallback_setup(self) -> tuple[Event, EventSignup]:
        event = self.make_event(StaffReasonPolicy.ALL_STAFF_CHANGES)
        self.signup(self.make_user(), SignupStatus.APPROVED)
        self._open(event)
        return event, self.signup(self.make_user(), SignupStatus.APPROVED)

    def _assert_refused(self, response: Response, event: Event, rows: int) -> None:
        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(response.json(), REASON_REQUIRED)
        self.assertEqual(self.ledger_count(event), rows)

    def test_signup_confirm_live_check(self) -> None:
        event, signup = self._live_setup()
        rows = self.ledger_count(event)
        refused = self.post(self.signup_url("confirm", signup), {}, as_user=self.admin)
        self._assert_refused(refused, event, rows)
        self.assertEqual(
            EventSignup.objects.get(pk=signup.pk).status, SignupStatus.APPROVED
        )
        self.assertEqual(
            ReadyCheckEntry.objects.get(signup=signup).state,
            ReadyCheckEntryState.PENDING,
        )

        response = self.post(
            self.signup_url("confirm", signup), {"reason": " r1 "}, as_user=self.admin
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(self._confirmed_row(signup).reason, "r1")

    def test_signup_confirm_closed_check(self) -> None:
        event, signup = self._closed_setup()
        rows = self.ledger_count(event)
        refused = self.post(self.signup_url("confirm", signup), {}, as_user=self.admin)
        self._assert_refused(refused, event, rows)

        response = self.post(
            self.signup_url("confirm", signup), {"reason": "r1"}, as_user=self.admin
        )
        self.assertEqual(response.status_code, 200, response.content)
        row = self._confirmed_row(signup)
        self.assertEqual(row.reason, "r1")
        self.assertEqual(row.rules_overridden, ["ready_check_closed"])

    def test_signup_confirm_not_in_check_fallback(self) -> None:
        event, signup = self._fallback_setup()
        self.assertFalse(ReadyCheckEntry.objects.filter(signup=signup).exists())
        rows = self.ledger_count(event)
        refused = self.post(self.signup_url("confirm", signup), {}, as_user=self.admin)
        self._assert_refused(refused, event, rows)

        response = self.post(
            self.signup_url("confirm", signup), {"reason": "r1"}, as_user=self.admin
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(self._confirmed_row(signup).reason, "r1")

    def test_confirm_keeps_machine_literal_without_reason(self) -> None:
        cases: list[tuple[str, Callable[[], tuple[Event, EventSignup]], str]] = [
            ("live", self._live_setup, "ready_check_confirmed"),
            ("closed", self._closed_setup, "staff_confirmed"),
            ("fallback", self._fallback_setup, "staff_confirmed"),
        ]
        for name, setup, literal in cases:
            with self.subTest(path=name):
                event, signup = setup()
                Event.objects.filter(pk=event.pk).update(
                    staff_reason_policy=StaffReasonPolicy.OPTIONAL
                )
                response = self.post(
                    self.signup_url("confirm", signup), {}, as_user=self.admin
                )
                self.assertEqual(response.status_code, 200, response.content)
                self.assertEqual(self._confirmed_row(signup).reason, literal)

    def test_ready_check_confirm_accepting_and_closed(self) -> None:
        for name, setup in (
            ("accepting", self._live_setup),
            ("closed", self._closed_setup),
        ):
            with self.subTest(path=name):
                event, signup = setup()
                rows = self.ledger_count(event)
                self._assert_refused(
                    self._rc_confirm(event, signup.user, None), event, rows
                )
                response = self._rc_confirm(event, signup.user, "r2")
                self.assertEqual(response.status_code, 200, response.content)
                self.assertEqual(self._confirmed_row(signup).reason, "r2")
                self.assertEqual(
                    EventSignup.objects.get(pk=signup.pk).status,
                    SignupStatus.CONFIRMED,
                )

    def test_ready_check_confirm_reason_too_long(self) -> None:
        event, signup = self._live_setup()
        response = self._rc_confirm(event, signup.user, "x" * (REASON_MAX_LENGTH + 1))
        self.assertEqual(response.status_code, 400)
        self.assertIn("reason", response.json())

    def test_ready_check_confirm_not_in_check_still_409(self) -> None:
        event, signup = self._fallback_setup()
        rows = self.ledger_count(event)
        response = self._rc_confirm(event, signup.user, None)
        self.assertEqual(response.status_code, 409, response.content)
        self.assertEqual(response.json()["code"], "not_in_check")
        self.assertEqual(self.ledger_count(event), rows)

    def test_operator_confirm_self_exempt(self) -> None:
        event = self.make_event(StaffReasonPolicy.ALL_STAFF_CHANGES)
        own = self.signup(self.admin, SignupStatus.APPROVED)
        self._open(event)
        response = self._rc_confirm(event, self.admin, None)
        self.assertEqual(response.status_code, 200, response.content)
        row = self._confirmed_row(own)
        self.assertEqual(row.reason, "ready_check_confirmed")
        self.assertEqual(row.actor_role, ActorRole.STAFF)

    def test_voice_presence_override_not_checked(self) -> None:
        self.org.discord_server_id = VOICE_GUILD
        self.org.save()
        set_client_for_tests(FakeRedis())
        self.addCleanup(set_client_for_tests, None)
        event = self.make_event(
            StaffReasonPolicy.ALL_STAFF_CHANGES,
            scheduled_at=tz.now() + timedelta(hours=1),
            event_voice_channel_id=VOICE_CHANNEL,
            voice_presence_confirms=True,
        )
        signup = self.signup(self.make_user(), SignupStatus.APPROVED)
        self._open(event)
        with self.captureOnCommitCallbacks(execute=True):
            response = self.post(
                f"/api/events/{event.pk}/voice-presence/",
                {"user_id": signup.user_id, "present": True, "reason": "on stage"},
                as_user=self.admin,
            )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["confirm"], "confirmed")
        self.assertTrue(
            SignupLedgerEntry.objects.filter(
                signup=signup, action=SignupAction.VOICE_PRESENCE_SET
            ).exists()
        )
        self.assertEqual(self._confirmed_row(signup).reason, "ready_check_confirmed")

    def test_ready_check_close_exempt(self) -> None:
        event = self.make_event(
            StaffReasonPolicy.ALL_STAFF_CHANGES,
            roll_call_enabled=True,
            roll_call_mode=RollCallMode.AUTOMATIC,
            ready_check_min_completion_pct=70,
        )
        signups = [
            self.signup(self.make_user(), SignupStatus.APPROVED) for _ in range(4)
        ]
        self._open(event)
        for signup in signups[:3]:
            confirm_ready(
                event,
                signup.user,
                via=ReadyCheckConfirmVia.WEB,
                actor=SignupActor(
                    user=signup.user, role=ActorRole.MEMBER, means=SignupMeans.WEB
                ),
            )
        with self.captureOnCommitCallbacks(execute=True):
            response = self.post(
                f"/api/events/{event.pk}/ready-check/close/", {}, as_user=self.admin
            )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["dropped_user_ids"], [signups[3].user_id])

    def test_each_request_checks_once(self) -> None:
        shared = mock.Mock(wraps=ledger.require_staff_reason)
        paths: list[tuple[str, Callable[[], tuple[Event, EventSignup]], bool]] = [
            ("signup_live", self._live_setup, False),
            ("signup_closed", self._closed_setup, False),
            ("signup_fallback", self._fallback_setup, False),
            ("rc_accepting", self._live_setup, True),
            ("rc_closed", self._closed_setup, True),
        ]
        with (
            mock.patch("events.services.require_staff_reason", shared),
            mock.patch("events.ready_check.require_staff_reason", shared),
        ):
            for name, setup, via_rc in paths:
                with self.subTest(path=name):
                    event, signup = setup()
                    shared.reset_mock()
                    if via_rc:
                        response = self._rc_confirm(event, signup.user, "r")
                    else:
                        response = self.post(
                            self.signup_url("confirm", signup),
                            {"reason": "r"},
                            as_user=self.admin,
                        )
                    self.assertEqual(response.status_code, 200, response.content)
                    self.assertEqual(shared.call_count, 1)
