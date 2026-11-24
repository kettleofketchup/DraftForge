from unittest import mock
from unittest.mock import MagicMock

from django.conf import settings
from django.core.cache.backends.locmem import LocMemCache
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from app.models import CustomUser
from common.game import GameType
from league.models import League, LeagueUser
from lobby.bot_access.dota import DotaBotAccess
from lobby.bot_access.schemas import BotAccessSnapshot, ServiceState
from lobby.bot_access.views import (
    BotAccessReadThrottle,
    BotAccessRefreshGlobalThrottle,
    BotAccessRefreshThrottle,
)
from lobby.client import DotaLobbyClient, DotaLobbyError, DotaLobbyUnavailable
from lobby.tests.test_bot_access import LEAGUE_ID, SID1, SID2, bot, bot_leagues
from lobby.tests.test_bot_access import league as league_view
from org.models import Organization, OrgUser

ROW_KEYS = {
    "position",
    "identity",
    "status",
    "access",
    "access_note",
    "access_checked_at",
    "refresh",
}


def fixture_snapshot() -> BotAccessSnapshot:
    return BotAccessSnapshot(
        game_type=int(GameType.DOTA2),
        supported=True,
        provider="dota2",
        external_league_id=str(LEAGUE_ID),
        service=ServiceState(status="ok"),
        bots=[],
        held_count=0,
        checked_at=timezone.now(),
    )


class BotAccessViewTestCase(TestCase):
    def setUp(self) -> None:
        throttle_cache = LocMemCache("bot-access-throttle-test", {})
        throttle_cache.clear()
        for cls in (
            BotAccessReadThrottle,
            BotAccessRefreshThrottle,
            BotAccessRefreshGlobalThrottle,
        ):
            patcher = mock.patch.object(cls, "cache", throttle_cache)
            patcher.start()
            self.addCleanup(patcher.stop)

        make = CustomUser.objects.create_user
        self.site_staff = make(username="sitestaff", password="x", is_staff=True)
        self.org_admin = make(username="orgadmin", password="x")
        self.org_staff = make(username="orgstaff", password="x")
        self.league_admin = make(username="leagueadmin", password="x")
        self.league_staff = make(username="leaguestaff", password="x")
        self.other_admin = make(username="otheradmin", password="x")
        self.member = make(username="member", password="x")

        self.org = Organization.objects.create(name="Org")
        self.org.admins.add(self.org_admin)
        self.org.staff.add(self.org_staff)
        self.league = League.objects.create(
            organization=self.org, name="League", steam_league_id=LEAGUE_ID
        )
        self.league.admins.add(self.league_admin)
        self.league.staff.add(self.league_staff)
        self.other_league = League.objects.create(organization=self.org, name="Other")
        self.other_league.admins.add(self.other_admin)
        org_user = OrgUser.objects.create(user=self.member, organization=self.org)
        LeagueUser.objects.create(
            user=self.member, org_user=org_user, league=self.league
        )

        self.provider = MagicMock()
        self.provider.supported = True
        self.provider.external_league_id.return_value = str(LEAGUE_ID)
        self.provider.snapshot.return_value = fixture_snapshot()
        self.provider.refresh.return_value = fixture_snapshot()
        patcher = mock.patch(
            "lobby.bot_access.views.get_bot_access", return_value=self.provider
        )
        self.get_bot_access = patcher.start()
        self.get_bot_access_patcher = patcher
        self.addCleanup(mock.patch.stopall)

    def url(self, league_id: int | None = None, refresh: bool = False) -> str:
        pk = self.league.pk if league_id is None else league_id
        return f"/api/leagues/{pk}/bot-access/" + ("refresh/" if refresh else "")

    def as_user(self, user: CustomUser | None) -> APIClient:
        client = APIClient()
        if user is not None:
            client.force_authenticate(user=user)
        return client

    def get(self, user: CustomUser | None, league_id: int | None = None):
        return self.as_user(user).get(self.url(league_id))

    def post(self, user: CustomUser | None, league_id: int | None = None):
        return self.as_user(user).post(self.url(league_id, refresh=True))


class BotAccessPermissionTests(BotAccessViewTestCase):
    def assert_ok(self, user: CustomUser) -> None:
        resp = self.get(user)
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.json()["service"]["status"], "ok")
        self.provider.snapshot.assert_called_with(str(LEAGUE_ID))

    def assert_hidden(self, user: CustomUser) -> None:
        resp = self.get(user)
        self.assertEqual(resp.status_code, 404)
        self.provider.snapshot.assert_not_called()

    def test_site_staff_200(self) -> None:
        self.assert_ok(self.site_staff)

    def test_org_admin_200(self) -> None:
        self.assert_ok(self.org_admin)

    def test_league_admin_200(self) -> None:
        self.assert_ok(self.league_admin)

    def test_league_staff_404(self) -> None:
        self.assert_hidden(self.league_staff)

    def test_org_staff_404(self) -> None:
        self.assert_hidden(self.org_staff)

    def test_other_league_admin_404(self) -> None:
        self.assert_hidden(self.other_admin)

    def test_member_404(self) -> None:
        self.assert_hidden(self.member)

    def test_anonymous_denied(self) -> None:
        sibling = self.as_user(None).post(f"/api/leagues/{self.league.pk}/admins/")
        self.assertIn(sibling.status_code, (401, 403))
        self.assertEqual(self.get(None).status_code, sibling.status_code)
        self.assertEqual(self.post(None).status_code, sibling.status_code)
        self.provider.snapshot.assert_not_called()
        self.provider.refresh.assert_not_called()

    def test_unknown_league_404(self) -> None:
        self.assertEqual(self.get(self.site_staff, league_id=999_999).status_code, 404)
        self.assertEqual(self.post(self.site_staff, league_id=999_999).status_code, 404)

    def test_refresh_league_admin_200(self) -> None:
        resp = self.post(self.league_admin)
        self.assertEqual(resp.status_code, 200, resp.content)
        self.provider.refresh.assert_called_once_with(str(LEAGUE_ID))
        self.provider.snapshot.assert_not_called()

    def test_refresh_league_staff_404(self) -> None:
        self.assertEqual(self.post(self.league_staff).status_code, 404)
        self.assertEqual(self.post(self.other_admin).status_code, 404)
        self.provider.refresh.assert_not_called()

    def test_read_route_rejects_post(self) -> None:
        resp = self.as_user(self.league_admin).post(self.url())
        self.assertEqual(resp.status_code, 405)


class BotAccessBehaviourTests(BotAccessViewTestCase):
    def test_not_linked_no_upstream_call(self) -> None:
        self.league.steam_league_id = None
        self.league.save()
        self.get_bot_access_patcher.stop()
        factory = MagicMock(spec=DotaLobbyClient)
        with mock.patch(
            "lobby.bot_access.views.get_bot_access",
            return_value=DotaBotAccess(client_factory=factory),
        ):
            for resp in (self.get(self.league_admin), self.post(self.league_admin)):
                self.assertEqual(resp.status_code, 200)
                body = resp.json()
                self.assertEqual(body["service"]["status"], "league_not_linked")
                self.assertEqual(body["bots"], [])
                self.assertIsNone(body["external_league_id"])
        factory.assert_not_called()

    def test_unsupported_game(self) -> None:
        self.get_bot_access_patcher.stop()
        with mock.patch(
            "lobby.bot_access.views.league_game_type",
            return_value=GameType.DEADLOCK,
        ):
            for resp in (self.get(self.league_admin), self.post(self.league_admin)):
                self.assertEqual(resp.status_code, 200)
                body = resp.json()
                self.assertIs(body["supported"], False)
                self.assertEqual(body["service"]["status"], "unsupported")
                self.assertEqual(body["bots"], [])

    @override_settings(DOTA_LOBBY_ENABLED=True)
    def test_upstream_down_is_200(self) -> None:
        client = MagicMock(spec=DotaLobbyClient)
        client.timeout = 15
        client.list_bots.side_effect = DotaLobbyUnavailable("ReadTimeout")
        client.refresh_leagues.side_effect = DotaLobbyUnavailable("ReadTimeout")
        self.get_bot_access.return_value = DotaBotAccess(
            client_factory=MagicMock(return_value=client)
        )
        for resp in (self.get(self.league_admin), self.post(self.league_admin)):
            self.assertEqual(resp.status_code, 200)
            self.assertEqual(resp.json()["service"]["status"], "unavailable")

    @override_settings(DOTA_LOBBY_ENABLED=True)
    def test_self_service_admin_sees_withheld_status(self) -> None:
        creator = CustomUser.objects.create_user(username="selfserve", password="x")
        org = Organization.objects.create(name="Mine", owner=creator)
        org.admins.add(creator)
        mine = League.objects.create(
            organization=org, name="Mine", steam_league_id=LEAGUE_ID + 1
        )
        client = MagicMock(spec=DotaLobbyClient)
        client.timeout = 15
        client.list_bots.return_value = [
            bot("sim_bot_1", steam_id=SID1, leagues=[LEAGUE_ID]),
            bot("sim_bot_2", steam_id=SID2, state="gc_ready", lobby="L1"),
        ]
        client.get_league.side_effect = DotaLobbyError("not_found", status=404)
        client.get_bot_leagues.return_value = bot_leagues()
        self.get_bot_access.return_value = DotaBotAccess(
            client_factory=MagicMock(return_value=client)
        )
        resp = self.get(creator, league_id=mine.pk)
        self.assertEqual(resp.status_code, 200, resp.content)
        rows = resp.json()["bots"]
        self.assertEqual(len(rows), 2)
        for row in rows:
            self.assertEqual(set(row), ROW_KEYS)
            self.assertIsNone(row["status"])

    @override_settings(DOTA_LOBBY_ENABLED=True)
    def test_no_leak(self) -> None:
        client = MagicMock(spec=DotaLobbyClient)
        client.timeout = 15
        client.list_bots.return_value = [
            bot("sim_bot_1", steam_id=SID1, leagues=[LEAGUE_ID]),
            bot("sim_bot_2", steam_id=SID2),
        ]
        client.get_league.return_value = league_view()
        client.get_bot_leagues.side_effect = DotaLobbyError(
            "not_found", status=404, detail='no bot named "sim_bot_2"'
        )
        self.get_bot_access.return_value = DotaBotAccess(
            client_factory=MagicMock(return_value=client)
        )
        for resp in (self.get(self.league_admin), self.post(self.league_admin)):
            self.assertEqual(resp.status_code, 200)
            text = resp.content.decode()
            for secret in (
                "sim_bot_",
                "login_sim_bot",
                "secret detail",
                "no bot named",
            ):
                self.assertNotIn(secret, text)
            if settings.DOTA_LOBBY_URL:
                self.assertNotIn(settings.DOTA_LOBBY_URL, text)

    def test_cache_control_no_store(self) -> None:
        for resp in (self.get(self.league_admin), self.post(self.league_admin)):
            self.assertEqual(resp.status_code, 200)
            self.assertIn("no-store", resp["Cache-Control"])


class BotAccessThrottleTests(BotAccessViewTestCase):
    def assert_throttled(self, resp) -> None:
        self.assertEqual(resp.status_code, 429)
        self.assertEqual(resp.json()["code"], "throttled")
        self.assertGreater(int(resp["Retry-After"]), 0)
        self.assertIn("no-store", resp["Cache-Control"])

    def test_refresh_throttle_429_retry_after(self) -> None:
        for _ in range(6):
            self.assertEqual(self.post(self.league_admin).status_code, 200)
        self.assert_throttled(self.post(self.league_admin))
        self.assertEqual(self.provider.refresh.call_count, 6)
        self.assertEqual(self.post(self.org_admin).status_code, 200)

    def test_global_refresh_throttle_across_users(self) -> None:
        with mock.patch.object(BotAccessRefreshThrottle, "rate", "100/min"):
            for i in range(20):
                user = self.league_admin if i % 2 else self.org_admin
                self.assertEqual(self.post(user).status_code, 200)
            self.assert_throttled(self.post(self.site_staff))
        self.assertEqual(self.provider.refresh.call_count, 20)

    def test_read_throttle(self) -> None:
        for _ in range(30):
            self.assertEqual(self.get(self.league_admin).status_code, 200)
        self.assert_throttled(self.get(self.league_admin))
        self.assertEqual(self.provider.snapshot.call_count, 30)

    def test_denied_user_never_throttled(self) -> None:
        for _ in range(40):
            self.assertEqual(self.get(self.league_staff).status_code, 404)
        for _ in range(10):
            self.assertEqual(self.post(self.league_staff).status_code, 404)
