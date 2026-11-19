import ast
from pathlib import Path

from django.test import SimpleTestCase

from events.constants import (
    LINE_EXCLUDED_STATUSES,
    ActorRole,
    Commitment,
    RsvpClass,
    SignupAction,
    SignupMeans,
)
from events.exceptions import ImmutableFieldError, LedgerAppendOnlyError
from events.schemas import SignupSnapshot

EXPECTED_ACTIONS: list[str] = [
    "backfilled",
    "signed_up",
    "resigned_up",
    "switched_commitment",
    "approved",
    "confirmed",
    "unconfirmed",
    "rejected",
    "withdrew",
    "declined",
    "waitlisted",
    "promoted",
    "demoted",
    "reinstated",
    "voided_withdrawal",
    "transferred_out",
    "transferred_in",
    "swapped",
    "staff_added",
    "account_merged",
    "moved_event",
    "event_cancelled",
]


class SignupLedgerFoundationsTests(SimpleTestCase):
    def test_signup_action_values(self) -> None:
        self.assertEqual([a.value for a in SignupAction], EXPECTED_ACTIONS)

    def test_choices(self) -> None:
        self.assertEqual(Commitment.values, ["main", "maybe"])
        self.assertEqual(RsvpClass.values, ["standard"])
        self.assertEqual(ActorRole.values, ["member", "staff", "system"])
        self.assertEqual(
            SignupMeans.values,
            ["web", "discord_button", "discord_reaction", "system"],
        )

    def test_line_excluded_statuses(self) -> None:
        self.assertIsInstance(LINE_EXCLUDED_STATUSES, frozenset)
        self.assertEqual(
            LINE_EXCLUDED_STATUSES, frozenset({"cancelled", "rejected", "dropped"})
        )

    def test_exceptions_hierarchy(self) -> None:
        self.assertTrue(issubclass(ImmutableFieldError, ValueError))
        self.assertTrue(issubclass(LedgerAppendOnlyError, RuntimeError))

        source = (Path(__file__).resolve().parent.parent / "exceptions.py").read_text()
        imported: list[str] = []
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.ImportFrom) and node.module:
                imported.append(node.module)
            elif isinstance(node, ast.Import):
                imported.extend(alias.name for alias in node.names)
        self.assertFalse(
            [m for m in imported if m.startswith("events.models")], imported
        )

    def test_snapshot_round_trip(self) -> None:
        snap = SignupSnapshot(
            status="dropped", commitment="main", rsvp_class="standard", line_seq=3
        )
        restored = SignupSnapshot.model_validate(snap.model_dump(mode="json"))
        self.assertEqual(restored, snap)

        with_unknown = SignupSnapshot.model_validate(
            {"status": "rsvp", "commitment": "main", "rsvp_class": "standard", "foo": 1}
        )
        self.assertNotIn("foo", with_unknown.model_dump())

        a = SignupSnapshot(status="rsvp", commitment="main", rsvp_class="standard")
        b = SignupSnapshot(status="rsvp", commitment="main", rsvp_class="standard")
        self.assertEqual(a.extra, {})
        a.extra["fill_tier"] = 1
        self.assertEqual(b.extra, {})
