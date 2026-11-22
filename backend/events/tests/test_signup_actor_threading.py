import inspect
from collections.abc import Callable
from typing import Any
from unittest.mock import patch

from events import services
from events.constants import ActorRole, SignupMeans, SignupStatus
from events.ledger import SignupActor
from events.services import (
    _promote_from_waitlist,
    _promote_one,
    _staff_or_system_actor,
    approve_signup,
    cancel_signup,
    process_rsvp,
    reinstate_signup,
    reject_signup,
    staff_add_signup,
    unconfirm_signup,
)
from events.tests.base import EventTestCase

ACTOR_REQUIRED: list[Callable[..., Any]] = [
    approve_signup,
    reject_signup,
    staff_add_signup,
    unconfirm_signup,
    reinstate_signup,
    _promote_from_waitlist,
    _promote_one,
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
    def test_promotion_receives_cancel_actor(self) -> None:
        event = self.make_event(max_players=1)
        seated, waiting = self.make_user(), self.make_user()
        seated_signup = process_rsvp(event, seated)
        waiting_signup = process_rsvp(event, waiting)
        self.assertEqual(waiting_signup.status, SignupStatus.WAITLISTED)
        actor = SignupActor(user=seated, role=ActorRole.MEMBER, means=SignupMeans.WEB)

        with patch.object(
            services, "_promote_one", wraps=services._promote_one
        ) as promote:
            cancel_signup(seated_signup, actor=actor)

        promote.assert_called_once()
        self.assertEqual(promote.call_args.kwargs["actor"], actor)
        waiting_signup.refresh_from_db()
        self.assertEqual(waiting_signup.status, SignupStatus.APPROVED)

    def test_promotion_without_cancel_actor_is_system(self) -> None:
        event = self.make_event(max_players=1)
        seated, waiting = self.make_user(), self.make_user()
        seated_signup = process_rsvp(event, seated)
        process_rsvp(event, waiting)

        with patch.object(
            services, "_promote_one", wraps=services._promote_one
        ) as promote:
            cancel_signup(seated_signup)

        self.assertEqual(promote.call_args.kwargs["actor"], SignupActor.system())

    def test_promotion_receives_reject_actor(self) -> None:
        event = self.make_event(max_players=1)
        seated, waiting, staff = self.make_user(), self.make_user(), self.make_user()
        seated_signup = process_rsvp(event, seated)
        process_rsvp(event, waiting)
        actor = _staff_or_system_actor(staff)

        with patch.object(
            services, "_promote_one", wraps=services._promote_one
        ) as promote:
            reject_signup(seated_signup, actor=actor)

        self.assertEqual(promote.call_args.kwargs["actor"], actor)
