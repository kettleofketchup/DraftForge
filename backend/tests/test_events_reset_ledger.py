from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone as tz
from rest_framework.test import APIRequestFactory, force_authenticate

from app.models import CustomUser
from events.constants import ActorRole, SignupAction, SignupMeans
from events.models import Event, EventRepeater, EventSignup, SignupLedgerEntry
from org.models import Organization
from tests.data.organizations import EVENTS_ORG
from tests.data.users import EVENT_ADMIN_USER, EVENT_PLAYER_1
from tests.populate.events import populate_events_data
from tests.populate.organizations import populate_organizations_and_leagues
from tests.populate.users import populate_test_auth_users
from tests.test_auth import reset_events_data, reset_events_demo


class EventsResetLedgerTest(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        populate_organizations_and_leagues(force=True)
        populate_test_auth_users(force=True)
        populate_events_data(force=True)

    def setUp(self) -> None:
        self.org = Organization.objects.get(name=EVENTS_ORG.name)
        self.player = CustomUser.objects.get(username=EVENT_PLAYER_1.username)
        self.signup_event = Event.objects.get(
            organization=self.org, name="E2E Signup Event"
        )
        self.generated = Event.objects.create(
            organization=self.org,
            name="Generated Inhouse",
            scheduled_at=tz.now(),
            event_repeater=EventRepeater.objects.get(
                organization=self.org, name="Weekly Inhouse"
            ),
        )
        other_org = Organization.objects.exclude(pk=self.org.pk).first()
        assert other_org is not None
        self.unrelated = Event.objects.create(
            organization=other_org, name="Unrelated Event", scheduled_at=tz.now()
        )
        for event in (self.signup_event, self.generated, self.unrelated):
            self._ledger(event)

    def _ledger(self, event: Event) -> None:
        signup = EventSignup.objects.create(event=event, user=self.player)
        SignupLedgerEntry.objects.create(
            event=event,
            organization=event.organization,
            signup=signup,
            event_snapshot={"id": event.pk},
            subject_user=self.player,
            subject_snapshot={"user_id": self.player.pk},
            actor_role=ActorRole.SYSTEM,
            means=SignupMeans.SYSTEM,
            action=SignupAction.SIGNED_UP,
        )

    def _post(self, view) -> None:
        request = APIRequestFactory().post("/x/")
        force_authenticate(
            request, CustomUser.objects.get(username=EVENT_ADMIN_USER.username)
        )
        with patch("tests.test_auth.isTestEnvironment", return_value=True):
            resp = view(request)
        self.assertEqual(resp.status_code, 200, resp.data)

    def _ledger_event_pks(self) -> set[int]:
        return set(SignupLedgerEntry.objects.values_list("event_id", flat=True))

    def _orphans(self) -> list[int]:
        return list(
            SignupLedgerEntry.objects.exclude(
                signup_id__in=EventSignup.objects.values("pk")
            )
            .exclude(signup_id=None)
            .values_list("pk", flat=True)
        )

    def test_reset_drops_ledger_of_the_events_it_resets(self) -> None:
        self._post(reset_events_data)
        self.assertEqual(self._ledger_event_pks(), {self.unrelated.pk})
        self.assertEqual(self._orphans(), [])

    def test_demo_reset_drops_the_org_ledger(self) -> None:
        self._post(reset_events_demo)
        self.assertEqual(self._ledger_event_pks(), {self.unrelated.pk})
        self.assertEqual(self._orphans(), [])
