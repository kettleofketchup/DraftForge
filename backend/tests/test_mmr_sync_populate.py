"""Regression tests for the MMR sync API E2E data and its test endpoints."""

from django.contrib.sessions.backends.db import SessionStore
from django.test import TestCase, override_settings
from rest_framework.test import APIRequestFactory

from app.models import CustomUser
from common.game import GameType
from org.api_tokens.tokens import issue_token
from org.features import FeatureKey, org_has_feature
from org.mmr import game_mmrs_prefetch, get_org_mmr
from org.models import Organization, OrgApiLimits, OrgApiToken, OrgUser
from tests.data.mmr_sync import (
    MMR_SYNC_LOCKED_ORG,
    MMR_SYNC_ORG,
    MMR_SYNC_ROLE_USERS,
    MS_ADMIN,
    MS_PLAYER,
    MS_PLAYER_SEED_MMR,
)
from tests.populate.mmr_sync import populate_mmr_sync_data, reset_mmr_sync_data
from tests.test_mmr_sync import login_mmr_sync, reset_mmr_sync


@override_settings(DEBUG=True)
class MmrSyncDataTest(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        populate_mmr_sync_data(force=True)

    def setUp(self) -> None:
        self.factory = APIRequestFactory()

    def test_switches_follow_the_seed(self) -> None:
        self.assertTrue(org_has_feature(MMR_SYNC_ORG.pk, FeatureKey.MMR_SYNC))
        self.assertFalse(org_has_feature(MMR_SYNC_LOCKED_ORG.pk, FeatureKey.MMR_SYNC))

    def test_player_has_steam_account_and_seed_mmr(self) -> None:
        user = CustomUser.objects.get(pk=MS_PLAYER.pk)
        self.assertEqual(user.steam_account_id, MS_PLAYER.steam_id)
        org_user = OrgUser.objects.prefetch_related(game_mmrs_prefetch(fresh=True)).get(
            organization_id=MMR_SYNC_ORG.pk, user=user
        )
        self.assertEqual(get_org_mmr(org_user, GameType.DOTA2), MS_PLAYER_SEED_MMR)

    def test_reset_drops_tokens_and_limits(self) -> None:
        org = Organization.objects.get(pk=MMR_SYNC_ORG.pk)
        issue_token(org, CustomUser.objects.get(pk=MS_ADMIN.pk), "Leftover")
        OrgApiLimits.objects.create(organization=org, per_minute=5, per_day=10)
        body = reset_mmr_sync(self.factory.post("/api/tests/mmr-sync/reset/")).data
        self.assertEqual(body["orgs"]["unlocked"]["pk"], MMR_SYNC_ORG.pk)
        self.assertFalse(OrgApiToken.objects.filter(organization=org).exists())
        self.assertFalse(OrgApiLimits.objects.filter(organization=org).exists())

    def test_reset_is_idempotent(self) -> None:
        for _ in range(2):
            reset_mmr_sync_data()
            self.assertEqual(
                CustomUser.objects.get(pk=MS_PLAYER.pk).steam_account_id,
                MS_PLAYER.steam_id,
            )
        self.assertEqual(
            set(
                OrgUser.objects.filter(organization_id=MMR_SYNC_ORG.pk).values_list(
                    "user_id", flat=True
                )
            ),
            {8100, 8101, 8102, 8103},
        )

    def test_every_role_logs_in(self) -> None:
        for role in [*MMR_SYNC_ROLE_USERS, "nobody"]:
            request = self.factory.post(f"/api/tests/login-mmr-sync/{role}/")
            request.session = SessionStore()
            expected = 400 if role == "nobody" else 200
            self.assertEqual(login_mmr_sync(request, role).status_code, expected, role)
