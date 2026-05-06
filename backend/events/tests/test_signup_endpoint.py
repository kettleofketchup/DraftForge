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

    def test_unauthenticated_returns_401(self):
        resp = self.client.post(
            f"/api/events/{self.event.pk}/signup/",
            {"intent": "rsvp"},
            format="json",
        )
        self.assertEqual(resp.status_code, 401)

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
