from unittest.mock import patch

from django.test import TestCase
from rest_framework.test import APIRequestFactory

from app.models import CustomUser
from events.constants import SEAT_HOLDING_STATUSES, SignupAction, SignupStatus
from events.models import Event, EventSignup, SignupLedgerEntry
from league.models import League
from org.models import Organization
from tests.data.leagues import EVENTS_LEAGUE, EVENTS_LEAGUE_ALT
from tests.data.organizations import EVENTS_ORG
from tests.data.users import (
    EVENT_ADMIN_USER,
    EVENT_PLAYER_1,
    EVENT_PLAYER_2,
    EVENT_PLAYER_4,
    EVENT_PLAYER_NO_PROFILE,
)
from tests.populate.constants import LINE_ORDER_KEEP_PLACE_EVENT_NAME
from tests.populate.events import populate_events_data
from tests.populate.organizations import populate_organizations_and_leagues
from tests.populate.users import populate_test_auth_users
from tests.test_events_data import events_data


class EventsDataEndpointTest(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        populate_organizations_and_leagues(force=True)
        populate_test_auth_users(force=True)
        populate_events_data(force=True)

    def _get(self, in_test_env: bool = True):
        with patch(
            "tests.test_events_data.isTestEnvironment", return_value=in_test_env
        ):
            return events_data(APIRequestFactory().get("/x/"))

    def test_returns_the_seeded_pks(self) -> None:
        resp = self._get()
        self.assertEqual(resp.status_code, 200, resp.data)
        org = Organization.objects.get(name=EVENTS_ORG.name)
        alt = League.objects.get(organization=org, name=EVENTS_LEAGUE_ALT.name)
        self.assertEqual(
            resp.data,
            {
                "org_pk": org.pk,
                "event_pk": Event.objects.get(
                    organization=org, name="E2E Signup Event"
                ).pk,
                "events_league_pk": League.objects.get(
                    steam_league_id=EVENTS_LEAGUE.steam_league_id
                ).pk,
                "alt_league_pk": alt.pk,
                "alt_league_name": alt.name,
                "users": {
                    role: CustomUser.objects.get(username=user.username).pk
                    for role, user in {
                        "admin": EVENT_ADMIN_USER,
                        "player": EVENT_PLAYER_1,
                        "player_2": EVENT_PLAYER_2,
                        "player_4": EVENT_PLAYER_4,
                        "no_profile": EVENT_PLAYER_NO_PROFILE,
                    }.items()
                },
            },
        )

    def test_hidden_outside_test_env(self) -> None:
        self.assertEqual(self._get(in_test_env=False).status_code, 404)

    def test_404_when_not_populated(self) -> None:
        Event.objects.filter(name="E2E Signup Event").delete()
        resp = self._get()
        self.assertEqual(resp.status_code, 404)
        self.assertIn("populate", resp.data["detail"])

    def test_survives_a_steam_league_id_edit(self) -> None:
        League.objects.filter(steam_league_id=EVENTS_LEAGUE.steam_league_id).update(
            steam_league_id=None
        )
        resp = self._get()
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertEqual(
            resp.data["events_league_pk"],
            League.objects.get(name=EVENTS_LEAGUE.name).pk,
        )


class KeepPlaceEventPopulateTest(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        populate_organizations_and_leagues(force=True)
        populate_test_auth_users(force=True)
        populate_events_data(force=True)

    def _event(self) -> Event:
        return Event.objects.nocache().get(
            organization__name=EVENTS_ORG.name, name=LINE_ORDER_KEEP_PLACE_EVENT_NAME
        )

    def test_keep_place_event_populated(self) -> None:
        event = self._event()
        self.assertFalse(event.line_withdraw_forfeits)
        self.assertFalse(event.line_switch_restamps)
        self.assertTrue(event.allow_user_signups)
        signups = list(EventSignup.objects.nocache().filter(event=event))
        self.assertEqual(len(signups), 1)
        signup = signups[0]
        self.assertEqual(signup.user_id, EVENT_PLAYER_1.pk)
        self.assertIn(signup.status, SEAT_HOLDING_STATUSES)
        self.assertIsNotNone(signup.line_seq)
        self.assertIsNotNone(signup.signed_up_at)
        self.assertEqual(
            list(
                SignupLedgerEntry.objects.filter(signup=signup).values_list(
                    "action", flat=True
                )
            ),
            [SignupAction.SIGNED_UP],
        )

    def test_rerun_keeps_one_seated_row(self) -> None:
        event = self._event()
        signup = EventSignup.objects.nocache().get(event=event)
        signup.status = SignupStatus.CANCELLED
        signup.save(update_fields=["status"])
        populate_events_data()
        rows = list(EventSignup.objects.nocache().filter(event=self._event()))
        self.assertEqual([r.pk for r in rows], [signup.pk])
        self.assertIn(rows[0].status, SEAT_HOLDING_STATUSES)
