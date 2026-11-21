from datetime import timedelta

from django.db import connection, reset_queries
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APIClient

from app.models import CustomUser
from common.game import GameType
from events.constants import SignupStatus
from events.models import Event, EventSignup, EventTeam
from events.schemas import EventSignupSchema
from events.services import create_tournament_for_event
from org.models import Organization, OrgUser
from tests.cache import flush_run_cache
from tests.populate.utils import ensure_org_user


class SignupNameFieldsTest(TestCase):
    def setUp(self) -> None:
        flush_run_cache()
        self.owner = CustomUser.objects.create_user(username="snf_owner", password="x")
        self.org = Organization.objects.create(
            name="SNF Org", owner=self.owner, members_private=True
        )
        self._seq = 0

    def _event(self, *, tournament: bool) -> Event:
        self._seq += 1
        event = Event.objects.create(
            organization=self.org,
            name=f"SNF Event {self._seq}",
            scheduled_at=timezone.now() + timedelta(days=3),
            created_by=self.owner,
        )
        if tournament:
            create_tournament_for_event(event)
        return event

    def _signup(self, event: Event, name: str) -> CustomUser:
        user = CustomUser.objects.create_user(
            username=name, password="x", discordNickname=f"{name}_global"
        )
        ensure_org_user(
            user,
            self.org,
            mmr=4000,
            guild_nickname=f"{name}_server",
            game_mmrs={GameType.DEADLOCK: 2000},
        )
        EventSignup.objects.create(event=event, user=user, status=SignupStatus.RSVP)
        return user

    def _list(self, event: Event, viewer: CustomUser | None) -> tuple[list[dict], int]:
        client = APIClient()
        if viewer is not None:
            client.force_authenticate(viewer)
        reset_queries()
        with CaptureQueriesContext(connection) as ctx:
            response = client.get(f"/api/events/signups/?event={event.pk}")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        rows = body["results"] if isinstance(body, dict) else body
        return rows, len(ctx.captured_queries)

    def test_member_viewer_sees_server_nickname(self) -> None:
        for tournament in (True, False):
            with self.subTest(tournament=tournament):
                event = self._event(tournament=tournament)
                self._signup(event, f"snf_seen_{tournament}")
                rows, _ = self._list(event, self.owner)
                data = rows[0]["user_data"]
                self.assertEqual(data["guildNickname"], f"snf_seen_{tournament}_server")
                self.assertEqual(
                    data["discordNickname"], f"snf_seen_{tournament}_global"
                )

    def test_anonymous_viewer_of_private_org_gets_no_server_nickname_or_mmr(
        self,
    ) -> None:
        for tournament in (True, False):
            with self.subTest(tournament=tournament):
                event = self._event(tournament=tournament)
                self._signup(event, f"snf_hidden_{tournament}")
                rows, _ = self._list(event, None)
                data = rows[0]["user_data"]
                self.assertIsNone(data.get("guildNickname"))
                self.assertNotIn("mmr", data)
                self.assertNotIn("mmr_game_type", data)
                self.assertNotIn("league_mmr", data)
                self.assertIsNone(rows[0]["org_user_game_mmrs"])
                self.assertNotEqual(rows[0]["suggested_mmr"], 4000)
                self.assertEqual(
                    data["discordNickname"], f"snf_hidden_{tournament}_global"
                )

    def test_query_count_does_not_grow_with_signups(self) -> None:
        for tournament in (True, False):
            with self.subTest(tournament=tournament):
                small = self._event(tournament=tournament)
                large = self._event(tournament=tournament)
                self._signup(small, f"snf_q1_{tournament}")
                for i in range(5):
                    self._signup(large, f"snf_q5_{tournament}_{i}")
                _, one = self._list(small, self.owner)
                _, five = self._list(large, self.owner)
                self.assertEqual(one, five)


class SignupAndCaptainNameTest(TestCase):
    def setUp(self) -> None:
        flush_run_cache()
        self.owner = CustomUser.objects.create_user(username="scn_owner", password="x")
        self.org = Organization.objects.create(
            name="SCN Org", owner=self.owner, members_private=True
        )
        self.event = Event.objects.create(
            organization=self.org,
            name="SCN Event",
            scheduled_at=timezone.now() + timedelta(days=3),
            created_by=self.owner,
        )
        self.dragon = self._member(
            "scn_dragon", global_name="Gwaihir", guild_nick="DragonClaw"
        )
        self.plain = self._member("scn_plain", global_name=None, guild_nick=None)
        self.sited = self._member("scn_sited", global_name="Windlord", guild_nick=None)
        self.sited.nickname = "SiteName"
        self.both = self._member(
            "scn_both", global_name="Landroval", guild_nick="Guildy"
        )
        self.both.nickname = "SiteBoth"
        self.steam = CustomUser.objects.create(username=None, steamid=76561198000099001)
        OrgUser.objects.create(user=self.steam, organization=self.org)
        self.users = [self.dragon, self.plain, self.sited, self.both, self.steam]
        for user in self.users:
            EventSignup.objects.create(
                event=self.event, user=user, status=SignupStatus.RSVP
            )
            EventTeam.objects.create(
                event=self.event, name=f"Team {user.pk}", captain=user
            )

    def _member(
        self, username: str, *, global_name: str | None, guild_nick: str | None
    ) -> CustomUser:
        user = CustomUser.objects.create_user(
            username=username, password="x", discordNickname=global_name
        )
        OrgUser.objects.create(
            user=user, organization=self.org, guild_nickname=guild_nick
        )
        return user

    def _rows(self, path: str, viewer: CustomUser | None) -> list[dict]:
        client = APIClient()
        if viewer is not None:
            client.force_authenticate(viewer)
        response = client.get(path)
        self.assertEqual(response.status_code, 200)
        body = response.json()
        return body["results"] if isinstance(body, dict) else body

    def _names(self, viewer: CustomUser | None) -> tuple[dict, dict]:
        signups = self._rows(f"/api/events/signups/?event={self.event.pk}", viewer)
        teams = self._rows(f"/api/events/teams/?event={self.event.pk}", viewer)
        return (
            {row["user"]: row["username"] for row in signups},
            {row["captain"]: row["captain_name"] for row in teams},
        )

    def test_member_viewer_sees_server_nickname(self) -> None:
        for names in self._names(self.owner):
            self.assertEqual(names[self.dragon.pk], "DragonClaw")
            self.assertEqual(names[self.plain.pk], "scn_plain")
            self.assertEqual(names[self.sited.pk], "Windlord")
            self.assertEqual(names[self.both.pk], "Guildy")
            self.assertEqual(names[self.steam.pk], f"User {self.steam.pk}")

    def test_anonymous_viewer_of_private_org_gets_global_chain(self) -> None:
        for names in self._names(None):
            self.assertEqual(names[self.dragon.pk], "Gwaihir")
            self.assertEqual(names[self.plain.pk], "scn_plain")
            self.assertEqual(names[self.sited.pk], "Windlord")
            self.assertEqual(names[self.both.pk], "Landroval")
            self.assertEqual(names[self.steam.pk], f"User {self.steam.pk}")

    @override_settings(INTERNAL_SERVICE_TOKEN="snf-internal-token")
    def test_internal_service_sees_server_nickname_for_bot_embeds(self) -> None:
        client = APIClient()
        client.credentials(HTTP_X_INTERNAL_TOKEN="snf-internal-token")
        response = client.get(f"/api/events/signups/?event={self.event.pk}")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        rows = body["results"] if isinstance(body, dict) else body
        by_user = {row["user"]: row for row in rows}
        self.assertEqual(by_user[self.dragon.pk]["username"], "DragonClaw")
        names = {
            row["user"]: EventSignupSchema.model_validate(row).display_name
            for row in rows
        }
        self.assertEqual(names[self.dragon.pk], "DragonClaw")
        self.assertEqual(names[self.plain.pk], "scn_plain")
        self.assertEqual(names[self.sited.pk], "Windlord")
        self.assertEqual(names[self.both.pk], "Guildy")
        self.assertEqual(names[self.steam.pk], f"User {self.steam.pk}")

    def test_team_list_query_count_does_not_grow_with_teams(self) -> None:
        small = Event.objects.create(
            organization=self.org,
            name="SCN Small",
            scheduled_at=timezone.now() + timedelta(days=3),
            created_by=self.owner,
        )
        EventTeam.objects.create(event=small, name="Solo", captain=self.dragon)
        client = APIClient()
        client.force_authenticate(self.owner)
        reset_queries()
        with CaptureQueriesContext(connection) as one:
            client.get(f"/api/events/teams/?event={small.pk}")
        reset_queries()
        with CaptureQueriesContext(connection) as three:
            client.get(f"/api/events/teams/?event={self.event.pk}")
        self.assertEqual(len(one.captured_queries), len(three.captured_queries))
