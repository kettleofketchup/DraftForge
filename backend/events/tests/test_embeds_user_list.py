"""Issue #194 — show up to 40 users, splitting fields on >1024-char overflow."""

from unittest.mock import MagicMock, patch

from django.test import TestCase

from events.discord.embeds import (
    _signup_counts,
    build_announcement_embeds,
    build_announcement_v2,
)
from events.schemas import EventSignupSchema
from events.tests.base import EventTestCase


def _mock_signup(name, status="confirmed"):
    s = MagicMock()
    s.display_name = name
    s.status = status
    return s


class UserListSplitTest(TestCase):
    """40-cap and 1024-char auto-split."""

    def test_under_40_short_names_single_field(self):
        from events.discord.embeds import _user_list

        signups = [_mock_signup(f"player{i}") for i in range(35)]
        result = _user_list(signups)
        # Single field: newline-joined, no "and N more"
        self.assertNotIn("and ", result)
        self.assertEqual(result.count("\n"), 34)

    def test_exactly_40_short_names_single_field_no_truncation(self):
        from events.discord.embeds import _user_list

        signups = [_mock_signup(f"player{i}") for i in range(40)]
        result = _user_list(signups)
        self.assertNotIn("and ", result)
        self.assertEqual(result.count("\n"), 39)

    def test_over_40_truncates_to_first_40(self):
        from events.discord.embeds import _user_list

        signups = [_mock_signup(f"player{i}") for i in range(45)]
        result = _user_list(signups)
        self.assertIn("and 5 more", result)

    def test_long_names_split_into_two_fields(self):
        """Field value can't exceed 1024 chars — overflow goes to a continuation field."""
        from events.discord.embeds import build_user_list_fields

        # 40 × ~32-char Discord usernames = ~1280 chars > 1024
        long = "a" * 30
        signups = [_mock_signup(f"{long}{i:02}") for i in range(40)]
        fields = build_user_list_fields(signups, name="Signed Up", inline=True)

        self.assertEqual(len(fields), 2)
        self.assertEqual(fields[0]["name"], "Signed Up")
        self.assertEqual(fields[1]["name"], "Signed Up (cont.)")
        self.assertLessEqual(len(fields[0]["value"]), 1024)
        self.assertLessEqual(len(fields[1]["value"]), 1024)

    def test_short_names_dont_split(self):
        from events.discord.embeds import build_user_list_fields

        signups = [_mock_signup(f"p{i:02}") for i in range(40)]
        fields = build_user_list_fields(signups, name="Signed Up", inline=True)
        self.assertEqual(len(fields), 1)
        self.assertEqual(fields[0]["name"], "Signed Up")

    def test_empty_input_returns_none_yet(self):
        from events.discord.embeds import build_user_list_fields

        fields = build_user_list_fields([], name="Signed Up", inline=True)
        self.assertEqual(len(fields), 1)
        self.assertEqual(fields[0]["value"], "*None yet*")


class SignedUpFollowsHoldsSeatTest(EventTestCase):
    def _row(self, pk: int, status: str, holds_seat: bool) -> EventSignupSchema:
        return EventSignupSchema.model_validate(
            {
                "id": pk,
                "event": 1,
                "user": pk,
                "username": f"player{pk}",
                "status": status,
                "holds_seat": holds_seat,
            }
        )

    def _rows(self) -> list[EventSignupSchema]:
        return [
            self._row(1, "confirmed", True),
            self._row(2, "rsvp", True),
            self._row(3, "tentative", False),
            self._row(4, "waitlisted", False),
            self._row(5, "rsvp", False),
        ]

    def test_signup_counts_use_holds_seat(self) -> None:
        with patch(
            "events.discord.embeds.get_event_signups", return_value=self._rows()
        ):
            active, confirmed = _signup_counts(self.event)
        self.assertEqual((active, confirmed), (2, 1))

    def test_signed_up_lists_exclude_seatless_rows(self) -> None:
        event = self.make_event(max_players=10)
        with patch(
            "events.discord.embeds.get_event_signups", return_value=self._rows()
        ):
            embeds = build_announcement_embeds(event)
            v2_fields = build_announcement_v2(event)["embeds"][1]["fields"]

        for fields in (embeds[1]["fields"], v2_fields):
            signed_up = next(f for f in fields if "Signed Up" in f["name"])
            self.assertIn("(2/10)", signed_up["name"])
            for name in ("player3", "player4", "player5"):
                self.assertNotIn(name, signed_up["value"])
