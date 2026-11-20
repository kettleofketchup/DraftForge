import ast
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

ROOT = Path(settings.BASE_DIR)
LEAVES = ("base", "types", "cache", "errors", "scoring", "periods", "kinds", "ledger")
DISPATCH = ("org.standing.api", "org.standing.registry")
ADAPTER_FORBIDDEN = (
    "events.services",
    "events.views",
    "events.completion",
    "events.reopen",
    "events.admission",
    "events.eligibility.evaluate",
    "events.eligibility.store",
)
PUBLIC = ("org.standing.api", "org.standing.cache")


def imports(path: Path) -> set[str]:
    found: set[str] = set()
    for node in ast.parse(path.read_text()).body:
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
            found.update(f"{node.module}.{alias.name}" for alias in node.names)
    return found


def module_path(module: str) -> Path | None:
    base = ROOT.joinpath(*module.split("."))
    for candidate in (base.with_suffix(".py"), base / "__init__.py"):
        if candidate.exists():
            return candidate
    return None


def closure(module: str) -> set[str]:
    seen: set[str] = set()
    stack = [module]
    while stack:
        current = stack.pop()
        if current in seen:
            continue
        seen.add(current)
        path = module_path(current)
        if path is None:
            continue
        stack.extend(
            name
            for name in imports(path)
            if name.split(".")[0] in {"org", "events", "app"}
        )
    return seen


def non_test_files(package: str) -> list[Path]:
    return [
        p
        for p in (ROOT / package).rglob("*.py")
        if "tests" not in p.parts and "migrations" not in p.parts
    ]


class StandingLayeringTest(SimpleTestCase):
    def test_init_is_empty(self) -> None:
        self.assertEqual((ROOT / "org/standing/__init__.py").read_text().strip(), "")

    def test_leaves_never_reach_dispatch_or_adapters(self) -> None:
        for leaf in LEAVES:
            reached = closure(f"org.standing.{leaf}")
            with self.subTest(leaf=leaf):
                self.assertFalse(
                    {m for m in reached if m in DISPATCH or m.endswith(".adapter")},
                    reached,
                )

    def test_scoring_is_pure(self) -> None:
        names = imports(ROOT / "org/standing/scoring.py")
        self.assertFalse(
            {n for n in names if n.split(".")[0] in {"org", "events", "app", "django"}}
        )

    def test_adapters_avoid_event_services(self) -> None:
        reached = closure("org.standing.registry")
        self.assertFalse(
            {m for m in reached if m.startswith(ADAPTER_FORBIDDEN)}, sorted(reached)
        )

    def test_app_and_events_use_only_public_surface(self) -> None:
        for package in ("app", "events"):
            for path in non_test_files(package):
                for name in imports(path):
                    with self.subTest(path=str(path), name=name):
                        if name.startswith("org.standing"):
                            self.assertTrue(
                                name.startswith(PUBLIC) or name == "org.standing",
                                name,
                            )
                        self.assertFalse(name.startswith("org.contributions"), name)
