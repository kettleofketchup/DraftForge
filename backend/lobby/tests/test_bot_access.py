import ast
import subprocess
import sys
from pathlib import Path
from types import ModuleType

from django.test import SimpleTestCase
from pydantic import ValidationError
from structlog.testing import capture_logs

from common.game import GameType
from league.models import League
from lobby.bot_access import base, schemas
from lobby.bot_access.base import BotAccessProvider, UnsupportedBotAccess
from lobby.bot_access.registry import get_bot_access, league_game_type
from lobby.bot_access.schemas import BotAccessApi, BotIdentity, PlatformLink

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
