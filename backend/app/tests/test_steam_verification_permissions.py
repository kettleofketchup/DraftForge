from django.contrib.auth.models import AnonymousUser

from app.models import CustomUser
from app.permissions_steam import (
    VerifyGrant,
    can_verify_steam_account,
    can_view_steam_verification,
    self_signup_events,
)
from events.models import Event, EventSignup
from events.services import cancel_signup, process_rsvp, staff_add_signup
from events.tests.base import EventTestCase
from org.membership import resolve_or_create_org_user
from org.models import Organization


class SteamVerifyPermissionTests(EventTestCase):
    def setUp(self) -> None:
        self.target = self.make_user()
        self.target.steam_account_id = 4242
        self.target.save()
        self.open_event: Event = self.make_event(tournament_league=self.league)

    def _self_signup(self, event: Event) -> EventSignup:
        signup = process_rsvp(event, self.target)
        self.assertTrue(signup.self_made)
        return signup

    def _staff_signup(self, event: Event) -> EventSignup:
        signup = staff_add_signup(event, self.target)
        self.assertFalse(signup.self_made)
        return signup

    def _superuser(self) -> CustomUser:
        return CustomUser.objects.create_superuser(
            username="sv_super", password="x", email="sv_super@example.com"
        )

    def test_superuser_on_other_allowed_org_none(self) -> None:
        self.assertEqual(
            can_verify_steam_account(self._superuser(), self.target),
            VerifyGrant(org_id=None),
        )

    def test_self_denied_even_superuser(self) -> None:
        su = self._superuser()
        su.steam_account_id = 5151
        su.save()
        self.assertIsNone(can_verify_steam_account(su, su))
        self._self_signup(self.open_event)
        self.assertIsNone(can_verify_steam_account(self.target, self.target))

    def test_site_staff_allowed(self) -> None:
        staff = CustomUser.objects.create_user(username="sv_site_staff", password="x")
        staff.is_staff = True
        staff.save()
        self.assertEqual(
            can_verify_steam_account(staff, self.target), VerifyGrant(org_id=None)
        )

    def test_event_staff_of_self_signup_allowed_records_org(self) -> None:
        self._self_signup(self.open_event)
        self.assertEqual(
            can_verify_steam_account(self.admin, self.target),
            VerifyGrant(org_id=self.org.pk),
        )

    def test_most_recent_self_signup_org_recorded(self) -> None:
        other_org = Organization.objects.create(name="SV Second Org", owner=self.admin)
        other_org.staff.add(self.admin)
        self._self_signup(self.open_event)
        later = self.make_event(organization=other_org)
        self._self_signup(later)
        self.assertEqual(
            can_verify_steam_account(self.admin, self.target),
            VerifyGrant(org_id=other_org.pk),
        )
        events = list(self_signup_events(self.target))
        self.assertEqual([e.pk for e in events], [later.pk, self.open_event.pk])

    def test_league_staff_of_event_league_allowed(self) -> None:
        self._self_signup(self.open_event)
        self.assertEqual(
            can_verify_steam_account(self.league_staff, self.target),
            VerifyGrant(org_id=self.org.pk),
        )

    def test_org_staff_added_member_without_signup_denied(self) -> None:
        actor = CustomUser.objects.create_user(username="sv_org_creator", password="x")
        own_org = Organization.objects.create(name="SV Own Org", owner=actor)
        resolve_or_create_org_user(self.target, own_org)
        self.assertIsNone(can_verify_steam_account(actor, self.target))
        self.assertFalse(can_view_steam_verification(actor, self.target))

    def test_signup_made_by_staff_on_behalf_denied(self) -> None:
        self._staff_signup(self.open_event)
        self.assertIsNone(can_verify_steam_account(self.admin, self.target))
        self.assertIsNone(can_verify_steam_account(self.league_staff, self.target))

    def test_cancelled_self_signup_denied(self) -> None:
        cancel_signup(self._self_signup(self.open_event))
        self.assertIsNone(can_verify_steam_account(self.admin, self.target))
        self.assertEqual(list(self_signup_events(self.target)), [])

    def test_unrelated_org_staff_denied(self) -> None:
        other_org = Organization.objects.create(
            name="SV Unrelated Org", owner=self.unrelated_user
        )
        other_org.staff.add(self.unrelated_user)
        self._self_signup(self.open_event)
        self.assertIsNone(can_verify_steam_account(self.unrelated_user, self.target))

    def test_plain_member_denied(self) -> None:
        member = self.make_user()
        self._self_signup(self.open_event)
        self.assertIsNone(can_verify_steam_account(member, self.target))

    def test_anonymous_denied(self) -> None:
        self._self_signup(self.open_event)
        self.assertIsNone(can_verify_steam_account(AnonymousUser(), self.target))
        self.assertIsNone(can_verify_steam_account(None, self.target))
        self.assertFalse(can_view_steam_verification(AnonymousUser(), self.target))
        self.assertFalse(can_view_steam_verification(None, self.target))

    def test_can_view_matches_rules(self) -> None:
        self._self_signup(self.open_event)
        staff = CustomUser.objects.create_user(username="sv_view_staff", password="x")
        staff.is_staff = True
        staff.save()
        self.assertTrue(can_view_steam_verification(staff, self.target))
        self.assertTrue(can_view_steam_verification(self.admin, self.target))
        self.assertTrue(can_view_steam_verification(self.league_staff, self.target))
        self.assertFalse(can_view_steam_verification(self.make_user(), self.target))
