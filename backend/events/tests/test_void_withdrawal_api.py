from collections.abc import Sequence
from typing import Any
from unittest.mock import patch

from django.urls import reverse
from rest_framework.response import Response
from rest_framework.test import APIClient

from app.models import CustomUser
from events.constants import (
    ActorRole,
    SignupAction,
    SignupMeans,
    SignupStatus,
    StaffReasonPolicy,
)
from events.ledger import SignupActor
from events.models import Event, EventSignup, SignupLedgerEntry
from events.overrides import REASON_MAX_LENGTH
from events.schemas import SignupSnapshot
from events.services import VOID_NO_HISTORY_MESSAGE, cancel_signup, process_rsvp
from events.tests.base import EventTestCase
from org.models import Organization, OrgSettings
from org.settings_constants import StaffOverridePolicy
from org.settings_service import get_org_settings


class _VoidApiFixtures(EventTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.client = APIClient()
        self._set_policy(StaffOverridePolicy.CONFIRM)

    def _set_policy(
        self, policy: str, codes: Sequence[str] = ("over_capacity",)
    ) -> None:
        row = get_org_settings(self.org)
        OrgSettings.objects.filter(pk=row.pk).update(
            staff_override_policy=policy, staff_override_warning_codes=list(codes)
        )

    def _row(self, signup: EventSignup) -> EventSignup:
        return EventSignup.objects.nocache().get(pk=signup.pk)

    def _join(self, event: Event, user: CustomUser | None = None) -> EventSignup:
        user = user or self.make_user()
        actor = SignupActor(user=user, role=ActorRole.MEMBER, means=SignupMeans.WEB)
        return process_rsvp(event, user, actor=actor)

    def _withdraw(self, signup: EventSignup) -> SignupLedgerEntry:
        actor = SignupActor(
            user=signup.user, role=ActorRole.MEMBER, means=SignupMeans.WEB
        )
        cancel_signup(self._row(signup), actor=actor)
        return SignupLedgerEntry.objects.filter(
            signup=signup, action=SignupAction.WITHDREW
        ).latest("pk")

    def _void_entries(self, signup: EventSignup) -> list[SignupLedgerEntry]:
        return list(
            SignupLedgerEntry.objects.filter(
                signup=signup, action=SignupAction.VOIDED_WITHDRAWAL
            )
        )

    def _post(
        self,
        signup: EventSignup,
        body: dict[str, Any],
        *,
        as_user: CustomUser,
        endpoint: str = "event-signup-void-withdrawal",
    ) -> Response:
        self.client.force_authenticate(as_user)
        return self.client.post(
            reverse(endpoint, args=[signup.pk]), body, format="json"
        )

    def _withdrawn(
        self, **event_fields: object
    ) -> tuple[EventSignup, SignupLedgerEntry]:
        event = self.make_event(**event_fields)
        signup = self._join(event, self.user)
        return signup, self._withdraw(signup)

    def _full_after_withdrawal(
        self, **event_fields: object
    ) -> tuple[EventSignup, SignupLedgerEntry]:
        event = self.make_event(max_players=2, **event_fields)
        self._join(event)
        signup = self._join(event, self.user)
        self._join(event)
        return signup, self._withdraw(signup)


@patch("events.services.notify_signup_changed")
class VoidWithdrawalApiTests(_VoidApiFixtures):
    def test_member_gets_403(self, _notify: Any) -> None:
        signup, _withdrew = self._withdrawn()

        response = self._post(signup, {"reason": "mine"}, as_user=self.user)

        self.assertEqual(response.status_code, 403)
        self.assertEqual(self._void_entries(signup), [])
        self.assertEqual(self._row(signup).status, SignupStatus.CANCELLED)

    def test_cross_org_staff_gets_403(self, _notify: Any) -> None:
        signup, _withdrew = self._withdrawn()
        outsider = self.make_user()
        other_org = Organization.objects.create(name="Other Org", owner=outsider)
        other_org.staff.add(outsider)

        reinstate = self._post(
            signup, {}, as_user=outsider, endpoint="event-signup-reinstate"
        )
        response = self._post(signup, {"reason": "x"}, as_user=outsider)

        self.assertEqual(reinstate.status_code, 403)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self._void_entries(signup), [])

    def test_full_event_409_then_200(self, _notify: Any) -> None:
        signup, withdrew = self._full_after_withdrawal()

        first = self._post(signup, {"reason": "mistaken"}, as_user=self.admin)

        self.assertEqual(first.status_code, 409)
        self.assertEqual(first.data["code"], "override_required")
        self.assertIs(first.data["blocked"], False)
        [violation] = first.data["violations"]
        self.assertEqual(violation["code"], "over_capacity")
        self.assertEqual(violation["category"], "seating")
        self.assertEqual(self._void_entries(signup), [])

        second = self._post(
            signup,
            {"reason": "mistaken", "acknowledged_codes": ["over_capacity"]},
            as_user=self.admin,
        )

        self.assertEqual(second.status_code, 200)
        snap = SignupSnapshot.model_validate(withdrew.before)
        self.assertEqual(second.data["status"], snap.status)
        self.assertEqual(second.data["commitment"], snap.commitment)
        self.assertEqual(second.data["rsvp_class"], snap.rsvp_class)
        row = self._row(signup)
        self.assertEqual(row.line_seq, snap.line_seq)
        self.assertEqual(row.signed_up_at, snap.signed_up_at)
        [entry] = self._void_entries(signup)
        self.assertEqual(entry.rules_overridden, ["over_capacity"])
        self.assertEqual(entry.caused_by_id, withdrew.pk)

    def test_reason_required_400(self, _notify: Any) -> None:
        signup, _withdrew = self._withdrawn(
            staff_reason_policy=StaffReasonPolicy.PLACEMENTS
        )

        response = self._post(signup, {}, as_user=self.admin)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data, {"error": "reason_required"})
        self.assertEqual(self._void_entries(signup), [])

    def test_override_reason_required_400(self, _notify: Any) -> None:
        signup, _withdrew = self._full_after_withdrawal(
            staff_reason_policy=StaffReasonPolicy.OPTIONAL
        )

        response = self._post(
            signup, {"acknowledged_codes": ["over_capacity"]}, as_user=self.admin
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["code"], "override_reason_required")
        self.assertEqual(self._void_entries(signup), [])
        self.assertEqual(self._row(signup).status, SignupStatus.CANCELLED)

    def test_no_history_400(self, _notify: Any) -> None:
        event = self.make_event()
        signup = EventSignup.objects.create(
            event=event, user=self.user, status=SignupStatus.CANCELLED
        )

        response = self._post(signup, {"reason": "x"}, as_user=self.admin)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data, {"error": VOID_NO_HISTORY_MESSAGE})
        self.assertEqual(
            response.data["error"],
            "This withdrawal has no recorded place to restore.",
        )

    def test_reason_over_500_rejected(self, _notify: Any) -> None:
        signup, _withdrew = self._withdrawn()

        response = self._post(
            signup, {"reason": "x" * (REASON_MAX_LENGTH + 1)}, as_user=self.admin
        )

        self.assertEqual(REASON_MAX_LENGTH, 500)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self._void_entries(signup), [])
        self.assertEqual(self._row(signup).status, SignupStatus.CANCELLED)

    def test_staff_self_void_uses_staff_power(self, _notify: Any) -> None:
        event = self.make_event()
        signup = self._join(event, self.admin)
        self._withdraw(signup)

        response = self._post(signup, {}, as_user=self.admin)

        self.assertEqual(response.status_code, 200)
        [entry] = self._void_entries(signup)
        self.assertIs(entry.after["extra"]["staff_power"], True)

    def test_success_returns_restored_signup(self, _notify: Any) -> None:
        signup, withdrew = self._withdrawn()

        response = self._post(signup, {"reason": "mistaken"}, as_user=self.admin)

        self.assertEqual(response.status_code, 200)
        snap = SignupSnapshot.model_validate(withdrew.before)
        self.assertEqual(response.data["id"], signup.pk)
        self.assertEqual(response.data["status"], snap.status)
        [entry] = self._void_entries(signup)
        self.assertEqual(entry.reason, "mistaken")


@patch("events.services.notify_signup_changed")
class ReinstateDelegationApiTests(_VoidApiFixtures):
    def _actions(self, signup: EventSignup) -> list[str]:
        return list(
            SignupLedgerEntry.objects.filter(signup=signup)
            .order_by("pk")
            .values_list("action", flat=True)
        )

    def test_staff_reinstate_with_history_voids(self, _notify: Any) -> None:
        signup, withdrew = self._withdrawn()

        response = self._post(
            signup, {}, as_user=self.admin, endpoint="event-signup-reinstate"
        )

        self.assertEqual(response.status_code, 200, response.content)
        snap = SignupSnapshot.model_validate(withdrew.before)
        self.assertEqual(response.data["status"], snap.status)
        [entry] = self._void_entries(signup)
        self.assertEqual(entry.caused_by_id, withdrew.pk)
        self.assertEqual(self._row(signup).line_seq, snap.line_seq)

    def test_staff_reinstate_full_event_never_409s(self, _notify: Any) -> None:
        for policy in StaffOverridePolicy:
            with self.subTest(policy=policy):
                self._set_policy(policy)
                signup, _withdrew = self._full_after_withdrawal()

                response = self._post(
                    signup,
                    {"acknowledged_codes": ["over_capacity"], "reason": "x"},
                    as_user=self.admin,
                    endpoint="event-signup-reinstate",
                )

                self.assertEqual(response.status_code, 200, response.content)
                self.assertEqual(response.data["status"], SignupStatus.WAITLISTED)
                self.assertEqual(self._void_entries(signup), [])
                self.assertEqual(self._actions(signup)[-1], SignupAction.REINSTATED)

    def test_member_reinstate_never_delegates(self, _notify: Any) -> None:
        signup, _withdrew = self._withdrawn()

        response = self._post(
            signup,
            {"acknowledged_codes": ["over_capacity"]},
            as_user=self.user,
            endpoint="event-signup-reinstate",
        )

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(self._void_entries(signup), [])
        self.assertEqual(self._actions(signup)[-1], SignupAction.REINSTATED)
