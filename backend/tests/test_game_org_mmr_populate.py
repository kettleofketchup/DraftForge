from unittest.mock import patch

from django.test import TestCase
from rest_framework.test import APIRequestFactory

from app.models import CustomUser, Tournament
from common.game import GameType
from events.constants import SignupStatus
from events.models import Event, EventSignup
from league.models import League
from org.models import Organization, OrgUser, OrgUserGameMmr
from org.models_profiles import PlayerDeadlockProfile
from tests.data.game_org_mmr import (
    GAME_MMR_APPROVE_RANK,
    GAME_MMR_APPROVE_USER,
    GAME_MMR_LEAGUE,
    GAME_MMR_ORG,
    GAME_MMR_PLAYERS,
)
from tests.populate.game_org_mmr import (
    populate_game_org_mmr_data,
    reset_game_org_mmr_approve,
)
from tests.test_game_org_mmr import game_org_mmr_approve_setup, game_org_mmr_data


def _ratings(game: int) -> dict[int, int]:
    return dict(
        OrgUserGameMmr.objects.nocache()
        .filter(org_user__organization_id=GAME_MMR_ORG.pk, game_type=game)
        .values_list("org_user__user_id", "mmr")
    )


class GameOrgMmrPopulateTest(TestCase):
    def setUp(self) -> None:
        populate_game_org_mmr_data()

    def test_org_league_and_users(self) -> None:
        org = Organization.objects.get(pk=GAME_MMR_ORG.pk)
        self.assertEqual(org.name, "Game MMR Org")
        league = League.objects.get(pk=GAME_MMR_LEAGUE.pk)
        self.assertEqual(league.organization_id, org.pk)
        self.assertEqual(league.steam_league_id, 17944)
        self.assertEqual(
            set(
                OrgUser.objects.filter(organization=org).values_list(
                    "user_id", flat=True
                )
            ),
            set(range(8000, 8008)),
        )

    def test_both_games_seeded_with_different_orderings(self) -> None:
        dota = _ratings(GameType.DOTA2)
        deadlock = _ratings(GameType.DEADLOCK)
        self.assertEqual(set(dota), set(range(8000, 8008)))
        self.assertEqual(set(deadlock), set(range(8000, 8007)))
        for p in GAME_MMR_PLAYERS:
            self.assertEqual(dota[p.user.pk], p.dota)
            self.assertNotEqual(dota[p.user.pk], deadlock.get(p.user.pk))
        display = [p.user.pk for p in GAME_MMR_PLAYERS[:5]]
        self.assertNotEqual(
            sorted(display, key=dota.__getitem__),
            sorted(display, key=deadlock.__getitem__),
        )

    def test_dota_and_deadlock_tournaments(self) -> None:
        dota = Tournament.objects.get(name="Game MMR Dota Cup")
        self.assertEqual(dota.game_type, GameType.DOTA2)
        self.assertEqual(dota.league_id, GAME_MMR_LEAGUE.pk)
        event = Event.objects.get(name="Game MMR Deadlock Night")
        self.assertEqual(event.game_type, GameType.DEADLOCK)
        self.assertIsNotNone(event.tournament_id)
        deadlock = event.tournament
        self.assertEqual(deadlock.name, "Game MMR Deadlock Cup")
        self.assertEqual(deadlock.game_type, GameType.DEADLOCK)
        self.assertEqual(deadlock.league_id, GAME_MMR_LEAGUE.pk)
        for t in (dota, deadlock):
            self.assertEqual(
                set(t.users.values_list("pk", flat=True)), set(range(8000, 8007))
            )

    def test_approve_user_deadlock_rank(self) -> None:
        profile = PlayerDeadlockProfile.objects.get(
            org_user__user_id=GAME_MMR_APPROVE_USER.pk,
            org_user__organization_id=GAME_MMR_ORG.pk,
        )
        self.assertEqual(profile.rank, "Phantom 4 (e2e)")
        self.assertEqual(GAME_MMR_APPROVE_RANK, "Phantom 4 (e2e)")
        self.assertIsNotNone(profile.rank_date)

    def test_rerun_is_idempotent(self) -> None:
        counts = (
            OrgUserGameMmr.objects.count(),
            Tournament.objects.count(),
            Event.objects.count(),
            CustomUser.objects.count(),
        )
        populate_game_org_mmr_data()
        populate_game_org_mmr_data(force=True)
        self.assertEqual(
            counts,
            (
                OrgUserGameMmr.objects.count(),
                Tournament.objects.count(),
                Event.objects.count(),
                CustomUser.objects.count(),
            ),
        )
        self.assertEqual(_ratings(GameType.DOTA2)[8006], 3000)


class GameOrgMmrApproveSetupTest(TestCase):
    def setUp(self) -> None:
        populate_game_org_mmr_data()

    def test_creates_fresh_pending_deadlock_signup(self) -> None:
        first = reset_game_org_mmr_approve()
        signup = EventSignup.objects.get(pk=first["signup_pk"])
        signup.status = SignupStatus.APPROVED
        signup.save(update_fields=["status"])
        OrgUserGameMmr.objects.create(
            org_user=OrgUser.objects.get(
                organization_id=GAME_MMR_ORG.pk, user_id=GAME_MMR_APPROVE_USER.pk
            ),
            game_type=GameType.DEADLOCK,
            mmr=2222,
        )
        PlayerDeadlockProfile.objects.filter(
            org_user__user_id=GAME_MMR_APPROVE_USER.pk
        ).update(rank="changed")

        second = reset_game_org_mmr_approve()

        self.assertFalse(Event.objects.filter(pk=first["event_pk"]).exists())
        event = Event.objects.get(pk=second["event_pk"])
        self.assertEqual(event.game_type, GameType.DEADLOCK)
        self.assertIsNotNone(event.tournament_id)
        signup = EventSignup.objects.get(pk=second["signup_pk"])
        self.assertEqual(signup.status, SignupStatus.PENDING_APPROVAL)
        self.assertEqual(signup.user_id, GAME_MMR_APPROVE_USER.pk)
        self.assertNotIn(GAME_MMR_APPROVE_USER.pk, _ratings(GameType.DEADLOCK))
        self.assertEqual(
            _ratings(GameType.DOTA2)[GAME_MMR_APPROVE_USER.pk], second["dota_mmr"]
        )
        self.assertEqual(
            PlayerDeadlockProfile.objects.get(
                org_user__user_id=GAME_MMR_APPROVE_USER.pk
            ).rank,
            "Phantom 4 (e2e)",
        )

    def test_endpoints(self) -> None:
        factory = APIRequestFactory()
        with patch("tests.test_game_org_mmr.isTestEnvironment", return_value=True):
            data = game_org_mmr_data(factory.get("/x/"))
            setup = game_org_mmr_approve_setup(factory.post("/x/"))
        self.assertEqual(data.status_code, 200, data.data)
        body = data.data
        self.assertEqual(body["org"]["pk"], GAME_MMR_ORG.pk)
        self.assertEqual(body["users"]["edit"]["pk"], 8006)
        self.assertEqual(body["users"]["display"]["pk"], 8005)
        self.assertEqual(body["users"]["approve"]["pk"], 8007)
        self.assertEqual(
            body["tournaments"]["deadlock"]["pk"],
            Event.objects.get(name="Game MMR Deadlock Night").tournament_id,
        )
        self.assertEqual(setup.status_code, 200, setup.data)
        self.assertEqual(
            EventSignup.objects.get(pk=setup.data["signup_pk"]).status,
            SignupStatus.PENDING_APPROVAL,
        )

    def test_endpoints_hidden_outside_test_env(self) -> None:
        factory = APIRequestFactory()
        with patch("tests.test_game_org_mmr.isTestEnvironment", return_value=False):
            self.assertEqual(game_org_mmr_data(factory.get("/x/")).status_code, 404)
            self.assertEqual(
                game_org_mmr_approve_setup(factory.post("/x/")).status_code, 404
            )
