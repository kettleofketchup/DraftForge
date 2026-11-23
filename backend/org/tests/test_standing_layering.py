import ast
from collections import deque
from collections.abc import Iterable, Iterator
from functools import cache
from pathlib import Path

from django.test import SimpleTestCase

BACKEND_DIR = Path(__file__).resolve().parents[2]
STANDING_DIR = BACKEND_DIR / "org" / "standing"
CONTRIBUTIONS_DIR = BACKEND_DIR / "org" / "contributions"
CONDUCT_DIR = BACKEND_DIR / "org" / "conduct"
LEADERSHIP_DIR = BACKEND_DIR / "org" / "leadership"
LEADERSHIP_LEAF = "org.leadership.kinds"
CONDUCT_CHECK = "events.eligibility.checks.conduct"
CONDUCT_CHECK_IMPORTS = frozenset({"org.conduct.eligibility", "org.standing.cache"})
CONDUCT_CHECK_TARGET = "org.conduct.eligibility"
CONDUCT_MODELS = frozenset({"AttendanceOutcome", "OrgConductSettings"})
FEATURE_TOGGLE_CALLERS = ("views_features.py", "admin.py")

LEAVES = (
    "types",
    "errors",
    "cache",
    "periods",
    "kinds",
    "ledger",
    "scoring",
    "base",
    "restamp",
    "serializers",
)
DISPATCHERS = (
    "org.standing.api",
    "org.standing.registry",
    "org.contributions.adapter",
    "org.conduct.adapter",
    "org.leadership.adapter",
    "org.standing.views",
    "org.standing.urls",
)
LEAF_FORBIDDEN = (
    *DISPATCHERS,
    "org.contributions.services",
    "org.contributions.queries",
    "org.conduct",
    "org.leadership.adapter",
    "org.leadership.lifecycle",
    "org.leadership.reviews",
    "org.leadership.maintenance",
    "org.leadership.queries",
    "org.leadership.views",
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
RESTAMP = "org.standing.restamp"
RESTAMP_IMPORTER = "events.eligibility.store"
LEDGER_MODELS = frozenset({"ContributionEntry", "ContributionPointValue"})
LEADERSHIP_MODELS = frozenset(
    {"CaptainTrait", "EventCaptain", "CaptainReview", "CaptainTraitScore"}
)
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


def _module_all(path: Path) -> set[str]:
    for node in ast.parse(path.read_text()).body:
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "__all__" for t in node.targets
        ):
            return {ast.literal_eval(e) for e in node.value.elts}
    return set()


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

    def test_leaves_reach_only_the_leadership_kind_table(self) -> None:
        for leaf in LEAVES:
            for name in _imported_modules(STANDING_DIR / f"{leaf}.py"):
                if _matches(name, "org.leadership"):
                    with self.subTest(leaf=leaf, imported=name):
                        self.assertTrue(_matches(name, LEADERSHIP_LEAF), name)

    def test_registry_reaches_leadership_adapter(self) -> None:
        self.assertIn("org.leadership.adapter", _graph()["org.standing.registry"])

    def test_scoring_is_pure(self) -> None:
        for name in _imported_modules(STANDING_DIR / "scoring.py"):
            with self.subTest(imported=name):
                self.assertFalse(
                    _matches_any(name, ("org", "events", "app", "django")),
                    f"scoring imports {name}",
                )

    def test_adapters_avoid_event_flows(self) -> None:
        paths = [
            *CONTRIBUTIONS_DIR.glob("*.py"),
            *CONDUCT_DIR.glob("*.py"),
            *LEADERSHIP_DIR.glob("*.py"),
            *STANDING_DIR.glob("*.py"),
        ]
        for path in sorted(paths):
            for name in _imported_modules(path):
                with self.subTest(module=_module_name(path), imported=name):
                    self.assertFalse(
                        _matches_any(name, EVENT_FLOWS),
                        f"{_module_name(path)} imports {name}",
                    )

    def test_events_and_app_use_only_the_api(self) -> None:
        for package in ("events", "app", "tournament"):
            for path in _caller_files(package):
                module = _module_name(path)
                for imported, members in _imports(path):
                    targets = [imported, *(f"{imported}.{m}" for m in members)]
                    with self.subTest(module=module, imported=imported):
                        self.assertFalse(
                            any(
                                _matches(t, "org.contributions")
                                or _matches(t, "org.leadership")
                                or _matches(t, "org.models_leadership")
                                for t in targets
                            ),
                            f"{module} imports {imported} {members}",
                        )
                        for target in targets:
                            if _matches(target, RESTAMP):
                                self.assertEqual(module, RESTAMP_IMPORTER)
                            elif _matches(target, "org.standing") and target != (
                                "org.standing"
                            ):
                                self.assertTrue(
                                    _matches_any(target, PUBLIC_STANDING),
                                    f"{module} imports {target}",
                                )
                        if imported == "org.models":
                            self.assertFalse(
                                (LEDGER_MODELS | LEADERSHIP_MODELS) & set(members),
                                f"{module} imports {members} from org.models",
                            )

    def test_only_conduct_check_imports_conduct(self) -> None:
        paths = [
            *(
                path
                for package in ("events", "app", "tournament")
                for path in _caller_files(package)
            ),
            *(BACKEND_DIR / "org" / name for name in FEATURE_TOGGLE_CALLERS),
        ]
        for path in paths:
            module = _module_name(path)
            for imported, members in _imports(path):
                with self.subTest(module=module, imported=imported):
                    if _matches(imported, "org.conduct"):
                        self.assertEqual(
                            (module, imported), (CONDUCT_CHECK, CONDUCT_CHECK_TARGET)
                        )
                    if imported in ("org.models", "org.models_conduct"):
                        self.assertFalse(
                            CONDUCT_MODELS & set(members),
                            f"{module} imports {members} from {imported}",
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

    def test_conduct_check_imports_only_the_sanctioned_modules(self) -> None:
        path = BACKEND_DIR / "events" / "eligibility" / "checks" / "conduct.py"
        org_imports = {
            module
            for module, _ in _imports(path)
            if _matches(module, "org") or _matches(module, "app")
        }
        self.assertEqual(org_imports, CONDUCT_CHECK_IMPORTS)

    def test_api_never_imports_the_http_layer(self) -> None:
        for name in _imported_modules(STANDING_DIR / "api.py"):
            with self.subTest(imported=name):
                self.assertFalse(
                    _matches_any(name, ("org.standing.views", "org.standing.urls")),
                    f"api imports {name}",
                )

    def test_api_exports_payloads_not_serializers(self) -> None:
        exported = _module_all(STANDING_DIR / "api.py")
        self.assertIn("tracks_payload", exported)
        self.assertIn("ViewerRoles", exported)
        self.assertFalse({"track_info_data", "leaderboard_data"} & exported)

    def test_registry_reaches_conduct_adapter(self) -> None:
        self.assertIn("org.conduct.adapter", _graph()["org.standing.registry"])

    def test_finalize_and_reopen_register_the_restamp_slot(self) -> None:
        for module in ("events.completion", "events.reopen"):
            with self.subTest(module=module):
                self.assertIn(RESTAMP_IMPORTER, _graph()[module])
