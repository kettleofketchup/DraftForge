from django.test import TestCase
from django.utils import timezone

from app.models import (
    CustomUser,
    League,
    Organization,
    PositionsModel,
    Team,
    Tournament,
)
from app.services.team_leadership import successor_after_removal
from org.models import OrgUser
from tests.populate.utils import ensure_org_user


def _make_user(name: str) -> CustomUser:
    return CustomUser.objects.create(
        username=name,
        discordId=f"discord_{name}",
        positions=PositionsModel.objects.create(),
    )


class CaptainSuccessionRegressionTests(TestCase):
    def setUp(self) -> None:
        self.org = Organization.objects.create(name="Pin Org")
        self.league = League.objects.create(name="Pin League", organization=self.org)
        self.tournament = Tournament.objects.create(
            name="Pin Tournament",
            tournament_type="single_elimination",
            date_played=timezone.now(),
            league=self.league,
        )
        self.users = [_make_user(f"pin_{i}") for i in range(4)]
        self.team = Team.objects.create(tournament=self.tournament, name="Pin Team")
        self.team.members.set(self.users)
        Team.objects.filter(pk=self.team.pk).update(captain=self.users[0])
        self.team.refresh_from_db()

    def _remove_captain(self) -> set[int]:
        Team.members.through.objects.filter(
            team=self.team, customuser=self.users[0]
        ).delete()
        return {self.users[0].pk}

    def test_all_zero_team_returns_org_user_member(self) -> None:
        for user in self.users[1:]:
            ensure_org_user(user, self.org, mmr=0)

        captain, deputy, how = successor_after_removal(
            self.team, self._remove_captain()
        )

        self.assertEqual(how, "org_mmr")
        self.assertIsNone(deputy)
        self.assertIn(captain, self.users[1:])

    def test_zero_mmr_org_user_beats_member_without_org_user(self) -> None:
        ensure_org_user(self.users[3], self.org, mmr=0)

        captain, deputy, how = successor_after_removal(
            self.team, self._remove_captain()
        )

        self.assertEqual((captain, deputy, how), (self.users[3], None, "org_mmr"))
        self.assertFalse(
            OrgUser.objects.filter(user=self.users[1], organization=self.org).exists()
        )
