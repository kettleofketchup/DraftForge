"""Access control for league member lists and the org MMR event signups carry."""

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from app.models import CustomUser, GameType, League
from events.models import Event, EventSignup, EventState, SignupStatus
from league.models import LeagueUser
from org.mmr import set_org_mmr
from org.models import Organization, OrgUser
from tests.populate.utils import ensure_org_user


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
        ensure_org_user(self.member, self.org, mmr=4200)
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

    def test_staff_of_sibling_league_can_read_league_members(self) -> None:
        sibling = League.objects.create(
            name="Sibling League", organization=self.org, steam_league_id=434343
        )
        sibling_admin = CustomUser.objects.create_user(username="sib", password="x")
        sibling.admins.add(sibling_admin)
        self.assertEqual(self._status_for(sibling_admin), status.HTTP_200_OK)
        self.assertIs(self._flag_for(sibling_admin), True)

    def _league_member(self, username: str, league: League) -> CustomUser:
        user = CustomUser.objects.create_user(username=username, password="x")
        org_user = ensure_org_user(user, self.org, mmr=3000)
        LeagueUser.objects.create(user=user, org_user=org_user, league=league, mmr=3000)
        return user

    def test_private_org_still_shows_league_members_their_own_league(self) -> None:
        player = self._league_member("player", self.league)
        self.org.members_private = True
        self.org.save()
        self.assertEqual(self._status_for(player), status.HTTP_200_OK)
        self.assertIs(self._flag_for(player), True)
        self.client.force_authenticate(user=player)
        org_users = self.client.get(f"/api/organizations/{self.org.pk}/users/")
        self.assertEqual(org_users.status_code, status.HTTP_403_FORBIDDEN)

    def test_private_org_hides_other_leagues_from_league_members(self) -> None:
        sibling = League.objects.create(
            name="Other League", organization=self.org, steam_league_id=454545
        )
        player = self._league_member("sibplayer", sibling)
        self.org.members_private = True
        self.org.save()
        self.assertEqual(self._status_for(player), status.HTTP_403_FORBIDDEN)
        self.assertIs(self._flag_for(player), False)

    def test_orgless_league_members_visible_to_staff_and_its_members(self) -> None:
        league = League.objects.create(name="Orgless", steam_league_id=444444)
        league.staff.add(self.league_staff)
        url = f"/api/leagues/{league.pk}/users/"
        player = CustomUser.objects.create_user(username="orgless", password="x")
        org_user = OrgUser.objects.create(user=player, organization=self.org)
        LeagueUser.objects.create(user=player, org_user=org_user, league=league)
        for user, expected in [
            (self.league_staff, status.HTTP_200_OK),
            (player, status.HTTP_200_OK),
            (self.member, status.HTTP_403_FORBIDDEN),
        ]:
            with self.subTest(user=user.username):
                self.client.force_authenticate(user=user)
                self.assertEqual(self.client.get(url).status_code, expected)


class EventSignupOrgMmrPrivacyTest(TestCase):
    def setUp(self) -> None:
        self.owner = CustomUser.objects.create_user(username="owner", password="x")
        self.player = CustomUser.objects.create_user(username="player", password="x")
        self.member = CustomUser.objects.create_user(username="member", password="x")
        self.outsider = CustomUser.objects.create_user(
            username="outsider", password="x"
        )

        self.org = Organization.objects.create(name="Event Org", owner=self.owner)
        ensure_org_user(self.player, self.org, mmr=5100)
        ensure_org_user(self.member, self.org, mmr=3000)
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

    def _row_for(self, user: CustomUser | None) -> dict:
        self.client.force_authenticate(user=user)
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        rows = resp.data["results"] if isinstance(resp.data, dict) else resp.data
        return rows[0]

    def _mmr_for(self, user: CustomUser | None) -> int | None:
        return self._row_for(user)["org_user_mmr"]

    def test_outsiders_do_not_see_org_mmr(self) -> None:
        for user in (None, self.outsider):
            with self.subTest(user=getattr(user, "username", "anon")):
                row = self._row_for(user)
                self.assertIsNone(row["org_user_mmr"])
                self.assertIsNone(row["org_user_game_mmrs"])
                # The org MMR is not a suggestion prior for outsiders: they
                # get the fallback midpoint of DOTA_DEFAULT_MMR_RANGE.
                self.assertEqual(row["suggested_mmr"], 1000)

    def test_members_staff_and_self_see_org_mmr(self) -> None:
        for user in (self.member, self.owner, self.player):
            with self.subTest(user=user.username):
                row = self._row_for(user)
                self.assertEqual(row["org_user_mmr"], 5100)
                self.assertEqual(row["org_user_game_mmrs"], {"1": 5100, "2": 0})
                self.assertEqual(row["suggested_mmr"], 5100)

    def test_private_org_hides_mmr_from_plain_members_but_not_self(self) -> None:
        self.org.members_private = True
        self.org.save()
        self.assertIsNone(self._mmr_for(self.member))
        self.assertEqual(self._mmr_for(self.player), 5100)
        self.assertEqual(self._mmr_for(self.owner), 5100)


class LeagueUsersOrgMmrTest(TestCase):
    def setUp(self) -> None:
        self.owner = CustomUser.objects.create_user(username="lo_owner", password="x")
        self.org = Organization.objects.create(name="League MMR Org", owner=self.owner)
        self.league = League.objects.create(
            name="League MMR", organization=self.org, steam_league_id=464646
        )
        self.player = self._member("lo_player", 5100, 4800)
        self.other = self._member("lo_other", 3200, 3000)
        self.client = APIClient()
        self.url = f"/api/leagues/{self.league.pk}/users/"

    def _member(self, username: str, org_mmr: int, snapshot: int) -> CustomUser:
        user = CustomUser.objects.create_user(username=username, password="x")
        org_user = ensure_org_user(user, self.org, mmr=org_mmr)
        LeagueUser.objects.create(
            user=user, org_user=org_user, league=self.league, mmr=snapshot
        )
        return user

    def _rows_for(self, user: CustomUser) -> dict[int, dict]:
        self.client.force_authenticate(user=user)
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        return {row["pk"]: row for row in resp.json()}

    def test_rows_carry_org_link_game_mmrs_and_league_mmr(self) -> None:
        row = self._rows_for(self.owner)[self.player.pk]
        org_user = OrgUser.objects.get(user=self.player, organization=self.org)
        self.assertEqual(row["orgUserPk"], org_user.pk)
        self.assertEqual(row["game_mmrs"], {"1": 5100, "2": 0})
        self.assertEqual(row["league_mmr"], 4800)

    def test_private_org_shows_plain_members_only_their_own_org_mmr(self) -> None:
        self.org.members_private = True
        self.org.save()
        rows = self._rows_for(self.player)
        self.assertEqual(rows[self.player.pk]["game_mmrs"], {"1": 5100, "2": 0})
        self.assertNotIn("game_mmrs", rows[self.other.pk])
        self.assertNotIn("orgUserPk", rows[self.other.pk])
        self.assertEqual(rows[self.other.pk]["league_mmr"], 3000)

    def test_org_mmr_edit_reaches_the_cached_list(self) -> None:
        self._rows_for(self.owner)
        org_user = OrgUser.objects.get(user=self.player, organization=self.org)
        set_org_mmr(org_user, GameType.DOTA2, 6000, mark_verified=False)
        row = self._rows_for(self.owner)[self.player.pk]
        self.assertEqual(row["game_mmrs"]["1"], 6000)
