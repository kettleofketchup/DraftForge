import itertools
from typing import Any

from django.test import TestCase, TransactionTestCase
from django.utils import timezone
from rest_framework.test import APIClient

from app.models import (
    CustomUser,
    Organization,
    PositionsModel,
    ProfileClaimRequest,
    Tournament,
)
from common.game import GameType
from events.models import Event
from events.services import create_tournament_for_event
from org.models import OrgUser, OrgUserGameMmr
from user.tests.test_cacheops_integration import _redis_reachable

_discord_ids = itertools.count(930_000_000_000_000_000)


def _make_user(name: str, **kwargs: Any) -> CustomUser:
    return CustomUser.objects.create(
        username=name, positions=PositionsModel.objects.create(), **kwargs
    )


class ClaimFixtures:
    client: APIClient
    admin: CustomUser
    org: Organization
    claimer: CustomUser
    target: CustomUser
    keeper: OrgUser
    claim: ProfileClaimRequest

    def build(self) -> None:
        self.admin = CustomUser.objects.create_superuser(
            username="cg_admin", password="testpass"
        )
        self.org = Organization.objects.create(name="Claim Game Org")
        self.claimer = _make_user("cg_claimer", discordId=str(next(_discord_ids)))
        self.target = _make_user("cg_target", steamid=76561198000300001)
        self.keeper = OrgUser.objects.create(user=self.claimer, organization=self.org)
        OrgUser.objects.filter(pk=self.keeper.pk).update(
            has_active_dota_mmr=False, dota_mmr_last_verified=None
        )
        loser = OrgUser.objects.create(user=self.target, organization=self.org)
        OrgUserGameMmr.objects.create(
            org_user=self.keeper, game_type=GameType.DOTA2, mmr=4000
        )
        OrgUserGameMmr.objects.create(
            org_user=loser, game_type=GameType.DOTA2, mmr=25000
        )
        OrgUserGameMmr.objects.create(
            org_user=loser, game_type=GameType.DEADLOCK, mmr=1200
        )
        self.claim = ProfileClaimRequest.objects.create(
            claimer=self.claimer,
            target_user=self.target,
            organization=self.org,
            status=ProfileClaimRequest.Status.PENDING,
        )
        self.client = APIClient()
        self.client.force_authenticate(self.admin)

    def approve(self) -> int:
        return self.client.post(
            f"/api/claim-requests/{self.claim.pk}/approve/"
        ).status_code

    def keeper_rows(self) -> dict[int, int]:
        return dict(
            OrgUserGameMmr.objects.nocache()
            .filter(org_user_id=self.keeper.pk)
            .values_list("game_type", "mmr")
        )


class ClaimMergeGameMmrsTests(ClaimFixtures, TestCase):
    def setUp(self) -> None:
        self.build()

    def test_claim_merge_keeps_higher_per_game(self) -> None:
        self.assertEqual(self.approve(), 200)

        self.assertEqual(
            self.keeper_rows(), {GameType.DOTA2: 25000, GameType.DEADLOCK: 1200}
        )
        kept = OrgUser.objects.nocache().get(pk=self.keeper.pk)
        self.assertFalse(kept.has_active_dota_mmr)
        self.assertIsNone(kept.dota_mmr_last_verified)
        self.assertFalse(OrgUser.objects.filter(user_id=self.target.pk).exists())


class ClaimMergeCacheTests(ClaimFixtures, TransactionTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls._redis_ok = _redis_reachable()

    def setUp(self) -> None:
        if not self._redis_ok:
            self.fail("Cacheops Redis not reachable: cache tests cannot run")
        self.build()

    def _deadlock_tournament(self) -> Tournament:
        event = Event.objects.create(
            name="Claim DL Night",
            organization=self.org,
            scheduled_at=timezone.now(),
            timezone="UTC",
            created_by=self.admin,
            tournament_name="Claim DL Cup",
            game_type=GameType.DEADLOCK,
        )
        tournament = create_tournament_for_event(event)
        assert tournament.league_id is None
        tournament.users.add(self.claimer)
        return tournament

    def _claimer_mmr(self, tournament: Tournament) -> int:
        response = self.client.get(f"/api/tournaments/{tournament.pk}/")
        self.assertEqual(response.status_code, 200)
        return response.json()["_users"][str(self.claimer.pk)]["mmr"]

    def test_claim_merge_busts_tournament_detail(self) -> None:
        tournament = self._deadlock_tournament()
        self.assertEqual(self._claimer_mmr(tournament), 0)

        self.assertEqual(self.approve(), 200)

        self.assertEqual(self._claimer_mmr(tournament), 1200)
