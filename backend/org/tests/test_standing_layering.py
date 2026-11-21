import ast
from collections import deque
from collections.abc import Iterable, Iterator
from functools import cache
from pathlib import Path

from django.test import SimpleTestCase

BACKEND_DIR = Path(__file__).resolve().parents[2]
STANDING_DIR = BACKEND_DIR / "org" / "standing"
CONTRIBUTIONS_DIR = BACKEND_DIR / "org" / "contributions"

LEAVES = ("types", "errors", "cache", "periods", "kinds", "ledger", "scoring", "base")
DISPATCHERS = (
    "org.standing.api",
    "org.standing.registry",
    "org.contributions.adapter",
)
LEAF_FORBIDDEN = (
    *DISPATCHERS,
    "org.contributions.services",
    "org.contributions.queries",
)
EVENT_FLOWS = (
    "events.services",
    "events.views",
    "events.completion",
    "events.reopen",
    "events.admission",
    "events.eligibility",
)
PUBLIC_STANDING = ("org.standing.api", "org.standing.cache")
LEDGER_MODELS = frozenset({"ContributionEntry", "ContributionPointValue"})
SKIPPED_DIRS = frozenset({"tests", "migrations", "__pycache__"})


def _matches(name: str, prefix: str) -> bool:
    return name == prefix or name.startswith(f"{prefix}.")


def _matches_any(name: str, prefixes: Iterable[str]) -> bool:
    return any(_matches(name, prefix) for prefix in prefixes)


def _module_name(path: Path) -> str:
    parts = path.relative_to(BACKEND_DIR).with_suffix("").parts
    return ".".join(parts[:-1] if parts[-1] == "__init__" else parts)


def _is_package(path: Path) -> bool:
    return path.name == "__init__.py"


def _source_files() -> list[Path]:
    return sorted(
        path
        for path in BACKEND_DIR.rglob("*.py")
        if not SKIPPED_DIRS & set(path.relative_to(BACKEND_DIR).parts)
    )


@cache
def _modules() -> dict[str, Path]:
    return {_module_name(path): path for path in _source_files()}


def _resolve_from(path: Path, node: ast.ImportFrom) -> str:
    if not node.level:
        return node.module or ""
    package = _module_name(path).split(".")
    if not _is_package(path):
        package = package[:-1]
    base = package[: len(package) - (node.level - 1)]
    return ".".join([*base, *([node.module] if node.module else [])])


def _is_type_checking(node: ast.If) -> bool:
    test = node.test
    return (isinstance(test, ast.Name) and test.id == "TYPE_CHECKING") or (
        isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING"
    )


def _import_time_nodes(node: ast.AST) -> Iterator[ast.AST]:
    for child in ast.iter_child_nodes(node):
        if isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef | ast.Lambda):
            continue
        if isinstance(child, ast.If) and _is_type_checking(child):
            for branch in child.orelse:
                yield branch
                yield from _import_time_nodes(branch)
            continue
        yield child
        yield from _import_time_nodes(child)


def _imports(path: Path, *, import_time: bool = False) -> list[tuple[str, list[str]]]:
    tree = ast.parse(path.read_text(), filename=str(path))
    nodes = _import_time_nodes(tree) if import_time else ast.walk(tree)
    found: list[tuple[str, list[str]]] = []
    for node in nodes:
        if isinstance(node, ast.Import):
            found.extend((alias.name, []) for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            found.append((_resolve_from(path, node), [a.name for a in node.names]))
    return found


def _imported_modules(path: Path, *, import_time: bool = False) -> set[str]:
    names: set[str] = set()
    for module, members in _imports(path, import_time=import_time):
        names.add(module)
        names.update(f"{module}.{member}" for member in members if member != "*")
    return names


def _with_parents(name: str) -> list[str]:
    parts = name.split(".")
    return [".".join(parts[: i + 1]) for i in range(len(parts))]


@cache
def _graph() -> dict[str, frozenset[str]]:
    modules = _modules()
    graph: dict[str, frozenset[str]] = {}
    for name, path in modules.items():
        edges = {
            target
            for imported in _imported_modules(path, import_time=True)
            for target in _with_parents(imported)
            if target in modules and target != name
        }
        graph[name] = frozenset(edges)
    return graph


def _closure(start: str) -> set[str]:
    graph = _graph()
    seen = {start}
    queue = deque([start])
    while queue:
        for target in graph.get(queue.popleft(), frozenset()):
            if target not in seen:
                seen.add(target)
                queue.append(target)
    return seen


def _caller_files(package: str) -> list[Path]:
    skipped = SKIPPED_DIRS | {"management"}
    root = BACKEND_DIR / package
    return sorted(
        path
        for path in root.rglob("*.py")
        if not skipped & set(path.relative_to(root).parts)
    )


class StandingLayeringTest(SimpleTestCase):
    def test_init_is_empty(self) -> None:
        tree = ast.parse((STANDING_DIR / "__init__.py").read_text())
        self.assertEqual(tree.body, [])

    def test_leaves_never_import_dispatchers(self) -> None:
        for leaf in LEAVES:
            for name in _imported_modules(STANDING_DIR / f"{leaf}.py"):
                with self.subTest(leaf=leaf, imported=name):
                    self.assertFalse(
                        _matches_any(name, LEAF_FORBIDDEN), f"{leaf} imports {name}"
                    )

    def test_scoring_is_pure(self) -> None:
        for name in _imported_modules(STANDING_DIR / "scoring.py"):
            with self.subTest(imported=name):
                self.assertFalse(
                    _matches_any(name, ("org", "events", "app", "django")),
                    f"scoring imports {name}",
                )

    def test_adapters_avoid_event_flows(self) -> None:
        paths = [*CONTRIBUTIONS_DIR.glob("*.py"), *STANDING_DIR.glob("*.py")]
        for path in sorted(paths):
            for name in _imported_modules(path):
                with self.subTest(module=_module_name(path), imported=name):
                    self.assertFalse(
                        _matches_any(name, EVENT_FLOWS),
                        f"{_module_name(path)} imports {name}",
                    )

    def test_events_and_app_use_only_the_api(self) -> None:
        for package in ("events", "app"):
            for path in _caller_files(package):
                module = _module_name(path)
                for imported, members in _imports(path):
                    targets = [imported, *(f"{imported}.{m}" for m in members)]
                    with self.subTest(module=module, imported=imported):
                        self.assertFalse(
                            any(_matches(t, "org.contributions") for t in targets),
                            f"{module} imports {imported} {members}",
                        )
                        for target in targets:
                            if _matches(target, "org.standing") and target != (
                                "org.standing"
                            ):
                                self.assertTrue(
                                    _matches_any(target, PUBLIC_STANDING),
                                    f"{module} imports {target}",
                                )
                        if imported == "org.models":
                            self.assertFalse(
                                LEDGER_MODELS & set(members),
                                f"{module} imports {members} from org.models",
                            )

    def test_graph_resolves_known_edges(self) -> None:
        self.assertIn("org.standing.registry", _graph()["org.standing.api"])
        self.assertIn("org.contributions.adapter", _graph()["org.standing.registry"])

    def test_leaf_closure_never_reaches_dispatchers(self) -> None:
        for leaf in LEAVES:
            reached = _closure(f"org.standing.{leaf}")
            with self.subTest(leaf=leaf):
                self.assertFalse(
                    reached & set(DISPATCHERS),
                    f"org.standing.{leaf} reaches {sorted(reached & set(DISPATCHERS))}",
                )

    def test_registry_closure_avoids_event_flows(self) -> None:
        reached = _closure("org.standing.registry")
        bad = sorted(name for name in reached if _matches_any(name, EVENT_FLOWS))
        self.assertFalse(bad, f"org.standing.registry reaches {bad}")
