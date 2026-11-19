import ast
from contextlib import ExitStack
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import requests
from django.conf import settings
from django.test import SimpleTestCase

from discordbot import utils as discord_utils
from events.tests.base import EventTestCase
from opsnotices.models import OpsNotice
from opsnotices.registry import isolated_registry
from opsnotices.services import emit_notice, resolve_notice
from opsnotices.signals import notice_emitted, notice_resolved
from opsnotices.tests.types import register_test_types

# Module paths (relative to backend/) allowed to reach Discord; #562 adds opsnotices/dispatch.py.
ALLOWED_SENDERS: frozenset[str] = frozenset()

FORBIDDEN_MODULES: tuple[str, ...] = (
    "discordbot",
    "events.discord",
    "discord",
    "aiohttp",
)
FORBIDDEN_PREFIXES: tuple[str, ...] = ("sync_send_", "sync_edit_", "sync_create_dm")
FORBIDDEN_NAMES: frozenset[str] = frozenset(
    {
        "send_dm",
        "sync_send_dm",
        "sync_send_dm_result",
        "_send_dm_raw",
        "create_dm",
        "send_modal_v2",
        "_rate_limited_request",
    }
)
FORBIDDEN_HOSTS: tuple[str, ...] = ("discord.com", "discordapp.com")
FIXED_TARGETS: tuple[str, ...] = (
    "opsnotices/registry.py",
    "opsnotices/services.py",
    "opsnotices/signals.py",
    "opsnotices/internal_views.py",
    "opsnotices/views.py",
)


def _forbidden_module(name: str) -> bool:
    return any(name == m or name.startswith(f"{m}.") for m in FORBIDDEN_MODULES)


def _forbidden_name(name: str) -> bool:
    return name in FORBIDDEN_NAMES or name.startswith(FORBIDDEN_PREFIXES)


def find_violations(source: str, path: str) -> list[str]:
    tree = ast.parse(source, filename=path)
    found: list[str] = []
    for node in ast.walk(tree):
        line = getattr(node, "lineno", 0)
        if isinstance(node, ast.Import):
            for alias in node.names:
                if _forbidden_module(alias.name):
                    found.append(f"{path}:{line}: import {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if node.level == 0 and _forbidden_module(module):
                found.append(f"{path}:{line}: from {module} import")
            for alias in node.names:
                full = f"{module}.{alias.name}" if module else alias.name
                if _forbidden_name(alias.name) or (
                    node.level == 0 and _forbidden_module(full)
                ):
                    found.append(f"{path}:{line}: imports {alias.name}")
        elif isinstance(node, ast.Name) and _forbidden_name(node.id):
            found.append(f"{path}:{line}: name {node.id}")
        elif isinstance(node, ast.Attribute) and _forbidden_name(node.attr):
            found.append(f"{path}:{line}: attribute {node.attr}")
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            if any(host in node.value for host in FORBIDDEN_HOSTS):
                found.append(f"{path}:{line}: Discord URL string")
            elif node.value != "discord" and _forbidden_module(node.value):
                found.append(f"{path}:{line}: module string {node.value}")
    return found


def _calls_register_notice_type(tree: ast.AST) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            name = (
                func.attr
                if isinstance(func, ast.Attribute)
                else getattr(func, "id", "")
            )
            if name == "register_notice_type":
                return True
    return False


def notice_modules(base: Path) -> list[Path]:
    targets: set[Path] = {base / rel for rel in FIXED_TARGETS}
    targets.update(base.glob("*/ops_notices.py"))
    for path in base.glob("*/**/*.py"):
        rel = path.relative_to(base)
        if "tests" in rel.parts or "migrations" in rel.parts:
            continue
        source = path.read_text()
        if "register_notice_type" in source and _calls_register_notice_type(
            ast.parse(source, filename=str(path))
        ):
            targets.add(path)
    return sorted(
        p
        for p in targets
        if p.exists() and p.relative_to(base).as_posix() not in ALLOWED_SENDERS
    )


def _imports_emit_service(tree: ast.AST) -> list[int]:
    lines: list[int] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if any(a.name == "opsnotices.services" for a in node.names):
                lines.append(node.lineno)
        elif isinstance(node, ast.ImportFrom) and node.level == 0:
            if node.module == "opsnotices.services" or (
                node.module == "opsnotices"
                and any(a.name == "services" for a in node.names)
            ):
                lines.append(node.lineno)
    return lines


class DiscordGuardTests(SimpleTestCase):
    def test_self_test_flags_synthetic_violation(self) -> None:
        samples = [
            "from discordbot.utils import sync_send_dm",
            "import discord",
            "import aiohttp",
            "from events import discord",
            "from events.discord import anything",
            "utils.sync_edit_message(1, 2)",
            "sync_create_dm_channel(1)",
            "x._rate_limited_request('POST', u)",
            "requests.post('https://discord.com/api/v10/channels/1/messages')",
            "importlib.import_module('discordbot.utils')",
        ]
        for source in samples:
            with self.subTest(source=source):
                self.assertNotEqual(find_violations(source, "<synthetic>"), [])

    def test_clean_source_has_no_violations(self) -> None:
        source = (
            "from opsnotices.registry import register_notice_type\n"
            "SYSTEM = 'discord'\n"
            "def summary(p):\n    return f'Member {p.member_id}'\n"
        )
        self.assertEqual(find_violations(source, "<synthetic>"), [])

    def test_notice_modules_never_reach_discord(self) -> None:
        base: Path = settings.BASE_DIR_PATH
        modules = notice_modules(base)
        self.assertIn(base / "opsnotices" / "services.py", modules)
        violations: list[str] = []
        for path in modules:
            violations.extend(
                find_violations(path.read_text(), str(path.relative_to(base)))
            )
        self.assertEqual(violations, [])

    def test_celery_tasks_never_import_emit_service(self) -> None:
        base: Path = settings.BASE_DIR_PATH
        task_files = sorted({*base.glob("*/tasks.py"), *base.glob("*/tasks/**/*.py")})
        self.assertNotEqual(task_files, [])
        offenders: list[str] = []
        for path in task_files:
            tree = ast.parse(path.read_text(), filename=str(path))
            offenders.extend(
                f"{path.relative_to(base)}:{line}"
                for line in _imports_emit_service(tree)
            )
        self.assertEqual(offenders, [])


class EmitNoNetworkTests(EventTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.enterContext(isolated_registry())
        register_test_types()
        self.signals: list[str] = []
        notice_emitted.connect(self._on_emitted, weak=False)
        notice_resolved.connect(self._on_resolved, weak=False)
        self.addCleanup(notice_emitted.disconnect, self._on_emitted)
        self.addCleanup(notice_resolved.disconnect, self._on_resolved)

    def _on_emitted(self, sender: type[OpsNotice], **kwargs: Any) -> None:
        self.signals.append("emitted")

    def _on_resolved(self, sender: type[OpsNotice], **kwargs: Any) -> None:
        self.signals.append("resolved")

    def test_emit_calls_no_network(self) -> None:
        org, event = self.org, self.event
        helper_names = sorted(
            name
            for name in dir(discord_utils)
            if _forbidden_name(name) and callable(getattr(discord_utils, name))
        )
        self.assertIn("sync_send_dm", helper_names)
        self.assertIn("_rate_limited_request", helper_names)
        mocks: dict[str, MagicMock] = {}
        with ExitStack() as stack:
            for name in helper_names:
                mocks[name] = stack.enter_context(
                    patch.object(
                        discord_utils,
                        name,
                        create=False,
                        side_effect=AssertionError(name),
                    )
                )
            network_targets: tuple[tuple[Any, str], ...] = (
                (requests, "post"),
                (requests, "request"),
                (requests.Session, "request"),
            )
            for target, attr in network_targets:
                mocks[f"{target.__name__}.{attr}"] = stack.enter_context(
                    patch.object(target, attr, side_effect=AssertionError(attr))
                )
            self.assertEqual(len(mocks), len(helper_names) + len(network_targets))
            with self.captureOnCommitCallbacks(execute=True):
                notice = emit_notice(
                    "test.alert",
                    {"member_id": 1, "reason": "late"},
                    organization=org,
                    event=event,
                )
            assert notice is not None
            with self.captureOnCommitCallbacks(execute=True):
                resolved = resolve_notice(
                    "test.alert",
                    "member:1",
                    organization=org,
                    event=event,
                    reason="fixed",
                )
            assert resolved is not None
        self.assertEqual(self.signals, ["emitted", "resolved"])
        called = sorted(name for name, mock in mocks.items() if mock.called)
        self.assertEqual(called, [])
