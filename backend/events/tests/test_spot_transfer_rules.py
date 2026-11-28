import json

from django.test import SimpleTestCase

from events.constants import EventState, SignupStatus
from events.eligibility import (
    EligibilityResult,
    FixAction,
    FixKind,
    Reason,
    ReasonCode,
    Rule,
    Severity,
)
from events.exceptions import SpotTransferRefused
from events.models import EventSignup
from events.services import (
    TRANSFER_EVENT_STATES,
    _member_safe_reasons,
    _member_status_cap,
    _place_rank,
)

GENERIC = {
    "code": "recipient_ineligible",
    "severity": "block",
    "rule": "eligibility",
    "message": "Not eligible for this event",
    "fix": None,
    "params": {},
}
E2_KEYS = {"code", "severity", "rule", "message", "fix", "params"}


def _row(pk: int, status: str, line_seq: int | None) -> EventSignup:
    return EventSignup(pk=pk, status=status, line_seq=line_seq)


def _conduct(rule: str, severity: Severity) -> Reason:
    return Reason(
        code=ReasonCode.CONDUCT_BELOW_THRESHOLD,
        severity=severity,
        rule=rule,
        message="Your attendance record is below this organization's threshold.",
        params={"tier": "block"},
    )


class SpotTransferRefusedTests(SimpleTestCase):
    def test_refused_carries_code_and_reasons(self) -> None:
        exc = SpotTransferRefused("same_user", "x", [{"code": "a"}])
        self.assertEqual(exc.code, "same_user")
        self.assertEqual(exc.message, "x")
        self.assertEqual(list(exc.reasons), [{"code": "a"}])
        self.assertEqual(str(exc), "x")
        self.assertIsInstance(exc, ValueError)

    def test_refused_reasons_default_empty(self) -> None:
        self.assertEqual(list(SpotTransferRefused("same_user", "x").reasons), [])

    def test_transfer_event_states(self) -> None:
        self.assertEqual(
            TRANSFER_EVENT_STATES,
            frozenset({EventState.SIGNUPS_OPEN, EventState.ROLL_CALL}),
        )


class PlaceRankTests(SimpleTestCase):
    def test_place_rank_orders_classes(self) -> None:
        approved = _row(1, SignupStatus.APPROVED, 9)
        rsvp = _row(2, SignupStatus.RSVP, 1)
        pending = _row(3, SignupStatus.PENDING_APPROVAL, 2)
        waitlisted = _row(4, SignupStatus.WAITLISTED, 1)
        tentative = _row(5, SignupStatus.TENTATIVE, 0)
        self.assertLess(_place_rank(approved), _place_rank(rsvp))
        self.assertLess(_place_rank(rsvp), _place_rank(pending))
        self.assertLess(_place_rank(rsvp), _place_rank(waitlisted))
        self.assertLess(_place_rank(waitlisted), _place_rank(tentative))

    def test_confirmed_and_approved_share_a_class(self) -> None:
        confirmed = _row(1, SignupStatus.CONFIRMED, 5)
        approved = _row(2, SignupStatus.APPROVED, 3)
        self.assertLess(_place_rank(approved), _place_rank(confirmed))
        self.assertEqual(_place_rank(approved)[0], _place_rank(confirmed)[0])

    def test_line_seq_then_pk_break_ties(self) -> None:
        early = _row(9, SignupStatus.APPROVED, 1)
        late = _row(1, SignupStatus.APPROVED, 2)
        self.assertLess(_place_rank(early), _place_rank(late))
        low_pk = _row(3, SignupStatus.APPROVED, 4)
        high_pk = _row(7, SignupStatus.APPROVED, 4)
        self.assertLess(_place_rank(low_pk), _place_rank(high_pk))

    def test_missing_line_seq_ranks_last_in_class(self) -> None:
        unsequenced = _row(1, SignupStatus.APPROVED, None)
        sequenced = _row(2, SignupStatus.APPROVED, 500)
        self.assertLess(_place_rank(sequenced), _place_rank(unsequenced))


class MemberStatusCapTests(SimpleTestCase):
    def test_member_status_cap(self) -> None:
        cases = [
            (SignupStatus.APPROVED, SignupStatus.RSVP, SignupStatus.RSVP),
            (SignupStatus.CONFIRMED, SignupStatus.APPROVED, SignupStatus.APPROVED),
            (SignupStatus.APPROVED, SignupStatus.CONFIRMED, SignupStatus.APPROVED),
            (
                SignupStatus.PENDING_APPROVAL,
                SignupStatus.CONFIRMED,
                SignupStatus.PENDING_APPROVAL,
            ),
            (SignupStatus.WAITLISTED, SignupStatus.RSVP, SignupStatus.WAITLISTED),
            (SignupStatus.TENTATIVE, SignupStatus.RSVP, SignupStatus.TENTATIVE),
        ]
        for giver, decided, expected in cases:
            with self.subTest(giver=giver, decided=decided):
                self.assertEqual(_member_status_cap(giver, decided), expected)


class MemberSafeReasonsTests(SimpleTestCase):
    def test_member_safe_reasons_keep_e2_shape(self) -> None:
        reason = Reason(
            code=ReasonCode.STEAM_ID_MISSING,
            severity=Severity.NEEDS_APPROVAL,
            rule=Rule.REQUIRE_STEAM_ID,
            message="This event requires a Steam friend ID on your profile.",
            fix=FixAction(FixKind.UPDATE_PROFILE, url="https://x/profile"),
        )
        out = _member_safe_reasons(EligibilityResult(reasons=(reason,)))
        self.assertEqual(out, [reason.as_dict()])
        self.assertEqual(set(out[0]), E2_KEYS)

    def test_member_safe_reasons_redact_recipient_profile_params(self) -> None:
        below = Reason(
            code=ReasonCode.BELOW_MIN_MMR,
            severity=Severity.NEEDS_APPROVAL,
            rule=Rule.DOTA_MIN_MMR,
            message="Your MMR is below this event's minimum.",
            params={"min_mmr": 3000, "mmr": 2512},
        )
        rank_type = Reason(
            code=ReasonCode.RANK_TYPE_DISALLOWED,
            severity=Severity.NEEDS_APPROVAL,
            rule=Rule.DOTA_RANK_TYPE,
            message="This event does not accept your rank type.",
            params={"rank_status": "never"},
        )
        out = _member_safe_reasons(EligibilityResult(reasons=(below, rank_type)))
        self.assertEqual(out[0]["params"], {"min_mmr": 3000})
        self.assertEqual(out[1]["params"], {})
        self.assertEqual(out[0]["message"], below.message)
        self.assertEqual(out[0]["severity"], "needs_approval")
        self.assertNotIn("2512", json.dumps(out))
        self.assertNotIn("never", json.dumps(out))

    def test_member_safe_reasons_collapse_conduct(self) -> None:
        for rule, severity in (
            (Rule.CONDUCT_BLOCK, Severity.BLOCK),
            (Rule.CONDUCT_REQUIRE_APPROVAL, Severity.NEEDS_APPROVAL),
        ):
            with self.subTest(rule=rule):
                out = _member_safe_reasons(
                    EligibilityResult(reasons=(_conduct(rule, severity),))
                )
                self.assertEqual(out, [GENERIC])
                dumped = json.dumps(out).lower()
                self.assertNotIn("standing", dumped)
                self.assertNotIn("conduct", dumped)
                self.assertNotIn("attendance", dumped)

    def test_generic_entry_deduplicated_and_requirements_kept(self) -> None:
        steam = Reason(
            code=ReasonCode.STEAM_ID_MISSING,
            severity=Severity.NEEDS_APPROVAL,
            rule=Rule.REQUIRE_STEAM_ID,
            message="m",
        )
        out = _member_safe_reasons(
            EligibilityResult(
                reasons=(
                    _conduct(Rule.CONDUCT_REQUIRE_APPROVAL, Severity.NEEDS_APPROVAL),
                    steam,
                    _conduct(Rule.CONDUCT_BLOCK, Severity.BLOCK),
                )
            )
        )
        self.assertEqual(
            [e["code"] for e in out], ["steam_id_missing", "recipient_ineligible"]
        )
        self.assertEqual(out.count(GENERIC), 1)

    def test_opaque_refusal_matches_conduct_collapse(self) -> None:
        steam = Reason(
            code=ReasonCode.STEAM_ID_MISSING,
            severity=Severity.NEEDS_APPROVAL,
            rule=Rule.REQUIRE_STEAM_ID,
            message="m",
        )
        conduct = _conduct(Rule.CONDUCT_BLOCK, Severity.BLOCK)
        self.assertEqual(
            _member_safe_reasons(EligibilityResult(reasons=(steam,)), opaque=True),
            _member_safe_reasons(EligibilityResult(reasons=(conduct, steam))),
        )
        self.assertEqual(
            _member_safe_reasons(EligibilityResult(), opaque=True), [GENERIC]
        )

    def test_clean_result_gives_no_reasons(self) -> None:
        self.assertEqual(_member_safe_reasons(EligibilityResult()), [])
