"""Tests for removing a single tournament member (issue #963)."""

from django.test import TestCase
from rest_framework.response import Response

from app.models import CustomUser
from tournament.models import Team
from tournament.tests import test_add_member


class RemoveTournamentMemberTest(TestCase):
    setUp = test_add_member.AddTournamentMemberTest.setUp

    def _delete(self, actor: CustomUser, target: CustomUser) -> Response:
        self.client.force_authenticate(user=actor)
        return self.client.delete(
            f"/api/tournaments/{self.tournament.pk}/members/{target.pk}/"
        )

    def _member_pks(self) -> set[int]:
        return set(self.tournament.users.nocache().values_list("pk", flat=True))

    def test_concurrent_add_and_remove_both_survive(self) -> None:
        staying = CustomUser.objects.create_user(username="staying", password="x")
        self.tournament.users.add(staying, self.target_user)
        newcomer = CustomUser.objects.create_user(username="newcomer", password="x")

        self.client.force_authenticate(user=self.orgadmin)
        added = self.client.post(
            f"/api/tournaments/{self.tournament.pk}/members/",
            {"user_id": newcomer.pk},
            format="json",
        )
        self.assertEqual(added.status_code, 200)

        removed = self._delete(self.orgstaff, self.target_user)

        self.assertEqual(removed.status_code, 200)
        self.assertEqual(self._member_pks(), {staying.pk, newcomer.pk})
        returned = set(removed.data["tournament"]["users"])
        self.assertEqual(returned, {staying.pk, newcomer.pk})

    def test_removing_non_member_returns_404(self) -> None:
        response = self._delete(self.orgadmin, self.target_user)

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.data["code"], "not_a_member")

    def test_regular_user_cannot_remove_member(self) -> None:
        self.tournament.users.add(self.target_user)

        response = self._delete(self.regular, self.target_user)

        self.assertEqual(response.status_code, 403)
        self.assertIn(self.target_user.pk, self._member_pks())

    def test_removed_captain_pre_draft_team_is_deleted(self) -> None:
        self.tournament.users.add(self.target_user)
        team = Team.objects.create(
            name="Pre-draft", captain=self.target_user, tournament=self.tournament
        )

        response = self._delete(self.orgadmin, self.target_user)

        self.assertEqual(response.status_code, 200)
        self.assertFalse(Team.objects.nocache().filter(pk=team.pk).exists())
