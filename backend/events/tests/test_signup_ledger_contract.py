import inspect
from collections.abc import Callable
from typing import Any
from unittest.mock import patch

from django.test import SimpleTestCase

from app.models import CustomUser
from events.constants import (
    ActorRole,
    Commitment,
    EventState,
    SignupAction,
    SignupMeans,
    SignupStatus,
)
from events.ledger import SignupActor
from events.models import Event, EventSignup, SignupLedgerEntry
from events.services import (
    _create_signup,
    _promote_from_waitlist,
    approve_signup,
    cancel_signup,
    confirm_signup,
    create_tentative_signup,
    decline_signup,
    demote_to_waitlist,
    process_rsvp,
    reinstate_signup,
    reject_signup,
    staff_add_signup,
    unconfirm_signup,
)
from events.tests.base import EventTestCase
from org.mmr import game_for_event

SIGNUP_SERVICES: list[Callable[..., Any]] = [
    process_rsvp,
    _create_signup,
    create_tentative_signup,
    decline_signup,
    staff_add_signup,
    approve_signup,
    reject_signup,
    confirm_signup,
    cancel_signup,
    unconfirm_signup,
    demote_to_waitlist,
    reinstate_signup,
]


def _assert_required_keyword_only(
    case: SimpleTestCase, fn: Callable[..., Any], name: str
) -> None:
    param = inspect.signature(fn).parameters[name]
    case.assertEqual(param.kind, inspect.Parameter.KEYWORD_ONLY, fn.__name__)
    case.assertIs(param.default, inspect.Parameter.empty, fn.__name__)


class SignupSignatureContractTests(SimpleTestCase):
    def test_actor_is_required_keyword_only(self) -> None:
        for fn in SIGNUP_SERVICES:
            with self.subTest(fn=fn.__name__):
                _assert_required_keyword_only(self, fn, "actor")

    def test_promote_cause_is_required_keyword_only(self) -> None:
        _assert_required_keyword_only(self, _promote_from_waitlist, "cause")


class SignupCallWithoutActorTests(EventTestCase):
    def test_call_without_actor_raises_type_error(self) -> None:
        signup = EventSignup.objects.create(
            event=self.event, user=self.user, status=SignupStatus.APPROVED
        )
        with self.assertRaises(TypeError):
            cancel_signup(signup)  # type: ignore[call-arg]
        signup.refresh_from_db()
        self.assertEqual(signup.status, SignupStatus.APPROVED)


class LedgerContractMixin:
    staff: CustomUser
    subject: CustomUser
    member_actor: SignupActor
    staff_actor: SignupActor

    def setUp(self) -> None:
        super().setUp()  # type: ignore[misc]
        self.subject = self.user  # type: ignore[attr-defined]
        self.staff = self.admin  # type: ignore[attr-defined]
        self.member_actor = SignupActor(
            user=self.subject, role=ActorRole.MEMBER, means=SignupMeans.WEB
        )
        self.staff_actor = SignupActor(
            user=self.staff, role=ActorRole.STAFF, means=SignupMeans.WEB
        )

    def ledger(self, event: Event) -> list[SignupLedgerEntry]:
        return list(
            SignupLedgerEntry.objects.filter(event=event)
            .exclude(action=SignupAction.BACKFILLED)
            .order_by("pk")
        )

    def assert_single_entry(
        self,
        event: Event,
        *,
        action: SignupAction,
        actor: SignupActor,
        signup: EventSignup | None,
        before_status: str | None,
        after_status: str | None,
        on_behalf: bool = False,
        correlation_id: str = "",
        subject: CustomUser | None = None,
    ) -> SignupLedgerEntry:
        case: SimpleTestCase = self  # type: ignore[assignment]
        entries = self.ledger(event)
        case.assertEqual(len(entries), 1, [e.action for e in entries])
        entry = entries[0]
        expected_subject = subject or (signup.user if signup is not None else None)
        case.assertEqual(entry.action, action)
        case.assertEqual(entry.signup_id, signup.pk if signup is not None else None)
        case.assertEqual(
            entry.subject_user_id,
            expected_subject.pk if expected_subject is not None else None,
        )
        case.assertEqual(
            entry.actor_user_id, actor.user.pk if actor.user is not None else None
        )
        case.assertEqual(entry.actor_role, actor.role)
        case.assertEqual(entry.means, actor.means)
        case.assertEqual(entry.on_behalf, on_behalf)
        case.assertEqual(entry.correlation_id, correlation_id)
        case.assertIsNone(entry.caused_by_id)
        case.assertEqual(entry.organization_id, event.organization_id)
        if before_status is None:
            case.assertIsNone(entry.before)
        else:
            case.assertEqual(entry.before["status"], before_status)
        if after_status is None:
            case.assertIsNone(entry.after)
        else:
            case.assertEqual(entry.after["status"], after_status)
        return entry


@patch("events.services.notify_signup_changed")
class LeafMutationLedgerTests(LedgerContractMixin, EventTestCase):
    def _signup(
        self, event: Event, status: str, *, user: CustomUser | None = None
    ) -> EventSignup:
        return EventSignup.objects.create(
            event=event, user=user or self.subject, status=status
        )

    def test_leaf_table_records_one_entry(self, _notify: Any) -> None:
        rows: list[tuple[str, Callable[..., Any], str, SignupAction, str | None]] = [
            (
                "approve",
                approve_signup,
                SignupStatus.RSVP,
                SignupAction.APPROVED,
                SignupStatus.APPROVED,
            ),
            (
                "confirm",
                confirm_signup,
                SignupStatus.APPROVED,
                SignupAction.CONFIRMED,
                SignupStatus.CONFIRMED,
            ),
            (
                "unconfirm",
                unconfirm_signup,
                SignupStatus.CONFIRMED,
                SignupAction.UNCONFIRMED,
                SignupStatus.APPROVED,
            ),
            (
                "demote",
                demote_to_waitlist,
                SignupStatus.APPROVED,
                SignupAction.DEMOTED,
                SignupStatus.WAITLISTED,
            ),
            (
                "reinstate",
                reinstate_signup,
                SignupStatus.CANCELLED,
                SignupAction.REINSTATED,
                None,
            ),
        ]
        for name, fn, start, action, end in rows:
            with self.subTest(leaf=name):
                event = self.make_event()
                signup = self._signup(event, start)
                fn(signup, actor=self.staff_actor)
                signup.refresh_from_db()
                entry = self.assert_single_entry(
                    event,
                    action=action,
                    actor=self.staff_actor,
                    signup=signup,
                    before_status=start,
                    after_status=end or signup.status,
                    on_behalf=True,
                )
                self.assertEqual(entry.after["status"], signup.status)

    def test_demote_records_waitlist_position(self, _notify: Any) -> None:
        event = self.make_event()
        other = self.make_user()
        EventSignup.objects.create(
            event=event,
            user=other,
            status=SignupStatus.WAITLISTED,
            waitlist_position=3,
        )
        signup = self._signup(event, SignupStatus.APPROVED)
        demote_to_waitlist(signup, actor=self.staff_actor)
        entry = self.ledger(event)[0]
        self.assertEqual(entry.action, SignupAction.DEMOTED)
        self.assertIsNone(entry.before["waitlist_position"])
        self.assertEqual(entry.after["waitlist_position"], 4)

    def test_reinstate_roll_call_records(self, _notify: Any) -> None:
        event = self.make_event(state=EventState.ROLL_CALL)
        signup = EventSignup.objects.create(
            event=event,
            user=self.subject,
            status=SignupStatus.REJECTED,
            commitment=Commitment.MAYBE,
        )
        reinstate_signup(signup, actor=self.staff_actor)
        entry = self.assert_single_entry(
            event,
            action=SignupAction.REINSTATED,
            actor=self.staff_actor,
            signup=signup,
            before_status=SignupStatus.REJECTED,
            after_status=SignupStatus.APPROVED,
            on_behalf=True,
        )
        self.assertEqual(entry.before["commitment"], Commitment.MAYBE)
        self.assertEqual(entry.after["commitment"], Commitment.MAIN)

    def test_reinstate_full_event_records_waitlisted(self, _notify: Any) -> None:
        event = self.make_event(max_players=1)
        self._signup(event, SignupStatus.APPROVED, user=self.make_user())
        signup = self._signup(event, SignupStatus.CANCELLED)
        reinstate_signup(signup, actor=self.staff_actor)
        self.assert_single_entry(
            event,
            action=SignupAction.REINSTATED,
            actor=self.staff_actor,
            signup=signup,
            before_status=SignupStatus.CANCELLED,
            after_status=SignupStatus.WAITLISTED,
            on_behalf=True,
        )

    def test_approve_with_mmr_override_records_extra(self, _notify: Any) -> None:
        event = self.make_event()
        signup = self._signup(event, SignupStatus.RSVP)
        approve_signup(signup, mmr_override=4200, actor=self.staff_actor)
        entry = self.ledger(event)[0]
        self.assertEqual(
            entry.after["extra"],
            {"mmr_override": 4200, "game_type": int(game_for_event(event))},
        )

    def test_approve_without_override_has_empty_extra(self, _notify: Any) -> None:
        event = self.make_event()
        signup = self._signup(event, SignupStatus.RSVP)
        approve_signup(signup, actor=self.staff_actor)
        self.assertEqual(self.ledger(event)[0].after["extra"], {})

    def test_leaf_raising_paths_write_nothing(self, _notify: Any) -> None:
        rows: list[tuple[str, Callable[..., Any], str]] = [
            ("approve", approve_signup, SignupStatus.CONFIRMED),
            ("confirm", confirm_signup, SignupStatus.RSVP),
            ("unconfirm", unconfirm_signup, SignupStatus.APPROVED),
            ("demote", demote_to_waitlist, SignupStatus.WAITLISTED),
            ("reinstate", reinstate_signup, SignupStatus.APPROVED),
        ]
        for name, fn, start in rows:
            with self.subTest(leaf=name):
                event = self.make_event()
                signup = self._signup(event, start)
                with self.assertRaises(ValueError):
                    fn(signup, actor=self.staff_actor)
                self.assertEqual(self.ledger(event), [])
                signup.refresh_from_db()
                self.assertEqual(signup.status, start)

    def test_stale_instance_guard_reads_db(self, _notify: Any) -> None:
        event = self.make_event()
        stale = self._signup(event, SignupStatus.APPROVED)
        EventSignup.objects.filter(pk=stale.pk).update(status=SignupStatus.CANCELLED)
        with self.assertRaises(ValueError):
            demote_to_waitlist(stale, actor=self.staff_actor)
        self.assertEqual(self.ledger(event), [])
        self.assertEqual(
            EventSignup.objects.nocache().get(pk=stale.pk).status,
            SignupStatus.CANCELLED,
        )

    def test_stale_instance_before_matches_db(self, _notify: Any) -> None:
        event = self.make_event()
        stale = self._signup(event, SignupStatus.RSVP)
        EventSignup.objects.filter(pk=stale.pk).update(
            status=SignupStatus.PENDING_APPROVAL
        )
        approve_signup(stale, actor=self.staff_actor)
        entry = self.ledger(event)[0]
        self.assertEqual(entry.before["status"], SignupStatus.PENDING_APPROVAL)
        self.assertEqual(entry.after["status"], SignupStatus.APPROVED)

    def test_staff_power_flag_on_own_signup(self, _notify: Any) -> None:
        event = self.make_event()
        signup = self._signup(event, SignupStatus.APPROVED)
        actor = SignupActor(
            user=self.subject,
            role=ActorRole.MEMBER,
            means=SignupMeans.WEB,
            staff_power=True,
        )
        confirm_signup(signup, actor=actor)
        entry = self.assert_single_entry(
            event,
            action=SignupAction.CONFIRMED,
            actor=actor,
            signup=signup,
            before_status=SignupStatus.APPROVED,
            after_status=SignupStatus.CONFIRMED,
        )
        self.assertIs(entry.after["extra"]["staff_power"], True)

    def test_member_actor_records_member_role(self, _notify: Any) -> None:
        event = self.make_event()
        signup = self._signup(event, SignupStatus.APPROVED)
        confirm_signup(signup, actor=self.member_actor)
        self.assert_single_entry(
            event,
            action=SignupAction.CONFIRMED,
            actor=self.member_actor,
            signup=signup,
            before_status=SignupStatus.APPROVED,
            after_status=SignupStatus.CONFIRMED,
        )
