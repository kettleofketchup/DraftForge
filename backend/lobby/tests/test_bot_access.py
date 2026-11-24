import ast
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock

from django.test import SimpleTestCase, override_settings
from pydantic import ValidationError
from structlog.testing import capture_logs

from common.game import GameType
from league.models import League
from lobby.bot_access import base, schemas
from lobby.bot_access.base import BotAccessProvider, UnsupportedBotAccess
from lobby.bot_access.dota import (
    DotaBotAccess,
    bot_status,
    league_admin_link,
    steam_identity,
)
from lobby.bot_access.registry import get_bot_access, league_game_type
from lobby.bot_access.schemas import (
    BotAccessApi,
    BotAccessRow,
    BotAccessSnapshot,
    BotIdentity,
    PlatformLink,
)
from lobby.client import (
    DotaLobbyClient,
    DotaLobbyError,
    DotaLobbyNotConfigured,
    DotaLobbyUnavailable,
)
from lobby.schemas import (
    BotLeagueEntry,
    BotLeagues,
    BotLeaguesRefresh,
    BotView,
    LeagueBot,
    LeagueHolder,
    LeagueView,
)

SCHEMAS_PATH = Path(schemas.__file__)
ALLOWED_SCHEMA_IMPORTS = {"__future__", "datetime", "enum", "pydantic", "typing"}


class BotAccessContractTests(SimpleTestCase):
    def test_unsupported_satisfies_protocol(self) -> None:
        self.assertIsInstance(UnsupportedBotAccess(), BotAccessProvider)

    def test_unsupported_snapshot(self) -> None:
        provider = UnsupportedBotAccess()
        for snap in (provider.snapshot("1"), provider.refresh("1")):
            self.assertIs(snap.supported, False)
            self.assertEqual(snap.service.status, "unsupported")
            self.assertEqual(snap.bots, [])
            self.assertEqual(snap.provider, "unsupported")
            self.assertEqual(snap.held_count, 0)
            self.assertIsNone(snap.league_link)
        self.assertIsNone(provider.external_league_id(League(name="x")))

    def test_get_bot_access_unknown_falls_back_and_logs(self) -> None:
        with capture_logs() as logs:
            self.assertIsInstance(
                get_bot_access(GameType.DEADLOCK), UnsupportedBotAccess
            )
            self.assertIsInstance(get_bot_access(999), UnsupportedBotAccess)
        fallbacks = [e for e in logs if e["event"] == "bot_access_provider_fallback"]
        self.assertEqual([e["game_type"] for e in fallbacks], [GameType.DEADLOCK, 999])
        for entry in fallbacks:
            self.assertEqual(entry["log_level"], "info")
            self.assertEqual(entry["system"], "lobby")
            self.assertEqual(entry["subsystem"], "bot_access")

    def test_league_game_type_is_dota(self) -> None:
        self.assertEqual(league_game_type(League(name="x")), GameType.DOTA2)

    def test_profile_url_must_be_https(self) -> None:
        with self.assertRaises(ValidationError):
            BotIdentity(kind="steam", value="x", profile_url="http://a")
        with self.assertRaises(ValidationError):
            PlatformLink(kind="league_admin_portal", url="http://a")
        BotIdentity(kind="steam", value="x", profile_url="https://a")
        PlatformLink(kind="league_admin_portal", url="https://a")

    def test_generic_names_have_no_steam(self) -> None:
        modules: list[ModuleType] = [schemas, base]
        for module in modules:
            for name in vars(module):
                lowered = name.lower()
                self.assertNotIn("steam", lowered, f"{module.__name__}.{name}")
                self.assertNotIn("valve", lowered, f"{module.__name__}.{name}")

    def test_schemas_module_imports_only_pydantic_and_stdlib(self) -> None:
        tree = ast.parse(SCHEMAS_PATH.read_text())
        roots: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                roots.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                roots.add((node.module or "").split(".")[0])
        self.assertLessEqual(roots, ALLOWED_SCHEMA_IMPORTS)

    def test_schemas_module_is_django_free(self) -> None:
        code = (
            "import importlib.util, sys\n"
            f"spec = importlib.util.spec_from_file_location('s', {str(SCHEMAS_PATH)!r})\n"
            "mod = importlib.util.module_from_spec(spec)\n"
            "spec.loader.exec_module(mod)\n"
            "mod.BotAccessApi.model_json_schema(mode='serialization')\n"
            "assert 'django' not in sys.modules\n"
        )
        result = subprocess.run(
            [sys.executable, "-I", "-c", code], capture_output=True, text=True
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_defaults_required_in_json_schema(self) -> None:
        defs = BotAccessApi.model_json_schema(mode="serialization")["$defs"]
        row_required = set(defs["BotAccessRow"]["required"])
        self.assertLessEqual(
            {"access_note", "access_checked_at", "refresh"}, row_required
        )
        snapshot_required = set(defs["BotAccessSnapshot"]["required"])
        self.assertLessEqual({"league_link", "refresh_outcome"}, snapshot_required)
        self.assertLessEqual(
            {"code", "retryable"}, set(defs["ServiceState"]["required"])
        )

    def test_identity_kind_accepts_other(self) -> None:
        identity = BotIdentity(kind="riot", value="x", profile_url=None)
        self.assertEqual(identity.kind, "riot")


LEAGUE = "17940"
LEAGUE_ID = 17940
SID1 = "76561197960265729"
SID2 = "76561197960265730"
SID3 = "76561197960265731"
T0 = datetime(2026, 11, 1, 12, 0, tzinfo=UTC)
T1 = datetime(2026, 11, 2, 12, 0, tzinfo=UTC)

CONNECTING_STATES = (
    "connecting",
    "logging_on",
    "authenticating",
    "steam_online",
    "gc_hello",
    "gc_queued",
)
OFFLINE_STATES = (
    "disconnected",
    "backoff",
    "cooling_down",
    "needs_attention",
    "suspended",
    "stopped",
)


def bot(
    name: str,
    *,
    steam_id: str | None = SID1,
    state: str = "gc_ready",
    ready: bool | None = None,
    leagues: list[int] | None = None,
    lobby: str | None = None,
    lobby_stale: bool = False,
) -> BotView:
    return BotView.model_validate(
        {
            "name": name,
            "username": f"login_{name}",
            "state": state,
            "ready": state == "gc_ready" if ready is None else ready,
            "steam_id": steam_id,
            "leagues": leagues or [],
            "lobby": lobby,
            "lobby_stale": lobby_stale,
            "last_error_message": "secret detail",
        }
    )


def holder(
    name: str, source: str = "gc", *, refreshed_at: datetime | None = T0
) -> LeagueHolder:
    return LeagueHolder(
        bot=name,
        source=source,
        verified=source == "gc",
        refreshed_at=refreshed_at if source == "gc" else None,
    )


def league(
    holders: list[LeagueHolder] | None = None, stale: set[str] | None = None
) -> LeagueView:
    holders = holders or []
    return LeagueView(
        league_id=LEAGUE_ID,
        holders=holders,
        bots=[LeagueBot(name=h.bot, stale=h.bot in (stale or set())) for h in holders],
    )


def bot_leagues(
    ok_at: datetime | None = None, entries: list[BotLeagueEntry] | None = None
) -> BotLeagues:
    return BotLeagues(leagues=entries or [], refresh=BotLeaguesRefresh(ok_at=ok_at))


def entry(league_id: int, source: str = "gc", *, stale: bool = False) -> BotLeagueEntry:
    return BotLeagueEntry(
        league_id=league_id,
        source=source,
        verified=source == "gc",
        refreshed_at=T1 if source == "gc" else None,
        stale=stale,
    )


@override_settings(DOTA_LOBBY_ENABLED=True)
class DotaBotAccessSnapshotTests(SimpleTestCase):
    def setUp(self) -> None:
        self.now = [0.0]
        self.client = MagicMock(spec=DotaLobbyClient)
        self.client.timeout = 15
        self.client.list_bots.return_value = []
        self.client.get_league.return_value = league()
        self.client.get_bot_leagues.return_value = bot_leagues()
        self.factory = MagicMock(return_value=self.client)
        self.provider = DotaBotAccess(
            client_factory=self.factory, clock=lambda: self.now[0]
        )

    def run_snapshot(
        self, bots: list[BotView], view: LeagueView | Exception | None = None
    ) -> BotAccessSnapshot:
        self.client.list_bots.return_value = bots
        if isinstance(view, Exception):
            self.client.get_league.side_effect = view
        elif view is not None:
            self.client.get_league.return_value = view
        return self.provider.snapshot(LEAGUE)

    def only_row(self, snap: BotAccessSnapshot) -> BotAccessRow:
        self.assertEqual(snap.service.status, "ok")
        self.assertEqual(len(snap.bots), 1)
        return snap.bots[0]

    # ---- service state ----

    @override_settings(DOTA_LOBBY_ENABLED=False)
    def test_disabled(self) -> None:
        snap = self.provider.snapshot(LEAGUE)
        self.assertEqual(snap.service.status, "disabled")
        self.assertEqual(snap.bots, [])
        self.assertEqual(snap.provider, "dota2")
        self.assertEqual(snap.game_type, int(GameType.DOTA2))
        self.factory.assert_not_called()

    def test_not_configured(self) -> None:
        self.factory.side_effect = DotaLobbyNotConfigured()
        snap = self.provider.snapshot(LEAGUE)
        self.assertEqual(snap.service.status, "not_configured")
        self.assertEqual(snap.bots, [])

    def test_list_bots_unreachable_is_unavailable(self) -> None:
        self.client.list_bots.side_effect = DotaLobbyUnavailable("ConnectionError")
        with capture_logs() as logs:
            snap = self.provider.snapshot(LEAGUE)
        self.assertEqual(snap.service.status, "unavailable")
        self.assertEqual(snap.service.code, "unreachable")
        self.assertIs(snap.service.retryable, True)
        self.assertEqual(snap.bots, [])
        self.client.get_league.assert_not_called()
        failed = [e for e in logs if e["event"] == "bot_access_upstream_failed"]
        self.assertEqual(len(failed), 1)
        self.assertEqual(failed[0]["action"], "list_bots")
        self.assertEqual(failed[0]["log_level"], "warning")
        self.assertEqual(failed[0]["system"], "lobby")
        self.assertEqual(failed[0]["subsystem"], "bot_access")
        self.assertEqual(failed[0]["league_id"], LEAGUE_ID)

    def test_list_bots_retryable_status_is_unavailable(self) -> None:
        self.client.list_bots.side_effect = DotaLobbyError(
            "unavailable", status=503, retryable=True
        )
        snap = self.provider.snapshot(LEAGUE)
        self.assertEqual(snap.service.status, "unavailable")
        self.assertEqual(snap.service.code, "unavailable")

    def test_list_bots_non_retryable_is_error(self) -> None:
        self.client.list_bots.side_effect = DotaLobbyError("unauthorized", status=401)
        snap = self.provider.snapshot(LEAGUE)
        self.assertEqual(snap.service.status, "error")
        self.assertEqual(snap.service.code, "unauthorized")
        self.assertIs(snap.service.retryable, False)
        self.assertEqual(snap.bots, [])

    def test_ok_snapshot_fields(self) -> None:
        snap = self.run_snapshot([bot("sim_bot_1")], league([holder("sim_bot_1")]))
        self.assertIs(snap.supported, True)
        self.assertEqual(snap.provider, "dota2")
        self.assertEqual(snap.external_league_id, LEAGUE)
        self.assertEqual(snap.game_type, int(GameType.DOTA2))
        self.assertIsNone(snap.refresh_outcome)
        self.assertEqual(snap.held_count, 1)
        assert snap.league_link is not None
        self.assertEqual(
            snap.league_link.url, "https://www.dota2.com/league/17940/admins"
        )

    # ---- access matrix ----

    def test_verified_gc_holder(self) -> None:
        row = self.only_row(
            self.run_snapshot(
                [bot("sim_bot_1", leagues=[LEAGUE_ID])], league([holder("sim_bot_1")])
            )
        )
        self.assertEqual(row.access, "verified")
        self.assertIsNone(row.access_note)
        self.assertEqual(row.access_checked_at, T0)

    def test_verified_holder_skips_per_bot_call(self) -> None:
        self.run_snapshot([bot("sim_bot_1")], league([holder("sim_bot_1")]))
        self.client.get_bot_leagues.assert_not_called()

    def test_holder_name_match_ignores_case(self) -> None:
        row = self.only_row(
            self.run_snapshot([bot("Sim_Bot_1")], league([holder("sim_bot_1")]))
        )
        self.assertEqual(row.access, "verified")

    def test_stale_gc_holder_unverified_not_rechecked(self) -> None:
        row = self.only_row(
            self.run_snapshot(
                [bot("sim_bot_1")], league([holder("sim_bot_1")], stale={"sim_bot_1"})
            )
        )
        self.assertEqual(row.access, "unverified")
        self.assertEqual(row.access_note, "not_rechecked")
        self.client.get_bot_leagues.assert_not_called()

    def test_config_holder_ok_at_null_unverified(self) -> None:
        self.client.get_bot_leagues.return_value = bot_leagues(
            None, [entry(LEAGUE_ID, "config")]
        )
        snap = self.run_snapshot(
            [bot("sim_bot_1", leagues=[LEAGUE_ID])],
            league([holder("sim_bot_1", "config")]),
        )
        row = self.only_row(snap)
        self.assertEqual(row.access, "unverified")
        self.assertIsNone(row.access_note)
        self.assertIsNone(row.access_checked_at)
        self.assertEqual(snap.held_count, 1)

    def test_gc_ready_ok_at_null_not_configured_unknown(self) -> None:
        row = self.only_row(self.run_snapshot([bot("sim_bot_1")], league()))
        self.assertEqual(row.access, "unknown")

    def test_first_fetch_failed_unknown(self) -> None:
        row = self.only_row(
            self.run_snapshot([bot("sim_bot_1", state="gc_ready")], league())
        )
        self.assertEqual(row.access, "unknown")
        self.client.get_bot_leagues.assert_called_once()

    def test_gc_source_disabled_unknown(self) -> None:
        self.client.get_bot_leagues.return_value = bot_leagues(
            None, [entry(99, "config")]
        )
        row = self.only_row(
            self.run_snapshot([bot("sim_bot_1", leagues=[99])], league())
        )
        self.assertEqual(row.access, "unknown")

    def test_ok_at_set_absent_missing(self) -> None:
        self.client.get_bot_leagues.return_value = bot_leagues(T1, [entry(99)])
        row = self.only_row(self.run_snapshot([bot("sim_bot_1")], league()))
        self.assertEqual(row.access, "missing")
        self.assertIsNone(row.access_note)
        self.assertEqual(row.access_checked_at, T1)

    def test_ok_at_set_config_holder_missing_with_note(self) -> None:
        self.client.get_bot_leagues.return_value = bot_leagues(
            T1, [entry(LEAGUE_ID, "config")]
        )
        snap = self.run_snapshot(
            [bot("sim_bot_1", leagues=[LEAGUE_ID])],
            league([holder("sim_bot_1", "config")]),
        )
        row = self.only_row(snap)
        self.assertEqual(row.access, "missing")
        self.assertEqual(row.access_note, "allowed_unverified")
        self.assertEqual(snap.held_count, 0)

    def test_ok_at_set_config_entry_only_in_bot_list_gets_note(self) -> None:
        self.client.get_bot_leagues.return_value = bot_leagues(
            T1, [entry(LEAGUE_ID, "config")]
        )
        row = self.only_row(self.run_snapshot([bot("sim_bot_1")], league()))
        self.assertEqual(row.access, "missing")
        self.assertEqual(row.access_note, "allowed_unverified")

    def test_ok_at_set_not_holder_missing_no_note(self) -> None:
        self.client.get_bot_leagues.return_value = bot_leagues(T1)
        row = self.only_row(
            self.run_snapshot([bot("sim_bot_1")], league([holder("sim_bot_2")]))
        )
        self.assertEqual(row.access, "missing")
        self.assertIsNone(row.access_note)

    def test_ok_at_set_stale_gc_entries_unknown_not_rechecked(self) -> None:
        self.client.get_bot_leagues.return_value = bot_leagues(
            T1, [entry(99, stale=True)]
        )
        row = self.only_row(self.run_snapshot([bot("sim_bot_1")], league()))
        self.assertEqual(row.access, "unknown")
        self.assertEqual(row.access_note, "not_rechecked")

    def test_ok_at_set_gc_entry_present_verified(self) -> None:
        self.client.get_bot_leagues.return_value = bot_leagues(T1, [entry(LEAGUE_ID)])
        row = self.only_row(self.run_snapshot([bot("sim_bot_1")], league()))
        self.assertEqual(row.access, "verified")
        self.assertEqual(row.access_checked_at, T1)

    def test_per_bot_error_unknown(self) -> None:
        self.client.get_bot_leagues.side_effect = DotaLobbyUnavailable("ReadTimeout")
        with capture_logs() as logs:
            row = self.only_row(
                self.run_snapshot([bot("sim_bot_1", leagues=[LEAGUE_ID])], league())
            )
        self.assertEqual(row.access, "unknown")
        actions = [
            e["action"] for e in logs if e["event"] == "bot_access_upstream_failed"
        ]
        self.assertEqual(actions, ["get_bot_leagues"])
        self.assertNotIn("sim_bot_1", repr(logs))

    def test_per_bot_404_unknown(self) -> None:
        self.client.get_bot_leagues.side_effect = DotaLobbyError(
            "not_found", status=404
        )
        row = self.only_row(self.run_snapshot([bot("sim_bot_1")], league()))
        self.assertEqual(row.access, "unknown")

    def test_per_bot_budget_exhausted_unknown(self) -> None:
        def slow(name: str, *, timeout: float | None = None) -> BotLeagues:
            self.now[0] += 15
            return bot_leagues(T1)

        self.client.get_bot_leagues.side_effect = slow
        snap = self.run_snapshot(
            [bot("sim_bot_1", steam_id=SID1), bot("sim_bot_2", steam_id=SID2)],
            league(),
        )
        self.assertEqual([r.access for r in snap.bots], ["missing", "unknown"])
        self.assertEqual(self.client.get_bot_leagues.call_count, 1)

    def test_per_bot_timeout_is_remaining_budget(self) -> None:
        def slow(name: str, *, timeout: float | None = None) -> BotLeagues:
            self.now[0] += 10
            return bot_leagues(T1)

        self.client.get_bot_leagues.side_effect = slow
        self.run_snapshot(
            [bot("sim_bot_1", steam_id=SID1), bot("sim_bot_2", steam_id=SID2)],
            league(),
        )
        timeouts = [
            c.kwargs["timeout"] for c in self.client.get_bot_leagues.call_args_list
        ]
        self.assertEqual(len(timeouts), 2)
        self.assertLessEqual(timeouts[0], 15.0)
        self.assertLessEqual(timeouts[1], 5.0)
        self.assertGreaterEqual(timeouts[1], 1.0)

    def test_access_checked_at_sources(self) -> None:
        self.client.get_bot_leagues.return_value = bot_leagues(T1)
        snap = self.run_snapshot(
            [bot("sim_bot_1", steam_id=SID1), bot("sim_bot_2", steam_id=SID2)],
            league([holder("sim_bot_1", refreshed_at=T0)]),
        )
        self.assertEqual([r.access_checked_at for r in snap.bots], [T0, T1])

    # ---- league call failures ----

    def test_league_404_no_bot_lists_it_zero_holders(self) -> None:
        self.client.get_bot_leagues.return_value = bot_leagues(T1)
        snap = self.run_snapshot(
            [bot("sim_bot_1", leagues=[99])], DotaLobbyError("not_found", status=404)
        )
        row = self.only_row(snap)
        self.assertEqual(row.access, "missing")
        self.assertIsNone(row.status)
        self.assertEqual(snap.held_count, 0)

    def test_league_404_some_bot_lists_it_all_unknown(self) -> None:
        snap = self.run_snapshot(
            [
                bot("sim_bot_1", steam_id=SID1, leagues=[LEAGUE_ID]),
                bot("sim_bot_2", steam_id=SID2),
            ],
            DotaLobbyError("not_found", status=404),
        )
        self.assertEqual(snap.service.status, "ok")
        self.assertEqual([r.access for r in snap.bots], ["unknown", "unknown"])
        self.assertEqual(snap.bots[0].status, "available")
        self.assertIsNone(snap.bots[1].status)
        self.client.get_bot_leagues.assert_not_called()

    def test_league_call_error_degrades(self) -> None:
        with capture_logs() as logs:
            snap = self.run_snapshot(
                [
                    bot("sim_bot_1", steam_id=SID1, leagues=[LEAGUE_ID]),
                    bot("sim_bot_2", steam_id=SID2),
                ],
                DotaLobbyError("unavailable", status=503, retryable=True),
            )
        self.assertEqual(snap.service.status, "ok")
        self.assertEqual([r.access for r in snap.bots], ["unverified", "unknown"])
        self.assertEqual([r.access_checked_at for r in snap.bots], [None, None])
        self.assertEqual(snap.bots[0].status, "available")
        self.assertIsNone(snap.bots[1].status)
        self.assertEqual(snap.held_count, 1)
        self.client.get_bot_leagues.assert_not_called()
        failed = [e for e in logs if e["event"] == "bot_access_upstream_failed"]
        self.assertEqual([e["action"] for e in failed], ["get_league"])
        self.assertEqual(failed[0]["upstream_status"], 503)

    # ---- status ----

    def test_bot_status_mapping(self) -> None:
        cases: list[tuple[BotView, str]] = [
            (bot("b", lobby="L1"), "busy"),
            (bot("b"), "available"),
            (bot("b", lobby_stale=True), "connecting"),
            (bot("b", state="gc_ready", ready=False), "connecting"),
        ]
        cases += [(bot("b", state=s), "connecting") for s in CONNECTING_STATES]
        cases += [(bot("b", state=s), "offline") for s in OFFLINE_STATES]
        known = {"gc_ready", *CONNECTING_STATES, *OFFLINE_STATES}
        self.assertEqual(len(known), 13)
        for view, expected in cases:
            with self.subTest(state=view.state, ready=view.ready, lobby=view.lobby):
                self.assertEqual(bot_status(view), expected)

    def test_unknown_state_logs_once(self) -> None:
        bots = [
            bot("sim_bot_1", steam_id=SID1, state="brand_new"),
            bot("sim_bot_2", steam_id=SID2, state="brand_new"),
        ]
        with capture_logs() as logs:
            snap = self.run_snapshot(
                bots, league([holder("sim_bot_1"), holder("sim_bot_2")])
            )
        self.assertEqual([r.status for r in snap.bots], ["unknown", "unknown"])
        unknown = [e for e in logs if e["event"] == "bot_access_unknown_bot_state"]
        self.assertEqual(len(unknown), 1)
        self.assertEqual(unknown[0]["state"], "brand_new")
        self.assertEqual(unknown[0]["log_level"], "info")
        self.assertEqual(unknown[0]["subsystem"], "bot_access")

    def test_non_holder_status_withheld(self) -> None:
        self.client.get_bot_leagues.return_value = bot_leagues(T1)
        snap = self.run_snapshot(
            [
                bot("sim_bot_1", steam_id=SID1, lobby="L1"),
                bot("sim_bot_2", steam_id=SID2, lobby="L2"),
            ],
            league([holder("sim_bot_1")]),
        )
        self.assertEqual([r.status for r in snap.bots], ["busy", None])

    # ---- identity, link, order ----

    def test_identity_valid(self) -> None:
        identity = steam_identity(SID1)
        assert identity is not None
        self.assertEqual(identity.kind, "steam")
        self.assertEqual(identity.value, SID1)
        self.assertEqual(
            identity.profile_url,
            "https://steamcommunity.com/profiles/76561197960265729",
        )

    def test_identity_rejects(self) -> None:
        for value in (
            None,
            "",
            "abc",
            "7656119796026572",
            "765611979602657290",
            "76561190000000001",
            " 76561197960265729",
            "76561202255233024",
            "86561197960265729",
        ):
            with self.subTest(value=value):
                self.assertIsNone(steam_identity(value))

    def test_identity_lower_bound_inclusive(self) -> None:
        self.assertIsNotNone(steam_identity("76561197960265728"))

    def test_identity_accepts_full_account_id_range(self) -> None:
        for value in ("76561201960265729", "76561202255233023"):
            with self.subTest(value=value):
                self.assertIsNotNone(steam_identity(value))

    def test_identity_null_until_logon(self) -> None:
        row = self.only_row(
            self.run_snapshot(
                [bot("sim_bot_1", steam_id=None, state="disconnected")], league()
            )
        )
        self.assertIsNone(row.identity)
        self.client.get_bot_leagues.assert_called_once()

    def test_league_link(self) -> None:
        link = league_admin_link(17940)
        self.assertEqual(link.kind, "league_admin_portal")
        self.assertEqual(link.url, "https://www.dota2.com/league/17940/admins")

    def test_invalid_league_id_not_linked(self) -> None:
        for value in ("0", "-3", "abc"):
            with self.subTest(value=value):
                snap = self.provider.snapshot(value)
                self.assertEqual(snap.service.status, "league_not_linked")
                self.assertIsNone(snap.league_link)
        self.client.list_bots.assert_not_called()

    def test_order_and_positions(self) -> None:
        self.client.get_bot_leagues.return_value = bot_leagues(T1)
        snap = self.run_snapshot(
            [
                bot("sim_bot_a", steam_id=SID3),
                bot("sim_bot_b", steam_id=None),
                bot("sim_bot_c", steam_id=SID1),
            ],
            league(),
        )
        self.assertEqual([r.position for r in snap.bots], [1, 2, 3])
        self.assertEqual(
            [r.identity.value if r.identity else None for r in snap.bots],
            [SID1, SID3, None],
        )

    def test_no_upstream_names_in_dump(self) -> None:
        self.client.get_bot_leagues.return_value = bot_leagues(T1)
        snap = self.run_snapshot(
            [bot("sim_bot_1", steam_id=SID1), bot("sim_bot_2", steam_id=SID2)],
            league([holder("sim_bot_1")]),
        )
        dumped = json.dumps(snap.model_dump(mode="json"))
        self.assertNotIn("sim_bot_", dumped)
        self.assertNotIn("login_", dumped)
        self.assertNotIn("secret detail", dumped)

    def test_all_calls_single_attempt(self) -> None:
        self.run_snapshot([bot("sim_bot_1")], league())
        self.client.list_bots.assert_called_once_with()
        self.client.get_league.assert_called_once_with(LEAGUE_ID, retry=False)
        self.assertEqual(self.client.get_bot_leagues.call_count, 1)
        self.factory.assert_called_once_with()

    # ---- protocol / registry ----

    def test_external_league_id(self) -> None:
        self.assertEqual(
            self.provider.external_league_id(League(name="x", steam_league_id=17940)),
            "17940",
        )
        self.assertIsNone(self.provider.external_league_id(League(name="x")))

    def test_registry_dota(self) -> None:
        provider = get_bot_access(GameType.DOTA2)
        self.assertIsInstance(provider, DotaBotAccess)
        self.assertIsInstance(provider, BotAccessProvider)
        self.assertIs(provider.supported, True)
