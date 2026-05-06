from datetime import timedelta
from django.test import TestCase
from django.utils import timezone

from app.models import CustomUser, GameType, Organization
from events.models import Event, EventState
from events.schemas import SignupInputPatch
from events.services import apply_signup_input, resolve_or_create_org_user
from org.models_profiles import PlayerDotaProfile


class ApplySignupInputTests(TestCase):
    def setUp(self):
        self.user = CustomUser.objects.create(username="alice")
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
        self.org_user = resolve_or_create_org_user(self.user, self.org)

    def test_empty_patch_is_noop(self):
        before = PlayerDotaProfile.objects.filter(org_user=self.org_user).count()
        result = apply_signup_input(
            org_user=self.org_user,
            event=self.event,
            patch=SignupInputPatch(),
        )
        after = PlayerDotaProfile.objects.filter(org_user=self.org_user).count()
        # Empty patch should NOT create a profile and SHOULD return None.
        self.assertIsNone(result)
        self.assertEqual(after, before)
