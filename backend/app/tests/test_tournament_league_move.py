from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.response import Response
from rest_framework.test import APIClient

from app.models import CustomUser, League, Organization, Tournament
from events.constants import EventState
from events.models import Event


class TournamentLeagueMoveTests(TestCase):
    def setUp(self) -> None:
        def user(name: str, **kwargs: bool) -> CustomUser:
            return CustomUser.objects.create_user(username=name, password="x", **kwargs)

        owner_a = user("owner_a")
        owner_b = user("owner_b")
        self.org_a = Organization.objects.create(name="Org A", owner=owner_a)
        self.org_b = Organization.objects.create(name="Org B", owner=owner_b)
        self.league_a = League.objects.create(
            name="League A", organization=self.org_a, steam_league_id=9001
        )
        self.league_a2 = League.objects.create(
            name="League A2", organization=self.org_a, steam_league_id=9002
        )
        self.league_b = League.objects.create(
            name="League B", organization=self.org_b, steam_league_id=9003
        )

        self.org_admin_a = user("org_admin_a")
        self.org_a.admins.add(self.org_admin_a)
        self.admin_ab = user("admin_ab")
        self.league_a.admins.add(self.admin_ab)
        self.league_b.admins.add(self.admin_ab)
        self.admin_a = user("admin_a")
        self.league_a.admins.add(self.admin_a)
        self.staff_a_admin_b = user("staff_a_admin_b")
        self.league_a.staff.add(self.staff_a_admin_b)
        self.league_b.admins.add(self.staff_a_admin_b)
        self.orgstaff_a_admin_b = user("orgstaff_a_admin_b")
        self.org_a.staff.add(self.orgstaff_a_admin_b)
        self.league_b.admins.add(self.orgstaff_a_admin_b)
        self.league_staff_a = user("league_staff_a")
        self.league_a.staff.add(self.league_staff_a)
        self.org_staff_a = user("org_staff_a")
        self.org_a.staff.add(self.org_staff_a)
        self.site_staff = user("site_staff", is_staff=True)

        self.t = self.make_tournament("Move Me", self.league_a)
        self.client = APIClient()

    def make_tournament(self, name: str, league: League | None) -> Tournament:
        return Tournament.objects.create(
            name=name,
            league=league,
            tournament_type="double_elimination",
            date_played=timezone.now(),
        )

    def make_event(self, tournament: Tournament) -> Event:
        return Event.objects.create(
            organization=self.org_a,
            name=f"Event {tournament.pk}",
            scheduled_at=timezone.now() + timedelta(days=1),
            state=EventState.SIGNUPS_OPEN,
            tournament_league=self.league_a,
            tournament=tournament,
        )

    def patch_as(
        self, user: CustomUser, data: dict, tournament: Tournament | None = None
    ) -> Response:
        self.client.force_authenticate(user)
        target = tournament or self.t
        return self.client.patch(f"/api/tournaments/{target.pk}/", data, format="json")

    def league_id(self, tournament: Tournament | None = None) -> int | None:
        return Tournament.objects.get(pk=(tournament or self.t).pk).league_id

    def assert_rejected(
        self, resp: Response, message: str | None = None, expected_league: int | None = -1
    ) -> None:
        self.assertEqual(resp.status_code, 400, resp.data)
        self.assertIn("league_id_write", resp.data)
        if message is not None:
            self.assertEqual(str(resp.data["league_id_write"]), message)
        if expected_league == -1:
            self.assertEqual(self.league_id(), self.league_a.pk)

    def test_admin_of_both_moves(self) -> None:
        resp = self.patch_as(self.admin_ab, {"league_id_write": self.league_b.pk})
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertEqual(self.league_id(), self.league_b.pk)

    def test_admin_of_source_only_rejected(self) -> None:
        resp = self.patch_as(self.admin_a, {"league_id_write": self.league_b.pk})
        self.assert_rejected(
            resp,
            "You must be an admin of the league you are moving this tournament to.",
        )

    def test_league_staff_of_source_admin_of_target_rejected(self) -> None:
        resp = self.patch_as(self.staff_a_admin_b, {"league_id_write": self.league_b.pk})
        self.assert_rejected(
            resp,
            "You must be an admin of the tournament's current league to move it.",
        )

    def test_org_staff_of_source_admin_of_target_rejected(self) -> None:
        resp = self.patch_as(
            self.orgstaff_a_admin_b, {"league_id_write": self.league_b.pk}
        )
        self.assert_rejected(
            resp,
            "You must be an admin of the tournament's current league to move it.",
        )

    def test_league_staff_unchanged_league_saves(self) -> None:
        resp = self.patch_as(
            self.league_staff_a, {"league_id_write": self.league_a.pk, "name": "N"}
        )
        self.assertEqual(resp.status_code, 200, resp.data)

    def test_org_staff_unchanged_league_saves(self) -> None:
        resp = self.patch_as(
            self.org_staff_a, {"league_id_write": self.league_a.pk, "name": "N"}
        )
        self.assertEqual(resp.status_code, 200, resp.data)

    def test_league_admin_cannot_clear_league(self) -> None:
        resp = self.patch_as(self.admin_a, {"league_id_write": None})
        self.assert_rejected(resp, "Only site staff can remove a tournament's league.")

    def test_site_staff_clears_league(self) -> None:
        resp = self.patch_as(self.site_staff, {"league_id_write": None})
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertIsNone(self.league_id())

    def test_event_tournament_cross_org_move_rejected_for_site_staff(self) -> None:
        self.make_event(self.t)
        for user in (self.site_staff, self.admin_ab):
            with self.subTest(user=user.username):
                resp = self.patch_as(user, {"league_id_write": self.league_b.pk})
                self.assert_rejected(
                    resp, "League must belong to the event's organization."
                )

    def test_event_tournament_same_org_move_allowed(self) -> None:
        self.make_event(self.t)
        resp = self.patch_as(self.site_staff, {"league_id_write": self.league_a2.pk})
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertEqual(self.league_id(), self.league_a2.pk)

    def test_org_admin_moves_between_own_org_leagues(self) -> None:
        resp = self.patch_as(self.org_admin_a, {"league_id_write": self.league_a2.pk})
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertEqual(self.league_id(), self.league_a2.pk)

    def test_org_admin_cannot_move_to_other_org_league(self) -> None:
        resp = self.patch_as(self.org_admin_a, {"league_id_write": self.league_b.pk})
        self.assert_rejected(
            resp,
            "You must be an admin of the league you are moving this tournament to.",
        )

    def test_site_staff_assigns_league_to_leagueless_event_tournament(self) -> None:
        t0 = self.make_tournament("Leagueless", None)
        self.make_event(t0)
        resp = self.patch_as(self.site_staff, {"league_id_write": self.league_b.pk}, t0)
        self.assert_rejected(
            resp, "League must belong to the event's organization.", expected_league=None
        )
        self.assertIsNone(self.league_id(t0))
        resp = self.patch_as(self.site_staff, {"league_id_write": self.league_a.pk}, t0)
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertEqual(self.league_id(t0), self.league_a.pk)

    def test_write_key_wins_over_read_key(self) -> None:
        resp = self.patch_as(
            self.admin_a,
            {"league": self.league_a.pk, "league_id_write": self.league_b.pk},
        )
        self.assert_rejected(resp)

    def create_as(self, user: CustomUser, extra: dict) -> Response:
        self.client.force_authenticate(user)
        payload = {
            "name": "Sneak",
            "date_played": "2026-11-08T00:00:00Z",
            "tournament_type": "double_elimination",
            **extra,
        }
        return self.client.post("/api/tournaments/", payload, format="json")

    def test_create_bypass_closed(self) -> None:
        resp = self.create_as(
            self.admin_a,
            {"league": self.league_a.pk, "league_id_write": self.league_b.pk},
        )
        self.assertEqual(resp.status_code, 400, resp.data)
        self.assertIn("league_id_write", resp.data)
        self.assertFalse(Tournament.objects.filter(name="Sneak").exists())

    def test_create_in_admin_league_allowed(self) -> None:
        resp = self.create_as(self.admin_a, {"league_id_write": self.league_a.pk})
        self.assertEqual(resp.status_code, 201, resp.data)
        self.assertEqual(
            Tournament.objects.get(name="Sneak").league_id, self.league_a.pk
        )

    def test_create_without_league_rejected(self) -> None:
        resp = self.create_as(self.admin_a, {})
        self.assertEqual(resp.status_code, 400, resp.data)
        self.assertIn("league_id_write", resp.data)
        self.assertFalse(Tournament.objects.filter(name="Sneak").exists())
