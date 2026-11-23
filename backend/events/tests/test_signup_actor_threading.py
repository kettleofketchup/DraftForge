import inspect
from collections.abc import Callable
from typing import Any

from django.db import transaction

from events.constants import ActorRole, SignupAction, SignupMeans, SignupStatus
from events.ledger import SignupActor
from events.models import SignupLedgerEntry
from events.services import (
    _promote_from_waitlist,
    _staff_or_system_actor,
    approve_signup,
    cancel_signup,
    process_rsvp,
    reinstate_signup,
    reject_signup,
    staff_add_signup,
    unconfirm_signup,
)
from events.tests.actors import SYSTEM
from events.tests.base import EventTestCase

ACTOR_REQUIRED: list[Callable[..., Any]] = [
    approve_signup,
    reject_signup,
    staff_add_signup,
    unconfirm_signup,
    reinstate_signup,
]


class SignupActorSignatureTests(EventTestCase):
    def test_actor_is_required_keyword_only(self) -> None:
        for fn in ACTOR_REQUIRED:
            with self.subTest(fn=fn.__name__):
                param = inspect.signature(fn).parameters.get("actor")
                self.assertIsNotNone(param)
                assert param is not None
                self.assertEqual(param.kind, inspect.Parameter.KEYWORD_ONLY)
                self.assertIs(param.default, inspect.Parameter.empty)

    def test_promotion_takes_required_cause_and_optional_actor(self) -> None:
        params = inspect.signature(_promote_from_waitlist).parameters
        self.assertEqual(params["cause"].kind, inspect.Parameter.KEYWORD_ONLY)
        self.assertIs(params["cause"].default, inspect.Parameter.empty)
        self.assertEqual(params["actor"].kind, inspect.Parameter.KEYWORD_ONLY)
        self.assertIsNone(params["actor"].default)


class StaffOrSystemActorTests(EventTestCase):
    def test_user_becomes_staff_web_actor(self) -> None:
        user = self.make_user()
        self.assertEqual(
            _staff_or_system_actor(user),
            SignupActor(user=user, role=ActorRole.STAFF, means=SignupMeans.WEB),
        )

    def test_no_user_is_system(self) -> None:
        self.assertEqual(_staff_or_system_actor(None), SignupActor.system())


class PromotionActorTests(EventTestCase):
    def _promoted(self, signup_id: int) -> list[SignupLedgerEntry]:
        return list(
            SignupLedgerEntry.objects.filter(
                signup_id=signup_id, action=SignupAction.PROMOTED
            )
        )

    def test_cancel_promotion_is_one_system_row_caused_by_the_withdrawal(
        self,
    ) -> None:
        event = self.make_event(max_players=1)
        seated, waiting = self.make_user(), self.make_user()
        seated_signup = process_rsvp(event, seated, actor=SYSTEM)
        waiting_signup = process_rsvp(event, waiting, actor=SYSTEM)
        self.assertEqual(waiting_signup.status, SignupStatus.WAITLISTED)
        actor = SignupActor(user=seated, role=ActorRole.MEMBER, means=SignupMeans.WEB)

        cancel_signup(seated_signup, actor=actor)

        waiting_signup.refresh_from_db()
        self.assertEqual(waiting_signup.status, SignupStatus.APPROVED)
        withdrew = SignupLedgerEntry.objects.get(
            signup=seated_signup, action=SignupAction.WITHDREW
        )
        promoted = self._promoted(waiting_signup.pk)
        self.assertEqual(len(promoted), 1)
        self.assertEqual(promoted[0].actor_role, ActorRole.SYSTEM)
        self.assertEqual(promoted[0].caused_by_id, withdrew.pk)

    def test_actor_overrides_the_system_promoter(self) -> None:
        event = self.make_event(max_players=1)
        seated, waiting, staff = self.make_user(), self.make_user(), self.make_user()
        seated_signup = process_rsvp(event, seated, actor=SYSTEM)
        waiting_signup = process_rsvp(event, waiting, actor=SYSTEM)
        actor = _staff_or_system_actor(staff)
        seated_signup.status = SignupStatus.CANCELLED
        seated_signup.save(update_fields=["status"])

        with transaction.atomic():
            promoted = _promote_from_waitlist(event, cause=None, actor=actor)

        self.assertEqual([s.pk for s in promoted], [waiting_signup.pk])
        rows = self._promoted(waiting_signup.pk)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].actor_user, staff)
        self.assertEqual(rows[0].actor_role, ActorRole.STAFF)
