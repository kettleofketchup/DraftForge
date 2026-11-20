import ast
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from django.apps import apps
from django.conf import settings
from django.test import SimpleTestCase

from config.installed_apps import MODEL_APPS


@dataclass(frozen=True)
class MovedSlice:
    name: str
    source_app: str
    new_app: str
    moved: frozenset[tuple[str, str]]
    retired_modules: frozenset[str]
    model_labels: frozenset[str]


HERO_DRAFT = MovedSlice(
    name="hero-draft",
    source_app="app",
    new_app="draft",
    moved=frozenset(
        {
            ("app.models", "HeroDraftState"),
            ("app.models", "HeroDraft"),
            ("app.models", "DraftTeam"),
            ("app.models", "HeroDraftRound"),
            ("app.models", "HeroDraftEvent"),
            ("app.consumers", "HeroDraftConsumer"),
            ("app.broadcast", "broadcast_herodraft_event"),
            ("app.broadcast", "broadcast_herodraft_state"),
            ("app.draft_state", "herodraft_state_queryset"),
            ("app.serializers", "HeroDraftRoundSerializerFull"),
            ("app.serializers", "DraftTeamSerializerFull"),
            ("app.serializers", "HERODRAFT_GUILD_NICKNAMES"),
            ("app.serializers", "HeroDraftUserSerializer"),
            ("app.serializers", "HeroDraftTeamSerializer"),
            ("app.serializers", "HeroDraftEventSerializer"),
            ("app.serializers", "HeroDraftSerializer"),
            ("app.serializers", "HeroDraftTickSerializer"),
            ("app.serializers_ssr", "HeroDraftSerializerSSR"),
            ("app.views.ssr", "HeroDraftSSRView"),
            ("app.views.internal", "list_auto_herodraft_games"),
            ("app.views.internal", "create_herodraft_for_game"),
            ("app.admin", "HeroDraftEventInline"),
            ("app.admin", "HeroDraftAdmin"),
            ("app.admin", "HeroDraftEventAdmin"),
            ("app.signals", "reset_herodraft_on_team_change"),
            ("app.signals", "_broadcast_draft_event"),
            ("app.consumers", "broadcast_herodraft_state"),
            ("app.consumers", "herodraft_state_queryset"),
            ("app.consumers", "HeroDraftSerializer"),
            ("app.broadcast", "herodraft_state_queryset"),
            ("app.views.internal", "new_herodraft_for_game"),
        }
    ),
    retired_modules=frozenset(
        {
            "app.functions.herodraft",
            "app.functions.herodraft_views",
            "app.tasks.herodraft_tick",
        }
    ),
    model_labels=frozenset(
        {"herodraft", "draftteam", "herodraftround", "herodraftevent"}
    ),
)

MOVED_SLICES: tuple[MovedSlice, ...] = (HERO_DRAFT,)

# target app -> production file (relative to backend/) -> names it may import from that app
ALLOWED_BACK_EDGES: dict[str, dict[str, frozenset[str]]] = {
    "draft": {
        "app/draft_state.py": frozenset({"HeroDraft"}),
        "app/permissions_org.py": frozenset({"HeroDraft"}),
        "app/services/draft_reset.py": frozenset({"delete_team_chat"}),
        "app/services/team_management.py": frozenset(
            {
                "DraftTeam",
                "HeroDraft",
                "HeroDraftState",
                "apply_captain_tenure",
                "broadcast_herodraft_state",
            }
        ),
        "app/services/team_references.py": frozenset({"DraftTeam", "HeroDraft"}),
        "app/views/bracket.py": frozenset({"HeroDraft"}),
        "app/views_main.py": frozenset({"DraftTeam"}),
    },
}

GUARD_FILE = "tests/test_app_boundaries.py"


def _module_of(path: str) -> str:
    parts = Path(path).with_suffix("").parts
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _package_of(path: str) -> str:
    module = _module_of(path)
    if Path(path).name == "__init__.py":
        return module
    return module.rpartition(".")[0]


def _resolve(node: ast.ImportFrom, path: str) -> str:
    if node.level == 0:
        return node.module or ""
    package = _package_of(path).split(".")
    base = package[: len(package) - (node.level - 1)] if node.level > 1 else package
    return ".".join([*base, node.module] if node.module else base)


def _within(name: str, prefix: str) -> bool:
    return name == prefix or name.startswith(f"{prefix}.")


def _is_test_module(path: str) -> bool:
    p = Path(path)
    return "tests" in p.parts or p.name.startswith("test_")


def _top_level_names(tree: ast.Module) -> Iterator[tuple[str, int]]:
    for node in tree.body:
        if isinstance(node, ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            yield node.name, node.lineno
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    yield target.id, node.lineno
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            yield node.target.id, node.lineno


def _imported(tree: ast.Module, path: str) -> Iterator[tuple[str, str | None, int]]:
    """Yield (module, imported name or None for plain import, line)."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name, None, node.lineno
        elif isinstance(node, ast.ImportFrom):
            module = _resolve(node, path)
            for alias in node.names:
                yield module, alias.name, node.lineno


def collect_back_edges(
    source: str, path: str, slices: tuple[MovedSlice, ...] = MOVED_SLICES
) -> dict[str, set[str]]:
    edges: dict[str, set[str]] = {}
    if _is_test_module(path):
        return edges
    tree = ast.parse(source, filename=path)
    for s in slices:
        if not _within(_module_of(path), s.source_app):
            continue
        for module, name, _line in _imported(tree, path):
            if _within(module, s.new_app):
                edges.setdefault(s.new_app, set()).add(name or module)
    return edges


def find_violations(
    source: str,
    path: str,
    slices: tuple[MovedSlice, ...] = MOVED_SLICES,
    back_edges: dict[str, dict[str, frozenset[str]]] = ALLOWED_BACK_EDGES,
) -> list[str]:
    tree = ast.parse(source, filename=path)
    module_name = _module_of(path)
    found: list[str] = []
    for s in slices:
        re_exports = {
            (_module_of(file), name)
            for file, names in back_edges.get(s.new_app, {}).items()
            if file != path
            for name in names
        }
        forbidden = s.moved | re_exports
        moved_here = {name for old, name in s.moved if old == module_name}
        for name, line in _top_level_names(tree):
            if name in moved_here:
                found.append(
                    f"{path}:{line}: [{s.name}] {name} redefined in {module_name}"
                )

        for module, name, line in _imported(tree, path):
            full = f"{module}.{name}" if name else module
            if name and (module, name) in forbidden:
                found.append(f"{path}:{line}: [{s.name}] imports {name} via {module}")
            if any(_within(module, r) or _within(full, r) for r in s.retired_modules):
                found.append(f"{path}:{line}: [{s.name}] imports retired module {full}")

        lazy_labels = {f"{s.source_app}.{label}" for label in s.model_labels}
        prefixes = [f"{old}.{name}" for old, name in s.moved] + sorted(
            s.retired_modules
        )
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Constant) and isinstance(node.value, str)):
                continue
            value = node.value
            if value.casefold() in lazy_labels:
                found.append(
                    f"{path}:{node.lineno}: [{s.name}] lazy model label {value!r}"
                )
            elif any(_within(value, p) for p in prefixes):
                found.append(
                    f"{path}:{node.lineno}: [{s.name}] string back-door {value!r}"
                )

    for new_app, names in collect_back_edges(source, path, slices).items():
        allowed = back_edges.get(new_app, {}).get(path)
        if allowed is None:
            found.append(
                f"{path}: imports {sorted(names)} from {new_app}; not in ALLOWED_BACK_EDGES"
            )
            continue
        for name in sorted(names - allowed):
            found.append(
                f"{path}: imports {name} from {new_app}; not listed in ALLOWED_BACK_EDGES"
            )
    return found


def find_stale_back_edges(
    observed: dict[str, dict[str, set[str]]],
    back_edges: dict[str, dict[str, frozenset[str]]] = ALLOWED_BACK_EDGES,
) -> list[str]:
    stale: list[str] = []
    for new_app, files in back_edges.items():
        for path, names in files.items():
            unused = names - observed.get(new_app, {}).get(path, set())
            stale.extend(
                f"{path}: ALLOWED_BACK_EDGES[{new_app!r}] lists {name}, no longer imported"
                for name in sorted(unused)
            )
    return stale


def _python_files(base: Path) -> Iterator[tuple[Path, str]]:
    for file in sorted(base.rglob("*.py")):
        rel = file.relative_to(base).as_posix()
        if "migrations" in Path(rel).parts or rel == GUARD_FILE:
            continue
        yield file, rel


SMALL_EDGES: dict[str, dict[str, frozenset[str]]] = {
    "draft": {"app/draft_state.py": frozenset({"HeroDraft"})},
}


class GuardSelfTests(SimpleTestCase):
    def assertFlagged(self, source: str, path: str, **kwargs: object) -> None:
        self.assertNotEqual(find_violations(source, path, **kwargs), [], source)

    def assertClean(self, source: str, path: str, **kwargs: object) -> None:
        self.assertEqual(find_violations(source, path, **kwargs), [], source)

    def test_redefinition_in_old_module(self) -> None:
        self.assertFlagged("class HeroDraft:\n    pass\n", "app/models.py")
        self.assertFlagged(
            "def _broadcast_draft_event():\n    pass\n", "app/signals.py"
        )
        self.assertFlagged("HERODRAFT_GUILD_NICKNAMES = {}\n", "app/serializers.py")
        self.assertClean("class Game:\n    pass\n", "app/models.py")
        self.assertClean("class HeroDraft:\n    pass\n", "draft/models/hero.py")

    def test_absolute_import_through_old_module(self) -> None:
        self.assertFlagged("from app.models import HeroDraft\n", "app/views_main.py")
        self.assertClean("from draft.models import HeroDraft\n", "draft/views/hero.py")
        self.assertClean("from app.models import Game\n", "app/views_main.py")

    def test_relative_import_through_old_module(self) -> None:
        self.assertFlagged("from .models import HeroDraft\n", "app/views_main.py")
        self.assertFlagged("from ..models import DraftTeam\n", "app/views/foo.py")
        self.assertFlagged(
            "from .internal import create_herodraft_for_game\n", "app/views/__init__.py"
        )
        self.assertClean("from .models import Game\n", "app/views_main.py")

    def test_retired_module_import(self) -> None:
        self.assertFlagged("import app.tasks.herodraft_tick\n", "tests/test_x.py")
        self.assertFlagged("from app.tasks import herodraft_tick\n", "tests/test_x.py")
        self.assertFlagged("from app.functions.herodraft import submit_pick\n", "x.py")
        self.assertClean("from app.tasks import draft_tick\n", "tests/test_x.py")

    def test_patch_string_back_doors(self) -> None:
        self.assertFlagged('patch("app.consumers.broadcast_herodraft_state")\n', "x.py")
        self.assertFlagged('patch("app.functions.herodraft.submit_pick")\n', "x.py")
        self.assertFlagged('ForeignKey("app.HeroDraft")\n', "x.py")
        self.assertFlagged('apps.get_model("APP.herodraft")\n', "x.py")
        self.assertClean(
            'patch("draft.consumers.hero.broadcast_herodraft_state")\n', "x.py"
        )
        self.assertClean('ForeignKey("draft.HeroDraft")\n', "x.py")
        self.assertClean(
            'patch("app.tasks.draft_tick.start_tick_broadcaster")\n', "x.py"
        )

    def test_back_edge_unlisted_file(self) -> None:
        self.assertFlagged(
            "from draft.models import HeroDraft\n",
            "app/views/foo.py",
            back_edges=SMALL_EDGES,
        )
        self.assertFlagged(
            "import draft.models\n", "app/views/foo.py", back_edges=SMALL_EDGES
        )

    def test_back_edge_listed_file_unlisted_name(self) -> None:
        self.assertFlagged(
            "from draft.models import DraftTeam\n",
            "app/draft_state.py",
            back_edges=SMALL_EDGES,
        )
        self.assertClean(
            "from draft.models import HeroDraft\n",
            "app/draft_state.py",
            back_edges=SMALL_EDGES,
        )

    def test_back_edge_stale_listed_name(self) -> None:
        observed: dict[str, dict[str, set[str]]] = {"draft": {}}
        self.assertNotEqual(find_stale_back_edges(observed, SMALL_EDGES), [])
        observed = {"draft": {"app/draft_state.py": {"HeroDraft"}}}
        self.assertEqual(find_stale_back_edges(observed, SMALL_EDGES), [])

    def test_same_name_in_other_module_not_flagged(self) -> None:
        self.assertClean(
            "from app.internal_client import create_herodraft_for_game\n", "x.py"
        )
        self.assertClean(
            'patch("app.internal_client.create_herodraft_for_game")\n', "x.py"
        )

    def test_back_edge_names_not_reexported(self) -> None:
        self.assertFlagged("from app.draft_state import HeroDraft\n", "discordbot/x.py")
        self.assertFlagged("from app.views_main import DraftTeam\n", "events/views.py")
        self.assertFlagged(
            "from .draft_state import HeroDraft\n", "app/x.py", back_edges=SMALL_EDGES
        )
        self.assertClean(
            "from app.draft_state import build_draft_state\n", "discordbot/x.py"
        )
        self.assertClean(
            "from draft.models import HeroDraft\n",
            "app/draft_state.py",
            back_edges=SMALL_EDGES,
        )

    def test_test_modules_exempt_from_back_edges(self) -> None:
        self.assertClean("from draft.models import HeroDraft\n", "app/tests/test_x.py")
        self.assertClean("from draft.models import HeroDraft\n", "app/test_x.py")

    def test_non_source_app_files_exempt_from_back_edges(self) -> None:
        self.assertClean("from draft.models import HeroDraft\n", "discordbot/models.py")


class AppBoundaryTests(SimpleTestCase):
    base: Path = settings.BASE_DIR_PATH

    def test_no_moved_code_reachable_through_source_app(self) -> None:
        violations: list[str] = []
        observed: dict[str, dict[str, set[str]]] = {}
        for file, rel in _python_files(self.base):
            source = file.read_text()
            violations.extend(find_violations(source, rel))
            for new_app, names in collect_back_edges(source, rel).items():
                observed.setdefault(new_app, {})[rel] = names
        violations.extend(find_stale_back_edges(observed))
        self.assertEqual(violations, [])

    def test_walk_covers_the_tree(self) -> None:
        rels = {rel for _file, rel in _python_files(self.base)}
        self.assertIn("app/models.py", rels)
        self.assertIn("draft/models/hero.py", rels)
        self.assertNotIn(GUARD_FILE, rels)
        self.assertFalse(any("/migrations/" in rel for rel in rels))

    def test_retired_modules_are_gone(self) -> None:
        for s in MOVED_SLICES:
            for module in s.retired_modules:
                rel = Path(*module.split("."))
                with self.subTest(module=module):
                    self.assertFalse((self.base / rel.with_suffix(".py")).exists())
                    self.assertFalse((self.base / rel / "__init__.py").exists())

    def test_new_apps_registered(self) -> None:
        labels = {entry.split(".")[0] for entry in MODEL_APPS}
        for s in MOVED_SLICES:
            with self.subTest(slice=s.name):
                self.assertIn(s.new_app, labels)

    def test_no_cacheops_key_for_moved_models(self) -> None:
        keys = {key.casefold() for key in settings.CACHEOPS}
        for s in MOVED_SLICES:
            for label in s.model_labels:
                with self.subTest(label=label):
                    self.assertNotIn(f"{s.source_app}.{label}", keys)

    def test_moved_models_keep_their_tables(self) -> None:
        for s in MOVED_SLICES:
            for label in s.model_labels:
                with self.subTest(label=label):
                    model = apps.get_model(s.new_app, label)
                    self.assertEqual(model._meta.app_label, s.new_app)
                    self.assertEqual(model._meta.db_table, f"{s.source_app}_{label}")
