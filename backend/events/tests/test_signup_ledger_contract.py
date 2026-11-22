import inspect
from collections.abc import Callable
from typing import Any

from django.test import SimpleTestCase

from events.constants import SignupStatus
from events.models import EventSignup
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
