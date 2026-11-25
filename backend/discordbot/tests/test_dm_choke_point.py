"""Guard: every Discord DM goes through the ledger choke points.

``discordbot/dm.py`` (Celery/REST) and ``discordbot/gateway_dm.py`` (gateway
bot) are the only modules allowed to open a DM channel or send into one. The
rules below fail with ``path:line`` for any other path.

Limit: the guard catches new code paths, not a module that builds Discord URLs
dynamically through raw ``aiohttp``. R1, R3 and review cover that.
"""

import ast
import re
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from importlib import import_module
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase
from django.urls import URLPattern, URLResolver

from discordbot.dm_keys import KEY_BUILDERS
from discordbot.models import DMKind

DM_MODULE = "discordbot/dm.py"
GATEWAY_DM_MODULE = "discordbot/gateway_dm.py"
LEDGER_MODULE = "discordbot/dm_ledger.py"

R1_DM_CHANNEL_URL = "/users/@me/channels"
R2_NAMES: frozenset[str] = frozenset(
    {"_open_dm_channel", "sync_create_dm_channel", "sync_send_dm"}
)
R2_ALLOWED: dict[str, frozenset[str]] = {"_open_dm_channel": frozenset({DM_MODULE})}
R3_ATTRS: frozenset[str] = frozenset(
    {
        "create_dm",
        "dm_channel",
        "start_private_message",
        "get_partial_messageable",
        "fetch_user",
        "get_user",
        "create_dm_channel",
    }
)
R4_EXEMPT: frozenset[str] = frozenset(
    {
        DM_MODULE,
        GATEWAY_DM_MODULE,
        "discordbot/utils.py",
        "discordbot/tasks.py",
        "discordbot/views.py",
        "discordbot/activity_views.py",
        "discordbot/admin.py",
        "discordbot/models.py",
        "discordbot/urls.py",
        "discordbot/internal_urls.py",
        "discordbot/internal_dm_views.py",
        "discordbot/internal_signup_views.py",
        "discordbot/internal_voice_views.py",
        "discordbot/internal_leadership_views.py",
    }
)
R4_SAFE_RECEIVERS: frozenset[str] = frozenset({"followup", "response"})
R4_COMMENT = re.compile(r"#\s*dm-guard:\s*not-a-dm\b(?P<reason>.*)$")
R5_ATTRS: frozenset[str] = frozenset({"discord_channel_id", "discord_message_id"})
R5_DM_MODULES: frozenset[str] = frozenset(
    {
        LEDGER_MODULE,
        DM_MODULE,
        GATEWAY_DM_MODULE,
        "discordbot/admin.py",
        "discordbot/internal_dm_views.py",
        "discordbot/schemas.py",
        "discordbot/models.py",
        "org/leadership/review_dm.py",
        "discordbot/internal_client/dm_ledger.py",
        "discordbot/internal_client/leadership_actions.py",
        "discordbot/internal_leadership_views.py",
        "discordbot/leadership_gateway.py",
    }
)
# Files that read DiscordMessageLog / signup-post ids, never DM ids. Add an
# entry only for non-DM ids, with the reason; fix every other R5 hit in code.
R5_NON_DM_FILES: dict[str, str] = {
    "events/tasks.py": "DiscordMessageLog ids of event announcement posts and scheduled events, not DMs",
    "discordbot/internal_signup_views.py": "reaction payload ids of guild signup posts, not DMs",
    "app/views/internal.py": "DiscordMessageLog listing of channel posts, not DMs",
    "scripts/cleanup_discord_spam.py": "DiscordMessageLog channel posts being deleted, not DMs",
    "discordbot/test_utils.py": "DiscordMessageLog channel posts on the test stack, not DMs",
    "scripts/test_forum_thread.py": "DiscordMessageLog forum-thread post, not a DM",
}
R6_METHODS: frozenset[str] = frozenset({"delete", "update", "save"})
R6_NAMES: frozenset[str] = frozenset({"DiscordDM", "discordbot.DiscordDM"})
KIND_DEFINITION_FILES: frozenset[str] = frozenset(
    {"discordbot/models.py", "discordbot/dm_keys.py", "discordbot/dm_context.py"}
)
PENDING_KINDS: frozenset[DMKind] = frozenset({DMKind.LEADERSHIP_REVIEW})
SKIP_DIRS: frozenset[str] = frozenset(
    {".venv", "venv", "node_modules", "migrations", "__pycache__"}
)


@dataclass(frozen=True, slots=True)
class Violation:
    path: str
    line: int
    rule: str
    detail: str

    def __str__(self) -> str:
        return f"{self.path}:{self.line} {self.rule} {self.detail}"


def _name_of(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _references_ledger_model(node: ast.AST) -> bool:
    return (_name_of(node) in R6_NAMES) or (
        isinstance(node, ast.Constant) and node.value in R6_NAMES
    )


def _walk_scope(node: ast.AST) -> Iterator[ast.AST]:
    """Walk ``node`` without descending into nested function bodies."""
    for child in ast.iter_child_nodes(node):
        yield child
        if not isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef | ast.Lambda):
            yield from _walk_scope(child)


def _r4_comment(lines: list[str], node: ast.Call) -> str | None:
    end = node.end_lineno or node.lineno
    for text in lines[node.lineno - 1 : end]:
        match = R4_COMMENT.search(text)
        if match:
            return match.group("reason").strip()
    return None


def _check_r6(path: str, tree: ast.Module) -> list[Violation]:
    if path == LEDGER_MODULE:
        return []
    found: list[Violation] = []
    scopes: list[ast.AST] = [tree]
    scopes.extend(
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef)
    )
    for scope in scopes:
        nodes = list(_walk_scope(scope))
        if not any(_references_ledger_model(n) for n in nodes):
            continue
        found.extend(
            Violation(path, n.lineno, "R6", f"DiscordDM scope calls .{n.func.attr}()")
            for n in nodes
            if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Attribute)
            and n.func.attr in R6_METHODS
        )
    return found


def check_source(path: str, source: str) -> list[Violation]:
    tree = ast.parse(source, filename=path)
    lines = source.splitlines()
    gateway_module = path.startswith("discordbot/") and path not in R4_EXEMPT
    found: list[Violation] = []
    for node in ast.walk(tree):
        line = getattr(node, "lineno", 0)
        if (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and R1_DM_CHANNEL_URL in node.value
            and path != DM_MODULE
        ):
            found.append(Violation(path, line, "R1", "DM channel URL"))

        r2_names: list[str] = []
        if isinstance(node, ast.Name | ast.Attribute):
            r2_names.append(_name_of(node) or "")
        elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            r2_names.append(node.name)
        elif isinstance(node, ast.ImportFrom | ast.Import):
            r2_names.extend(a.name.rsplit(".", 1)[-1] for a in node.names)
        for name in r2_names:
            if name in R2_NAMES and path not in R2_ALLOWED.get(name, frozenset()):
                found.append(Violation(path, line, "R2", name))

        if (
            isinstance(node, ast.Attribute)
            and node.attr in R3_ATTRS
            and path != GATEWAY_DM_MODULE
        ):
            found.append(Violation(path, line, "R3", f".{node.attr}"))

        if (
            gateway_module
            and isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "send"
            and _name_of(node.func.value) not in R4_SAFE_RECEIVERS
        ):
            reason = _r4_comment(lines, node)
            if reason is None:
                found.append(
                    Violation(path, line, "R4", ".send() outside followup/response")
                )
            elif not reason:
                found.append(
                    Violation(path, line, "R4", "dm-guard comment without a reason")
                )

        if (
            isinstance(node, ast.Attribute)
            and node.attr in R5_ATTRS
            and isinstance(node.ctx, ast.Load)
            and path not in R5_DM_MODULES
            and path not in R5_NON_DM_FILES
        ):
            found.append(Violation(path, line, "R5", f"reads .{node.attr}"))

    found.extend(_check_r6(path, tree))
    return sorted(set(found), key=lambda v: (v.path, v.line, v.rule, v.detail))


def scan_sources(paths: Iterable[Path]) -> list[Violation]:
    base: Path = settings.BASE_DIR_PATH
    violations: list[Violation] = []
    for path in paths:
        rel = path.relative_to(base).as_posix()
        violations.extend(check_source(rel, path.read_text()))
    return violations


def _is_runner_test_module(rel: Path) -> bool:
    return rel.name == "tests.py" or "tests" in rel.parts[:-1]


def _all_backend_files(base: Path) -> list[Path]:
    return sorted(
        p
        for p in base.rglob("*.py")
        if not SKIP_DIRS.intersection(p.relative_to(base).parts)
    )


def _module_path(base: Path, module: str) -> Path | None:
    parts = module.split(".")
    for candidate in (
        base.joinpath(*parts).with_suffix(".py"),
        base.joinpath(*parts, "__init__.py"),
    ):
        if candidate.is_file() and not SKIP_DIRS.intersection(
            candidate.relative_to(base).parts
        ):
            return candidate
    return None


def _module_name(base: Path, path: Path) -> str:
    rel = path.relative_to(base).with_suffix("")
    parts = rel.parts[:-1] if rel.name == "__init__" else rel.parts
    return ".".join(parts)


def _local_imports(base: Path, path: Path) -> set[Path]:
    tree = ast.parse(path.read_text(), filename=str(path))
    package = _module_name(base, path)
    if path.name != "__init__.py":
        package = package.rpartition(".")[0]
    found: set[Path] = set()
    for node in ast.walk(tree):
        modules: list[str] = []
        if isinstance(node, ast.Import):
            modules = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                anchor = package.split(".") if package else []
                anchor = anchor[: len(anchor) - (node.level - 1)]
                root = ".".join([*anchor, *([node.module] if node.module else [])])
            else:
                root = node.module or ""
            modules = [
                root,
                *(f"{root}.{a.name}" if root else a.name for a in node.names),
            ]
        for module in modules:
            target = _module_path(base, module) if module else None
            if target is not None:
                found.add(target)
    return found


def _view_modules(patterns: Iterable[URLPattern | URLResolver]) -> set[str]:
    modules: set[str] = set()
    for pattern in patterns:
        if isinstance(pattern, URLResolver):
            modules |= _view_modules(pattern.url_patterns)
        else:
            modules.add(pattern.callback.__module__)
    return modules


def test_helper_view_files(base: Path) -> set[Path]:
    """``tests.urls`` view modules and every backend module they import."""
    urls = import_module("tests.urls")
    pending = [
        p
        for p in (_module_path(base, m) for m in _view_modules(urls.urlpatterns))
        if p is not None
    ]
    seen: set[Path] = set()
    while pending:
        path = pending.pop()
        if path in seen:
            continue
        seen.add(path)
        pending.extend(_local_imports(base, path) - seen)
    return seen


test_helper_view_files.__test__ = False  # type: ignore[attr-defined]


def scanned_files() -> list[Path]:
    base: Path = settings.BASE_DIR_PATH
    files = {
        p
        for p in _all_backend_files(base)
        if not _is_runner_test_module(p.relative_to(base))
    }
    return sorted(files | test_helper_view_files(base))


def _kind_references(paths: Iterable[Path]) -> set[str]:
    base: Path = settings.BASE_DIR_PATH
    refs: set[str] = set()
    for path in paths:
        if path.relative_to(base).as_posix() in KIND_DEFINITION_FILES:
            continue
        for node in ast.walk(ast.parse(path.read_text(), filename=str(path))):
            if (
                isinstance(node, ast.Attribute)
                and isinstance(node.value, ast.Name)
                and node.value.id == "DMKind"
            ):
                refs.add(node.attr)
    return refs


def _flags(source: str, path: str = "discordbot/bad.py") -> set[str]:
    return {v.rule for v in check_source(path, source)}


class RuleSelfTests(SimpleTestCase):
    def test_rule_R1_flags_url(self) -> None:
        source = "URL = 'https://discord.com/api/v10/users/@me/channels'\n"
        self.assertIn("R1", _flags(source, "events/tasks.py"))
        self.assertNotIn("R1", _flags(source, DM_MODULE))

    def test_rule_R2_flags_helpers(self) -> None:
        for source in (
            "from discordbot.utils import sync_send_dm\n",
            "utils.sync_create_dm_channel('1')\n",
            "def sync_send_dm(x):\n    return x\n",
            "from discordbot.dm import _open_dm_channel\n",
        ):
            with self.subTest(source=source):
                self.assertIn("R2", _flags(source, "events/tasks.py"))
        self.assertNotIn("R2", _flags("_open_dm_channel('1')\n", DM_MODULE))
        self.assertIn("R2", _flags("sync_send_dm('1')\n", DM_MODULE))

    def test_rule_R3_flags_dm_openers(self) -> None:
        for source in (
            "async def f(i):\n    await i.user.create_dm()\n",
            "async def f(c, uid):\n    await c.fetch_user(uid)\n",
            "def f(c, uid):\n    return c.get_user(uid)\n",
            "def f(u):\n    return u.dm_channel\n",
            "async def f(client, uid):\n    await client.http.start_private_message(uid)\n",
            "def f(bot, cid):\n    return bot.get_partial_messageable(cid)\n",
        ):
            with self.subTest(source=source):
                self.assertIn("R3", _flags(source))
        self.assertNotIn(
            "R3",
            _flags(
                "async def f(i):\n    await i.user.create_dm()\n", GATEWAY_DM_MODULE
            ),
        )

    def test_rule_R4_flags_send(self) -> None:
        for source in (
            "async def f(discord_user):\n    await discord_user.send('hi')\n",
            "async def f(client, uid):\n    await (await client.fetch_user(uid)).send('hi')\n",
            "async def f(bot, cid):\n    await bot.get_partial_messageable(cid).send('x')\n",
            "async def f(i):\n    await i.user.send('hi')\n",
            "async def f(channel):\n    await channel.send('hi')\n",
        ):
            with self.subTest(source=source):
                self.assertIn("R4", _flags(source))

    def test_rule_R4_allows_followup_response_and_reason(self) -> None:
        for source in (
            "async def f(i):\n    await i.followup.send('hi', ephemeral=True)\n",
            "async def f(i):\n    await i.response.send('x')\n",
            "async def f(ch):\n    await ch.send('x')  # dm-guard: not-a-dm guild text channel\n",
        ):
            with self.subTest(source=source):
                self.assertNotIn("R4", _flags(source))
        self.assertNotIn(
            "R4", _flags("async def f(c):\n    await c.send('x')\n", "events/tasks.py")
        )
        self.assertNotIn(
            "R4", _flags("async def f(c):\n    await c.send('x')\n", GATEWAY_DM_MODULE)
        )

    def test_R4_comment_requires_reason(self) -> None:
        violations = check_source(
            "discordbot/bad.py",
            "async def f(ch):\n    await ch.send('x')  # dm-guard: not-a-dm\n",
        )
        self.assertEqual(
            [(v.rule, v.detail) for v in violations],
            [("R4", "dm-guard comment without a reason")],
        )

    def test_rule_R5_flags_message_id_read(self) -> None:
        source = "def f(log):\n    return log.discord_message_id\n"
        self.assertIn("R5", _flags(source, "events/new_module.py"))
        self.assertIn(
            "R5",
            _flags("def f(row):\n    return row.discord_channel_id\n", "org/x.py"),
        )
        self.assertNotIn("R5", _flags(source, LEDGER_MODULE))
        self.assertNotIn("R5", _flags(source, "org/leadership/review_dm.py"))
        self.assertNotIn(
            "R5", _flags("def f(row, v):\n    row.discord_message_id = v\n", "org/x.py")
        )

    def test_rule_R5_non_dm_file_is_allowed(self) -> None:
        source = (
            "from discordbot.models import DiscordMessageLog\n"
            "def f(pk):\n"
            "    return DiscordMessageLog.objects.get(pk=pk).discord_message_id\n"
        )
        self.assertIn("R5", _flags(source, "events/unlisted.py"))
        self.assertNotIn("R5", _flags(source, "events/tasks.py"))

    def test_r5_non_dm_entries_have_reasons(self) -> None:
        for path, reason in R5_NON_DM_FILES.items():
            with self.subTest(path=path):
                self.assertTrue(reason.strip(), f"{path} needs a reason")
                self.assertNotIn(path, R5_DM_MODULES)

    def test_rule_R6_flags_ledger_update(self) -> None:
        for source in (
            "def f(pk):\n    DiscordDM.objects.filter(pk=pk).update(status='sent')\n",
            "def f(pk):\n    DiscordDM.objects.filter(pk=pk).delete()\n",
            "def f(pk):\n    row = DiscordDM.objects.get(pk=pk)\n    row.save()\n",
            "def f(pk):\n    M = apps.get_model('discordbot', 'DiscordDM')\n"
            "    M.objects.filter(pk=pk).update(error='')\n",
        ):
            with self.subTest(source=source):
                self.assertIn("R6", _flags(source, "org/x.py"))
        self.assertNotIn(
            "R6",
            _flags(
                "def f(pk):\n    DiscordDM.objects.filter(pk=pk).update(error='')\n",
                LEDGER_MODULE,
            ),
        )
        self.assertNotIn(
            "R6",
            _flags(
                "def f(o):\n    o.save()\ndef g():\n    return DiscordDM\n", "org/x.py"
            ),
        )

    def test_clean_source_has_no_violations(self) -> None:
        source = (
            "from discordbot.dm import DMRequest, send_dm\n"
            "def f(req):\n    return send_dm(req)\n"
        )
        self.assertEqual(check_source("events/tasks.py", source), [])


class RepoGuardTests(SimpleTestCase):
    def test_scan_set_includes_discordbot_test_utils(self) -> None:
        base: Path = settings.BASE_DIR_PATH
        files = {p.relative_to(base).as_posix() for p in scanned_files()}
        self.assertIn("discordbot/test_utils.py", files)
        self.assertIn("tests/test_events_discord.py", files)
        self.assertIn(DM_MODULE, files)
        self.assertNotIn("discordbot/tests/test_dm_choke_point.py", files)
        self.assertNotIn("opsnotices/tests/test_discord_guard.py", files)
        self.assertFalse(any("/migrations/" in f for f in files))

    def test_repo_has_no_violations(self) -> None:
        violations = scan_sources(scanned_files())
        self.assertEqual(violations, [], "\n" + "\n".join(str(v) for v in violations))

    def test_r5_non_dm_entries_not_stale(self) -> None:
        base: Path = settings.BASE_DIR_PATH
        for path in R5_NON_DM_FILES:
            with self.subTest(path=path):
                source = (base / path).read_text()
                hits = [
                    n
                    for n in ast.walk(ast.parse(source))
                    if isinstance(n, ast.Attribute)
                    and n.attr in R5_ATTRS
                    and isinstance(n.ctx, ast.Load)
                ]
                self.assertTrue(hits, f"{path} no longer reads a Discord id; drop it")

    def test_every_kind_has_key_and_reference(self) -> None:
        refs = _kind_references(scanned_files())
        for kind in DMKind:
            with self.subTest(kind=kind.value):
                self.assertIn(kind, KEY_BUILDERS)
                if kind in PENDING_KINDS:
                    continue
                self.assertIn(kind.name, refs, f"DMKind.{kind.name} is never sent")
