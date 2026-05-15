from datetime import timedelta
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from app.models import CustomUser, GameType, Organization
from events.models import Event, EventState


class SignupEndpointAuthTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.org = Organization.objects.create(name="Org")
        self.event = Event.objects.create(
            name="Evt",
            organization=self.org,
            game_type=GameType.DOTA2,
            scheduled_at=timezone.now() + timedelta(days=7),
            state=EventState.SIGNUPS_OPEN,
            allow_active_mmr=True,
            allow_previous_rank=True,
            allow_battlecup_rating=True,
        )

    def test_unauthenticated_returns_403(self):
        # DRF returns 403 (not 401) when only SessionAuthentication is
        # configured because SessionAuthentication.authenticate_header()
        # returns None — without a WWW-Authenticate header DRF emits 403.
        # Matches the project-wide convention (see events.tests.test_api).
        resp = self.client.post(
            f"/api/events/{self.event.pk}/signup/",
            {"intent": "rsvp"},
            format="json",
        )
        self.assertEqual(resp.status_code, 403)

    def test_wrong_state_returns_400(self):
        self.event.state = EventState.CANCELLED
        self.event.save()
        user = CustomUser.objects.create(username="alice")
        self.client.force_authenticate(user)
        resp = self.client.post(
            f"/api/events/{self.event.pk}/signup/",
            {"intent": "rsvp"},
            format="json",
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("not accepting signups", resp.json()["error"])

    def test_invalid_intent_returns_400(self):
        user = CustomUser.objects.create(username="alice")
        self.client.force_authenticate(user)
        resp = self.client.post(
            f"/api/events/{self.event.pk}/signup/",
            {"intent": "bogus"},
            format="json",
        )
        self.assertEqual(resp.status_code, 400)

    def test_unknown_profile_field_rejected(self):
        user = CustomUser.objects.create(username="alice")
        self.client.force_authenticate(user)
        resp = self.client.post(
            f"/api/events/{self.event.pk}/signup/",
            {"intent": "rsvp", "profile": {"unknown_field": "x"}},
            format="json",
        )
        self.assertEqual(resp.status_code, 400)


class SignupEndpointHappyPathTests(TestCase):
    def setUp(self):
        from datetime import timedelta
        from django.utils import timezone

        self.client = APIClient()
        self.org = Organization.objects.create(name="Org")
        self.event = Event.objects.create(
            name="Evt",
            organization=self.org,
            game_type=GameType.DOTA2,
            scheduled_at=timezone.now() + timedelta(days=7),
            state=EventState.SIGNUPS_OPEN,
            allow_active_mmr=True,
            allow_previous_rank=True,
            allow_battlecup_rating=True,
            min_players=2,
            max_players=10,
        )
        self.user = CustomUser.objects.create(username="alice")
        self.client.force_authenticate(self.user)

    def test_empty_patch_creates_signup(self):
        resp = self.client.post(
            f"/api/events/{self.event.pk}/signup/",
            {"intent": "rsvp", "profile": {}},
            format="json",
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        self.assertIn("status", resp.json())

    def test_full_patch_creates_signup_and_writes_profile(self):
        resp = self.client.post(
            f"/api/events/{self.event.pk}/signup/",
            {
                "intent": "rsvp",
                "profile": {
                    "unverified_friend_id": "12345",
                    "positions": [1, 2],
                    "rank_status": "active",
                    "rank_medal": "Legend 4",
                },
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        from org.models_profiles import PlayerDotaProfile
        from org.models import OrgUser

        org_user = OrgUser.objects.get(user=self.user, organization=self.org)
        profile = PlayerDotaProfile.objects.get(org_user=org_user)
        self.assertEqual(profile.unverified_friend_id, "12345")
        self.assertEqual(profile.rank_medal, "Legend 4")

    def test_tentative_intent_creates_tentative_signup(self):
        resp = self.client.post(
            f"/api/events/{self.event.pk}/signup/",
            {"intent": "tentative"},
            format="json",
        )
        self.assertEqual(resp.status_code, 201)
        from events.models import EventSignup, SignupStatus

        signup = EventSignup.objects.get(event=self.event, user=self.user)
        self.assertEqual(signup.status, SignupStatus.TENTATIVE)


from django.test import TransactionTestCase


class SignupEndpointRollbackTests(TransactionTestCase):
    """Pin transactional rollback: when process_rsvp raises, profile writes from
    apply_signup_input must roll back too.

    Gate choice: the duplicate-signup gate inside _create_signup (raises
    ValueError "User has already signed up for this event.") is the only
    unambiguous hard gate that raises *inside* process_rsvp. The min_mmr and
    screenshot-required checks live in check_requirements() and only downgrade
    the signup status to PENDING_APPROVAL — they never raise — so they cannot
    drive a 400/rollback path from process_rsvp itself.
    """

    def test_process_rsvp_failure_rolls_back_profile_write(self):
        from datetime import timedelta
        from django.utils import timezone

        from app.models import CustomUser, GameType, Organization
        from events.models import (
            Event,
            EventSignup,
            EventState,
            SignupStatus,
            SignupType,
        )
        from org.models_profiles import PlayerDotaProfile
        from org.models import OrgUser

        org = Organization.objects.create(name="Org")
        event = Event.objects.create(
            name="Evt",
            organization=org,
            game_type=GameType.DOTA2,
            scheduled_at=timezone.now() + timedelta(days=7),
            state=EventState.SIGNUPS_OPEN,
            allow_active_mmr=True,
            allow_previous_rank=True,
            allow_battlecup_rating=True,
        )
        user = CustomUser.objects.create(username="alice")

        # Pre-create an active signup to trigger the duplicate-signup raise inside
        # _create_signup (status RSVP is not in the auto-delete set
        # CANCELLED/REJECTED/TENTATIVE).
        EventSignup.objects.create(
            event=event,
            user=user,
            signup_type=SignupType.USER,
            status=SignupStatus.RSVP,
        )

        # Confirm no profile exists yet — the endpoint's apply_signup_input would
        # create it via get_or_create before process_rsvp runs.
        self.assertFalse(
            PlayerDotaProfile.objects.filter(org_user__user=user).exists(),
        )

        client = APIClient()
        client.force_authenticate(user)
        resp = client.post(
            f"/api/events/{event.pk}/signup/",
            {
                "intent": "rsvp",
                "profile": {
                    "unverified_friend_id": "12345",
                    "rank_status": "active",
                    "rank_medal": "Legend 4",
                },
            },
            format="json",
        )

        # process_rsvp raises ValueError -> view returns 400.
        self.assertEqual(resp.status_code, 400, resp.content)
        self.assertIn("already signed up", resp.json()["error"])

        # Profile write inside apply_signup_input must have rolled back.
        org_user = OrgUser.objects.filter(user=user, organization=org).first()
        if org_user:
            self.assertFalse(
                PlayerDotaProfile.objects.filter(org_user=org_user).exists(),
                "PlayerDotaProfile should not exist after rollback; "
                f"got {PlayerDotaProfile.objects.filter(org_user=org_user).first()}",
            )

    def test_notify_signup_changed_fires_once_after_commit(self):
        from datetime import timedelta
        from unittest.mock import patch as mock_patch

        from django.utils import timezone

        from app.models import CustomUser, GameType, Organization
        from events.models import Event, EventState

        org = Organization.objects.create(name="Org")
        event = Event.objects.create(
            name="Evt",
            organization=org,
            game_type=GameType.DOTA2,
            scheduled_at=timezone.now() + timedelta(days=7),
            state=EventState.SIGNUPS_OPEN,
            allow_active_mmr=True,
            allow_previous_rank=True,
            allow_battlecup_rating=True,
        )
        user = CustomUser.objects.create(username="alice")
        client = APIClient()
        client.force_authenticate(user)

        # Patch where services.py imports it, so on_commit-registered callback hits the spy.
        with mock_patch("events.services.notify_signup_changed") as spy:
            resp = client.post(
                f"/api/events/{event.pk}/signup/",
                {"intent": "rsvp"},
                format="json",
            )
            self.assertEqual(resp.status_code, 201, resp.content)

        # TransactionTestCase commits writes, so on_commit callbacks fire.
        # The endpoint relies on process_rsvp/_create_signup to register
        # notify_signup_changed exactly once via on_commit. The endpoint must NOT
        # double-register it.
        self.assertEqual(spy.call_count, 1)

    def test_discord_then_web_idempotent(self):
        from datetime import timedelta
        from django.utils import timezone

        from app.models import CustomUser, GameType, Organization
        from events.models import Event, EventState, EventSignup
        from events.services import process_rsvp

        org = Organization.objects.create(name="Org")
        event = Event.objects.create(
            name="Evt",
            organization=org,
            game_type=GameType.DOTA2,
            scheduled_at=timezone.now() + timedelta(days=7),
            state=EventState.SIGNUPS_OPEN,
            allow_active_mmr=True,
            allow_previous_rank=True,
            allow_battlecup_rating=True,
        )
        user = CustomUser.objects.create(username="alice")
        # Simulate Discord-side signup first.
        process_rsvp(event, user)
        # Now web tries to sign up.
        client = APIClient()
        client.force_authenticate(user)
        resp = client.post(
            f"/api/events/{event.pk}/signup/",
            {"intent": "rsvp"},
            format="json",
        )
        self.assertEqual(resp.status_code, 400)
        # Only one signup exists.
        self.assertEqual(
            EventSignup.objects.filter(event=event, user=user).count(), 1
        )
