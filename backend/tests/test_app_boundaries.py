import ast
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path

from django.apps import apps
from django.conf import settings
from django.db.migrations.loader import MigrationLoader
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
    move_migration: tuple[str, str]
    cached_labels: frozenset[str]


@dataclass(frozen=True)
class BackEdge:
    names: frozenset[str]
    reason: str
    type_only: frozenset[str] = frozenset()


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
    move_migration=("app", "0108_move_hero_draft_models_to_draft"),
    cached_labels=frozenset({"herodraft", "draftteam"}),
)

TEAM_DRAFT = MovedSlice(
    name="team-draft",
    source_app="app",
    new_app="draft",
    moved=frozenset(
        {
            ("app.models", "TeamDraftState"),
            ("app.models", "TimeoutAction"),
            ("app.models", "Draft"),
            ("app.models", "DraftRound"),
            ("app.models", "DraftEvent"),
            ("app.models", "DraftOptions"),
            ("app.consumers", "DraftConsumer"),
            ("app.consumers", "emit_event"),
            ("app.consumers", "team_payload"),
            ("app.consumers", "build_draft_state"),
            ("app.consumers", "TickDriver"),
            ("app.consumers", "TEAM_TICK_DRIVER"),
            ("app.consumers", "captain_conn_key"),
            ("app.consumers", "captain_is_fresh"),
            ("app.consumers", "DraftEventSerializer"),
            ("app.serializers", "DraftSerializer"),
            ("app.serializers", "TournamentSerializerDraft"),
            ("app.serializers", "DraftSerializerMMRs"),
            ("app.serializers", "DraftRoundSerializer"),
            ("app.serializers", "DraftEventSerializer"),
            ("app.views_main", "DraftView"),
            ("app.views_main", "DraftRoundView"),
            ("app.views_main", "DraftCreateView"),
            ("app.views_main", "DraftRoundCreateView"),
            ("app.views", "DraftView"),
            ("app.views", "DraftRoundView"),
            ("app.views", "DraftCreateView"),
            ("app.views", "DraftRoundCreateView"),
            ("app.permissions_org", "CanEditDraft"),
            ("app.permissions_org", "CanEditDraftRound"),
            ("app.permissions_tournament", "CanEditDraft"),
            ("app.permissions_tournament", "CanEditDraftRound"),
            ("app.functions.tournament", "generate_draft_rounds"),
            ("app.functions.tournament", "rebuild_team"),
            ("app.functions.tournament", "get_draft_style_mmrs"),
            ("app.functions.tournament", "CreateDraftRounds"),
            ("app.functions.tournament", "DraftPredictMMRSerializer"),
            ("app.functions.tournament", "_get_or_create_draft"),
            ("app.functions.tournament", "_notify_draft_started_after_commit"),
            ("app.functions.tournament", "reset_draft_teams"),
            ("app.functions.tournament", "NoEligibleCaptains"),
            ("app.functions.tournament", "TeamsReferenced"),
            ("app.functions.tournament", "DraftSerializerMMRs"),
            ("app.functions.tournament", "notify_draft_started"),
        }
    ),
    retired_modules=frozenset(
        {
            "app.functions.teamdraft",
            "app.functions.teamdraft_timeout",
            "app.functions.teamdraft_views",
            "app.functions.shuffle_draft",
            "app.functions.draft_picks",
            "app.tasks.draft_tick",
            "app.tasks.teamdraft_tick",
            "app.broadcast",
            "app.draft_state",
            "app.consumers_base",
            "app.services.draft_reset",
            "app.tests.teamdraft_fixtures",
            "app.tests.ws_helpers",
        }
    ),
    model_labels=frozenset({"draft", "draftround", "draftevent", "draftoptions"}),
    move_migration=("app", "0109_move_team_draft_models_to_draft"),
    cached_labels=frozenset({"draft", "draftoptions", "draftround"}),
)

_ORG_PERMISSION_NAMES = (
    "is_org_owner",
    "has_org_admin_access",
    "has_org_staff_access",
    "is_site_admin",
    "is_org_role_holder",
    "has_org_promoter_access",
    "can_view_org_members",
    "_payload_lists_user",
    "_payload_has_user",
    "org_admin_staff_from_payload",
    "can_view_org_members_from_payload",
    "IsOrgOwner",
    "IsOrgAdmin",
    "IsOrgStaff",
)

ORG = MovedSlice(
    name="org",
    source_app="app",
    new_app="org",
    moved=frozenset(
        {
            ("app.views_main", "OrganizationView"),
            ("app.views_main", "_feature_access"),
            ("app.views_main", "_org_viewer_access"),
            ("app.views_main", "_member_access"),
            ("app.serializers", "OrganizationSerializer"),
            ("app.serializers", "_known_timezones"),
            ("app.serializers_ssr", "OrganizationSerializerSSR"),
            ("app.views.ssr", "OrganizationSSRView"),
            ("app.views.admin_team", "add_org_admin"),
            ("app.views.admin_team", "remove_org_admin"),
            ("app.views.admin_team", "add_org_staff"),
            ("app.views.admin_team", "remove_org_staff"),
            ("app.views.admin_team", "transfer_org_ownership"),
            ("app.views.admin_team", "add_org_member"),
            ("app.views.admin_team", "update_org_user"),
            ("app.views.admin_team", "_find_member"),
            ("app.views.admin_team", "_cached_guild_member"),
            ("app.views.admin_team", "_member_nick"),
            ("app.views.admin_team", "_resolve_user"),
            ("app.signals", "track_org_discord_server_id"),
            ("app.signals", "reset_guild_nicknames_on_server_change"),
            *(
                (module, name)
                for module in ("app.permissions_org", "app.permissions_tournament")
                for name in _ORG_PERMISSION_NAMES
            ),
        }
    ),
    retired_modules=frozenset(
        {
            "app.permissions_org",
            "app.tests.test_organization",
            "app.tests.test_org_role_fields",
        }
    ),
    model_labels=frozenset(),
    move_migration=("app", "0110_move_organization_models_to_org"),
    cached_labels=frozenset(),
)

MOVED_SLICES: tuple[MovedSlice, ...] = (HERO_DRAFT, TEAM_DRAFT, ORG)

# target app -> production file (relative to backend/) -> what it may import from that app
ALLOWED_BACK_EDGES: dict[str, dict[str, BackEdge]] = {
    "draft": {
        "app/discord_accounts.py": BackEdge(
            frozenset({"repoint_chat_attribution"}),
            "Discord account merge repoints hero draft chat authorship",
        ),
        "app/models.py": BackEdge(
            frozenset({"DraftOptions"}),
            "TYPE_CHECKING-only return annotation for Tournament.get_draft_options",
            type_only=frozenset({"DraftOptions"}),
        ),
        "app/services/team_management.py": BackEdge(
            frozenset(
                {
                    "Draft",
                    "DraftRound",
                    "DraftTeam",
                    "HeroDraft",
                    "HeroDraftState",
                    "TeamDraftState",
                    "apply_captain_tenure",
                    "broadcast_herodraft_state",
                    "emit_event",
                }
            ),
            "roster changes update live team and hero drafts, emit team_changed"
            " and move hero draft chat membership with captaincy",
        ),
        "app/services/team_references.py": BackEdge(
            frozenset({"DraftTeam", "HeroDraft"}),
            "Team-domain reference counts include hero drafts",
        ),
        "app/serializers.py": BackEdge(
            frozenset({"Draft", "DraftOptions", "DraftRound"}),
            "draft serializers embedded in TournamentSerializer",
        ),
        "app/tournament_state.py": BackEdge(
            frozenset({"Draft", "DraftOptions", "DraftRound", "HeroDraft"}),
            "tournament prefetch plan prefetches the team draft and games__herodraft",
        ),
        "app/views_main.py": BackEdge(
            frozenset({"Draft", "DraftRound", "DraftTeam", "apply_draft_options"}),
            "tournament/team @cached_as deps; current_user lists active hero drafts "
            "the user captains; tournament create/update applies draft options",
        ),
        "app/consumers.py": BackEdge(
            frozenset({"recent_draft_events"}),
            "TournamentConsumer replays a tournament's recent team-draft events",
        ),
        "app/permissions_tournament.py": BackEdge(
            frozenset({"HeroDraft"}),
            "tournament staff check resolves a hero draft's tournament",
        ),
        "app/views/bracket.py": BackEdge(
            frozenset({"HeroDraft"}),
            "bracket view prefetches each game's hero draft",
        ),
        "app/management/commands/import_prod_tournament.py": BackEdge(
            frozenset({"Draft", "DraftOptions", "DraftRound"}),
            "tournament import tooling copies a tournament's team draft",
        ),
        "app/management/commands/sync_prod_tournaments.py": BackEdge(
            frozenset({"Draft", "DraftOptions", "DraftRound"}),
            "tournament sync tooling copies a tournament's team draft",
        ),
    },
    "org": {
        "app/admin.py": BackEdge(
            frozenset({"api", "release_earning_sends"}),
            "CustomUser admin delete checks standing blockers, releases promo "
            "earning sends and records standing on user deletion",
        ),
        "app/discord_accounts.py": BackEdge(
            frozenset(
                {
                    "OrgUser",
                    "api",
                    "demote_colliding_earning_sends",
                    "repoint_org_attribution",
                }
            ),
            "user account merge pairs org memberships, merges standing and "
            "repoints org contribution and promo attribution",
        ),
        "app/functions/tournament.py": BackEdge(
            frozenset({"guild_nicknames", "org_nicknames_public"}),
            "tournament player payloads show the league org's guild nicknames",
        ),
        "app/management/commands/sync_prod_users.py": BackEdge(
            frozenset({"ContributionEntry", "PromoSend"}),
            "prod user sync clears org contribution and promo rows before reloading users",
        ),
        "app/permissions_tournament.py": BackEdge(
            frozenset(
                {
                    "_payload_lists_user",
                    "can_view_org_members",
                    "has_org_admin_access",
                    "has_org_staff_access",
                }
            ),
            "league access and member-visibility checks fall back to the league "
            "org's roles; leaves with the league slice",
        ),
        "app/serializers.py": BackEdge(
            frozenset({"OrgUser", "OrgUserSerializer"}),
            "tournament and league user serializers auto-create OrgUser rows and "
            "embed org MMR via OrgUserSerializer",
        ),
        "app/services/match_finalization.py": BackEdge(
            frozenset({"OrgUser"}),
            "league rating creation seeds base MMR from the league org's OrgUser",
        ),
        "app/services/team_leadership.py": BackEdge(
            frozenset({"OrgUser"}),
            "captain succession falls back to the highest-MMR OrgUser of the league org",
        ),
        "app/services/team_management.py": BackEdge(
            frozenset({"OrgSettings", "OrgUser", "get_org_settings"}),
            "roster rules read the league org's settings; member adds report OrgUser creation",
        ),
        "app/signals.py": BackEdge(
            frozenset({"OrgUser"}),
            "tournament user auto-add creates the league org's OrgUser",
        ),
        "app/views/admin_team.py": BackEdge(
            frozenset(
                {
                    "OrgUser",
                    "has_org_admin_access",
                    "has_org_staff_access",
                    "member_nick",
                    "resolve_member_user",
                    "user_name_q",
                }
            ),
            "user search and league/tournament member adds use org roles, the "
            "org guild member cache and OrgUser; leaves with the league and "
            "tournament slices",
        ),
        "app/views/csv_import.py": BackEdge(
            frozenset({"OrgUser", "has_org_staff_access"}),
            "shared CSV import pipeline, including the org door, writes OrgUser "
            "MMR; moves whole with the tournament slice",
        ),
        "app/views/internal.py": BackEdge(
            frozenset({"OrgUser"}),
            "repeater subscriber endpoint reports each subscriber's org membership",
        ),
        "app/views_main.py": BackEdge(
            frozenset(
                {
                    "OrgUser",
                    "api",
                    "has_org_staff_access",
                    "member_access",
                    "member_organization_ids",
                    "not_permitted",
                    "release_earning_sends",
                    "viewer_member_organization_ids",
                }
            ),
            "UserView org-staff checks, profile claims and deletion standing; "
            "TeamView feature errors and team log scope; current_user and "
            "tournament list membership ids; LeagueView member flag",
        ),
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


def _is_type_checking(test: ast.expr) -> bool:
    return (isinstance(test, ast.Name) and test.id == "TYPE_CHECKING") or (
        isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING"
    )


def _imported(
    tree: ast.Module, path: str
) -> Iterator[tuple[str, str | None, int, bool]]:
    """Yield (module, imported name or None for plain import, line, type_checking)."""
    type_checking: set[int] = {
        id(inner)
        for node in ast.walk(tree)
        if isinstance(node, ast.If) and _is_type_checking(node.test)
        for stmt in node.body
        for inner in ast.walk(stmt)
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name, None, node.lineno, id(node) in type_checking
        elif isinstance(node, ast.ImportFrom):
            module = _resolve(node, path)
            for alias in node.names:
                yield module, alias.name, node.lineno, id(node) in type_checking


def _back_edge_imports(
    tree: ast.Module, path: str, slices: tuple[MovedSlice, ...]
) -> dict[str, dict[str, bool]]:
    """new_app -> imported name -> whether every import of it is TYPE_CHECKING-only."""
    edges: dict[str, dict[str, bool]] = {}
    if _is_test_module(path):
        return edges
    for s in slices:
        if not _within(_module_of(path), s.source_app):
            continue
        for module, name, _line, type_checking in _imported(tree, path):
            if _within(module, s.new_app):
                names = edges.setdefault(s.new_app, {})
                key = name or module
                names[key] = names.get(key, True) and type_checking
    return edges


def collect_back_edges(
    source: str, path: str, slices: tuple[MovedSlice, ...] = MOVED_SLICES
) -> dict[str, set[str]]:
    if _is_test_module(path):
        return {}
    tree = ast.parse(source, filename=path)
    return {
        new_app: set(names)
        for new_app, names in _back_edge_imports(tree, path, slices).items()
    }


def find_violations(
    source: str,
    path: str,
    slices: tuple[MovedSlice, ...] = MOVED_SLICES,
    back_edges: dict[str, dict[str, BackEdge]] = ALLOWED_BACK_EDGES,
) -> list[str]:
    tree = ast.parse(source, filename=path)
    module_name = _module_of(path)
    found: list[str] = []
    for s in slices:
        re_exports = {
            (_module_of(file), name)
            for file, edge in back_edges.get(s.new_app, {}).items()
            if file != path
            for name in edge.names
        }
        forbidden = s.moved | re_exports
        moved_here = {name for old, name in s.moved if old == module_name}
        for name, line in _top_level_names(tree):
            if name in moved_here:
                found.append(
                    f"{path}:{line}: [{s.name}] {name} redefined in {module_name}"
                )

        for module, name, line, _type_checking in _imported(tree, path):
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

    for new_app, names in _back_edge_imports(tree, path, slices).items():
        allowed = back_edges.get(new_app, {}).get(path)
        if allowed is None:
            found.append(
                f"{path}: imports {sorted(names)} from {new_app}; not in ALLOWED_BACK_EDGES"
            )
            continue
        for name in sorted(names.keys() - allowed.names):
            found.append(
                f"{path}: imports {name} from {new_app}; not listed in ALLOWED_BACK_EDGES"
            )
        for name in sorted(allowed.type_only & names.keys()):
            if not names[name]:
                found.append(
                    f"{path}: imports {name} from {new_app} at runtime; "
                    "ALLOWED_BACK_EDGES allows it only under TYPE_CHECKING"
                )
    return found


def find_stale_back_edges(
    observed: dict[str, dict[str, set[str]]],
    back_edges: dict[str, dict[str, BackEdge]] = ALLOWED_BACK_EDGES,
) -> list[str]:
    stale: list[str] = []
    for new_app, files in back_edges.items():
        for path, edge in files.items():
            unused = edge.names - observed.get(new_app, {}).get(path, set())
            stale.extend(
                f"{path}: ALLOWED_BACK_EDGES[{new_app!r}] lists {name}, no longer imported"
                for name in sorted(unused)
            )
    return stale


def _migration_key(path: str) -> tuple[str, str]:
    p = Path(path)
    return p.parent.parent.name, p.stem


def _references_moved_model(tree: ast.Module, s: MovedSlice) -> Iterator[int]:
    lazy_labels = {f"{s.source_app}.{label}" for label in s.model_labels}
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if node.value.casefold() in lazy_labels:
                yield node.lineno
        elif isinstance(node, ast.Call):
            func = node.func
            name = func.attr if isinstance(func, ast.Attribute) else None
            if isinstance(func, ast.Name):
                name = func.id
            if name != "get_model" or len(node.args) < 2:
                continue
            app_arg, model_arg = node.args[0], node.args[1]
            if (
                isinstance(app_arg, ast.Constant)
                and app_arg.value == s.source_app
                and isinstance(model_arg, ast.Constant)
                and isinstance(model_arg.value, str)
                and model_arg.value.casefold() in s.model_labels
            ):
                yield node.lineno


def find_migration_ancestry_violations(
    slices: tuple[MovedSlice, ...],
    migration_files: Iterable[tuple[str, str]],
    ancestors: Callable[[tuple[str, str]], set[tuple[str, str]]],
) -> list[str]:
    """migration_files: (path like "<app>/migrations/<name>.py", source)."""
    files = list(migration_files)
    found: list[str] = []
    for s in slices:
        before_move: set[tuple[str, str]] | None = None
        for path, source in files:
            key = _migration_key(path)
            if key[0] == s.source_app:
                continue
            lines = sorted(set(_references_moved_model(ast.parse(source, path), s)))
            if not lines:
                continue
            if before_move is None:
                before_move = ancestors(s.move_migration)
            if key not in before_move:
                found.append(
                    f"{path}:{lines[0]}: [{s.name}] uses {s.source_app} models moved by "
                    f"{'.'.join(s.move_migration)} but is not its ancestor"
                )
    return found


def _python_files(base: Path) -> Iterator[tuple[Path, str]]:
    for file in sorted(base.rglob("*.py")):
        rel = file.relative_to(base).as_posix()
        if "migrations" in Path(rel).parts or rel == GUARD_FILE:
            continue
        yield file, rel


def _migration_files(base: Path) -> Iterator[tuple[str, str]]:
    for file in sorted(base.rglob("*.py")):
        if file.parent.name == "migrations" and file.name != "__init__.py":
            yield file.relative_to(base).as_posix(), file.read_text()


FIXTURE_SLICE = MovedSlice(
    name="fixture",
    source_app="src",
    new_app="dst",
    moved=frozenset({("src.models", "Moved"), ("src.views", "MovedView")}),
    retired_modules=frozenset({"src.old"}),
    model_labels=frozenset({"moved"}),
    move_migration=("src", "0002_move"),
    cached_labels=frozenset({"moved"}),
)

FIXTURE_EDGES: dict[str, dict[str, BackEdge]] = {
    "dst": {
        "src/state.py": BackEdge(frozenset({"Moved"}), "fixture"),
        "src/models.py": BackEdge(
            frozenset({"Moved"}), "fixture", type_only=frozenset({"Moved"})
        ),
    },
}

FIXTURE_MIGRATION = ("other", "0003_x")
FIXTURE_MIGRATION_PATH = "other/migrations/0003_x.py"


class GuardSelfTests(SimpleTestCase):
    def violations(self, source: str, path: str) -> list[str]:
        return find_violations(
            source, path, slices=(FIXTURE_SLICE,), back_edges=FIXTURE_EDGES
        )

    def assertFlagged(self, source: str, path: str) -> None:
        self.assertNotEqual(self.violations(source, path), [], source)

    def assertClean(self, source: str, path: str) -> None:
        self.assertEqual(self.violations(source, path), [], source)

    def ancestry(
        self, source: str, ancestors: set[tuple[str, str]], path: str
    ) -> list[str]:
        return find_migration_ancestry_violations(
            (FIXTURE_SLICE,), [(path, source)], lambda _key: ancestors
        )

    def test_redefinition_in_old_module(self) -> None:
        self.assertFlagged("class Moved:\n    pass\n", "src/models.py")
        self.assertFlagged("def MovedView():\n    pass\n", "src/views.py")
        self.assertFlagged("MovedView = object\n", "src/views.py")
        self.assertClean("class Other:\n    pass\n", "src/models.py")
        self.assertClean("class Moved:\n    pass\n", "dst/models.py")

    def test_absolute_import_through_old_module(self) -> None:
        self.assertFlagged("from src.models import Moved\n", "src/views.py")
        self.assertClean("from dst.models import Moved\n", "dst/views.py")
        self.assertClean("from src.models import Other\n", "src/views.py")

    def test_relative_import_through_old_module(self) -> None:
        self.assertFlagged("from .models import Moved\n", "src/views.py")
        self.assertFlagged("from ..models import Moved\n", "src/views/foo.py")
        self.assertFlagged("from .views import MovedView\n", "src/__init__.py")
        self.assertClean("from .models import Other\n", "src/views.py")

    def test_retired_module_import(self) -> None:
        self.assertFlagged("import src.old\n", "tests/test_x.py")
        self.assertFlagged("from src import old\n", "tests/test_x.py")
        self.assertFlagged("from src.old import thing\n", "x.py")
        self.assertClean("from src import other\n", "tests/test_x.py")

    def test_patch_string_back_doors(self) -> None:
        self.assertFlagged('patch("src.models.Moved")\n', "x.py")
        self.assertFlagged('patch("src.views.MovedView.get")\n', "x.py")
        self.assertFlagged('patch("src.old.thing")\n', "x.py")
        self.assertFlagged('ForeignKey("src.Moved")\n', "x.py")
        self.assertFlagged('apps.get_model("SRC.moved")\n', "x.py")
        self.assertClean('patch("dst.models.Moved")\n', "x.py")
        self.assertClean('ForeignKey("dst.Moved")\n', "x.py")
        self.assertClean('patch("src.models.Other")\n', "x.py")

    def test_back_edge_unlisted_file(self) -> None:
        self.assertFlagged("from dst.models import Moved\n", "src/views/foo.py")
        self.assertFlagged("import dst.models\n", "src/views/foo.py")

    def test_back_edge_listed_file_unlisted_name(self) -> None:
        self.assertFlagged("from dst.models import Other\n", "src/state.py")
        self.assertClean("from dst.models import Moved\n", "src/state.py")

    def test_back_edge_stale_listed_name(self) -> None:
        observed: dict[str, dict[str, set[str]]] = {"dst": {}}
        self.assertNotEqual(find_stale_back_edges(observed, FIXTURE_EDGES), [])
        observed = {"dst": {"src/state.py": {"Moved"}, "src/models.py": {"Moved"}}}
        self.assertEqual(find_stale_back_edges(observed, FIXTURE_EDGES), [])

    def test_collect_back_edges_reports_observed_names(self) -> None:
        source = "from dst.models import Moved\nimport dst.views\n"
        self.assertEqual(
            collect_back_edges(source, "src/state.py", slices=(FIXTURE_SLICE,)),
            {"dst": {"Moved", "dst.views"}},
        )
        self.assertEqual(
            collect_back_edges(source, "src/tests/test_x.py", slices=(FIXTURE_SLICE,)),
            {},
        )

    def test_same_name_in_other_module_not_flagged(self) -> None:
        self.assertClean("from src.client import Moved\n", "x.py")
        self.assertClean('patch("src.client.Moved")\n', "x.py")

    def test_back_edge_names_not_reexported(self) -> None:
        self.assertFlagged("from src.state import Moved\n", "other/x.py")
        self.assertFlagged("from .state import Moved\n", "src/x.py")
        self.assertClean("from src.state import helper\n", "other/x.py")
        self.assertClean("from dst.models import Moved\n", "src/state.py")

    def test_test_modules_exempt_from_back_edges(self) -> None:
        self.assertClean("from dst.models import Moved\n", "src/tests/test_x.py")
        self.assertClean("from dst.models import Moved\n", "src/test_x.py")

    def test_non_source_app_files_exempt_from_back_edges(self) -> None:
        self.assertClean("from dst.models import Moved\n", "other/models.py")

    def test_type_only_name_allowed_under_type_checking(self) -> None:
        self.assertClean(
            "from typing import TYPE_CHECKING\n"
            "if TYPE_CHECKING:\n"
            "    from dst.models import Moved\n",
            "src/models.py",
        )
        self.assertClean(
            "import typing\nif typing.TYPE_CHECKING:\n    from dst.models import Moved\n",
            "src/models.py",
        )

    def test_type_only_name_flagged_at_runtime(self) -> None:
        self.assertFlagged("from dst.models import Moved\n", "src/models.py")
        self.assertFlagged(
            "from typing import TYPE_CHECKING\n"
            "if TYPE_CHECKING:\n"
            "    from dst.models import Moved\n"
            "else:\n"
            "    from dst.models import Moved\n",
            "src/models.py",
        )
        self.assertFlagged(
            "from typing import TYPE_CHECKING\n"
            "if TYPE_CHECKING:\n"
            "    pass\n"
            "from dst.models import Moved\n",
            "src/models.py",
        )

    def test_back_edge_reasons_non_empty(self) -> None:
        for new_app, files in ALLOWED_BACK_EDGES.items():
            for path, edge in files.items():
                with self.subTest(new_app=new_app, path=path):
                    self.assertTrue(edge.reason.strip())
                    self.assertTrue(edge.names)
                    self.assertLessEqual(edge.type_only, edge.names)

    def test_migration_ancestry_flags_non_ancestor(self) -> None:
        for source in (
            'Moved = apps.get_model("src", "Moved")\n',
            'Moved = apps.get_model("src.Moved")\n',
            'field = ForeignKey(to="src.moved")\n',
        ):
            with self.subTest(source=source):
                self.assertNotEqual(
                    self.ancestry(
                        source, {("src", "0001_initial")}, FIXTURE_MIGRATION_PATH
                    ),
                    [],
                )

    def test_migration_ancestry_accepts_ancestor(self) -> None:
        for source in (
            'Moved = apps.get_model("src", "Moved")\n',
            'Moved = apps.get_model("src.Moved")\n',
            'field = ForeignKey(to="src.moved")\n',
        ):
            with self.subTest(source=source):
                self.assertEqual(
                    self.ancestry(source, {FIXTURE_MIGRATION}, FIXTURE_MIGRATION_PATH),
                    [],
                )

    def test_migration_ancestry_ignores_unrelated_and_source_app(self) -> None:
        self.assertEqual(
            self.ancestry(
                'apps.get_model("src", "Other")\n', set(), FIXTURE_MIGRATION_PATH
            ),
            [],
        )
        self.assertEqual(
            self.ancestry(
                'apps.get_model("dst", "Moved")\n', set(), FIXTURE_MIGRATION_PATH
            ),
            [],
        )
        self.assertEqual(
            self.ancestry(
                'apps.get_model("src", "Moved")\n', set(), "src/migrations/0003_x.py"
            ),
            [],
        )

    def test_migration_ancestry_checks_new_app_migrations(self) -> None:
        path = "dst/migrations/0003_x.py"
        source = 'apps.get_model("src", "Moved")\n'
        violations = self.ancestry(source, set(), path)
        self.assertEqual(len(violations), 1)
        self.assertIn(path, violations[0])
        self.assertEqual(self.ancestry(source, {("dst", "0003_x")}, path), [])


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
        self.assertIn("draft/models/team.py", rels)
        self.assertIn("org/permissions.py", rels)
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

    def test_new_cacheops_keys_present(self) -> None:
        if not settings.CACHEOPS:
            self.skipTest("CACHEOPS is empty (DISABLE_CACHE)")
        for s in MOVED_SLICES:
            for label in s.cached_labels:
                with self.subTest(label=label):
                    self.assertIn(f"{s.new_app}.{label}", settings.CACHEOPS)

    def test_cross_app_migrations_precede_move(self) -> None:
        graph = MigrationLoader(None, ignore_no_migrations=True).graph
        files = list(_migration_files(self.base))
        self.assertTrue(files)
        violations = find_migration_ancestry_violations(
            MOVED_SLICES, files, lambda key: set(graph.forwards_plan(key))
        )
        self.assertEqual(violations, [])

    def test_moved_models_keep_their_tables(self) -> None:
        for s in MOVED_SLICES:
            for label in s.model_labels:
                with self.subTest(label=label):
                    model = apps.get_model(s.new_app, label)
                    self.assertEqual(model._meta.app_label, s.new_app)
                    self.assertEqual(model._meta.db_table, f"{s.source_app}_{label}")
