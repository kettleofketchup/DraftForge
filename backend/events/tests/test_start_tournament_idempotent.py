"""Tests for events.services.ensure_tournament_with_signups (#200)."""

from django.test import TestCase
from django.utils import timezone as tz

from app.models import CustomUser, Organization, PositionsModel
from events.models import Event, EventSignup
from events.services import ensure_tournament_with_signups


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
