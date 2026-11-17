"""Team API writes keep the captain and deputy inside the member set (#571)."""

import itertools

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from app.models import CustomUser, PositionsModel, Team, Tournament
from app.serializers import TeamSerializer

_discord_ids = itertools.count(571000)


def _user(name: str) -> CustomUser:
    return CustomUser.objects.create(
        username=name,
        discordId=str(next(_discord_ids)),
        positions=PositionsModel.objects.create(),
    )


class TeamLeadershipApiTests(TestCase):
    def setUp(self):
        self.staff = CustomUser.objects.create_user(
            username="team_staff", password="x", is_staff=True
        )
        self.client = APIClient()
        self.client.force_authenticate(self.staff)
        self.tournament = Tournament.objects.create(
            name="Leadership Cup",
            tournament_type="single_elimination",
            date_played=timezone.now(),
        )
        self.a = _user("lead_a")
        self.b = _user("lead_b")
        self.c = _user("lead_c")
        self.outsider = _user("lead_outsider")
        self.tournament.users.set([self.a, self.b, self.c, self.outsider])
        self.team = Team.objects.create(tournament=self.tournament, name="Leaders")
        self.team.members.set([self.a, self.b, self.c])
        self.team.captain = self.a
        self.team.save(update_fields=["captain"])

    def _patch(self, data: dict):
        return self.client.patch(f"/api/teams/{self.team.pk}/", data, format="json")

    def test_patch_captain_non_member_rejected(self):
        response = self._patch({"captain_id": self.outsider.pk})

        self.assertEqual(response.status_code, 400, response.data)
        self.assertEqual(
            [str(m) for m in response.data["captain_id"]],
            ["Captain must be a member of the team."],
        )
        self.team.refresh_from_db()
        self.assertEqual(self.team.captain, self.a)

    def test_patch_deputy_non_member_rejected(self):
        response = self._patch({"deputy_captain_id": self.outsider.pk})

        self.assertEqual(response.status_code, 400, response.data)
        self.assertEqual(
            [str(m) for m in response.data["deputy_captain_id"]],
            ["Deputy captain must be a member of the team."],
        )

    def test_patch_deputy_equal_to_captain_rejected(self):
        response = self._patch({"deputy_captain_id": self.a.pk})

        self.assertEqual(response.status_code, 400, response.data)
        self.assertEqual(
            [str(m) for m in response.data["deputy_captain_id"]],
            ["Deputy captain cannot be the same as captain."],
        )

    def test_patch_members_and_captain_together_accepted(self):
        response = self._patch(
            {"member_ids": [self.a.pk, self.b.pk], "captain_id": self.b.pk}
        )

        self.assertEqual(response.status_code, 200, response.data)
        self.team.refresh_from_db()
        self.assertEqual(self.team.captain, self.b)

    def test_patch_captain_outside_new_members_rejected(self):
        response = self._patch({"member_ids": [self.b.pk], "captain_id": self.a.pk})

        self.assertEqual(response.status_code, 400, response.data)
        self.assertIn("captain_id", response.data)
        self.assertEqual(self.team.members.count(), 3)

    def test_patch_members_dropping_captain_promotes_remaining_member(self):
        response = self._patch({"member_ids": [self.b.pk]})

        self.assertEqual(response.status_code, 200, response.data)
        self.team.refresh_from_db()
        self.assertEqual(self.team.captain, self.b)

    def test_post_with_captain_in_members_created(self):
        response = self.client.post(
            "/api/teams/",
            {
                "name": "New Team",
                "tournament_id": self.tournament.pk,
                "member_ids": [self.b.pk, self.c.pk],
                "captain_id": self.b.pk,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201, response.data)

    def test_post_with_captain_outside_members_rejected(self):
        response = self.client.post(
            "/api/teams/",
            {
                "name": "Bad Team",
                "tournament_id": self.tournament.pk,
                "member_ids": [self.c.pk],
                "captain_id": self.b.pk,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400, response.data)
        self.assertIn("captain_id", response.data)
        self.assertFalse(Team.objects.filter(name="Bad Team").exists())


class TeamLeadershipMessagesTests(TestCase):
    def setUp(self):
        self.tournament = Tournament.objects.create(
            name="Messages Cup",
            tournament_type="single_elimination",
            date_played=timezone.now(),
        )
        self.a = _user("msg_a")
        self.b = _user("msg_b")
        self.outsider = _user("msg_outsider")
        self.team = Team.objects.create(tournament=self.tournament, name="Msg")
        self.team.members.set([self.a, self.b])

    def _serializer_errors(self, data: dict) -> dict[str, list[str]]:
        serializer = TeamSerializer(self.team, data=data, partial=True)
        self.assertFalse(serializer.is_valid())
        return {k: [str(m) for m in v] for k, v in serializer.errors.items()}

    def _clean_errors(self) -> dict[str, list[str]]:
        with self.assertRaises(ValidationError) as ctx:
            self.team.full_clean()
        return ctx.exception.message_dict

    def test_captain_non_member_same_message(self):
        serializer_errors = self._serializer_errors({"captain_id": self.outsider.pk})
        self.team.captain = self.outsider

        self.assertEqual(
            serializer_errors["captain_id"], self._clean_errors()["captain"]
        )

    def test_deputy_non_member_same_message(self):
        serializer_errors = self._serializer_errors(
            {"deputy_captain_id": self.outsider.pk}
        )
        self.team.deputy_captain = self.outsider

        self.assertEqual(
            serializer_errors["deputy_captain_id"],
            self._clean_errors()["deputy_captain"],
        )

    def test_deputy_is_captain_same_message(self):
        serializer_errors = self._serializer_errors(
            {"captain_id": self.a.pk, "deputy_captain_id": self.a.pk}
        )
        self.team.captain = self.a
        self.team.deputy_captain = self.a

        self.assertEqual(
            serializer_errors["deputy_captain_id"],
            self._clean_errors()["deputy_captain"],
        )

    def test_leadership_errors_is_pure(self):
        self.assertEqual(
            Team.leadership_errors({1, 2}, 3, 2),
            {"captain": "Captain must be a member of the team."},
        )
        self.assertEqual(
            Team.leadership_errors({1, 2}, 3, 4, check_captain=False),
            {"deputy_captain": "Deputy captain must be a member of the team."},
        )
        self.assertEqual(
            Team.leadership_errors({1}, 1, 1),
            {"deputy_captain": "Deputy captain cannot be the same as captain."},
        )
        self.assertEqual(Team.leadership_errors(set(), None, None), {})
