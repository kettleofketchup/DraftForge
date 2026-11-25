import itertools
from datetime import date
from typing import Any

from django.test import TestCase
from rest_framework.response import Response
from rest_framework.test import APIClient

from app.models import CustomUser
from common.game import GameType
from league.models import League
from org.models import Organization, OrgLog, OrgUser, OrgUserGameMmr
from tests.populate.utils import ensure_org_user
from tournament.models import Tournament
from user.models import PositionsModel

_discord_ids = itertools.count(930_000_000_000_000_000)


def _make_user(name: str) -> CustomUser:
    return CustomUser.objects.create(
        username=name,
        discordId=str(next(_discord_ids)),
        positions=PositionsModel.objects.create(),
    )


class LeagueStaffOrgMmrPatchTest(TestCase):
    """League staff edit org MMR for players in a tournament they manage."""

    def setUp(self) -> None:
        self.org = Organization.objects.create(
            name="LS Org", owner=_make_user("ls_owner")
        )
        self.league = League.objects.create(
            organization=self.org, name="LS League", steam_league_id=None
        )
        self.tournament = Tournament.objects.create(
            name="LS Cup", date_played=date.today(), league=self.league
        )
        self.member = _make_user("ls_member")
        self.org_user = ensure_org_user(self.member, self.org, mmr=3000)
        self.tournament.users.add(self.member)
        self.league_staff = _make_user("ls_staff")
        self.league.staff.add(self.league_staff)
        self.client = APIClient()
        self.client.force_authenticate(self.league_staff)

    def patch(
        self,
        body: dict[str, Any],
        tournament: Tournament | None = None,
        org_user: OrgUser | None = None,
    ) -> Response:
        target = org_user or self.org_user
        query = f"?tournament_id={tournament.pk}" if tournament else ""
        return self.client.patch(
            f"/api/organizations/{self.org.pk}/users/{target.pk}/{query}",
            body,
            format="json",
        )

    def dota_mmr(self, org_user: OrgUser | None = None) -> int | None:
        return (
            OrgUserGameMmr.objects.filter(
                org_user=org_user or self.org_user, game_type=GameType.DOTA2
            )
            .values_list("mmr", flat=True)
            .first()
        )

    def test_league_staff_edits_mmr_in_their_tournament(self) -> None:
        resp = self.patch({"game_mmrs": {"1": 4200}}, self.tournament)

        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertEqual(self.dota_mmr(), 4200)
        self.assertTrue(
            OrgLog.objects.filter(
                organization=self.org, actor=self.league_staff, action="set_mmr"
            ).exists()
        )

    def test_league_admin_edits_mmr_in_their_tournament(self) -> None:
        admin = _make_user("ls_admin")
        self.league.admins.add(admin)
        self.client.force_authenticate(admin)

        resp = self.patch({"game_mmrs": {"1": 4100}}, self.tournament)

        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertEqual(self.dota_mmr(), 4100)

    def test_requires_the_tournament(self) -> None:
        resp = self.patch({"game_mmrs": {"1": 4200}})

        self.assertEqual(resp.status_code, 403)
        self.assertEqual(self.dota_mmr(), 3000)

    def test_player_outside_the_tournament_is_refused(self) -> None:
        outsider = _make_user("ls_outsider")
        outsider_ou = ensure_org_user(outsider, self.org, mmr=2000)

        resp = self.patch({"game_mmrs": {"1": 4200}}, self.tournament, outsider_ou)

        self.assertEqual(resp.status_code, 403)
        self.assertEqual(self.dota_mmr(outsider_ou), 2000)

    def test_staff_of_another_league_is_refused(self) -> None:
        other_league = League.objects.create(
            organization=self.org, name="Other League", steam_league_id=None
        )
        stranger = _make_user("ls_stranger")
        other_league.staff.add(stranger)
        self.client.force_authenticate(stranger)

        resp = self.patch({"game_mmrs": {"1": 4200}}, self.tournament)

        self.assertEqual(resp.status_code, 403)
        self.assertEqual(self.dota_mmr(), 3000)

    def test_tournament_of_another_org_is_refused(self) -> None:
        other_org = Organization.objects.create(name="Other Org")
        other_league = League.objects.create(
            organization=other_org, name="Other Org League", steam_league_id=None
        )
        other_league.staff.add(self.league_staff)
        other_tournament = Tournament.objects.create(
            name="Other Cup", date_played=date.today(), league=other_league
        )
        other_tournament.users.add(self.member)

        resp = self.patch({"game_mmrs": {"1": 4200}}, other_tournament)

        self.assertEqual(resp.status_code, 403)
        self.assertEqual(self.dota_mmr(), 3000)

    def test_league_staff_cannot_edit_profile_fields(self) -> None:
        resp = self.patch(
            {"game_mmrs": {"1": 4200}, "nickname": "Renamed"}, self.tournament
        )

        self.assertEqual(resp.status_code, 403)
        self.member.refresh_from_db()
        self.assertNotEqual(self.member.nickname, "Renamed")
        self.assertEqual(self.dota_mmr(), 3000)

    def test_org_staff_still_edit_without_a_tournament(self) -> None:
        org_staff = _make_user("ls_orgstaff")
        self.org.staff.add(org_staff)
        self.client.force_authenticate(org_staff)

        resp = self.patch({"game_mmrs": {"1": 4300}, "nickname": "Okay"})

        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertEqual(self.dota_mmr(), 4300)
