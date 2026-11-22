from datetime import date, timedelta
from typing import Any
from unittest import mock
from uuid import uuid4

from django.conf import settings
from django.core.cache.backends.locmem import LocMemCache
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.response import Response
from rest_framework.test import APIClient
from structlog.testing import capture_logs

from app.models import CustomUser, Game, Team, Tournament
from discordbot.activity_auth import issue_activity_token
from discordbot.activity_intent import peek_intent, record_intent
from discordbot.activity_roles import draft_role
from discordbot.activity_views import ActivityViewsThrottle
from discordbot.models import DraftActivityInstance
from discordbot.tests.activity_helpers import ClearIntentsMixin
from draft.models import Draft, DraftTeam, HeroDraft, HeroDraftState, TeamDraftState
from league.models import League
from org.models import Organization

URL = "/api/discord/activity/drafts/"
VIEWS_URL = "/api/discord/activity/views/"


@override_settings(DISCORD_ACTIVITY_ENABLED=True)
class ActivityDraftsBase(ClearIntentsMixin, TestCase):
    def setUp(self) -> None:
        super().setUp()
        org = Organization.objects.create(name="Drafts Org")
        self.league = League.objects.create(name="Drafts League", organization=org)
        self.tournament = Tournament.objects.create(
            name="Kettle Cup", date_played=date.today(), league=self.league
        )
        self.captain = CustomUser.objects.create_user(
            username="d-captain", discordId="101"
        )
        self.player = CustomUser.objects.create_user(
            username="d-player", discordId="102"
        )
        self.staff = CustomUser.objects.create_user(username="d-staff", discordId="103")
        self.league.staff.add(self.staff)
        self.viewer = CustomUser.objects.create_user(
            username="d-viewer", discordId="777"
        )
        self.radiant = Team.objects.create(
            name="Radiant A", tournament=self.tournament, captain=self.captain
        )
        self.radiant.members.add(self.captain, self.player)
        self.dire = Team.objects.create(name="Dire B", tournament=self.tournament)
        self.team_draft = Draft.objects.create(tournament=self.tournament)
        self.hero = self.make_hero(round_=1)
        self.other_tournament = Tournament.objects.create(
            name="Other Cup", date_played=date.today()
        )
        self.foreign = HeroDraft.objects.create(
            game=Game.objects.create(tournament=self.other_tournament)
        )

    def make_hero(
        self,
        round_: int = 1,
        state: str = HeroDraftState.WAITING_FOR_CAPTAINS,
        updated_ago: timedelta | None = None,
        teams: tuple[Team, ...] | None = None,
    ) -> HeroDraft:
        game = Game.objects.create(
            tournament=self.tournament, round=round_, bracket_type="winners"
        )
        hero = HeroDraft.objects.create(game=game, state=state)
        for team in (self.radiant, self.dire) if teams is None else teams:
            DraftTeam.objects.create(draft=hero, tournament_team=team)
        if updated_ago is not None:
            HeroDraft.objects.filter(pk=hero.pk).update(
                updated_at=timezone.now() - updated_ago
            )
        return hero

    def token(
        self, user: CustomUser | None = None, anchor: HeroDraft | None = None
    ) -> str:
        instance, _ = DraftActivityInstance.objects.get_or_create(
            instance_id="drafts-instance",
            defaults={
                "guild_id": "1",
                "channel_id": "2",
                "draft": anchor or self.hero,
            },
        )
        return issue_activity_token(user or self.captain, instance)

    def get(self, user: CustomUser | None = None, token: str | None = None) -> Response:
        client = APIClient()
        client.credentials(
            HTTP_AUTHORIZATION=f"DraftActivity {token or self.token(user)}"
        )
        return client.get(URL)

    def hero_ids(self, response: Response) -> list[int]:
        return [entry["id"] for entry in response.data["hero_drafts"]]


class ActivityDraftsTests(ActivityDraftsBase):
    def test_lists_team_draft_live_and_recent_hero_drafts(self) -> None:
        stale_live = self.make_hero(
            state=HeroDraftState.DRAFTING, updated_ago=timedelta(hours=8)
        )
        recent = self.make_hero(
            state=HeroDraftState.COMPLETED, updated_ago=timedelta(hours=1)
        )
        old = self.make_hero(
            state=HeroDraftState.COMPLETED, updated_ago=timedelta(hours=4)
        )
        old_abandoned = self.make_hero(
            state=HeroDraftState.ABANDONED, updated_ago=timedelta(hours=4)
        )
        response = self.get()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.data["tournament"],
            {"id": self.tournament.pk, "name": "Kettle Cup"},
        )
        self.assertEqual(
            response.data["team_draft"],
            {
                "id": self.team_draft.pk,
                "state": "pending",
                "status": "waiting",
                "involves_me": True,
                "role": "captain",
            },
        )
        ids = self.hero_ids(response)
        self.assertCountEqual(ids, [self.hero.pk, stale_live.pk, recent.pk])
        for missing in (old.pk, old_abandoned.pk, self.foreign.pk):
            self.assertNotIn(missing, ids)
        entry = response.data["hero_drafts"][0]
        self.assertEqual(entry["id"], self.hero.pk)
        self.assertEqual(entry["game_id"], self.hero.game_id)
        self.assertEqual(entry["label"], "Winners Bracket R1 · Radiant A vs Dire B")
        self.assertEqual(entry["state"], "waiting_for_captains")
        self.assertIn("updated_at", entry)
        self.assertIsNone(response.data["launch_intent"])
        self.assertIsNone(response.data["notice"])
        self.assertEqual(response.data["site_url"], settings.SITE_URL)

    def test_no_team_draft_gives_null(self) -> None:
        self.team_draft.delete()
        response = self.get()
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.data["team_draft"])

    def test_status_mapping(self) -> None:
        expected_hero = {
            "waiting_for_captains": "waiting",
            "rolling": "waiting",
            "choosing": "waiting",
            "drafting": "drafting",
            "resuming": "drafting",
            "paused": "paused",
            "completed": "finished",
            "abandoned": "finished",
        }
        self.assertCountEqual(expected_hero, HeroDraftState.values)
        by_state = {
            state: self.make_hero(state=state).pk for state in HeroDraftState.values
        }
        token = self.token()
        response = self.get(token=token)
        statuses = {
            entry["id"]: (entry["state"], entry["status"])
            for entry in response.data["hero_drafts"]
        }
        for state, pk in by_state.items():
            self.assertEqual(statuses[pk], (state, expected_hero[state]))
        expected_team = {
            "pending": "waiting",
            "drafting": "drafting",
            "resuming": "drafting",
            "paused": "paused",
            "completed": "finished",
        }
        self.assertCountEqual(expected_team, TeamDraftState.values)
        for state, status in expected_team.items():
            with self.subTest(team_state=state):
                Draft.objects.filter(pk=self.team_draft.pk).update(state=state)
                team = self.get(token=token).data["team_draft"]
                self.assertEqual((team["state"], team["status"]), (state, status))

    def test_ordering_live_by_round_then_finished_recent_first(self) -> None:
        late_round = self.make_hero(round_=3, state=HeroDraftState.DRAFTING)
        early_round = self.make_hero(round_=1, state=HeroDraftState.PAUSED)
        middle = self.make_hero(round_=2)
        older_finished = self.make_hero(
            round_=1,
            state=HeroDraftState.COMPLETED,
            updated_ago=timedelta(hours=2),
        )
        newer_finished = self.make_hero(
            round_=1,
            state=HeroDraftState.ABANDONED,
            updated_ago=timedelta(minutes=10),
        )
        self.assertEqual(
            self.hero_ids(self.get()),
            [
                self.hero.pk,
                early_round.pk,
                middle.pk,
                late_round.pk,
                newer_finished.pk,
                older_finished.pk,
            ],
        )

    def test_involves_me_and_role(self) -> None:
        bench = Team.objects.create(name="Bench", tournament=self.tournament)
        unrelated = self.make_hero(teams=(bench,))
        expected = {
            self.captain: ("captain", True, "captain", False),
            self.player: ("player", True, "player", False),
            self.staff: ("staff", False, "staff", False),
            self.viewer: ("spectator", False, "spectator", False),
        }
        for user, (hero_role, hero_mine, team_role, unrelated_mine) in expected.items():
            with self.subTest(user=user.username):
                data = self.get(token=self.token(user)).data
                entries = {e["id"]: e for e in data["hero_drafts"]}
                self.assertEqual(entries[self.hero.pk]["role"], hero_role)
                self.assertEqual(entries[self.hero.pk]["involves_me"], hero_mine)
                self.assertEqual(entries[unrelated.pk]["involves_me"], unrelated_mine)
                self.assertEqual(data["team_draft"]["role"], team_role)
                self.assertEqual(data["team_draft"]["involves_me"], hero_mine)
                for pk, entry in entries.items():
                    self.assertEqual(entry["role"], draft_role(user, "hero", pk))
                self.assertEqual(
                    data["team_draft"]["role"],
                    draft_role(user, "team", self.team_draft.pk),
                )

    def test_query_count_does_not_grow_with_drafts(self) -> None:
        token = self.token()
        self.get(token=token)
        with CaptureQueriesContext(connection) as few:
            self.get(token=token)
        for round_ in range(2, 8):
            self.make_hero(round_=round_)
        with CaptureQueriesContext(connection) as many:
            response = self.get(token=token)
        self.assertEqual(len(response.data["hero_drafts"]), 7)
        self.assertEqual(len(many), len(few))

    def test_intent_peeked_not_consumed(self) -> None:
        other = self.make_hero(round_=2)
        intent_id = record_intent(
            "101",
            kind="hero",
            draft_id=other.pk,
            tournament_id=self.tournament.pk,
            guild_id="1",
            channel_id="2",
        )
        response = self.get()
        self.assertEqual(
            response.data["launch_intent"],
            {"intent_id": intent_id, "kind": "hero", "id": other.pk},
        )
        self.assertIsNone(response.data["notice"])
        peeked = peek_intent("101")
        assert peeked is not None
        self.assertEqual(peeked.intent_id, intent_id)
        self.assertEqual(self.get().data["launch_intent"]["intent_id"], intent_id)

    def test_intent_for_another_channel_is_ignored(self) -> None:
        record_intent(
            "101",
            kind="hero",
            draft_id=self.hero.pk,
            tournament_id=self.tournament.pk,
            guild_id="1",
            channel_id="9",
        )
        response = self.get()
        self.assertIsNone(response.data["launch_intent"])
        self.assertIsNone(response.data["notice"])
        self.assertIsNotNone(peek_intent("101"))

    def test_out_of_scope_intent_becomes_notice(self) -> None:
        intent_id = record_intent(
            "101",
            kind="hero",
            draft_id=self.foreign.pk,
            tournament_id=self.other_tournament.pk,
            guild_id="1",
            channel_id="2",
        )
        response = self.get()
        self.assertIsNone(response.data["launch_intent"])
        notice = response.data["notice"]
        self.assertEqual(notice["intent_id"], intent_id)
        self.assertEqual(notice["kind"], "hero")
        self.assertEqual(notice["draft_id"], self.foreign.pk)
        self.assertEqual(notice["tournament_name"], "Other Cup")
        self.assertTrue(notice["url"].endswith(f"/herodraft/{self.foreign.pk}"))
        self.assertIsNotNone(peek_intent("101"))

    def test_fallback_scope_returns_only_pinned_draft(self) -> None:
        loose = HeroDraft.objects.create(game=Game.objects.create())
        self.make_hero(round_=2)
        token = self.token(anchor=loose)
        response = self.get(token=token)
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.data["tournament"])
        self.assertIsNone(response.data["team_draft"])
        self.assertEqual(self.hero_ids(response), [loose.pk])
        entry = response.data["hero_drafts"][0]
        self.assertEqual(entry["role"], "spectator")
        self.assertFalse(entry["involves_me"])
        self.assertEqual(entry["status"], "waiting")

    def test_fallback_scope_lists_pinned_draft_even_when_old(self) -> None:
        loose = HeroDraft.objects.create(
            game=Game.objects.create(), state=HeroDraftState.COMPLETED
        )
        HeroDraft.objects.filter(pk=loose.pk).update(
            updated_at=timezone.now() - timedelta(hours=10)
        )
        response = self.get(token=self.token(anchor=loose))
        self.assertEqual(self.hero_ids(response), [loose.pk])

    def test_flag_off_with_header_401_disabled_and_without_header_403(self) -> None:
        token = self.token()
        with override_settings(DISCORD_ACTIVITY_ENABLED=False):
            response = self.get(token=token)
            self.assertEqual(response.status_code, 401)
            self.assertEqual(response["WWW-Authenticate"], "DraftActivity")
            self.assertEqual(response.data["code"], "activity_disabled")
            anonymous = APIClient().get(URL)
            self.assertEqual(anonymous.status_code, 403)
            self.assertNotIn("WWW-Authenticate", anonymous)
        anonymous = APIClient().get(URL)
        self.assertEqual(anonymous.status_code, 403)
        self.assertNotIn("WWW-Authenticate", anonymous)

    def test_website_session_is_not_an_activity_identity(self) -> None:
        client = APIClient()
        client.force_authenticate(self.captain)
        self.assertEqual(client.get(URL).status_code, 403)

    def test_no_store_header(self) -> None:
        response = self.get()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Cache-Control"], "no-store")


class ActivityViewsTests(ActivityDraftsBase):
    def setUp(self) -> None:
        super().setUp()
        self.throttle_cache = LocMemCache(f"activity-views-{uuid4().hex}", {})
        patcher = mock.patch.object(ActivityViewsThrottle, "cache", self.throttle_cache)
        patcher.start()
        self.addCleanup(patcher.stop)

    def post(self, body: dict[str, Any], token: str | None = None) -> Response:
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"DraftActivity {token or self.token()}")
        return client.post(VIEWS_URL, body, format="json")

    def post_logged(
        self, body: dict[str, Any], event: str
    ) -> tuple[Response, list[dict[str, Any]]]:
        token = self.token()
        with capture_logs() as logs:
            response = self.post(body, token=token)
        return response, [e for e in logs if e["event"] == event]

    def record(self, draft_id: int | None = None) -> str:
        intent_id = record_intent(
            "101",
            kind="hero",
            draft_id=draft_id or self.hero.pk,
            tournament_id=self.tournament.pk,
            guild_id="1",
            channel_id="2",
        )
        assert intent_id is not None
        return intent_id

    def test_view_change_logs_role_and_returns_204(self) -> None:
        response, events = self.post_logged(
            {
                "action": "view",
                "from": {"kind": "team", "id": self.team_draft.pk},
                "to": {"kind": "hero", "id": self.hero.pk},
                "trigger": "menu",
            },
            "activity_view_changed",
        )
        self.assertEqual(response.status_code, 204)
        self.assertEqual(len(events), 1)
        event = events[0]
        self.assertEqual(event["system"], "discord")
        self.assertEqual(event["subsystem"], "activity")
        self.assertEqual(event["from_kind"], "team")
        self.assertEqual(event["from_id"], self.team_draft.pk)
        self.assertEqual(event["to_kind"], "hero")
        self.assertEqual(event["to_id"], self.hero.pk)
        self.assertEqual(event["trigger"], "menu")
        self.assertEqual(event["role"], "captain")
        self.assertIsNone(event["intent_id"])
        self.assertFalse(event["intent_consumed"])
        self.assertEqual(event["user_id"], self.captain.pk)
        self.assertEqual(event["discord_user_id"], "101")
        self.assertEqual(event["instance_id"], "drafts-instance")
        self.assertEqual(event["guild_id"], "1")
        self.assertEqual(event["channel_id"], "2")
        self.assertEqual(event["tournament_id"], self.tournament.pk)

    def test_bracket_view_without_from_is_allowed(self) -> None:
        response, events = self.post_logged(
            {"action": "view", "to": {"kind": "bracket"}, "trigger": "initial"},
            "activity_view_changed",
        )
        self.assertEqual(response.status_code, 204)
        self.assertIsNone(events[0]["from_kind"])
        self.assertIsNone(events[0]["to_id"])
        self.assertIsNone(events[0]["role"])

    def test_intent_id_consumes_intent(self) -> None:
        intent_id = self.record()
        response, events = self.post_logged(
            {
                "action": "view",
                "to": {"kind": "hero", "id": self.hero.pk},
                "trigger": "launch_intent",
                "intent_id": intent_id,
            },
            "activity_view_changed",
        )
        self.assertEqual(response.status_code, 204)
        self.assertEqual(events[0]["intent_id"], intent_id)
        self.assertTrue(events[0]["intent_consumed"])
        self.assertIsNone(peek_intent("101"))

    def test_stale_intent_id_keeps_newer_intent(self) -> None:
        old = self.record()
        new = self.record()
        response, events = self.post_logged(
            {
                "action": "view",
                "to": {"kind": "hero", "id": self.hero.pk},
                "trigger": "launch_intent",
                "intent_id": old,
            },
            "activity_view_changed",
        )
        self.assertEqual(response.status_code, 204)
        self.assertFalse(events[0]["intent_consumed"])
        peeked = peek_intent("101")
        assert peeked is not None
        self.assertEqual(peeked.intent_id, new)

    def test_out_of_scope_target_is_403_coded(self) -> None:
        intent_id = self.record()
        for body in (
            {
                "action": "view",
                "to": {"kind": "hero", "id": self.foreign.pk},
                "trigger": "menu",
                "intent_id": intent_id,
            },
            {
                "action": "open_external",
                "view": {"kind": "hero", "id": self.foreign.pk},
            },
        ):
            with self.subTest(action=body["action"]):
                response, events = self.post_logged(body, "activity_auth_rejected")
                self.assertEqual(response.status_code, 403)
                self.assertEqual(response.data["code"], "activity_out_of_scope")
                self.assertIn("detail", response.data)
                self.assertEqual(len(events), 1)
                self.assertEqual(events[0]["surface"], "views")
                self.assertEqual(events[0]["reason"], "out_of_scope")
                self.assertEqual(events[0]["code"], "activity_out_of_scope")
                self.assertEqual(events[0]["kind"], "hero")
                self.assertEqual(events[0]["draft_id"], self.foreign.pk)
        self.assertIsNotNone(peek_intent("101"))

    def test_bad_shapes_are_400(self) -> None:
        hero = {"kind": "hero", "id": self.hero.pk}
        bodies = {
            "bracket_with_id": {
                "action": "view",
                "to": {"kind": "bracket", "id": 1},
                "trigger": "menu",
            },
            "hero_without_id": {
                "action": "view",
                "to": {"kind": "hero"},
                "trigger": "menu",
            },
            "zero_id": {
                "action": "view",
                "to": {"kind": "hero", "id": 0},
                "trigger": "menu",
            },
            "unknown_kind": {
                "action": "view",
                "to": {"kind": "lobby", "id": 1},
                "trigger": "menu",
            },
            "unknown_trigger": {"action": "view", "to": hero, "trigger": "teleport"},
            "missing_trigger": {"action": "view", "to": hero},
            "missing_to": {"action": "view", "trigger": "menu"},
            "long_intent": {
                "action": "view",
                "to": hero,
                "trigger": "launch_intent",
                "intent_id": "x" * 33,
            },
            "bad_from": {
                "action": "view",
                "from": {"kind": "bracket", "id": 3},
                "to": hero,
                "trigger": "menu",
            },
            "unknown_action": {"action": "teleport"},
            "declined_without_intent": {"action": "intent_declined"},
            "open_external_without_view": {"action": "open_external"},
        }
        token = self.token()
        for name, body in bodies.items():
            with self.subTest(name=name):
                self.assertEqual(self.post(body, token=token).status_code, 400)

    def test_notice_seen_consumes(self) -> None:
        intent_id = self.record(self.foreign.pk)
        response, events = self.post_logged(
            {"action": "notice_seen", "intent_id": intent_id}, "activity_notice_seen"
        )
        self.assertEqual(response.status_code, 204)
        self.assertEqual(events[0]["intent_id"], intent_id)
        self.assertTrue(events[0]["intent_consumed"])
        self.assertIsNone(peek_intent("101"))

    def test_intent_declined_consumes_and_logs(self) -> None:
        intent_id = self.record()
        response, events = self.post_logged(
            {
                "action": "intent_declined",
                "intent_id": intent_id,
                "view": {"kind": "team", "id": self.team_draft.pk},
            },
            "activity_intent_declined",
        )
        self.assertEqual(response.status_code, 204)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["intent_id"], intent_id)
        self.assertTrue(events[0]["intent_consumed"])
        self.assertEqual(events[0]["kind"], "team")
        self.assertEqual(events[0]["draft_id"], self.team_draft.pk)
        self.assertIsNone(peek_intent("101"))

    def test_open_external_logs_server_derived_path(self) -> None:
        cases = (
            ({"kind": "hero", "id": self.hero.pk}, f"/herodraft/{self.hero.pk}"),
            (
                {"kind": "team", "id": self.team_draft.pk},
                f"/tournament/{self.tournament.pk}/teams/draft",
            ),
            ({"kind": "bracket"}, f"/tournament/{self.tournament.pk}/bracket"),
        )
        for view, path in cases:
            with self.subTest(kind=view["kind"]):
                response, events = self.post_logged(
                    {"action": "open_external", "view": view, "path": "/evil"},
                    "activity_open_external",
                )
                self.assertEqual(response.status_code, 204)
                self.assertEqual(events[0]["path"], path)
                self.assertEqual(events[0]["view_kind"], view["kind"])
                self.assertEqual(events[0]["view_id"], view.get("id"))

    def test_website_session_is_rejected(self) -> None:
        client = APIClient()
        client.force_authenticate(self.captain)
        response = client.post(
            VIEWS_URL,
            {"action": "view", "to": {"kind": "bracket"}, "trigger": "menu"},
            format="json",
        )
        self.assertEqual(response.status_code, 403)

    def test_throttled_after_60_per_minute(self) -> None:
        token = self.token()
        body = {"action": "view", "to": {"kind": "bracket"}, "trigger": "menu"}
        for _ in range(60):
            self.assertEqual(self.post(body, token=token).status_code, 204)
        self.assertEqual(self.post(body, token=token).status_code, 429)
