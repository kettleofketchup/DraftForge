"""T1.9 — Cacheops integration guardrails for BaseUserProfile.

Local CI runs without a live Redis (cacheops degrades gracefully via
CACHEOPS_DEGRADE_ON_FAILURE=True), so we cannot reliably warm a real cached
endpoint and observe invalidation in unit tests. Instead we assert the
invariants directly:

1. The CACHEOPS dict registers ``user.baseuserprofile`` so cacheops will
   actually track invalidations for the model.
2. Every cacheops decorator block that depends on ``CustomUser`` *also*
   depends on ``BaseUserProfile`` — otherwise a PATCH to
   ``/api/users/me/profile/base/`` silently serves stale nickname/avatar to
   any cached endpoint that ships those fields (T1 epic regression risk).

A real-Redis integration test that warms a cached list endpoint, PATCHes the
nickname, and re-fetches to confirm invalidation belongs in the
container-backed test stack (just test::run ...) which has Redis available;
running it here would fall back to DummyCache and pass vacuously.
"""

import ast
import pathlib
import re
import tempfile
import textwrap
from collections.abc import Iterator

from cacheops.tree import dnfs
from django.conf import settings
from django.test import SimpleTestCase, TestCase

from app.models import CustomUser
from user.querysets import with_user_profiles

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
BACKEND_ROOT = REPO_ROOT / "backend"


def _iter_cached_as_blocks(path: pathlib.Path):
    """Yield ``(start_line, block_text)`` for every ``@cached_as(...)`` call
    in ``path``, correctly handling multi-line decorators by walking
    parentheses balance.
    """
    text = path.read_text()
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        match = re.search(r"@cached_as\s*\(", line)
        if not match:
            i += 1
            continue
        start_line = i + 1  # 1-indexed for error messages
        depth = 0
        chunks = []
        # Start scanning from the @cached_as position
        j = match.start()
        while i < len(lines):
            current = lines[i] if j == 0 else lines[i][j:]
            chunks.append(current)
            for ch in current:
                if ch == "(":
                    depth += 1
                elif ch == ")":
                    depth -= 1
                    if depth == 0:
                        break
            if depth == 0 and chunks:
                break
            i += 1
            j = 0
        yield start_line, "\n".join(chunks)
        i += 1


class CacheopsSettingsTests(TestCase):
    """The CACHEOPS dict must register user.baseuserprofile so that PATCHes
    on the model actually trigger invalidation of any @cached_as blocks that
    depend on it. Without this entry, cacheops silently treats the model as
    uncached and the dep is a no-op.

    When DISABLE_CACHE=1 (populate scripts, local test runs without Redis)
    settings.py clears CACHEOPS entirely — the dep is irrelevant there, so
    skip the assertion rather than reporting a spurious failure.
    """

    def test_cacheops_dict_registers_baseuserprofile(self):
        cacheops = getattr(settings, "CACHEOPS", {}) or {}
        if not getattr(settings, "CACHEOPS_ENABLED", True) or not cacheops:
            self.skipTest("CACHEOPS disabled (DISABLE_CACHE env or empty dict)")
        assert "user.baseuserprofile" in cacheops, (
            "CACHEOPS must register 'user.baseuserprofile' so @cached_as "
            "blocks depending on BaseUserProfile actually invalidate on PATCH "
            "to /api/users/me/profile/base/. See backend/backend/settings.py."
        )


# Files we scan. Add new files here whenever a new module starts using
# @cached_as with CustomUser deps.
SCAN_TARGETS = [
    REPO_ROOT / "backend" / "app" / "views_main.py",
    REPO_ROOT / "backend" / "app" / "functions" / "tournament.py",
    REPO_ROOT / "backend" / "app" / "user_cache.py",
]


def _customuser_blocks_missing(dep: str) -> list[str]:
    """Return formatted offender strings for every @cached_as block in
    SCAN_TARGETS that lists ``CustomUser`` but not ``dep``.

    Positions and nickname/avatar both ship on the same user-list/detail/org/
    league/draft endpoints, so any CustomUser-dependent block needs both
    BaseUserProfile (T1) and DotaUserProfile (T2) deps.
    """
    offenders = []
    for path in SCAN_TARGETS:
        assert path.exists(), f"Scan target missing: {path}"
        for start_line, block in _iter_cached_as_blocks(path):
            if "CustomUser" not in block:
                continue
            if dep not in block:
                offenders.append(
                    f"  {path.relative_to(REPO_ROOT)}:{start_line}\n"
                    f"    {block.splitlines()[0].strip()} ..."
                )
    return offenders


class CachedAsGuardrailTests(TestCase):
    """Every cacheops decorator block that depends on ``CustomUser`` MUST
    also depend on ``BaseUserProfile`` (nickname/avatar — T1 epic) AND
    ``DotaUserProfile`` (positions/dota-mmr — T2 epic). A CustomUser-only dep
    would serve stale data from cached endpoints (org rosters, tournament
    participants, draft payloads) after a PATCH to the profile-base or
    profile-game/dota endpoints.
    """

    def test_every_customuser_cached_as_block_also_lists_baseuserprofile(self):
        offenders = _customuser_blocks_missing("BaseUserProfile")
        assert not offenders, (
            "@cached_as sites depending on CustomUser but missing "
            "BaseUserProfile dep:\n"
            + "\n".join(offenders)
            + "\n\nAdd `BaseUserProfile` (from user.models) to each "
            "decorator's model list."
        )

    def test_every_customuser_cached_as_block_also_lists_dotauserprofile(self):
        """Any @cached_as(CustomUser, ...) site that ships positions must also
        depend on DotaUserProfile so a PATCH to /api/users/me/profile/game/dota/
        evicts it. Positions ship on the same user-list/detail/org/league
        endpoints that T1 guarded for BaseUserProfile, so the dependency set is
        identical."""
        offenders = _customuser_blocks_missing("DotaUserProfile")
        assert not offenders, (
            "@cached_as sites depending on CustomUser but missing "
            "DotaUserProfile dep:\n"
            + "\n".join(offenders)
            + "\n\nAdd `DotaUserProfile` (from user.models) to each "
            "decorator's model list."
        )


# Relation paths that reach a profile table owning nickname/avatar (T1) or
# positions/rank (T2) from some *other* base table.
_PROFILE_JOIN_RE = re.compile(r"base_profile|dota_user_profile|deadlock_user_profile")

_SANCTIONED_MODULE = "user/querysets.py"
_EXCLUDED_DIRS = frozenset({"migrations", "tests", ".venv"})
_MIN_SCANNED_FILES = 220

_FunctionNode = ast.FunctionDef | ast.AsyncFunctionDef


def _parent_map(tree: ast.AST) -> dict[ast.AST, ast.AST]:
    return {
        child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)
    }


def _chain_top(node: ast.AST, parents: dict[ast.AST, ast.AST]) -> ast.AST:
    while (parent := parents.get(node)) is not None:
        if isinstance(parent, ast.Attribute) and parent.value is node:
            node = parent
        elif isinstance(parent, ast.Call) and parent.func is node:
            node = parent
        else:
            break
    return node


def _chain_has_nocache(top: ast.AST) -> bool:
    node = top
    while True:
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Attribute) and node.func.attr == "nocache":
                return True
            node = node.func
        elif isinstance(node, ast.Attribute):
            node = node.value
        else:
            return False


def _literal_strings(node: ast.expr | None) -> list[str] | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return [node.value]
    if isinstance(node, ast.Tuple | ast.List) and all(
        isinstance(elt, ast.Constant) and isinstance(elt.value, str)
        for elt in node.elts
    ):
        return [elt.value for elt in node.elts]  # type: ignore[attr-defined]
    return None


def _enclosing_function(
    node: ast.AST, parents: dict[ast.AST, ast.AST]
) -> _FunctionNode | None:
    while (node := parents.get(node)) is not None:
        if isinstance(node, _FunctionNode):
            return node
    return None


def _param_default(
    func: _FunctionNode, name: str
) -> tuple[ast.expr | None, int | None] | None:
    """Return ``(default, positional_index)`` for parameter ``name``, or None if absent."""
    args = func.args
    positional = [*args.posonlyargs, *args.args]
    defaults: list[ast.expr | None] = [None] * (len(positional) - len(args.defaults))
    defaults += args.defaults
    for index, (arg, default) in enumerate(zip(positional, defaults, strict=True)):
        if arg.arg == name:
            return default, index
    for arg, kw_default in zip(args.kwonlyargs, args.kw_defaults, strict=True):
        if arg.arg == name:
            return kw_default, None
    return None


def _call_site_values(
    tree: ast.AST, func: _FunctionNode, name: str, positional_index: int | None
) -> list[ast.expr | None]:
    """Values passed for ``name`` at same-module call sites of ``func``.

    None marks a site whose value cannot be determined (``*args``/``**kwargs``).
    """
    first = [*func.args.posonlyargs, *func.args.args][:1]
    bound_offset = 1 if first and first[0].arg in {"self", "cls"} else 0
    values: list[ast.expr | None] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        callee = node.func
        if isinstance(callee, ast.Name) and callee.id == func.name:
            offset = 0
        elif isinstance(callee, ast.Attribute) and callee.attr == func.name:
            offset = bound_offset
        else:
            continue
        if any(isinstance(a, ast.Starred) for a in node.args) or any(
            kw.arg is None for kw in node.keywords
        ):
            values.append(None)
            continue
        values += [kw.value for kw in node.keywords if kw.arg == name]
        if positional_index is not None:
            index = positional_index - offset
            if 0 <= index < len(node.args):
                values.append(node.args[index])
    return values


def _resolve_name(
    name: str, call: ast.Call, tree: ast.AST, parents: dict[ast.AST, ast.AST]
) -> list[str] | None:
    """Resolve a non-literal ``select_related`` arg via its parameter's literal
    default plus same-module call-site literals; None when unverifiable."""
    func = _enclosing_function(call, parents)
    if func is None or (param := _param_default(func, name)) is None:
        return None
    default, positional_index = param
    candidates = [default, *_call_site_values(tree, func, name, positional_index)]
    resolved: list[str] = []
    for candidate in candidates:
        strings = _literal_strings(candidate)
        if strings is None:
            return None
        resolved += strings
    return resolved


def _select_related_paths(
    call: ast.Call, tree: ast.AST, parents: dict[ast.AST, ast.AST]
) -> list[str] | None:
    paths: list[str] = []
    for arg in call.args:
        value = arg.value if isinstance(arg, ast.Starred) else arg
        strings = _literal_strings(value) if not isinstance(arg, ast.Starred) else None
        if strings is None and isinstance(value, ast.Name):
            strings = _resolve_name(value.id, call, tree, parents)
        if strings is None:
            return None
        paths += strings
    return paths


def _profile_join_offenders(source: str, rel_path: str) -> list[str]:
    """``rel_path:lineno`` for each ``select_related`` call that joins a profile
    table without a same-chain ``.nocache()``, or whose args can't be verified."""
    try:
        tree = ast.parse(source, filename=rel_path)
    except SyntaxError as exc:
        raise SyntaxError(f"cannot parse {rel_path}: {exc}") from exc
    if rel_path == _SANCTIONED_MODULE:
        return []
    parents = _parent_map(tree)
    offenders: list[str] = []
    for node in ast.walk(tree):
        if not (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "select_related"
        ):
            continue
        paths = _select_related_paths(node, tree, parents)
        if paths is None or (
            any(_PROFILE_JOIN_RE.search(p) for p in paths)
            and not _chain_has_nocache(_chain_top(node, parents))
        ):
            offenders.append(f"{rel_path}:{node.func.end_lineno}")
    return sorted(set(offenders), key=lambda o: int(o.rsplit(":", 1)[1]))


def _iter_scanned_files(root: pathlib.Path) -> Iterator[pathlib.Path]:
    for path in sorted(root.rglob("*.py")):
        rel_parts = path.relative_to(root).parts
        if _EXCLUDED_DIRS.intersection(rel_parts[:-1]) or path.name.startswith("test_"):
            continue
        yield path


def _scan_tree(root: pathlib.Path) -> list[str]:
    offenders: list[str] = []
    for path in _iter_scanned_files(root):
        offenders += _profile_join_offenders(
            path.read_text(), path.relative_to(root).as_posix()
        )
    return offenders


class ProfileJoinNoCacheGuardrailTests(TestCase):
    """Cacheops registers an auto-cached queryset's invalidation keys against
    its *base* table only. A ``select_related()`` that joins into
    BaseUserProfile / DotaUserProfile / DeadlockUserProfile is therefore never
    evicted when those tables are written, so a PATCH to
    ``/api/users/me/profile/base/`` serves the pre-edit nickname until TTL —
    and an enclosing ``@cached_as`` does not save you: it is evicted correctly,
    then instantly repopulated from the stale inner join.

    Every such join must use ``user.querysets.with_user_profiles`` or chain
    ``.nocache()`` in the same expression.
    """

    def test_profile_joins_are_nocached(self) -> None:
        offenders = _scan_tree(BACKEND_ROOT)
        assert not offenders, (
            "select_related() joins into a profile table without a same-chain "
            ".nocache(), or with args the scanner cannot verify:\n  "
            + "\n  ".join(offenders)
            + "\n\nCacheops invalidates a cached JOIN only on its base table, "
            "so these serve stale nickname/avatar/positions after a profile "
            "PATCH. Use user.querysets.with_user_profiles, or chain `.nocache()` "
            "onto the same queryset expression."
        )


_EX = "app/example.py"


def _src(text: str) -> str:
    return textwrap.dedent(text).lstrip("\n")


class ProfileJoinScannerSelfTests(SimpleTestCase):
    def test_comment_only_nocache_is_flagged(self) -> None:
        src = 'X.objects.select_related("base_profile")  # .nocache()\n'
        self.assertEqual(_profile_join_offenders(src, _EX), [f"{_EX}:1"])

    def test_neighbouring_function_nocache_is_flagged(self) -> None:
        src = _src(
            """
            def a():
                return X.objects.select_related("base_profile")

            def b():
                return X.objects.all().nocache()
            """
        )
        self.assertEqual(_profile_join_offenders(src, _EX), [f"{_EX}:2"])

    def test_long_chain_nocache_past_old_window_passes(self) -> None:
        src = _src(
            """
            qs = (
                X.objects.select_related("base_profile")
                .prefetch_related(
                    Prefetch(
                        "members",
                        queryset=Y.objects.filter(
                            a=1,
                            b=2,
                            c=3,
                            d=4,
                            e=5,
                        ),
                    )
                )
                .order_by("pk")
                .nocache()
            )
            """
        )
        self.assertEqual(_profile_join_offenders(src, _EX), [])

    def test_prefetch_inner_join_without_its_own_nocache_is_flagged(self) -> None:
        src = _src(
            """
            qs = X.objects.prefetch_related(
                Prefetch(
                    "members",
                    queryset=Y.objects.select_related("base_profile"),
                )
            ).nocache()
            """
        )
        self.assertEqual(_profile_join_offenders(src, _EX), [f"{_EX}:4"])

    def test_reassigned_nocache_is_flagged(self) -> None:
        src = _src(
            """
            qs = X.objects.select_related("base_profile")
            qs = qs.nocache()
            """
        )
        self.assertEqual(_profile_join_offenders(src, _EX), [f"{_EX}:1"])

    def test_nocache_before_select_related_passes(self) -> None:
        src = 'X.objects.nocache().select_related("user__dota_user_profile")\n'
        self.assertEqual(_profile_join_offenders(src, _EX), [])

    def test_non_profile_literal_passes(self) -> None:
        src = 'X.objects.select_related("event", "organization")\n'
        self.assertEqual(_profile_join_offenders(src, _EX), [])

    def test_unresolved_starred_is_flagged(self) -> None:
        src = _src(
            """
            def f(paths):
                return X.objects.select_related(*paths)
            """
        )
        self.assertEqual(_profile_join_offenders(src, _EX), [f"{_EX}:2"])

    def test_unresolved_name_is_flagged(self) -> None:
        src = _src(
            """
            path = "event"
            X.objects.select_related(path)
            """
        )
        self.assertEqual(_profile_join_offenders(src, _EX), [f"{_EX}:2"])

    def _param_default_sources(self, call_args: str) -> dict[str, str]:
        return {
            "function": _src(
                f"""
                def f(select_related=("event",)):
                    return E.objects.select_related(*select_related)

                f({call_args})
                """
            ),
            "keyword_only": _src(
                f"""
                def f(x, *, select_related=("event",)):
                    return E.objects.select_related(*select_related)

                f(1, {call_args})
                """
            ),
            "method": _src(
                f"""
                class Loader:
                    def f(self, x, *, select_related=("event",)):
                        return E.objects.select_related(*select_related)

                    def g(self):
                        return self.f(1, {call_args})
                """
            ),
            "async": _src(
                f"""
                async def f(x, *, select_related=("event",)):
                    return await E.objects.select_related(*select_related).aget()

                async def g():
                    return await f(1, {call_args})
                """
            ),
        }

    def test_param_default_with_safe_call_site_passes(self) -> None:
        for shape, src in self._param_default_sources(
            'select_related=("league",)'
        ).items():
            with self.subTest(shape=shape):
                self.assertEqual(_profile_join_offenders(src, _EX), [])

    def test_param_default_with_profile_call_site_is_flagged(self) -> None:
        for shape, src in self._param_default_sources(
            'select_related=("base_profile",)'
        ).items():
            with self.subTest(shape=shape):
                self.assertEqual(len(_profile_join_offenders(src, _EX)), 1)

    def test_param_default_containing_profile_path_is_flagged(self) -> None:
        src = _src(
            """
            def f(*, select_related=("user__base_profile",)):
                return E.objects.select_related(*select_related)
            """
        )
        self.assertEqual(_profile_join_offenders(src, _EX), [f"{_EX}:2"])

    def test_non_literal_call_site_is_flagged(self) -> None:
        src = _src(
            """
            def f(*, select_related=("event",)):
                return E.objects.select_related(*select_related)

            f(select_related=PATHS)
            """
        )
        self.assertEqual(_profile_join_offenders(src, _EX), [f"{_EX}:2"])

    def test_sanctioned_module_is_exempt(self) -> None:
        src = _src(
            """
            def helper(qs, paths):
                return qs.select_related(*paths).nocache()

            X.objects.select_related("base_profile")
            """
        )
        self.assertEqual(_profile_join_offenders(src, "user/querysets.py"), [])
        self.assertEqual(_profile_join_offenders(src, _EX), [f"{_EX}:2", f"{_EX}:4"])

    def test_unparseable_source_raises_with_path(self) -> None:
        with self.assertRaisesRegex(SyntaxError, "app/broken.py"):
            _profile_join_offenders("def (:\n", "app/broken.py")

    def test_real_load_event_helper_passes(self) -> None:
        rel = "events/discord/_shared.py"
        self.assertEqual(
            _profile_join_offenders((BACKEND_ROOT / rel).read_text(), rel), []
        )

    def test_scan_tree_reports_only_non_exempt_files(self) -> None:
        src = 'X.objects.select_related("base_profile")\n'
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            for rel in (
                "app/x.py",
                "user/querysets.py",
                "tests/test_x.py",
                "app/tests/helpers.py",
                "app/migrations/0001_x.py",
                ".venv/lib/site.py",
                "app/test_y.py",
            ):
                path = root / rel
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(src)
            self.assertEqual(_scan_tree(root), ["app/x.py:1"])

    def test_scan_tree_raises_on_unparseable_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "app" / "broken.py"
            path.parent.mkdir(parents=True)
            path.write_text("def (:\n")
            with self.assertRaisesRegex(SyntaxError, "app/broken.py"):
                _scan_tree(pathlib.Path(tmp))

    def test_real_tree_scan_is_not_vacuous(self) -> None:
        rel_paths = {
            path.relative_to(BACKEND_ROOT).as_posix()
            for path in _iter_scanned_files(BACKEND_ROOT)
        }
        self.assertGreaterEqual(len(rel_paths), _MIN_SCANNED_FILES)
        for rel in ("app/models.py", "user/querysets.py", "events/discord/_shared.py"):
            self.assertIn(rel, rel_paths)


class ProfileJoinDnfsPinTests(SimpleTestCase):
    def test_select_related_profile_is_not_an_invalidation_dependency(self) -> None:
        self.assertNotIn(
            "user_baseuserprofile",
            dnfs(CustomUser.objects.select_related("base_profile")),
        )

    def test_values_through_profile_is_an_invalidation_dependency(self) -> None:
        self.assertIn(
            "user_baseuserprofile",
            dnfs(CustomUser.objects.values("base_profile__avatar")),
        )

    def test_with_user_profiles_opts_out_of_cacheops(self) -> None:
        self.assertEqual(
            with_user_profiles(CustomUser.objects.all())._cacheprofile["ops"], set()
        )
