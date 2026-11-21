import json
from datetime import date
from typing import Any
from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.response import Response
from rest_framework.test import APIClient

from app.models import CustomUser, Game, League, Team, Tournament
from draft.models import DraftTeam, HeroDraft, HeroDraftChatMessage, HeroDraftState
from draft.serializers.hero import HeroDraftSerializer
from draft.serializers.hero_ssr import HeroDraftSerializerSSR
from draft.services.hero import build_draft_rounds, new_herodraft_for_game
from org.models import Organization

Channel = HeroDraftChatMessage.Channel
Kind = HeroDraftChatMessage.Kind

TEAM_SENTINEL = "leak-team-a-3f9e1c"
ALL_SENTINEL = "leak-all-7b20d4"
SUGGESTED_HERO = 74
PICKED_HERO = 1
INTERNAL_TOKEN = "leak-sweep-internal-token"


def _hero_ids(node: Any) -> list[Any]:
    found: list[Any] = []
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "hero_id":
                found.append(value)
            found.extend(_hero_ids(value))
    elif isinstance(node, list):
        for item in node:
            found.extend(_hero_ids(item))
    return found


class ChatRestLeakTest(TestCase):
    def setUp(self) -> None:
        patcher = patch(
            "draft.tasks.hero_tick.start_tick_broadcaster", return_value=True
        )
        self.addCleanup(patcher.stop)
        self.tick_start: MagicMock = patcher.start()

        def user(name: str) -> CustomUser:
            return CustomUser.objects.create_user(username=name, password="x")

        self.cap_a = user("leak_cap_a")
        self.mem_a = user("leak_mem_a")
        self.cap_b = user("leak_cap_b")
        self.mem_b = user("leak_mem_b")
        self.outsider = user("leak_outsider")
        self.staff = user("leak_league_staff")
        self.superuser = CustomUser.objects.create_superuser(
            username="leak_super", password="x"
        )

        org = Organization.objects.create(name="Leak Org")
        league = League.objects.create(name="Leak League", organization=org)
        league.staff.add(self.staff)
        tournament = Tournament.objects.create(
            name="Leak Tournament", date_played=date.today(), league=league
        )
        self.team_a = Team.objects.create(
            name="Leak A", tournament=tournament, captain=self.cap_a
        )
        self.team_b = Team.objects.create(
            name="Leak B", tournament=tournament, captain=self.cap_b
        )
        self.team_a.members.add(self.mem_a)
        self.team_b.members.add(self.mem_b)
        game = Game.objects.create(
            tournament=tournament, radiant_team=self.team_a, dire_team=self.team_b
        )
        self.draft: HeroDraft = new_herodraft_for_game(game)

        self.team_text = HeroDraftChatMessage.objects.create(
            draft=self.draft,
            channel=Channel.TEAM,
            team=self.team_a,
            sender=self.mem_a,
            kind=Kind.TEXT,
            body=TEAM_SENTINEL,
        )
        self.suggestion = HeroDraftChatMessage.objects.create(
            draft=self.draft,
            channel=Channel.TEAM,
            team=self.team_a,
            sender=self.mem_a,
            kind=Kind.SUGGEST_BAN,
            hero_id=SUGGESTED_HERO,
            body="",
        )
        self.all_text = HeroDraftChatMessage.objects.create(
            draft=self.draft,
            channel=Channel.ALL,
            team=None,
            sender=self.cap_b,
            kind=Kind.TEXT,
            body=ALL_SENTINEL,
        )

    def client_for(self, user: CustomUser | None) -> APIClient:
        client = APIClient()
        if user is not None:
            client.force_authenticate(user=user)
        return client

    def internal_client(self) -> APIClient:
        return APIClient(HTTP_X_INTERNAL_TOKEN=INTERNAL_TOKEN, REMOTE_ADDR="127.0.0.1")

    def assert_no_chat(self, response: Response, label: str) -> None:
        self.assertEqual(response.status_code, 200, f"{label}: {response.content!r}")
        text = response.content.decode()
        for needle in (
            TEAM_SENTINEL,
            ALL_SENTINEL,
            str(self.team_text.public_id),
            str(self.suggestion.public_id),
            str(self.all_text.public_id),
            Kind.SUGGEST_BAN.value,
            Kind.SUGGEST_PICK.value,
            "chat",
        ):
            self.assertNotIn(needle, text, label)
        self.assertNotIn(SUGGESTED_HERO, _hero_ids(json.loads(text)), label)

    def read_urls(self) -> dict[str, str]:
        pk = self.draft.pk
        return {
            "draft": f"/api/herodraft/{pk}/",
            "events": f"/api/herodraft/{pk}/list-events/",
            "available": f"/api/herodraft/{pk}/list-available-heroes/",
            "ssr": f"/api/herodraft/{pk}/ssr/",
        }

    def start_drafting(self, first: Team) -> None:
        teams = {dt.tournament_team_id: dt for dt in self.draft.draft_teams.all()}
        first_dt = teams[first.pk]
        second_dt = next(dt for dt in teams.values() if dt.pk != first_dt.pk)
        DraftTeam.objects.filter(pk=first_dt.pk).update(is_first_pick=True)
        DraftTeam.objects.filter(pk=second_dt.pk).update(is_first_pick=False)
        build_draft_rounds(self.draft, first_dt, second_dt)
        self.draft.rounds.filter(round_number=1).update(
            state="active", started_at=timezone.now()
        )
        HeroDraft.objects.filter(pk=self.draft.pk).update(state=HeroDraftState.DRAFTING)

    def test_t4_t5_read_endpoints_as_non_members(self) -> None:
        with override_settings(INTERNAL_SERVICE_TOKEN=INTERNAL_TOKEN):
            viewers: dict[str, APIClient] = {
                "outsider": self.client_for(self.outsider),
                "team_b_captain": self.client_for(self.cap_b),
                "league_staff": self.client_for(self.staff),
                "superuser": self.client_for(self.superuser),
                "internal": self.internal_client(),
            }
            for name, client in viewers.items():
                for key, url in self.read_urls().items():
                    response = client.get(url)
                    self.assert_no_chat(response, f"{name} {key}")
                    if key == "available":
                        self.assertIn(
                            SUGGESTED_HERO, response.json()["available_heroes"]
                        )

    def test_t4_internal_service_user_authenticates(self) -> None:
        with override_settings(INTERNAL_SERVICE_TOKEN=INTERNAL_TOKEN):
            response = self.internal_client().get(
                f"/api/herodraft/{self.draft.pk}/list-events/"
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.wsgi_request.user.username, "_internal_service")

    def test_t4_public_endpoints_as_anonymous(self) -> None:
        anonymous = self.client_for(None)
        for key in ("draft", "ssr"):
            self.assert_no_chat(
                anonymous.get(self.read_urls()[key]), f"anonymous {key}"
            )
        self.assert_no_chat(
            anonymous.get(f"/api/users/{self.mem_a.pk}/ssr/"), "anonymous sender ssr"
        )

    def test_t4_read_endpoints_as_team_a_still_chat_free(self) -> None:
        member = self.client_for(self.mem_a)
        for key, url in self.read_urls().items():
            self.assert_no_chat(member.get(url), f"team_a {key}")

    def test_t5_serializers_have_no_chat(self) -> None:
        draft = HeroDraft.objects.get(pk=self.draft.pk)
        for data in (
            HeroDraftSerializer(draft).data,
            HeroDraftSerializerSSR(draft).data,
        ):
            self.assertNotIn("chat", data)
            self.assertNotIn("chat_messages", data)
            self.assertNotIn(TEAM_SENTINEL, json.dumps(data, default=str))

    def test_t4_staff_pause_and_resume(self) -> None:
        self.start_drafting(self.team_a)
        staff = self.client_for(self.staff)
        pk = self.draft.pk
        self.assert_no_chat(staff.post(f"/api/herodraft/{pk}/pause/"), "pause")
        self.assert_no_chat(staff.post(f"/api/herodraft/{pk}/resume/"), "resume")

    def test_t4_staff_reset(self) -> None:
        self.start_drafting(self.team_a)
        response = self.client_for(self.staff).post(
            f"/api/herodraft/{self.draft.pk}/reset/"
        )
        self.assert_no_chat(response, "reset")

    def test_t4_staff_abandon(self) -> None:
        response = self.client_for(self.staff).post(
            f"/api/herodraft/{self.draft.pk}/abandon/"
        )
        self.assert_no_chat(response, "abandon")
        self.assertEqual(response.json()["state"], HeroDraftState.ABANDONED)

    def test_t4_other_captain_submit_pick(self) -> None:
        self.start_drafting(self.team_b)
        response = self.client_for(self.cap_b).post(
            f"/api/herodraft/{self.draft.pk}/submit-pick/",
            {"hero_id": PICKED_HERO},
        )
        self.assert_no_chat(response, "submit-pick")
        self.assertIn(PICKED_HERO, _hero_ids(response.json()))
