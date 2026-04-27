from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase, TransactionTestCase
from django.utils import timezone as tz
from rest_framework import status
from rest_framework.test import APIClient

from app.models import CustomUser, League, Organization, PositionsModel
from events.constants import EventState, SignupStatus
from events.models import Event, EventSignup
from events.tests.base import EventTestCase


class EventAPITests(EventTestCase):
    def setUp(self):
        self.client = APIClient()

    def _create_event(self, **kwargs):
        defaults = dict(
            organization=self.org,
            name="API Event",
            scheduled_at=tz.now() + timedelta(days=7),
            state=EventState.UPCOMING,
            created_by=self.admin,
            tournament_name="API Tourney",
            tournament_league=self.league,
        )
        defaults.update(kwargs)
        return Event.objects.create(**defaults)

    def test_list_events_public(self):
        self._create_event()
        r = self.client.get("/api/events/")
        self.assertEqual(r.status_code, status.HTTP_200_OK)

    def test_create_event_requires_auth(self):
        r = self.client.post("/api/events/", {})
        self.assertEqual(r.status_code, status.HTTP_403_FORBIDDEN)

    def test_rsvp_for_event(self):
        event = self._create_event(state=EventState.SIGNUPS_OPEN)
        self.client.force_authenticate(user=self.user)
        r = self.client.post(f"/api/events/{event.pk}/rsvp/")
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        self.assertEqual(r.data["status"], SignupStatus.RSVP)

    def test_rsvp_duplicate_rejected(self):
        event = self._create_event(state=EventState.SIGNUPS_OPEN)
        self.client.force_authenticate(user=self.user)
        self.client.post(f"/api/events/{event.pk}/rsvp/")
        r = self.client.post(f"/api/events/{event.pk}/rsvp/")
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_open_signups_requires_staff(self):
        event = self._create_event()
        self.client.force_authenticate(user=self.user)
        r = self.client.post(f"/api/events/{event.pk}/open_signups/")
        self.assertEqual(r.status_code, status.HTTP_403_FORBIDDEN)

    def test_open_signups_as_staff(self):
        event = self._create_event()
        self.client.force_authenticate(user=self.admin)
        r = self.client.post(f"/api/events/{event.pk}/open_signups/")
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        event.refresh_from_db()
        self.assertEqual(event.state, EventState.SIGNUPS_OPEN)

    def test_cancel_event(self):
        event = self._create_event()
        self.client.force_authenticate(user=self.admin)
        r = self.client.post(f"/api/events/{event.pk}/cancel/")
        self.assertEqual(r.status_code, status.HTTP_200_OK)

    def test_approve_signup_requires_staff(self):
        event = self._create_event(state=EventState.SIGNUPS_OPEN)
        signup = EventSignup.objects.create(
            event=event, user=self.user, status=SignupStatus.RSVP
        )
        self.client.force_authenticate(user=self.user)
        r = self.client.post(f"/api/events/signups/{signup.pk}/approve/")
        self.assertEqual(r.status_code, status.HTTP_403_FORBIDDEN)

    def test_approve_signup_as_staff(self):
        event = self._create_event(state=EventState.SIGNUPS_OPEN)
        signup = EventSignup.objects.create(
            event=event, user=self.user, status=SignupStatus.RSVP
        )
        self.client.force_authenticate(user=self.admin)
        r = self.client.post(f"/api/events/signups/{signup.pk}/approve/")
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        signup.refresh_from_db()
        self.assertEqual(signup.status, SignupStatus.APPROVED)

    def test_cancel_own_signup(self):
        event = self._create_event(state=EventState.SIGNUPS_OPEN)
        signup = EventSignup.objects.create(
            event=event, user=self.user, status=SignupStatus.RSVP
        )
        self.client.force_authenticate(user=self.user)
        r = self.client.post(f"/api/events/signups/{signup.pk}/cancel_signup/")
        self.assertEqual(r.status_code, status.HTTP_200_OK)

    def test_cannot_cancel_others_signup(self):
        event = self._create_event(state=EventState.SIGNUPS_OPEN)
        signup = EventSignup.objects.create(
            event=event, user=self.admin, status=SignupStatus.RSVP
        )
        self.client.force_authenticate(user=self.user)
        r = self.client.post(f"/api/events/signups/{signup.pk}/cancel_signup/")
        self.assertEqual(r.status_code, status.HTTP_403_FORBIDDEN)

    def test_filter_by_organization(self):
        self._create_event()
        r = self.client.get(f"/api/events/?organization={self.org.pk}")
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        # Base class creates self.event for the same org, plus the one above
        self.assertEqual(len(r.data), 2)

    def test_filter_by_state(self):
        self._create_event(state=EventState.SIGNUPS_OPEN)
        self._create_event(
            name="F",
            state=EventState.UPCOMING,
            scheduled_at=tz.now() + timedelta(days=14),
        )
        r = self.client.get("/api/events/?state=signups_open")
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        # Base event (signups_open) + the one created above = 2
        self.assertEqual(len(r.data), 2)


class ReopenSignupsViewTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.staff = CustomUser.objects.create_user(username="reopen_staff", password="x")
        cls.staff.positions = PositionsModel.objects.create()
        cls.staff.save()
        cls.unrelated = CustomUser.objects.create_user(username="reopen_unrelated", password="x")
        cls.unrelated.positions = PositionsModel.objects.create()
        cls.unrelated.save()
        cls.org = Organization.objects.create(name="Reopen Org", owner=cls.staff)
        cls.org.staff.add(cls.staff)
        cls.event = Event.objects.create(
            organization=cls.org,
            name="Reopen Event",
            scheduled_at=tz.now() + timedelta(days=1),
            state=EventState.ROLL_CALL,
            created_by=cls.staff,
            tournament_name="T",
        )

    def setUp(self):
        self.client = APIClient()

    def test_reopen_signups_succeeds_for_staff_in_roll_call(self):
        self.client.force_authenticate(self.staff)
        with patch("events.discord.notify_event_announced") as mock_notify:
            resp = self.client.post(f"/api/events/{self.event.pk}/reopen_signups/")
        assert resp.status_code == 200, resp.content
        self.event.refresh_from_db()
        assert self.event.state == EventState.SIGNUPS_OPEN
        mock_notify.assert_not_called()

    def test_reopen_signups_403_for_unrelated(self):
        self.client.force_authenticate(self.unrelated)
        resp = self.client.post(f"/api/events/{self.event.pk}/reopen_signups/")
        assert resp.status_code == 403

    def test_reopen_signups_400_when_not_in_roll_call(self):
        self.event.state = EventState.SIGNUPS_OPEN
        self.event.save(update_fields=["state"])
        self.client.force_authenticate(self.staff)
        resp = self.client.post(f"/api/events/{self.event.pk}/reopen_signups/")
        assert resp.status_code == 400


class LeagueStaffEventActionsTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = CustomUser.objects.create_user(username="league_owner", password="x")
        cls.owner.positions = PositionsModel.objects.create()
        cls.owner.save()
        cls.league_staff_user = CustomUser.objects.create_user(username="league_staff_v", password="x")
        cls.league_staff_user.positions = PositionsModel.objects.create()
        cls.league_staff_user.save()
        cls.org = Organization.objects.create(name="LS Org", owner=cls.owner)
        cls.league = League.objects.create(name="LS League", organization=cls.org, steam_league_id=77777)
        cls.league.staff.add(cls.league_staff_user)
        cls.event = Event.objects.create(
            organization=cls.org,
            name="LS Event",
            scheduled_at=tz.now() + timedelta(days=1),
            state=EventState.ROLL_CALL,
            created_by=cls.owner,
            tournament_name="T",
            tournament_league=cls.league,
        )

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.league_staff_user)

    def test_league_staff_can_reopen_signups(self):
        resp = self.client.post(f"/api/events/{self.event.pk}/reopen_signups/")
        assert resp.status_code == 200, resp.content

    def test_league_staff_can_admin_signup(self):
        """League staff can admin-add during SIGNUPS_OPEN. Roll-call coverage lands in Task 5."""
        # Flip the event to SIGNUPS_OPEN since Task 5 (admin_signup → staff_add_signup) hasn't landed yet.
        self.event.state = EventState.SIGNUPS_OPEN
        self.event.save(update_fields=["state"])
        player = CustomUser.objects.create_user(username="ls_player", password="x")
        player.positions = PositionsModel.objects.create()
        player.save()
        resp = self.client.post(
            f"/api/events/{self.event.pk}/admin-signup/",
            {"user_id": player.pk},
            format="json",
        )
        assert resp.status_code == 201, resp.content

    def test_league_staff_can_act_on_event_signups(self):
        """Verify the EventSignup-level action permission widening (Task 4 step 4)."""
        from events.models import EventSignup
        from events.constants import SignupStatus

        # Create a signup to act on
        player = CustomUser.objects.create_user(username="ls_target", password="x")
        player.positions = PositionsModel.objects.create()
        player.save()
        signup = EventSignup.objects.create(
            event=self.event,
            user=player,
            status=SignupStatus.RSVP,
        )

        # League staff approves
        resp = self.client.post(f"/api/events/signups/{signup.pk}/approve/")
        assert resp.status_code == 200, resp.content

    def test_league_staff_can_restart_tournament(self):
        """League staff should be able to restart_tournament on a league event."""
        # restart_tournament typically requires the event to be in a state where a tournament exists.
        # If your test event doesn't have a tournament, the action may return 400 — acceptable;
        # we only care about the permission check (200 or 400, NOT 403).
        resp = self.client.post(f"/api/events/{self.event.pk}/restart_tournament/")
        assert resp.status_code != 403, resp.content


class AdminSignupDuringRollCallTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.staff = CustomUser.objects.create_user(username="adm_staff", password="x")
        cls.staff.positions = PositionsModel.objects.create()
        cls.staff.save()
        cls.player = CustomUser.objects.create_user(username="adm_player", password="x")
        cls.player.positions = PositionsModel.objects.create()
        cls.player.save()
        cls.org = Organization.objects.create(name="Adm Org", owner=cls.staff)
        cls.org.staff.add(cls.staff)
        cls.event = Event.objects.create(
            organization=cls.org,
            name="Adm Event",
            scheduled_at=tz.now() + timedelta(days=1),
            state=EventState.ROLL_CALL,
            created_by=cls.staff,
            tournament_name="T",
        )

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.staff)

    def test_admin_signup_succeeds_during_roll_call(self):
        resp = self.client.post(
            f"/api/events/{self.event.pk}/admin-signup/",
            {"user_id": self.player.pk},
            format="json",
        )
        assert resp.status_code == 201, resp.content

    def test_public_rsvp_still_rejected_during_roll_call(self):
        self.client.force_authenticate(self.player)
        resp = self.client.post(f"/api/events/{self.event.pk}/rsvp/")
        assert resp.status_code == 400


class UserCanManageRetrieveTest(EventTestCase):
    """Verify cached retrieve() emits per-request user_can_manage."""

    def setUp(self):
        self.client = APIClient()

    def test_org_staff_sees_user_can_manage_true(self):
        self.client.force_authenticate(self.admin)
        resp = self.client.get(f"/api/events/{self.event.pk}/")
        assert resp.status_code == 200
        assert resp.json()["user_can_manage"] is True

    def test_league_staff_sees_user_can_manage_true(self):
        self.client.force_authenticate(self.league_staff)
        resp = self.client.get(f"/api/events/{self.event.pk}/")
        assert resp.status_code == 200
        assert resp.json()["user_can_manage"] is True

    def test_unrelated_user_sees_user_can_manage_false(self):
        self.client.force_authenticate(self.unrelated_user)
        resp = self.client.get(f"/api/events/{self.event.pk}/")
        assert resp.status_code == 200
        assert resp.json()["user_can_manage"] is False

    def test_no_cache_leak_across_users(self):
        """Hit retrieve as staff, unrelated, then staff again — values must alternate per request.

        The third round-trip catches a regression where the cached payload gets
        mutated to True (from the staff read), which would only manifest after a re-read.
        """
        self.client.force_authenticate(self.admin)
        first = self.client.get(f"/api/events/{self.event.pk}/").json()
        assert first["user_can_manage"] is True

        self.client.force_authenticate(self.unrelated_user)
        second = self.client.get(f"/api/events/{self.event.pk}/").json()
        assert second["user_can_manage"] is False

        self.client.force_authenticate(self.admin)
        third = self.client.get(f"/api/events/{self.event.pk}/").json()
        assert third["user_can_manage"] is True, (
            "Third request as staff should be True again — if False, the cached "
            "payload was poisoned by the unrelated user's read."
        )

    def test_event_without_league_returns_false_for_league_staff(self):
        from events.models import Event

        no_league_event = Event.objects.create(
            organization=self.org,
            name="No League",
            scheduled_at=self.event.scheduled_at,
            state=self.event.state,
            created_by=self.admin,
            tournament_name="T",
        )
        self.client.force_authenticate(self.league_staff)
        resp = self.client.get(f"/api/events/{no_league_event.pk}/")
        assert resp.json()["user_can_manage"] is False


class EventPatchTournamentLeagueTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = CustomUser.objects.create_user(username="eptl_admin", password="x")
        cls.admin.positions = PositionsModel.objects.create()
        cls.admin.save()
        cls.org_a = Organization.objects.create(name="EPTL Org A", owner=cls.admin)
        cls.org_a.staff.add(cls.admin)
        cls.org_b = Organization.objects.create(name="EPTL Org B", owner=cls.admin)
        cls.league_a1 = League.objects.create(
            name="A League 1",
            organization=cls.org_a,
            steam_league_id=40001,
        )
        cls.league_a2 = League.objects.create(
            name="A League 2",
            organization=cls.org_a,
            steam_league_id=40002,
        )
        cls.league_b = League.objects.create(
            name="B League",
            organization=cls.org_b,
            steam_league_id=40003,
        )
        cls.event = Event.objects.create(
            organization=cls.org_a,
            name="EPTL Event",
            scheduled_at=tz.now() + timedelta(days=1),
            state=EventState.SIGNUPS_OPEN,
            created_by=cls.admin,
            tournament_name="T",
            tournament_league=cls.league_a1,
        )

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.admin)

    def test_swap_to_same_org_league_succeeds(self):
        resp = self.client.patch(
            f"/api/events/{self.event.pk}/",
            {"tournament_league": self.league_a2.pk},
            format="json",
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        self.event.refresh_from_db()
        self.assertEqual(self.event.tournament_league_id, self.league_a2.pk)

    def test_swap_to_different_org_league_returns_400(self):
        resp = self.client.patch(
            f"/api/events/{self.event.pk}/",
            {"tournament_league": self.league_b.pk},
            format="json",
        )
        self.assertEqual(resp.status_code, 400, resp.content)
        body = resp.json()
        self.assertIn("tournament_league", body)
        self.assertIn(
            "must belong to the event's organization",
            str(body["tournament_league"]),
        )

    def test_set_tournament_league_to_null_succeeds(self):
        resp = self.client.patch(
            f"/api/events/{self.event.pk}/",
            {"tournament_league": None},
            format="json",
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        self.event.refresh_from_db()
        self.assertIsNone(self.event.tournament_league_id)


class EventPatchTournamentLeagueCacheTest(TransactionTestCase):
    """Cache round-trip regression — uses TransactionTestCase so on_commit fires.

    `EventViewSet.perform_update` calls `invalidate_after_commit(event)` which
    registers a `transaction.on_commit` hook. Under the standard `TestCase`,
    the outer transaction never commits during the test, so on_commit never
    fires and a cache round-trip test would pass for the wrong reason.
    `TransactionTestCase` runs without that wrapper, so the invalidation
    actually executes between PATCH and GET.
    """

    def setUp(self):
        # cacheops Redis cache is NOT auto-flushed between TransactionTestCase runs.
        # Stale entries from prior tests in the module could pollute the assertion.
        from cacheops import invalidate_all
        invalidate_all()

        self.admin = CustomUser.objects.create_user(username="eptlc_admin", password="x")
        self.admin.positions = PositionsModel.objects.create()
        self.admin.save()
        self.org = Organization.objects.create(name="EPTLC Org", owner=self.admin)
        self.org.staff.add(self.admin)
        self.league_a1 = League.objects.create(
            name="A1", organization=self.org, steam_league_id=41001
        )
        self.league_a2 = League.objects.create(
            name="A2", organization=self.org, steam_league_id=41002
        )
        self.event = Event.objects.create(
            organization=self.org,
            name="Cache Event",
            scheduled_at=tz.now() + timedelta(days=1),
            state=EventState.SIGNUPS_OPEN,
            created_by=self.admin,
            tournament_name="T",
            tournament_league=self.league_a1,
        )
        self.client = APIClient()
        self.client.force_authenticate(self.admin)

    def test_get_after_patch_returns_new_league(self):
        # Prime the cache
        prime = self.client.get(f"/api/events/{self.event.pk}/")
        self.assertEqual(prime.status_code, 200)
        # Mutate — on_commit hooks fire because we're under TransactionTestCase
        patch_resp = self.client.patch(
            f"/api/events/{self.event.pk}/",
            {"tournament_league": self.league_a2.pk},
            format="json",
        )
        self.assertEqual(patch_resp.status_code, 200)
        # Read through cache — must be fresh
        get_resp = self.client.get(f"/api/events/{self.event.pk}/")
        self.assertEqual(get_resp.status_code, 200)
        self.assertEqual(get_resp.json()["tournament_league"], self.league_a2.pk)
