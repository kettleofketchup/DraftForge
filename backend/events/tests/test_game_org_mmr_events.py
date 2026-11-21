import datetime
import itertools
import json
import re
from collections.abc import Callable
from datetime import timedelta
from typing import Any
from unittest.mock import patch

from cacheops.conf import settings as cacheops_settings
from cacheops.signals import cache_read
from django.db import connection
from django.test import TestCase, TransactionTestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APIClient, APIRequestFactory

from app.models import CustomUser, PositionsModel, Tournament
from common.game import GameType
from events.constants import SignupStatus
from events.models import Event, EventSignup
from events.serializers import EventSignupSerializer
from events.services import create_tournament_for_event
from org.models import Organization, OrgLog, OrgUser, OrgUserGameMmr
from org.models_profiles import PlayerDeadlockProfile
from tests.populate.utils import ensure_org_user
from tests.test_auth import get_user_org_membership
from tests.test_events_discord import set_org_user_approved_mmr
from user.tests.test_cacheops_integration import _redis_reachable

_discord_ids = itertools.count(930_000_000_000_000_000)

DOTA_FALLBACK_MIDPOINT = 1000  # midpoint of settings.DOTA_DEFAULT_MMR_RANGE (0, 2000)


def _make_user(name: str) -> CustomUser:
    return CustomUser.objects.create(
        username=name,
        discordId=str(next(_discord_ids)),
        positions=PositionsModel.objects.create(),
    )


def _rows(response: Any) -> list[dict]:
    body = response.json()
    return body["results"] if isinstance(body, dict) else body


def _contains_number(text: str, value: int) -> bool:
    return re.search(rf"(?<!\d){value}(?!\d)", text) is not None


class EventGameFixtures:
    owner: CustomUser
    org: Organization

    def build_org(self, *, private: bool = True) -> None:
        self.owner = _make_user("ge_owner")
        self.org = Organization.objects.create(
            name="GE Org", owner=self.owner, members_private=private
        )
        self._seq = 0

    def event(self, game: int, *, tournament: bool = True) -> Event:
        self._seq += 1
        event = Event.objects.create(
            organization=self.org,
            name=f"GE Event {self._seq}",
            scheduled_at=timezone.now() + timedelta(days=3),
            timezone="UTC",
            created_by=self.owner,
            game_type=game,
        )
        if tournament:
            create_tournament_for_event(event)
            event.refresh_from_db()
        return event

    def player(
        self, name: str, dota: int | None = None, deadlock: int | None = None
    ) -> CustomUser:
        user = _make_user(name)
        ensure_org_user(
            user, self.org, mmr=dota, game_mmrs={GameType.DEADLOCK: deadlock}
        )
        return user

    def signup(self, event: Event, user: CustomUser) -> EventSignup:
        return EventSignup.objects.create(
            event=event, user=user, status=SignupStatus.RSVP
        )

    def list_rows(self, event: Event, viewer: CustomUser | None) -> list[dict]:
        client = APIClient()
        if viewer is not None:
            client.force_authenticate(viewer)
        response = client.get(f"/api/events/signups/?event={event.pk}")
        assert response.status_code == 200, response.content
        return _rows(response)

    def approve(self, signup: EventSignup, mmr: int) -> Any:
        client = APIClient()
        client.force_authenticate(self.owner)
        return client.post(
            f"/api/events/signups/{signup.pk}/approve/", {"mmr": mmr}, format="json"
        )

    def rating(self, user: CustomUser, game: int) -> int | None:
        return (
            OrgUserGameMmr.objects.nocache()
            .filter(
                org_user__user=user, org_user__organization=self.org, game_type=game
            )
            .values_list("mmr", flat=True)
            .first()
        )


class ApproveGameTests(EventGameFixtures, TestCase):
    def setUp(self) -> None:
        self.build_org()

    def test_deadlock_approve_writes_deadlock_row(self) -> None:
        event = self.event(GameType.DEADLOCK)
        user = self.player("ge_dl_appr", dota=4000)
        signup = self.signup(event, user)

        response = self.approve(signup, 2500)

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(self.rating(user, GameType.DEADLOCK), 2500)
        self.assertEqual(self.rating(user, GameType.DOTA2), 4000)
        org_user = OrgUser.objects.nocache().get(user=user, organization=self.org)
        self.assertFalse(org_user.has_active_dota_mmr)
        self.assertIsNone(org_user.dota_mmr_last_verified)
        entry = OrgLog.objects.get(action="set_mmr", target_user=user)
        self.assertEqual(entry.details["game_type"], GameType.DEADLOCK)
        self.assertEqual(entry.details["mmr"], 2500)

    def test_dota_approve_zero_sets_flags_no_row(self) -> None:
        event = self.event(GameType.DOTA2)
        user = self.player("ge_dota_zero")
        signup = self.signup(event, user)

        response = self.approve(signup, 0)

        self.assertEqual(response.status_code, 200, response.content)
        self.assertIsNone(self.rating(user, GameType.DOTA2))
        org_user = OrgUser.objects.nocache().get(user=user, organization=self.org)
        self.assertTrue(org_user.has_active_dota_mmr)
        self.assertIsNotNone(org_user.dota_mmr_last_verified)
        entry = OrgLog.objects.get(action="set_mmr", target_user=user)
        self.assertEqual(entry.details["game_type"], GameType.DOTA2)

    def test_approve_out_of_range_400(self) -> None:
        event = self.event(GameType.DEADLOCK)
        user = self.player("ge_range")
        signup = self.signup(event, user)

        for value in (20001, -1):
            with self.subTest(value=value):
                response = self.approve(signup, value)
                self.assertEqual(response.status_code, 400, response.content)
                self.assertIn("error", response.json())
        self.assertIsNone(self.rating(user, GameType.DEADLOCK))
        signup.refresh_from_db()
        self.assertEqual(signup.status, SignupStatus.RSVP)
        self.assertFalse(OrgLog.objects.filter(action="set_mmr").exists())


@override_settings(CACHEOPS_ENABLED=True)
class ApproveBustsTournamentDetailTests(EventGameFixtures, TransactionTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls._redis_ok = _redis_reachable()

    def setUp(self) -> None:
        if not self._redis_ok:
            self.fail("Cacheops Redis not reachable: cache tests cannot run")
        self.build_org()

    def _user_mmr(self, tournament: Tournament, user: CustomUser) -> int:
        response = APIClient().get(f"/api/tournaments/{tournament.pk}/")
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()["_users"][str(user.pk)]["mmr"]

    def test_deadlock_approve_busts_event_tournament_detail(self) -> None:
        event = self.event(GameType.DEADLOCK)
        tournament = event.tournament
        self.assertIsNone(tournament.league_id)
        self.assertEqual(tournament.game_type, GameType.DEADLOCK)
        user = self.player("ge_bust", dota=4000, deadlock=1200)
        tournament.users.add(user)
        # Past "future", approve's roster sync no longer touches the tournament,
        # so only the MMR write can bust its cache.
        tournament.state = "in_progress"
        tournament.save(update_fields=["state"])
        signup = self.signup(event, user)

        self.assertEqual(self._user_mmr(tournament, user), 1200)
        response = self.approve(signup, 2700)
        self.assertEqual(response.status_code, 200, response.content)

        self.assertEqual(self._user_mmr(tournament, user), 2700)


class SignupPayloadGameTests(EventGameFixtures, TestCase):
    def setUp(self) -> None:
        self.build_org()

    def test_signup_org_user_mmr_event_game(self) -> None:
        user = self.player("ge_payload", dota=4100, deadlock=2200)
        for game, expected in ((GameType.DEADLOCK, 2200), (GameType.DOTA2, 4100)):
            with self.subTest(game=game):
                event = self.event(game)
                self.signup(event, user)
                row = self.list_rows(event, self.owner)[0]
                self.assertEqual(row["org_user_mmr"], expected)
                self.assertEqual(row["org_user_game_mmrs"], {"1": 4100, "2": 2200})
                self.assertEqual(row["user_data"]["mmr"], expected)
                self.assertEqual(row["user_data"]["mmr_game_type"], game)

    def test_signup_user_data_memo_per_game(self) -> None:
        user = self.player("ge_memo", dota=4300, deadlock=2300)
        event = self.event(GameType.DEADLOCK)
        signup = self.signup(event, user)
        signup = EventSignup.objects.select_related("event__tournament").get(
            pk=signup.pk
        )
        request = APIRequestFactory().get("/")
        request.user = self.owner
        context: dict[str, Any] = {"request": request}

        signup.event.game_type = GameType.DOTA2
        dota = EventSignupSerializer(signup, context=context).data["user_data"]
        signup.event.game_type = GameType.DEADLOCK
        if hasattr(signup, "_mmr_suggestion_cache"):
            del signup._mmr_suggestion_cache
        deadlock = EventSignupSerializer(signup, context=context).data["user_data"]

        self.assertEqual((dota["mmr"], dota["mmr_game_type"]), (4300, 1))
        self.assertEqual((deadlock["mmr"], deadlock["mmr_game_type"]), (2300, 2))

    def test_deadlock_no_prior_suggestion_none(self) -> None:
        event = self.event(GameType.DEADLOCK)
        self.signup(event, self.player("ge_noprior", dota=4400))
        row = self.list_rows(event, self.owner)[0]
        self.assertIsNone(row["suggested_mmr"])
        self.assertIsNone(row["suggested_mmr_range"])
        self.assertEqual(row["suggested_mmr_range_source"], "none")

    def test_deadlock_prior_suggestion_is_prior(self) -> None:
        event = self.event(GameType.DEADLOCK)
        self.signup(event, self.player("ge_prior", dota=4400, deadlock=2600))
        row = self.list_rows(event, self.owner)[0]
        self.assertEqual(row["suggested_mmr"], 2600)
        self.assertIsNone(row["suggested_mmr_range"])
        self.assertEqual(row["suggested_mmr_range_source"], "none")

    def test_dota_prior_suggestion_unchanged(self) -> None:
        event = self.event(GameType.DOTA2)
        self.signup(event, self.player("ge_dprior", dota=4400, deadlock=2600))
        row = self.list_rows(event, self.owner)[0]
        self.assertEqual(row["suggested_mmr"], 4400)
        self.assertEqual(row["suggested_mmr_range"], [0, 2000])
        self.assertEqual(row["suggested_mmr_range_source"], "fallback")

    def test_outsider_sees_no_org_values(self) -> None:
        user = self.player("ge_secret", dota=4271, deadlock=3137)
        org_user = OrgUser.objects.get(user=user, organization=self.org)
        PlayerDeadlockProfile.objects.create(org_user=org_user, rank="Ascendant 2")
        outsider = _make_user("ge_outsider")
        deadlock_event = self.event(GameType.DEADLOCK)
        dota_event = self.event(GameType.DOTA2)
        self.signup(deadlock_event, user)
        self.signup(dota_event, user)

        for viewer in (None, outsider):
            label = getattr(viewer, "username", "anon")
            with self.subTest(viewer=label, game="deadlock"):
                rows = self.list_rows(deadlock_event, viewer)
                row = rows[0]
                self.assertIsNone(row["org_user_mmr"])
                self.assertIsNone(row.get("org_user_game_mmrs"))
                self.assertIsNone(row["self_reported_rank"])
                self.assertIsNone(row["self_reported_rank_date"])
                self.assertIsNone(row["suggested_mmr"])
                self.assertIsNone(row["suggested_mmr_range"])
                self.assertEqual(row["suggested_mmr_range_source"], "none")
                for key in ("mmr", "mmr_game_type", "game_mmrs", "league_mmr"):
                    self.assertNotIn(key, row["user_data"])
                dumped = json.dumps(rows)
                self.assertFalse(_contains_number(dumped, 3137), dumped)
                self.assertFalse(_contains_number(dumped, 4271), dumped)
            with self.subTest(viewer=label, game="dota"):
                rows = self.list_rows(dota_event, viewer)
                row = rows[0]
                # No Dota profile and the prior org MMR hidden: suggest_mmr's
                # fallback midpoint of DOTA_DEFAULT_MMR_RANGE.
                self.assertEqual(row["suggested_mmr"], DOTA_FALLBACK_MIDPOINT)
                self.assertEqual(row["suggested_mmr_range"], [0, 2000])
                self.assertEqual(row["suggested_mmr_range_source"], "fallback")
                self.assertIsNone(row.get("org_user_game_mmrs"))
                dumped = json.dumps(rows)
                self.assertFalse(_contains_number(dumped, 3137), dumped)
                self.assertFalse(_contains_number(dumped, 4271), dumped)

    def _query_count(self, event: Event) -> int:
        client = APIClient()
        client.force_authenticate(self.owner)
        with CaptureQueriesContext(connection) as ctx:
            response = client.get(f"/api/events/signups/?event={event.pk}")
        self.assertEqual(response.status_code, 200)
        return len(ctx.captured_queries)

    def test_self_reported_rank_deadlock_only(self) -> None:
        deadlock_event = self.event(GameType.DEADLOCK)
        dota_event = self.event(GameType.DOTA2)
        for i in range(2):
            user = self.player(f"ge_rank{i}", dota=4000 + i, deadlock=2000 + i)
            org_user = OrgUser.objects.get(user=user, organization=self.org)
            PlayerDeadlockProfile.objects.create(
                org_user=org_user,
                rank=f"Emissary {i + 1}",
                rank_date=datetime.date(2026, 10, 1 + i),
            )
            self.signup(deadlock_event, user)
            self.signup(dota_event, user)

        rows = {r["username"]: r for r in self.list_rows(deadlock_event, self.owner)}
        self.assertEqual(rows["ge_rank0"]["self_reported_rank"], "Emissary 1")
        self.assertEqual(rows["ge_rank1"]["self_reported_rank_date"], "2026-10-02")
        for row in self.list_rows(dota_event, self.owner):
            self.assertIsNone(row["self_reported_rank"])
            self.assertIsNone(row["self_reported_rank_date"])
        self.assertEqual(
            self._query_count(deadlock_event), self._query_count(dota_event)
        )

    def test_signup_list_constant_queries(self) -> None:
        small = self.event(GameType.DEADLOCK)
        large = self.event(GameType.DEADLOCK)
        for i in range(2):
            self.signup(
                small, self.player(f"ge_qs{i}", dota=3000 + i, deadlock=100 + i)
            )
        for i in range(6):
            self.signup(
                large, self.player(f"ge_ql{i}", dota=3500 + i, deadlock=200 + i)
            )
        self.assertEqual(self._query_count(small), self._query_count(large))


class SignupFreshReadTests(EventGameFixtures, TransactionTestCase):
    def setUp(self) -> None:
        self.assertTrue(
            cacheops_settings.CACHEOPS_ENABLED,
            "cacheops disabled: fresh-read test cannot run",
        )
        self.build_org()

    def _cached_reads(self, fn: Callable[[], object]) -> list[str]:
        reads: list[str] = []

        def record(sender: type | None, func: object = None, **kwargs: object) -> None:
            reads.append(getattr(sender, "__name__", None) or repr(func))

        cache_read.connect(record)
        try:
            fn()
        finally:
            cache_read.disconnect(record)
        return reads

    def test_signup_fresh_no_cached_reads_deadlock(self) -> None:
        event = self.event(GameType.DEADLOCK)
        user = self.player("ge_fresh", dota=4500)
        self.signup(event, user)
        org_user = OrgUser.objects.get(user=user, organization=self.org)
        self.list_rows(event, self.owner)
        OrgUserGameMmr.objects.create(
            org_user=org_user, game_type=GameType.DEADLOCK, mmr=2468
        )

        rows: list[dict] = []

        def serialize() -> None:
            rows.extend(self.list_rows(event, self.owner))

        reads = self._cached_reads(serialize)
        self.assertNotIn("OrgUser", reads)
        self.assertNotIn("OrgUserGameMmr", reads)
        self.assertEqual(rows[0]["org_user_mmr"], 2468)
        self.assertEqual(rows[0]["org_user_game_mmrs"], {"1": 4500, "2": 2468})
        self.assertEqual(rows[0]["user_data"]["mmr"], 2468)


class TestEndpointGameTests(EventGameFixtures, TestCase):
    factory = APIRequestFactory()

    def setUp(self) -> None:
        self.build_org()

    def test_test_endpoint_sets_game(self) -> None:
        user = self.player("ge_endpoint", dota=4600)
        request = self.factory.post(
            "/x/", {"mmr": 1900, "game_type": GameType.DEADLOCK}, format="json"
        )
        with patch("tests.test_events_discord.isTestEnvironment", return_value=True):
            response = set_org_user_approved_mmr(request, self.org.pk, user.pk)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(self.rating(user, GameType.DEADLOCK), 1900)
        self.assertEqual(self.rating(user, GameType.DOTA2), 4600)

        request = self.factory.post("/x/", {"mmr": 4700}, format="json")
        with patch("tests.test_events_discord.isTestEnvironment", return_value=True):
            response = set_org_user_approved_mmr(request, self.org.pk, user.pk)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(self.rating(user, GameType.DOTA2), 4700)

        with patch("tests.test_auth.isTestEnvironment", return_value=True):
            dump = get_user_org_membership(self.factory.get("/x/"), user.pk)
        self.assertEqual(dump.status_code, 200)
        (entry,) = dump.data["org_users"]
        self.assertEqual(entry["mmr"], 4700)
        self.assertEqual(entry["game_mmrs"], {"1": 4700, "2": 1900})

    def test_test_endpoint_rejects_unknown_game(self) -> None:
        user = self.player("ge_badgame")
        request = self.factory.post(
            "/x/", {"mmr": 1900, "game_type": 99}, format="json"
        )
        with patch("tests.test_events_discord.isTestEnvironment", return_value=True):
            response = set_org_user_approved_mmr(request, self.org.pk, user.pk)
        self.assertEqual(response.status_code, 400)
