from collections.abc import Callable
from datetime import timedelta
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

from django.utils import timezone as tz
from rest_framework.test import APIClient

from app.models import CustomUser, PositionsModel
from events.capacity import count_seats
from events.constants import EventState, SignupStatus
from events.discord._shared import _existing_active_signup
from events.discord.embeds import build_announcement_embeds, build_announcement_v2
from events.discord.handlers import handle_signup_button
from events.ledger import SignupActor
from events.models import Event, EventSignup, ReadyCheck, ReadyCheckEntry
from events.ready_check_constants import DROPPED_SIGNUP_MESSAGE, ReadyCheckEntryState
from events.services import (
    cancel_signup,
    create_tentative_signup,
    decline_signup,
    demote_to_waitlist,
    ensure_tournament_with_signups,
    is_registered_for_event,
    process_rsvp,
    reject_signup,
)
from events.tests.base import EventTestCase
from org.models import OrgUser
from org.promotion.recipients import candidates
from org.tests.test_promotion_recipients import _PoolFixture


class DroppedStatusTests(EventTestCase):
    def setUp(self) -> None:
        self.dropped_event = Event.objects.create(
            organization=self.org,
            name="Dropped Event",
            scheduled_at=tz.now() + timedelta(days=2),
            state=EventState.SIGNUPS_OPEN,
            created_by=self.admin,
        )
        self.player = self._player("dropped_player")

    def _player(self, username: str) -> CustomUser:
        return CustomUser.objects.create(
            username=username, positions=PositionsModel.objects.create()
        )

    def _signup(self, user: CustomUser, status: str) -> EventSignup:
        return EventSignup.objects.create(
            event=self.dropped_event, user=user, status=status
        )

    def _dropped(self) -> EventSignup:
        return self._signup(self.player, SignupStatus.DROPPED)

    def test_seat_count_excludes_dropped(self) -> None:
        self._signup(self._player("approved_player"), SignupStatus.APPROVED)
        self._dropped()

        self.assertEqual(count_seats(self.dropped_event), 1)

    def test_signup_count_annotation_excludes_dropped(self) -> None:
        self._signup(self._player("approved_player"), SignupStatus.APPROVED)
        self._dropped()
        client = APIClient()

        detail = client.get(f"/api/events/{self.dropped_event.pk}/")
        self.assertEqual(detail.status_code, 200, detail.content)
        self.assertEqual(detail.json()["signup_count"], 1)

        listing = client.get("/api/events/")
        self.assertEqual(listing.status_code, 200, listing.content)
        body = listing.json()
        rows = body["results"] if isinstance(body, dict) else body
        row = next(r for r in rows if r["id"] == self.dropped_event.pk)
        self.assertEqual(row["signup_count"], 1)

    def test_mutations_on_dropped_raise(self) -> None:
        signup = self._dropped()
        calls: dict[str, Callable[[], Any]] = {
            "cancel": lambda: cancel_signup(signup),
            "reject": lambda: reject_signup(signup, actor=SignupActor.system()),
            "demote": lambda: demote_to_waitlist(signup),
            "decline": lambda: decline_signup(self.dropped_event, self.player),
            "tentative": lambda: create_tentative_signup(
                self.dropped_event, self.player
            ),
        }
        for name, call in calls.items():
            with self.subTest(name):
                EventSignup.objects.filter(pk=signup.pk).update(
                    status=SignupStatus.DROPPED
                )
                signup.refresh_from_db()
                with self.assertRaises(ValueError):
                    call()
                stored = EventSignup.objects.get(pk=signup.pk)
                self.assertEqual(stored.status, SignupStatus.DROPPED)

    def test_tentative_message(self) -> None:
        self._dropped()

        with self.assertRaisesMessage(ValueError, DROPPED_SIGNUP_MESSAGE):
            create_tentative_signup(self.dropped_event, self.player)

    def test_resignup_rejected_and_row_kept(self) -> None:
        signup = self._dropped()

        with self.assertRaisesMessage(ValueError, DROPPED_SIGNUP_MESSAGE):
            process_rsvp(self.dropped_event, self.player)

        rows = EventSignup.objects.filter(event=self.dropped_event, user=self.player)
        self.assertEqual(
            list(rows.values_list("pk", "status")), [(signup.pk, "dropped")]
        )

    def test_entry_survives_resignup_attempts(self) -> None:
        signup = self._dropped()
        check = ReadyCheck.objects.create(event=self.dropped_event)
        entry = ReadyCheckEntry.for_signup(check, signup)
        entry.state = ReadyCheckEntryState.DROPPED
        entry.dropped_at = tz.now()
        entry.save()

        for attempt in (process_rsvp, create_tentative_signup):
            with self.subTest(attempt.__name__):
                with self.assertRaises(ValueError):
                    attempt(self.dropped_event, self.player)
                entry.refresh_from_db()
                self.assertEqual(entry.state, ReadyCheckEntryState.DROPPED)
                self.assertEqual(entry.signup_id, signup.pk)

        EventSignup.objects.filter(pk=signup.pk).delete()
        entry.refresh_from_db()
        self.assertIsNone(entry.signup)
        self.assertEqual(entry.user_id, self.player.pk)
        self.assertEqual(entry.state, ReadyCheckEntryState.DROPPED)

    def test_not_registered(self) -> None:
        self._dropped()

        self.assertFalse(is_registered_for_event(self.player, self.dropped_event))

    def test_tournament_roster_removes_dropped(self) -> None:
        for state in (EventState.ROLL_CALL, EventState.SIGNUPS_OPEN):
            with self.subTest(state):
                EventSignup.objects.filter(event=self.dropped_event).delete()
                self.dropped_event.state = state
                self.dropped_event.save(update_fields=["state", "updated_at"])
                keeper = self._player(f"keeper_{state}")
                self._signup(keeper, SignupStatus.CONFIRMED)
                self._dropped()
                tournament = ensure_tournament_with_signups(self.dropped_event)
                tournament.users.add(self.player)

                ensure_tournament_with_signups(self.dropped_event)

                users = set(tournament.users.values_list("pk", flat=True))
                self.assertIn(keeper.pk, users)
                self.assertNotIn(self.player.pk, users)

    def test_discord_existing_signup_returns_dropped(self) -> None:
        signup = self._dropped()

        self.assertEqual(
            _existing_active_signup(self.dropped_event, self.player), signup
        )

    def test_discord_signup_button_says_dropped(self) -> None:
        self.player.discordId = "100000000000000777"
        self.player.save()
        OrgUser.objects.create(user=self.player, organization=self.org)
        self._dropped()

        result = handle_signup_button(self.dropped_event.pk, "100000000000000777")

        self.assertEqual(result, {"action": "error", "message": DROPPED_SIGNUP_MESSAGE})


def _row(name: str, status: str) -> SimpleNamespace:
    return SimpleNamespace(
        display_name=name, status=status, waitlist_position=None, holds_seat=None
    )


class DroppedEmbedTests(EventTestCase):
    def _fields(self, builder: str) -> dict[str, str]:
        rows = [_row("ActiveAnn", "approved"), _row("DroppedDan", "dropped")]
        with patch("events.discord.embeds.get_event_signups", return_value=rows):
            if builder == "v2":
                fields = build_announcement_v2(self.event)["embeds"][1]["fields"]
            else:
                fields = build_announcement_embeds(self.event)[1]["fields"]
        return {f["name"]: f["value"] for f in fields}

    def test_embed_lists_dropped_as_declined(self) -> None:
        for builder in ("v1", "v2"):
            with self.subTest(builder):
                fields = self._fields(builder)
                signed_up = next(v for k, v in fields.items() if "Signed Up" in k)
                declined_name = next(k for k in fields if "Declined" in k)
                self.assertIn("ActiveAnn", signed_up)
                self.assertNotIn("DroppedDan", signed_up)
                self.assertIn(
                    "Signed Up (1/", next(k for k in fields if "Signed Up" in k)
                )
                self.assertIn("DroppedDan", fields[declined_name])
                self.assertIn("(1)", declined_name)


class DroppedPromotionRecipientsTests(_PoolFixture):
    def test_promotion_recipients_skip_dropped(self) -> None:
        dropped = self._user("dropped_recipient")
        cancelled = self._user("cancelled_recipient")
        kept = self._user("kept_recipient")
        self._tournament([dropped, cancelled, kept], days_ago=1, league=self.league)
        for user, status in (
            (dropped, SignupStatus.DROPPED),
            (cancelled, SignupStatus.CANCELLED),
        ):
            EventSignup.objects.create(event=self.event, user=user, status=status)

        rows = candidates(
            self.org, self.event, n=3, sender=self.sender, hide_signed_up=False
        )

        self.assertEqual({r["username"] for r in rows}, {"kept_recipient"})
