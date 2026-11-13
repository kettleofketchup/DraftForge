"""Tests for events.services.ensure_tournament_with_signups (#200)."""

from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone as tz
from rest_framework.test import APIClient

from app.models import CustomUser, Organization, PositionsModel
from events.constants import EventState
from events.models import Event, EventSignup
from events.services import (
    create_tournament_for_event,
    ensure_tournament_with_signups,
    restart_event_tournament,
)


class EnsureTournamentWithSignupsTest(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="Start Tournament Org")
        self.event = Event.objects.create(
            name="Start Test Event",
            organization=self.org,
            scheduled_at=tz.now(),
            timezone="UTC",
            roll_call_enabled=True,
        )
        self.users = []
        for i in range(5):
            u = CustomUser.objects.create(
                username=f"st_user_{i}",
                positions=PositionsModel.objects.create(),
            )
            self.users.append(u)

    def _make_signup(self, user, status):
        return EventSignup.objects.create(event=self.event, user=user, status=status)

    def test_creates_tournament_when_missing(self):
        self.assertIsNone(self.event.tournament)
        self._make_signup(self.users[0], "approved")
        ensure_tournament_with_signups(self.event)
        self.event.refresh_from_db()
        self.assertIsNotNone(self.event.tournament)
        self.assertEqual(self.event.tournament.users.count(), 1)

    def test_adds_only_approved_and_confirmed_users(self):
        self._make_signup(self.users[0], "approved")
        self._make_signup(self.users[1], "confirmed")
        self._make_signup(self.users[2], "rejected")
        self._make_signup(self.users[3], "cancelled")
        self._make_signup(self.users[4], "waitlisted")
        ensure_tournament_with_signups(self.event)
        self.event.refresh_from_db()
        added_pks = set(self.event.tournament.users.values_list("pk", flat=True))
        self.assertEqual(added_pks, {self.users[0].pk, self.users[1].pk})

    def test_idempotent_when_called_twice(self):
        self._make_signup(self.users[0], "approved")
        self._make_signup(self.users[1], "confirmed")
        ensure_tournament_with_signups(self.event)
        ensure_tournament_with_signups(self.event)
        self.event.refresh_from_db()
        # Same two users, no duplicates (Django M2M add is a no-op on existing)
        self.assertEqual(self.event.tournament.users.count(), 2)

    def test_works_when_tournament_already_exists(self):
        from events.services import create_tournament_for_event
        create_tournament_for_event(self.event)
        self.event.refresh_from_db()
        existing_pk = self.event.tournament.pk

        self._make_signup(self.users[0], "approved")
        ensure_tournament_with_signups(self.event)
        self.event.refresh_from_db()
        # Same tournament, just with the user added
        self.assertEqual(self.event.tournament.pk, existing_pk)
        self.assertEqual(self.event.tournament.users.count(), 1)

    def test_invalidates_cacheops_after_m2m_add(self):
        """M2M add does not auto-invalidate cacheops; ensure_tournament_with_signups must.

        The M2M change affects both sides of the relation — tournament.users.all()
        AND user.tournament_set.all() — so we invalidate the tournament, the event,
        AND every user we added. Mocking invalidate_after_commit is more deterministic
        than measuring live cache state and captures the actual invariant.

        Note: when the event has no tournament yet, create_tournament_for_event
        also calls invalidate_after_commit(event). So we expect 2 calls here:
        the create-tournament invalidation, then the M2M-add invalidation. We
        assert the M2M call (the one this test is really about) has the right
        shape regardless of the order.
        """
        from unittest.mock import patch

        self._make_signup(self.users[0], "approved")
        self._make_signup(self.users[1], "confirmed")
        with patch("events.services.invalidate_after_commit") as mock_inv:
            ensure_tournament_with_signups(self.event)

        self.event.refresh_from_db()
        # Find the M2M-add invalidation call — it's the one with the tournament
        # plus the two added users in its args.
        m2m_calls = [
            c for c in mock_inv.call_args_list
            if len(c.args) >= 2 and c.args[0] == self.event.tournament
        ]
        self.assertEqual(
            len(m2m_calls), 1,
            f"Expected exactly one M2M-add invalidation; got {mock_inv.call_args_list}",
        )
        args = m2m_calls[0].args
        self.assertEqual(args[0], self.event.tournament)
        self.assertEqual(args[1], self.event)
        # Both added users must be in the invalidation set
        self.assertEqual(set(args[2:]), {self.users[0], self.users[1]})


class EnsureTournamentRollCallRosterTest(TestCase):
    """Roster by event state: ROLL_CALL keeps only CONFIRMED players (#378)."""

    def setUp(self) -> None:
        self.org = Organization.objects.create(name="Roll Call Roster Org")
        self.users: list[CustomUser] = [
            CustomUser.objects.create(
                username=f"rc_user_{i}",
                positions=PositionsModel.objects.create(),
            )
            for i in range(5)
        ]

    def _event(self, state: str, roll_call_enabled: bool = True) -> Event:
        return Event.objects.create(
            name=f"Roll Call Roster {state}",
            organization=self.org,
            scheduled_at=tz.now(),
            timezone="UTC",
            roll_call_enabled=roll_call_enabled,
            state=state,
        )

    def _signups(self, event: Event) -> None:
        for user in self.users[:3]:
            EventSignup.objects.create(event=event, user=user, status="confirmed")
        for user in self.users[3:]:
            EventSignup.objects.create(event=event, user=user, status="approved")

    def _roster(self, event: Event) -> set[int]:
        event.refresh_from_db()
        return set(event.tournament.users.values_list("pk", flat=True))

    def test_roll_call_adds_only_confirmed(self) -> None:
        event = self._event(EventState.ROLL_CALL)
        self._signups(event)
        ensure_tournament_with_signups(event)
        self.assertEqual(self._roster(event), {u.pk for u in self.users[:3]})

    def test_roll_call_removes_unconfirmed_already_in_tournament(self) -> None:
        event = self._event(EventState.ROLL_CALL, roll_call_enabled=False)
        create_tournament_for_event(event)
        event.refresh_from_db()
        self._signups(event)
        event.tournament.users.add(*self.users)
        ensure_tournament_with_signups(event)
        self.assertEqual(self._roster(event), {u.pk for u in self.users[:3]})

    def test_roll_call_keeps_non_signup_tournament_members(self) -> None:
        event = self._event(EventState.ROLL_CALL)
        create_tournament_for_event(event)
        event.refresh_from_db()
        self._signups(event)
        extra = CustomUser.objects.create(
            username="rc_manual", positions=PositionsModel.objects.create()
        )
        event.tournament.users.add(extra)
        ensure_tournament_with_signups(event)
        self.assertEqual(
            self._roster(event), {u.pk for u in self.users[:3]} | {extra.pk}
        )

    def test_roll_call_idempotent(self) -> None:
        event = self._event(EventState.ROLL_CALL)
        self._signups(event)
        ensure_tournament_with_signups(event)
        ensure_tournament_with_signups(event)
        self.assertEqual(self._roster(event), {u.pk for u in self.users[:3]})

    def test_roll_call_invalidates_added_and_removed_users(self) -> None:
        event = self._event(EventState.ROLL_CALL)
        create_tournament_for_event(event)
        event.refresh_from_db()
        self._signups(event)
        event.tournament.users.add(self.users[3])
        with patch("events.services.invalidate_after_commit") as mock_inv:
            ensure_tournament_with_signups(event)
        args = mock_inv.call_args_list[-1].args
        self.assertEqual(args[0], event.tournament)
        self.assertEqual(args[1], event)
        self.assertEqual(set(args[2:]), set(self.users[:3]) | {self.users[3]})

    def test_signups_open_keeps_approved_and_confirmed(self) -> None:
        event = self._event(EventState.SIGNUPS_OPEN)
        self._signups(event)
        ensure_tournament_with_signups(event)
        self.assertEqual(self._roster(event), {u.pk for u in self.users})

    def test_start_tournament_endpoint_from_roll_call(self) -> None:
        event = self._event(EventState.ROLL_CALL)
        self._signups(event)
        staff = CustomUser.objects.create(
            username="rc_staff",
            is_staff=True,
            is_superuser=True,
            positions=PositionsModel.objects.create(),
        )
        client = APIClient()
        client.force_authenticate(staff)
        resp = client.post(f"/api/events/{event.pk}/start_tournament/")
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(self._roster(event), {u.pk for u in self.users[:3]})


class RestartEventTournamentRosterTest(TestCase):
    """restart_event_tournament rebuilds the SIGNUPS_OPEN roster."""

    def setUp(self) -> None:
        self.org = Organization.objects.create(name="Restart Roster Org")
        self.users: list[CustomUser] = [
            CustomUser.objects.create(
                username=f"rs_user_{i}",
                positions=PositionsModel.objects.create(),
            )
            for i in range(4)
        ]

    def _restart(self, roll_call_enabled: bool) -> set[int]:
        event = Event.objects.create(
            name="Restart Roster",
            organization=self.org,
            scheduled_at=tz.now(),
            timezone="UTC",
            roll_call_enabled=roll_call_enabled,
            state=EventState.IN_PROGRESS,
        )
        create_tournament_for_event(event)
        event.refresh_from_db()
        for user in self.users[:2]:
            EventSignup.objects.create(event=event, user=user, status="confirmed")
        for user in self.users[2:]:
            EventSignup.objects.create(event=event, user=user, status="approved")
        restart_event_tournament(event)
        event.refresh_from_db()
        self.assertEqual(event.state, EventState.SIGNUPS_OPEN)
        return set(event.tournament.users.values_list("pk", flat=True))

    def test_roll_call_event_re_adds_only_confirmed(self) -> None:
        self.assertEqual(self._restart(True), {u.pk for u in self.users[:2]})

    def test_no_roll_call_event_re_adds_approved_and_confirmed(self) -> None:
        self.assertEqual(self._restart(False), {u.pk for u in self.users})
