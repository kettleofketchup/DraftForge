import pathlib
import re
from collections.abc import Iterator

from django.conf import settings
from django.test import SimpleTestCase


class GameMmrCacheopsConfigTest(SimpleTestCase):
    def test_cacheops_lists_game_mmr(self) -> None:
        self.assertEqual(
            settings.CACHEOPS["org.orgusergamemmr"],
            {"ops": "all", "timeout": 3600},
        )


BACKEND_ROOT = pathlib.Path(__file__).resolve().parents[2]
_CACHED_AS = re.compile(r"\bcached_as\s*\(")


def _cached_as_args(text: str) -> Iterator[tuple[int, str]]:
    for match in _CACHED_AS.finditer(text):
        depth = 0
        for end in range(match.end() - 1, len(text)):
            if text[end] == "(":
                depth += 1
            elif text[end] == ")":
                depth -= 1
                if depth == 0:
                    break
        line = text.count("\n", 0, match.start()) + 1
        yield line, text[match.end() : end]


def _source_files() -> Iterator[pathlib.Path]:
    for path in BACKEND_ROOT.rglob("*.py"):
        parts = set(path.relative_to(BACKEND_ROOT).parts)
        if parts & {"migrations", "tests", ".venv", "node_modules"}:
            continue
        yield path


class GameMmrCachedAsGuardrailTest(SimpleTestCase):
    def test_cached_as_lists_game_mmr(self) -> None:
        offenders: list[str] = []
        seen = 0
        for path in _source_files():
            for line, args in _cached_as_args(path.read_text()):
                if re.search(r"\bOrgUser\b", args):
                    seen += 1
                    if "OrgUserGameMmr" not in args:
                        rel = path.relative_to(BACKEND_ROOT)
                        offenders.append(f"{rel}:{line}")
        self.assertGreater(seen, 0, "guardrail found no cached_as listing OrgUser")
        self.assertEqual(
            offenders, [], "cached_as lists OrgUser without OrgUserGameMmr"
        )

    def test_detail_payloads_with_org_mmr_list_game_mmr(self) -> None:
        views = BACKEND_ROOT / "tournament" / "views"
        for key, module in (
            ("team_detail:", "team.py"),
            ("tournament_detail_v2:", "tournament.py"),
        ):
            text = (views / module).read_text()
            block_start = text.index("@cached_as", text.index(key))
            args = next(_cached_as_args(text[block_start:]))[1]
            self.assertIn("OrgUserGameMmr", args, key)

    def test_mmr_module_has_no_event_defaults(self) -> None:
        source = (BACKEND_ROOT / "org" / "mmr.py").read_text()
        self.assertNotIn("OrgEventDefaults", source)
        self.assertNotIn("event_defaults", source)
