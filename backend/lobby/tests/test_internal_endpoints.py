from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from app.models import DotaLobbyMode
from discordbot.models import DiscordTournamentLog
from lobby import services, states
from lobby.models import GameLobby
from lobby.tests.helpers import (
    HEADERS,
    envelope,
    lobby_settings,
    lobby_view,
    make_game,
    make_tournament,
    make_user,
)

BASE = "/api/internal/lobbies"


@lobby_settings
class LobbyInternalApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.game = make_game()

    def post(self, path, data=None):
        with self.captureOnCommitCallbacks(execute=True):
            return self.client.post(
                f"{BASE}{path}", data or {}, format="json", **HEADERS
            )

    def get(self, path):
        return self.client.get(f"{BASE}{path}", **HEADERS)

    def claim(self, game=None, **data):
        game = game or self.game
        return self.post(f"/games/{game.pk}/claim/", {"trigger": "auto", **data})

    def test_requires_internal_token(self):
        resp = self.client.post(
            f"{BASE}/games/{self.game.pk}/claim/", {}, format="json"
        )
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(self.client.get(f"{BASE}/active/").status_code, 403)

    def test_claim_returns_body_with_password_once_stored_without(self):
        resp = self.claim()
        self.assertEqual(resp.status_code, 201)
        data = resp.json()
        row = GameLobby.objects.get(pk=data["game_lobby_id"])
        self.assertEqual(data["body"]["password"], row.password)
        self.assertEqual(row.password, self.game.tournament.dota_lobby_password)
        self.assertNotIn("password", row.request)
        self.assertEqual(data["external_ref"], f"game:{self.game.pk}")

        again = self.claim()
        self.assertEqual(again.status_code, 200)
        self.assertFalse(again.json()["created"])
        self.assertEqual(again.json()["body"], data["body"])
        self.assertEqual(GameLobby.objects.count(), 1)

    def test_claim_keeps_the_password_after_the_event_password_changes(self):
        # A retried create must stay byte-identical (dota_lobby replays it).
        data = self.claim().json()
        tournament = self.game.tournament
        tournament.dota_lobby_password = "changed-later"
        tournament.save()
        again = self.claim().json()
        self.assertEqual(again["body"], data["body"])
        self.assertNotEqual(again["body"]["password"], "changed-later")

    def test_claim_heals_a_tournament_without_password(self):
        from app.models import Tournament

        Tournament.objects.filter(pk=self.game.tournament_id).update(
            dota_lobby_password=""
        )
        data = self.claim().json()
        stored = Tournament.objects.get(pk=self.game.tournament_id)
        self.assertTrue(stored.dota_lobby_password)
        self.assertEqual(data["body"]["password"], stored.dota_lobby_password)

    def test_claim_with_body_leases_the_row(self):
        row_id = self.claim().json()["game_lobby_id"]
        row = GameLobby.objects.get(pk=row_id)
        lease = row.next_attempt_at - timezone.now()
        self.assertGreater(
            lease, timedelta(seconds=services.CREATE_ATTEMPT_LEASE_SECONDS - 5)
        )
        self.assertFalse(self.get("/active/").json()[0]["resend_due"])

    def test_claim_of_accepted_lobby_has_no_body(self):
        row = services.claim_lobby(self.game.pk).game_lobby
        row.lobby_id = "lob_1"
        row.state = states.WAITING
        row.save()
        data = self.claim().json()
        self.assertNotIn("body", data)
        self.assertEqual(data["lobby_id"], "lob_1")

    def test_claim_not_eligible(self):
        self.game.dire_team.members.add(make_user(steam=False))
        resp = self.claim()
        self.assertEqual(resp.status_code, 422)
        self.assertEqual(resp.json()["code"], "missing_steam_ids")
        self.assertFalse(GameLobby.objects.exists())

    def test_claim_unknown_game(self):
        self.assertEqual(self.post("/games/999999/claim/").status_code, 404)

    def test_accepted_strips_password_and_binds(self):
        row_id = self.claim().json()["game_lobby_id"]
        view = lobby_view(
            external_ref=f"game:{self.game.pk}",
            game_lobby_id=row_id,
            password="secret-pw",
            bot="bot1",
        )
        resp = self.post(f"/{row_id}/accepted/", {"lobby": view, "replayed": False})
        self.assertEqual(resp.json(), {"close": False})
        row = GameLobby.objects.get(pk=row_id)
        self.assertEqual(
            (row.lobby_id, row.state, row.bot), ("lob_1", "pending", "bot1")
        )
        self.assertIsNotNone(row.accepted_at)
        self.assertNotIn(
            "secret-pw", str(GameLobby.objects.filter(pk=row_id).values().get())
        )

    def test_accepted_after_local_end_asks_to_close(self):
        row_id = self.claim().json()["game_lobby_id"]
        services.end_locally(GameLobby.objects.get(pk=row_id), services.TEAMS_CHANGED)
        resp = self.post(
            f"/{row_id}/accepted/", {"lobby": lobby_view(game_lobby_id=row_id)}
        )
        self.assertEqual(resp.json(), {"close": True})
        row = GameLobby.objects.get(pk=row_id)
        self.assertEqual((row.lobby_id, row.state), ("lob_1", "closed"))

    def test_rejected_permanent_and_retryable(self):
        row_id = self.claim().json()["game_lobby_id"]
        self.post(f"/{row_id}/rejected/", {"code": "unavailable", "retryable": True})
        row = GameLobby.objects.get(pk=row_id)
        self.assertEqual((row.state, row.last_error_code), ("requested", "unavailable"))
        self.post(
            f"/{row_id}/rejected/",
            {"code": "league_not_held", "detail": "no bot", "retryable": False},
        )
        row.refresh_from_db()
        self.assertEqual(
            (row.state, row.ended, row.last_error_code),
            ("error", True, "league_not_held"),
        )

    def test_retryable_rejection_holds_resend_until_task_retry_is_due(self):
        row_id = self.claim().json()["game_lobby_id"]
        # Long past the create, but the task retries in 480 s.
        GameLobby.objects.filter(pk=row_id).update(
            created_at=timezone.now() - timedelta(minutes=20)
        )
        self.post(
            f"/{row_id}/rejected/",
            {"code": "unavailable", "retryable": True, "retry_in": 480},
        )
        row = GameLobby.objects.get(pk=row_id)
        wait = row.next_attempt_at - row.last_error_at
        self.assertEqual(
            wait.total_seconds(), 480 + services.CREATE_ATTEMPT_LEASE_SECONDS
        )
        self.assertFalse(self.get("/active/").json()[0]["resend_due"])

        GameLobby.objects.filter(pk=row_id).update(
            next_attempt_at=timezone.now() - timedelta(seconds=1)
        )
        self.assertTrue(self.get("/active/").json()[0]["resend_due"])

    def test_resend_due_without_attempt_counts_from_creation(self):
        row = services.claim_lobby(self.game.pk).game_lobby
        self.assertFalse(self.get("/active/").json()[0]["resend_due"])
        GameLobby.objects.filter(pk=row.pk).update(
            created_at=timezone.now() - timedelta(minutes=3)
        )
        self.assertTrue(self.get("/active/").json()[0]["resend_due"])
        GameLobby.objects.filter(pk=row.pk).update(lobby_id="lob_1")
        self.assertFalse(self.get("/active/").json()[0]["resend_due"])

    def test_conflict_actions(self):
        row_id = self.claim().json()["game_lobby_id"]
        ref = f"game:{self.game.pk}"
        # Our own lobby, whose 202 got lost.
        resp = self.post(
            f"/{row_id}/conflict/",
            {"lobby": lobby_view("lob_own", external_ref=ref, game_lobby_id=row_id)},
        )
        self.assertEqual(resp.json(), {"action": "adopt", "close": False})
        self.assertEqual(GameLobby.objects.get(pk=row_id).lobby_id, "lob_own")

    def test_conflict_with_earlier_lobby_of_game(self):
        old = services.claim_lobby(self.game.pk).game_lobby
        old.lobby_id = "lob_old"
        old.save()
        services.end_locally(old, services.TEAMS_CHANGED)
        row_id = self.post(
            f"/games/{self.game.pk}/claim/", {"trigger": "manual"}
        ).json()["game_lobby_id"]
        resp = self.post(
            f"/{row_id}/conflict/",
            {
                "lobby": lobby_view(
                    "lob_old", external_ref=old.external_ref, game_lobby_id=old.pk
                )
            },
        )
        self.assertEqual(resp.json(), {"action": "close_and_retry"})

    def test_conflict_with_foreign_lobby(self):
        row_id = self.claim().json()["game_lobby_id"]
        resp = self.post(
            f"/{row_id}/conflict/",
            {"lobby": lobby_view("lob_x", external_ref=f"game:{self.game.pk}")},
        )
        self.assertEqual(resp.json(), {"action": "reject"})
        row = GameLobby.objects.get(pk=row_id)
        self.assertEqual((row.state, row.last_error_code), ("error", "conflict"))

    def test_active_and_detail(self):
        row_id = self.claim().json()["game_lobby_id"]
        active = self.get("/active/").json()
        self.assertEqual([r["id"] for r in active], [row_id])
        self.assertEqual(active[0]["state"], "requested")
        self.assertFalse(active[0]["wants_flip"])
        self.assertEqual(self.get(f"/{row_id}/").json()["id"], row_id)

    def test_sync_applies_events_then_snapshot(self):
        row = services.claim_lobby(self.game.pk).game_lobby
        row.lobby_id = "lob_1"
        row.save()
        ref = row.external_ref
        events = [
            envelope(2, "lobby.player_joined", {"account_id": 5}, external_ref=ref),
            envelope(1, "lobby.created", {"league_verified": False}, external_ref=ref),
        ]
        view = lobby_view(external_ref=ref, state="waiting", seq=2)
        resp = self.post(f"/{row.pk}/sync/", {"lobby": view, "events": events})
        self.assertEqual(resp.json()["applied"], 2)
        row.refresh_from_db()
        self.assertEqual(
            (row.last_seq, row.state, row.league_verified), (2, "waiting", False)
        )
        self.assertIsNotNone(row.last_synced_at)

        # A snapshot behind the applied events is ignored.
        stale = lobby_view(external_ref=ref, state="pending", seq=1)
        self.post(f"/{row.pk}/sync/", {"lobby": stale})
        row.refresh_from_db()
        self.assertEqual(row.state, "waiting")

    def test_sync_rejects_other_lobby(self):
        row = services.claim_lobby(self.game.pk).game_lobby
        row.lobby_id = "lob_1"
        row.save()
        resp = self.post(f"/{row.pk}/sync/", {"lobby": lobby_view("lob_2")})
        self.assertEqual(resp.status_code, 409)

    def test_sync_missing_closes(self):
        row = services.claim_lobby(self.game.pk).game_lobby
        row.lobby_id = "lob_1"
        row.save()
        self.post(f"/{row.pk}/sync/", {"missing": True})
        row.refresh_from_db()
        self.assertEqual((row.state, row.state_reason), ("closed", "not_found"))

    def test_sync_missing_after_match_start_releases_game(self):
        row = services.claim_lobby(self.game.pk).game_lobby
        row.lobby_id = "lob_1"
        row.save()
        events = [
            envelope(
                1,
                "match.started",
                {"match_id": "8123456789"},
                external_ref=row.external_ref,
                state="in_game",
            )
        ]
        self.post(f"/{row.pk}/sync/", {"events": events})
        self.game.refresh_from_db()
        self.assertEqual(self.game.status, "live")

        self.post(f"/{row.pk}/sync/", {"missing": True})
        self.game.refresh_from_db()
        row.refresh_from_db()
        self.assertEqual(self.game.status, "pending")
        self.assertEqual((row.state, row.ended), ("closed", True))

    def test_eligible_games(self):
        make_game(make_tournament(dota_lobby_mode=DotaLobbyMode.OFF))
        self.assertEqual(self.get("/eligible-games/").json(), [{"id": self.game.pk}])
        services.claim_lobby(self.game.pk)
        self.assertEqual(self.get("/eligible-games/").json(), [])

    def test_notify_info_has_no_password(self):
        row = services.claim_lobby(self.game.pk).game_lobby
        data = self.get(f"/{row.pk}/notify/").json()
        self.assertEqual(len(data["recipients"]), 10)
        self.assertEqual({r["side"] for r in data["recipients"]}, {"radiant", "dire"})
        self.assertFalse(data["enabled"])
        self.assertTrue(row.password)
        self.assertNotIn(row.password, str(data))

    def test_lobby_info_notification_type(self):
        self.assertIn("lobby_info", DiscordTournamentLog.NotificationType.values)
