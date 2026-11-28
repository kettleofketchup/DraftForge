from typing import Any
from unittest.mock import patch

from django.urls import reverse
from rest_framework.response import Response
from rest_framework.test import APIClient

from app.models import CustomUser
from events.constants import ActorRole, SignupMeans, SignupStatus, StaffReasonPolicy
from events.eligibility import EligibilityResult, Reason, ReasonCode, Rule, Severity
from events.ledger import SignupActor
from events.models import Event, EventSignup, SignupLedgerEntry
from events.services import process_rsvp
from events.tests.base import EventTestCase

CONDUCT_BLOCK = EligibilityResult(
    reasons=(
        Reason(
            code=ReasonCode.CONDUCT_BELOW_THRESHOLD,
            severity=Severity.BLOCK,
            rule=Rule.CONDUCT_BLOCK,
            message="Below threshold",
            params={"tier": "block", "standing": 12},
        ),
    )
)


class SpotTransferApiTests(EventTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.client = APIClient()
        patch("events.services.notify_signup_changed").start()
        patch("events.services.notify_mark_interested").start()
        self.addCleanup(patch.stopall)

    def transfer_event(self, **overrides: Any) -> Event:
        fields: dict[str, Any] = {
            "allow_spot_transfer": True,
            "auto_approve": True,
            "auto_confirm": True,
        }
        fields.update(overrides)
        return self.make_event(**fields)

    def join(self, event: Event, user: CustomUser | None = None) -> EventSignup:
        user = user or self.make_user()
        actor = SignupActor(user=user, role=ActorRole.MEMBER, means=SignupMeans.WEB)
        return process_rsvp(event, user, actor=actor)

    def requiring(self, event: Event) -> None:
        Event.objects.filter(pk=event.pk).update(
            require_steam_id=True, require_mmr_verified=True
        )

    def row(self, signup: EventSignup) -> EventSignup:
        return EventSignup.objects.nocache().get(pk=signup.pk)

    def post(
        self, signup: EventSignup, body: dict[str, Any], *, as_user: CustomUser | None
    ) -> Response:
        if as_user is None:
            self.client.force_authenticate(None)
        else:
            self.client.force_authenticate(as_user)
        return self.client.post(
            reverse("event-signup-transfer", args=[signup.pk]), body, format="json"
        )

    def ledger_count(self, event: Event) -> int:
        return SignupLedgerEntry.objects.filter(event=event).count()

    def assert_refusal(self, response: Response, code: str) -> dict[str, Any]:
        self.assertEqual(response.status_code, 400, response.content)
        body = response.json()
        self.assertEqual(body["code"], code)
        self.assertIsInstance(body["error"], str)
        self.assertTrue(body["error"])
        return body

    def test_member_transfers_own_place(self) -> None:
        event = self.transfer_event()
        giver = self.join(event, self.user)
        recipient = self.make_user()

        response = self.post(
            giver, {"recipient_user_id": recipient.pk}, as_user=self.user
        )

        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertEqual(set(body), {"mode", "correlation_id", "giver", "recipient"})
        self.assertEqual(body["mode"], "transfer")
        self.assertTrue(body["correlation_id"].startswith("xfer:"))
        self.assertEqual(body["giver"]["id"], giver.pk)
        self.assertEqual(body["giver"]["status"], SignupStatus.CANCELLED)
        self.assertEqual(body["recipient"]["user"], recipient.pk)
        self.assertEqual(body["recipient"]["status"], giver.status)

    def test_member_swap_mode(self) -> None:
        event = self.transfer_event()
        giver = self.join(event, self.user)
        recipient = self.make_user()
        held = self.join(event, recipient)

        response = self.post(
            giver, {"recipient_user_id": recipient.pk}, as_user=self.user
        )

        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertEqual(body["mode"], "swap")
        self.assertEqual(body["recipient"]["id"], held.pk)

    def test_anonymous_403(self) -> None:
        event = self.transfer_event()
        giver = self.join(event, self.user)
        entries = self.ledger_count(event)

        response = self.post(
            giver, {"recipient_user_id": self.make_user().pk}, as_user=None
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.ledger_count(event), entries)

    def test_member_cannot_act_on_other_row_403(self) -> None:
        event = self.transfer_event()
        giver = self.join(event)
        entries = self.ledger_count(event)

        response = self.post(
            giver, {"recipient_user_id": self.user.pk}, as_user=self.user
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.ledger_count(event), entries)
        self.assertEqual(self.row(giver).status, giver.status)

    def test_staff_can_transfer_others(self) -> None:
        event = self.transfer_event()
        giver = self.join(event)
        recipient = self.make_user()

        response = self.post(
            giver, {"recipient_user_id": recipient.pk}, as_user=self.admin
        )

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["mode"], "transfer")
        entry = SignupLedgerEntry.objects.filter(event=event).latest("pk")
        self.assertEqual(entry.actor_role, ActorRole.STAFF)

    def test_staff_owner_uses_member_path(self) -> None:
        with self.subTest("ineligible recipient refused, not prompted"):
            event = self.transfer_event()
            giver = self.join(event, self.admin)
            self.requiring(event)

            response = self.post(
                giver,
                {
                    "recipient_user_id": self.make_user().pk,
                    "acknowledged_codes": [
                        ReasonCode.STEAM_ID_MISSING,
                        ReasonCode.MMR_UNVERIFIED,
                    ],
                    "reason": "mine",
                },
                as_user=self.admin,
            )

            self.assert_refusal(response, "recipient_ineligible")
        with self.subTest("placements policy needs no reason"):
            event = self.transfer_event(
                staff_reason_policy=StaffReasonPolicy.PLACEMENTS
            )
            giver = self.join(event, self.admin)

            response = self.post(
                giver, {"recipient_user_id": self.make_user().pk}, as_user=self.admin
            )

            self.assertEqual(response.status_code, 200, response.content)
            entry = SignupLedgerEntry.objects.filter(event=event).latest("pk")
            self.assertEqual(entry.actor_role, ActorRole.MEMBER)

    def test_disabled_returns_transfer_disabled(self) -> None:
        event = self.transfer_event(allow_spot_transfer=False)
        giver = self.join(event, self.user)

        response = self.post(
            giver, {"recipient_user_id": self.make_user().pk}, as_user=self.user
        )

        body = self.assert_refusal(response, "transfer_disabled")
        self.assertNotIn("reasons", body)

    def test_user_signups_off_refuses_member(self) -> None:
        event = self.transfer_event()
        giver = self.join(event, self.user)
        Event.objects.filter(pk=event.pk).update(allow_user_signups=False)

        response = self.post(
            giver, {"recipient_user_id": self.make_user().pk}, as_user=self.user
        )

        body = self.assert_refusal(response, "user_signups_disabled")
        self.assertNotIn("reasons", body)

    def test_deleted_giver_returns_refusal(self) -> None:
        event = self.transfer_event()
        giver = self.join(event, self.user)
        stale = self.row(giver)
        EventSignup.objects.filter(pk=giver.pk).delete()

        with patch("events.views.EventSignupViewSet.get_object", return_value=stale):
            response = self.post(
                giver, {"recipient_user_id": self.make_user().pk}, as_user=self.user
            )

        self.assert_refusal(response, "giver_not_active")

    def test_recipient_not_found_shapes(self) -> None:
        event = self.transfer_event()
        giver = self.join(event, self.user)
        missing_pk = CustomUser.objects.order_by("-pk").first().pk + 1000
        entries = self.ledger_count(event)
        bodies = []
        for label, body in (
            ("missing", {}),
            ("not an int", {"recipient_user_id": "abc"}),
            ("null", {"recipient_user_id": None}),
            ("nonexistent", {"recipient_user_id": missing_pk}),
            ("negative", {"recipient_user_id": -1}),
            ("overflow", {"recipient_user_id": 10**30}),
            ("list", {"recipient_user_id": [1]}),
        ):
            with self.subTest(label):
                for as_user in (self.user, self.admin):
                    response = self.post(giver, body, as_user=as_user)
                    bodies.append(self.assert_refusal(response, "recipient_not_found"))
        self.assertEqual(len({str(b) for b in bodies}), 1)
        self.assertEqual(set(bodies[0]), {"code", "error"})
        self.assertEqual(self.ledger_count(event), entries)

    def test_ineligible_body_has_reasons_without_params(self) -> None:
        event = self.transfer_event()
        giver = self.join(event, self.user)
        self.requiring(event)

        response = self.post(
            giver, {"recipient_user_id": self.make_user().pk}, as_user=self.user
        )

        body = self.assert_refusal(response, "recipient_ineligible")
        codes = {r["code"] for r in body["reasons"]}
        self.assertEqual(
            codes, {ReasonCode.STEAM_ID_MISSING, ReasonCode.MMR_UNVERIFIED}
        )
        for entry in body["reasons"]:
            self.assertEqual(
                set(entry), {"code", "severity", "rule", "message", "fix", "params"}
            )
            self.assertEqual(entry["severity"], "needs_approval")

        with patch("events.services.evaluate_signup", return_value=CONDUCT_BLOCK):
            response = self.post(
                giver, {"recipient_user_id": self.make_user().pk}, as_user=self.user
            )

        body = self.assert_refusal(response, "recipient_ineligible")
        self.assertEqual(
            body["reasons"],
            [
                {
                    "code": "recipient_ineligible",
                    "severity": "block",
                    "rule": "eligibility",
                    "message": "Not eligible for this event",
                    "fix": None,
                    "params": {},
                }
            ],
        )
        self.assertNotIn(b"standing", response.content)
        self.assertNotIn(b"conduct", response.content)

    def test_member_acknowledged_codes_ignored(self) -> None:
        event = self.transfer_event()
        giver = self.join(event, self.user)
        self.requiring(event)
        entries = self.ledger_count(event)

        response = self.post(
            giver,
            {
                "recipient_user_id": self.make_user().pk,
                "acknowledged_codes": [
                    ReasonCode.STEAM_ID_MISSING,
                    ReasonCode.MMR_UNVERIFIED,
                ],
                "reason": "please",
            },
            as_user=self.user,
        )

        self.assert_refusal(response, "recipient_ineligible")
        self.assertEqual(self.ledger_count(event), entries)

    def test_staff_override_409_then_200(self) -> None:
        event = self.transfer_event()
        giver = self.join(event)
        self.requiring(event)
        recipient = self.make_user()

        prompt = self.post(
            giver, {"recipient_user_id": recipient.pk}, as_user=self.admin
        )

        self.assertEqual(prompt.status_code, 409, prompt.content)
        body = prompt.json()
        self.assertEqual(body["code"], "override_required")
        codes = [v["code"] for v in body["violations"]]
        self.assertIn(ReasonCode.STEAM_ID_MISSING, codes)

        no_reason = self.post(
            giver,
            {"recipient_user_id": recipient.pk, "acknowledged_codes": codes},
            as_user=self.admin,
        )
        self.assertEqual(no_reason.status_code, 400, no_reason.content)
        self.assertEqual(no_reason.json(), {"code": "override_reason_required"})

        response = self.post(
            giver,
            {
                "recipient_user_id": recipient.pk,
                "acknowledged_codes": codes,
                "reason": "vouched for",
            },
            as_user=self.admin,
        )

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["recipient"]["user"], recipient.pk)

    def test_reason_required_400(self) -> None:
        event = self.transfer_event(staff_reason_policy=StaffReasonPolicy.PLACEMENTS)
        giver = self.join(event)
        recipient = self.make_user()
        entries = self.ledger_count(event)

        response = self.post(
            giver, {"recipient_user_id": recipient.pk}, as_user=self.admin
        )

        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(response.json(), {"error": "reason_required"})
        self.assertEqual(self.ledger_count(event), entries)

        response = self.post(
            giver,
            {"recipient_user_id": recipient.pk, "reason": "requested"},
            as_user=self.admin,
        )

        self.assertEqual(response.status_code, 200, response.content)
