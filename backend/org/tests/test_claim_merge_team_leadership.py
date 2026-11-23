"""Account claim merge keeps team leadership on the claimer (#571)."""

import itertools

from django.test import TestCase
from django.utils import timezone

from app.models import CustomUser, PositionsModel, Team, Tournament
from app.services.team_leadership import teams_with_leadership_problems
from events.tests.actors import SYSTEM
from org.views import ClaimRequestViewSet

_discord_ids = itertools.count(571500)


def _user(name: str) -> CustomUser:
    return CustomUser.objects.create(
        username=name,
        discordId=str(next(_discord_ids)),
        positions=PositionsModel.objects.create(),
    )


class ClaimMergeTeamLeadershipTests(TestCase):
    def setUp(self) -> None:
        self.tournament = Tournament.objects.create(
            name="Claim Cup",
            tournament_type="single_elimination",
            date_played=timezone.now(),
        )
        self.target = _user("claim_lead_target")
        self.claimer = _user("claim_lead_claimer")
        self.other = _user("claim_lead_other")
        self.tournament.users.set([self.target, self.other])
        self.team = Team.objects.create(tournament=self.tournament, name="Claimed")
        self.team.members.set([self.target, self.other])

    def _merge(self) -> None:
        ClaimRequestViewSet()._merge_profiles(self.claimer, self.target, actor=SYSTEM)
        self.team.refresh_from_db()

    def test_claimer_inherits_captaincy(self) -> None:
        Team.objects.filter(pk=self.team.pk).update(captain=self.target)

        self._merge()

        self.assertEqual(self.team.captain, self.claimer)
        self.assertEqual(
            set(self.team.members.values_list("pk", flat=True)),
            {self.claimer.pk, self.other.pk},
        )
        self.assertEqual(teams_with_leadership_problems(), [])

    def test_claimer_inherits_deputy(self) -> None:
        Team.objects.filter(pk=self.team.pk).update(
            captain=self.other, deputy_captain=self.target
        )

        self._merge()

        self.assertEqual(self.team.captain, self.other)
        self.assertEqual(self.team.deputy_captain, self.claimer)
        self.assertEqual(teams_with_leadership_problems(), [])

    def test_sole_member_captain_team_survives(self) -> None:
        solo = Team.objects.create(tournament=self.tournament, name="Solo")
        solo.members.set([self.target])
        Team.objects.filter(pk=solo.pk).update(captain=self.target)

        self._merge()

        solo.refresh_from_db()
        self.assertEqual(solo.captain, self.claimer)
        self.assertEqual(list(solo.members.all()), [self.claimer])

    def test_claimer_deputy_promoted_drops_duplicate_deputy(self) -> None:
        self.team.members.add(self.claimer)
        self.tournament.users.add(self.claimer)
        Team.objects.filter(pk=self.team.pk).update(
            captain=self.target, deputy_captain=self.claimer
        )

        self._merge()

        self.assertEqual(self.team.captain, self.claimer)
        self.assertIsNone(self.team.deputy_captain)
        self.assertEqual(teams_with_leadership_problems(), [])
