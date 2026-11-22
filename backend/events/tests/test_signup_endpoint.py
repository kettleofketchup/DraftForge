from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase, TransactionTestCase
from django.utils import timezone
from rest_framework.test import APIClient

from app.models import CustomUser, GameType
from events import admission
from events.models import Event, EventSignup, EventState
from events.tests.actors import SYSTEM
from events.tests.base import EventTestCase
from org.models import Organization, OrgUser


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
                    "steam_account_id": "12345",
                    "positions": [1, 2],
                    "rank_status": "active",
                    "rank_medal": "Legend 4",
                },
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        from org.models import OrgUser
        from org.models_profiles import PlayerDotaProfile

        org_user = OrgUser.objects.get(user=self.user, organization=self.org)
        profile = PlayerDotaProfile.objects.get(org_user=org_user)
        self.assertEqual(profile.rank_medal, "Legend 4")
        self.user.refresh_from_db()
        self.assertEqual(self.user.steam_account_id, 12345)

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

        from app.models import CustomUser, GameType
        from events.models import (
            Event,
            EventSignup,
            EventState,
            SignupStatus,
            SignupType,
        )
        from org.models_profiles import PlayerDotaProfile

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
                    "steam_account_id": "12345",
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
        user.refresh_from_db()
        self.assertIsNone(user.steam_account_id)

    def test_notify_signup_changed_fires_once_after_commit(self):
        from datetime import timedelta
        from unittest.mock import patch as mock_patch

        from django.utils import timezone

        from app.models import CustomUser, GameType
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

        from app.models import CustomUser, GameType
        from events.models import Event, EventSignup, EventState
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
        process_rsvp(event, user, actor=SYSTEM)
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
        self.assertEqual(EventSignup.objects.filter(event=event, user=user).count(), 1)


class SignupEndpointSteamGateTests(EventTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.api = APIClient()

    def _post(self, event: Event, profile: dict[str, object]) -> object:
        return self.api.post(
            f"/api/events/{event.pk}/signup/",
            {"intent": "rsvp", "profile": profile},
            format="json",
        )

    def test_friend_id_in_request_satisfies_require_steam_id(self) -> None:
        ev = self.make_event(require_steam_id=True)
        self.api.force_authenticate(self.make_user())
        resp = self._post(ev, {"steam_account_id": "98765"})
        self.assertEqual(resp.status_code, 201, resp.content)
        self.assertIn(resp.json()["status"], ("approved", "confirmed"))

    def test_steamid_user_empty_patch_approved(self) -> None:
        ev = self.make_event(require_steam_id=True)
        self.api.force_authenticate(self.make_user(steamid=76561197960365432))
        resp = self._post(ev, {})
        self.assertEqual(resp.status_code, 201, resp.content)
        self.assertIn(resp.json()["status"], ("approved", "confirmed"))

    def test_empty_profile_on_gated_event(self) -> None:
        ev = self.make_event(min_mmr=3000)
        self.api.force_authenticate(self.make_user())
        resp = self._post(ev, {})
        self.assertEqual(resp.status_code, 201, resp.content)
        self.assertEqual(resp.json()["status"], "pending_approval")
        self.assertEqual(resp.json()["unmet_requirements"], ["dota_rank_undeclared"])


class SignupRefusalReasonsTests(EventTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.api = APIClient()

    def test_400_includes_error_and_reasons(self) -> None:
        ev = self.make_event(require_steam_id=True, state=EventState.CANCELLED)
        self.api.force_authenticate(self.make_user())
        resp = self.api.post(
            f"/api/events/{ev.pk}/signup/", {"intent": "rsvp"}, format="json"
        )
        self.assertEqual(resp.status_code, 400, resp.content)
        body = resp.json()
        self.assertIn("not accepting signups", body["error"])
        self.assertEqual([r["code"] for r in body["reasons"]], ["steam_id_missing"])
        self.assertEqual(body["reasons"][0]["severity"], "needs_approval")

    def test_400_on_eligible_user_has_empty_reasons(self) -> None:
        ev = self.make_event()
        self.api.force_authenticate(self.make_user())
        resp = self.api.post(
            f"/api/events/{ev.pk}/signup/", {"intent": "bogus"}, format="json"
        )
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.json()["reasons"], [])
        self.assertIn("intent", resp.json()["error"])

    def test_non_string_intent_returns_400(self) -> None:
        ev = self.make_event()
        self.api.force_authenticate(self.make_user())
        for intent in (["rsvp"], {"rsvp": True}, 1):
            with self.subTest(intent=intent):
                resp = self.api.post(
                    f"/api/events/{ev.pk}/signup/", {"intent": intent}, format="json"
                )
                self.assertEqual(resp.status_code, 400, resp.content)
                body = resp.json()
                self.assertIn("intent", body["error"])
                self.assertEqual(body["reasons"], [])


class SignupEndpointAdmissionOnceTests(EventTestCase):
    """The service is the admission choke point; the view must not pre-check."""

    def setUp(self) -> None:
        super().setUp()
        self.api = APIClient()

    def _post(self, event: Event, intent: str, **extra: object) -> object:
        return self.api.post(
            f"/api/events/{event.pk}/signup/",
            {"intent": intent, **extra},
            format="json",
        )

    def test_rsvp_evaluates_admission_once(self) -> None:
        ev = self.make_event()
        self.api.force_authenticate(self.make_user())
        with patch(
            "events.admission.evaluate_signup", wraps=admission.evaluate_signup
        ) as evaluated:
            resp = self._post(ev, "rsvp")
        self.assertEqual(resp.status_code, 201, resp.content)
        self.assertEqual(evaluated.call_count, 1)

    def test_tentative_evaluates_admission_once(self) -> None:
        ev = self.make_event()
        self.api.force_authenticate(self.make_user())
        with patch(
            "events.admission.evaluate_signup", wraps=admission.evaluate_signup
        ) as evaluated:
            resp = self._post(ev, "tentative")
        self.assertEqual(resp.status_code, 201, resp.content)
        self.assertEqual(evaluated.call_count, 1)

    def test_closed_event_checks_state_once(self) -> None:
        ev = self.make_event(state=EventState.CANCELLED)
        self.api.force_authenticate(self.make_user())
        with patch(
            "events.admission.self_serve_refusal",
            wraps=admission.self_serve_refusal,
        ) as refused:
            resp = self._post(ev, "rsvp")
        self.assertEqual(resp.status_code, 400, resp.content)
        self.assertIn("not accepting signups", resp.json()["error"])
        self.assertEqual(refused.call_count, 1)

    def test_refusal_leaves_no_org_user_or_profile_write(self) -> None:
        ev = self.make_event(state=EventState.CANCELLED)
        user = CustomUser.objects.create_user(username="no_org_user", password="pw")
        self.api.force_authenticate(user)
        resp = self._post(ev, "rsvp", profile={"steam_account_id": "98765"})
        self.assertEqual(resp.status_code, 400, resp.content)
        self.assertIn("not accepting signups", resp.json()["error"])
        self.assertFalse(OrgUser.objects.filter(user=user).exists())
        self.assertFalse(EventSignup.objects.filter(event=ev).exists())
        user.refresh_from_db()
        self.assertIsNone(user.steam_account_id)


class EventEligibilityEndpointTests(EventTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.api = APIClient()

    def _get(self, event: Event, query: str = "") -> object:
        return self.api.get(f"/api/events/{event.pk}/eligibility/{query}")

    def test_requires_authentication(self) -> None:
        self.assertEqual(self._get(self.make_event()).status_code, 403)

    def test_reports_reasons_for_request_user(self) -> None:
        ev = self.make_event(require_steam_id=True, min_mmr=3000)
        self.api.force_authenticate(self.make_user())
        resp = self._get(ev, "?intent=maybe")
        self.assertEqual(resp.status_code, 200, resp.content)
        body = resp.json()
        self.assertTrue(body["admissible"])
        self.assertFalse(body["has_registered_steam_id"])
        self.assertEqual(
            [r["code"] for r in body["reasons"]],
            ["steam_id_missing", "dota_rank_undeclared"],
        )

    def test_user_without_org_user_is_not_enrolled(self) -> None:
        ev = self.make_event()
        user = CustomUser.objects.create_user(username="no_org_member", password="x")
        user.steamid = 76561198000777777
        user.save()
        self.api.force_authenticate(user)
        resp = self._get(ev)
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(
            resp.json(),
            {"admissible": True, "reasons": [], "has_registered_steam_id": True},
        )
        self.assertFalse(OrgUser.objects.filter(user=user).exists())

    def test_rejects_unknown_intent(self) -> None:
        self.api.force_authenticate(self.make_user())
        self.assertEqual(self._get(self.make_event(), "?intent=rsvp").status_code, 400)
