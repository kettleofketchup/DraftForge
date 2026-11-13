"""Access control for org and league member lists and the MMR they carry."""

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from app.models import CustomUser, GameType, League, Organization
from events.models import Event, EventSignup, EventState, SignupStatus
from org.models import OrgUser


class OrgMembersPrivacyTest(TestCase):
    def setUp(self) -> None:
        self.owner = CustomUser.objects.create_user(username="owner", password="x")
        self.admin = CustomUser.objects.create_user(username="admin", password="x")
        self.staff = CustomUser.objects.create_user(username="staff", password="x")
        self.member = CustomUser.objects.create_user(username="member", password="x")
        self.outsider = CustomUser.objects.create_user(
            username="outsider", password="x"
        )
        self.site_admin = CustomUser.objects.create_superuser(
            username="site", password="x"
        )

        self.org = Organization.objects.create(name="Privacy Org", owner=self.owner)
        self.org.admins.add(self.admin)
        self.org.staff.add(self.staff)
        OrgUser.objects.create(user=self.member, organization=self.org, mmr=4200)

        self.client = APIClient()
        self.url = f"/api/organizations/{self.org.pk}/users/"

    def _status_for(self, user: CustomUser | None) -> int:
        self.client.force_authenticate(user=user)
        return self.client.get(self.url).status_code

    def _set_private(self, private: bool) -> None:
        self.org.members_private = private
        self.org.save()

    def test_default_allows_members_and_staff(self) -> None:
        for user in (self.member, self.staff, self.admin, self.owner, self.site_admin):
            with self.subTest(user=user.username):
                self.assertEqual(self._status_for(user), status.HTTP_200_OK)

    def test_default_denies_outsiders(self) -> None:
        self.assertEqual(self._status_for(None), status.HTTP_403_FORBIDDEN)
        self.assertEqual(self._status_for(self.outsider), status.HTTP_403_FORBIDDEN)

    def test_private_allows_only_staff_tier(self) -> None:
        self._set_private(True)
        for user in (self.staff, self.admin, self.owner, self.site_admin):
            with self.subTest(user=user.username):
                self.assertEqual(self._status_for(user), status.HTTP_200_OK)
        for user in (self.member, self.outsider, None):
            with self.subTest(user=getattr(user, "username", "anon")):
                self.assertEqual(self._status_for(user), status.HTTP_403_FORBIDDEN)

    def test_member_cache_not_served_to_outsider(self) -> None:
        self.assertEqual(self._status_for(self.member), status.HTTP_200_OK)
        self.assertEqual(self._status_for(self.outsider), status.HTTP_403_FORBIDDEN)

    def test_private_toggle_takes_effect_after_cached_read(self) -> None:
        self.assertEqual(self._status_for(self.member), status.HTTP_200_OK)
        self._set_private(True)
        self.assertEqual(self._status_for(self.member), status.HTTP_403_FORBIDDEN)

    def test_retrieve_reports_viewer_access(self) -> None:
        detail = f"/api/organizations/{self.org.pk}/"
        cases = [(self.member, True), (self.outsider, False), (None, False)]
        for user, expected in cases:
            with self.subTest(user=getattr(user, "username", "anon")):
                self.client.force_authenticate(user=user)
                data = self.client.get(detail).data
                self.assertIs(data["can_view_members"], expected)
                self.assertIs(data["members_private"], False)

    def test_retrieve_access_flag_respects_private(self) -> None:
        self._set_private(True)
        detail = f"/api/organizations/{self.org.pk}/"
        for user, expected in [(self.member, False), (self.staff, True)]:
            with self.subTest(user=user.username):
                self.client.force_authenticate(user=user)
                self.assertIs(
                    self.client.get(detail).data["can_view_members"], expected
                )

    def test_admin_can_toggle_private_staff_cannot(self) -> None:
        detail = f"/api/organizations/{self.org.pk}/"
        self.client.force_authenticate(user=self.staff)
        resp = self.client.patch(detail, {"members_private": True}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

        self.client.force_authenticate(user=self.admin)
        resp = self.client.patch(detail, {"members_private": True}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.org.refresh_from_db()
        self.assertTrue(self.org.members_private)


class LeagueMembersPrivacyTest(TestCase):
    def setUp(self) -> None:
        self.owner = CustomUser.objects.create_user(username="owner", password="x")
        self.org_staff = CustomUser.objects.create_user(username="ostaff", password="x")
        self.league_staff = CustomUser.objects.create_user(
            username="lstaff", password="x"
        )
        self.member = CustomUser.objects.create_user(username="member", password="x")
        self.outsider = CustomUser.objects.create_user(
            username="outsider", password="x"
        )

        self.org = Organization.objects.create(name="League Org", owner=self.owner)
        self.org.staff.add(self.org_staff)
        OrgUser.objects.create(user=self.member, organization=self.org, mmr=4200)
        self.league = League.objects.create(
            name="Private League", organization=self.org, steam_league_id=424242
        )
        self.league.staff.add(self.league_staff)

        self.client = APIClient()
        self.users_url = f"/api/leagues/{self.league.pk}/users/"
        self.detail_url = f"/api/leagues/{self.league.pk}/"

    def _status_for(self, user: CustomUser | None) -> int:
        self.client.force_authenticate(user=user)
        return self.client.get(self.users_url).status_code

    def _flag_for(self, user: CustomUser | None) -> bool:
        self.client.force_authenticate(user=user)
        return self.client.get(self.detail_url).data["can_view_members"]

    def test_outsiders_cannot_read_league_members(self) -> None:
        for user in (None, self.outsider):
            with self.subTest(user=getattr(user, "username", "anon")):
                self.assertEqual(self._status_for(user), status.HTTP_403_FORBIDDEN)
                self.assertIs(self._flag_for(user), False)

    def test_members_and_staff_can_read_league_members(self) -> None:
        for user in (self.member, self.org_staff, self.league_staff, self.owner):
            with self.subTest(user=user.username):
                self.assertEqual(self._status_for(user), status.HTTP_200_OK)
                self.assertIs(self._flag_for(user), True)

    def test_private_org_hides_league_members_from_plain_members(self) -> None:
        self.org.members_private = True
        self.org.save()
        self.assertEqual(self._status_for(self.member), status.HTTP_403_FORBIDDEN)
        self.assertIs(self._flag_for(self.member), False)
        self.assertEqual(self._status_for(self.league_staff), status.HTTP_200_OK)


class EventSignupOrgMmrPrivacyTest(TestCase):
    def setUp(self) -> None:
        self.owner = CustomUser.objects.create_user(username="owner", password="x")
        self.player = CustomUser.objects.create_user(username="player", password="x")
        self.member = CustomUser.objects.create_user(username="member", password="x")
        self.outsider = CustomUser.objects.create_user(
            username="outsider", password="x"
        )

        self.org = Organization.objects.create(name="Event Org", owner=self.owner)
        OrgUser.objects.create(user=self.player, organization=self.org, mmr=5100)
        OrgUser.objects.create(user=self.member, organization=self.org, mmr=3000)
        event = Event.objects.create(
            name="Evt",
            organization=self.org,
            game_type=GameType.DOTA2,
            scheduled_at=timezone.now() + timedelta(days=7),
            state=EventState.SIGNUPS_OPEN,
        )
        EventSignup.objects.create(
            event=event, user=self.player, status=SignupStatus.RSVP
        )

        self.client = APIClient()
        self.url = f"/api/events/signups/?event={event.pk}"

    def _mmr_for(self, user: CustomUser | None) -> int | None:
        self.client.force_authenticate(user=user)
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        rows = resp.data["results"] if isinstance(resp.data, dict) else resp.data
        return rows[0]["org_user_mmr"]

    def test_outsiders_do_not_see_org_mmr(self) -> None:
        for user in (None, self.outsider):
            with self.subTest(user=getattr(user, "username", "anon")):
                self.assertIsNone(self._mmr_for(user))

    def test_members_staff_and_self_see_org_mmr(self) -> None:
        for user in (self.member, self.owner, self.player):
            with self.subTest(user=user.username):
                self.assertEqual(self._mmr_for(user), 5100)

    def test_private_org_hides_mmr_from_plain_members_but_not_self(self) -> None:
        self.org.members_private = True
        self.org.save()
        self.assertIsNone(self._mmr_for(self.member))
        self.assertEqual(self._mmr_for(self.player), 5100)
        self.assertEqual(self._mmr_for(self.owner), 5100)
