"""Profile claim merge moves rows on a shared org membership to the claimer."""

import itertools

from django.test import TestCase
from django.utils import timezone

from app.models import CustomUser, PositionsModel
from events.tests.actors import SYSTEM
from league.models import League, LeagueUser
from org.models import Organization, OrgUser, PlayerDotaProfile
from org.views import ClaimRequestViewSet

_discord_ids = itertools.count(798100)


def _user(name: str) -> CustomUser:
    return CustomUser.objects.create(
        username=name,
        discordId=str(next(_discord_ids)),
        positions=PositionsModel.objects.create(),
    )


class ClaimMergeMemberDependentsTests(TestCase):
    def setUp(self) -> None:
        self.target = _user("claim_dep_target")
        self.claimer = _user("claim_dep_claimer")
        self.org = Organization.objects.create(name="Claim Dep Org", owner=self.claimer)
        self.league = League.objects.create(name="Claim Dep", organization=self.org)
        self.claimer_ou = OrgUser.objects.create(
            user=self.claimer, organization=self.org
        )
        self.target_ou = OrgUser.objects.create(user=self.target, organization=self.org)

    def _merge(self) -> None:
        ClaimRequestViewSet()._merge_profiles(self.claimer, self.target, actor=SYSTEM)

    def test_league_membership_on_shared_org_moves_to_claimer(self) -> None:
        lu = LeagueUser.objects.create(
            user=self.target, org_user=self.target_ou, league=self.league, mmr=4200
        )

        self._merge()

        moved = LeagueUser.objects.nocache().get(pk=lu.pk)
        self.assertEqual(
            (moved.user_id, moved.org_user_id, moved.mmr),
            (self.claimer.pk, self.claimer_ou.pk, 4200),
        )

    def test_conflicting_league_membership_keeps_higher_mmr(self) -> None:
        existing = LeagueUser.objects.create(
            user=self.claimer, org_user=self.claimer_ou, league=self.league, mmr=3000
        )
        LeagueUser.objects.create(
            user=self.target, org_user=self.target_ou, league=self.league, mmr=4200
        )

        self._merge()

        self.assertEqual(LeagueUser.objects.nocache().get(pk=existing.pk).mmr, 4200)

    def test_official_league_mmr_survives_member_dependent_merge(self) -> None:
        verified_at = timezone.now()
        existing = LeagueUser.objects.create(
            user=self.claimer,
            org_user=self.claimer_ou,
            league=self.league,
            mmr=3000,
            mmr_verified_at=verified_at,
            mmr_verified_by=self.claimer,
        )
        LeagueUser.objects.create(
            user=self.target, org_user=self.target_ou, league=self.league, mmr=4200
        )

        self._merge()

        merged = LeagueUser.objects.nocache().get(pk=existing.pk)
        self.assertEqual(merged.mmr, 3000)
        self.assertEqual(merged.mmr_verified_at, verified_at)
        self.assertEqual(merged.mmr_verified_by_id, self.claimer.pk)

    def test_org_game_profile_moves_to_claimer(self) -> None:
        profile = PlayerDotaProfile.objects.create(
            org_user=self.target_ou, rank_medal="Legend"
        )

        self._merge()

        self.assertEqual(
            PlayerDotaProfile.objects.nocache().get(pk=profile.pk).org_user_id,
            self.claimer_ou.pk,
        )
