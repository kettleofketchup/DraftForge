#!/usr/bin/env python3
"""Enforce DraftForge structured-logging taxonomy.

Every call to a structlog logger (a variable assigned from
`telemetry.logging.get_logger(...)`) must:

  1. pass a string-literal event name as the first positional arg
     (snake_case by convention; not an f-string / `%`-format string), and
  2. include both `system=` and `subsystem=` keyword arguments.

Only files that bind a logger via `get_logger(...)` are checked, so stdlib
`logging` users (telemetry/, settings.py, tests, management commands) are
ignored automatically.

A call that forwards `**kwargs` is exempt (the taxonomy may be supplied
dynamically or via bound context vars).

Usage:
    python backend/scripts/check_logging_taxonomy.py [PATH ...]

With no PATH, scans `backend/` recursively. Exits non-zero on any violation.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

LEVELS = {"debug", "info", "warning", "warn", "error", "exception", "critical"}


def _logger_vars(tree: ast.Module) -> set[str]:
    """Names bound from get_logger(...), e.g. `log = get_logger(__name__)`."""
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
            fn = node.value.func
            fname = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", None)
            if fname == "get_logger":
                for tgt in node.targets:
                    if isinstance(tgt, ast.Name):
                        names.add(tgt.id)
    return names


def check_file(path: Path) -> list[str]:
    try:
        tree = ast.parse(path.read_text(), filename=str(path))
    except SyntaxError as e:
        return [f"{path}:{e.lineno}: could not parse ({e.msg})"]

    loggers = _logger_vars(tree)
    if not loggers:
        return []

    problems: list[str] = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
            continue
        if node.func.attr not in LEVELS:
            continue
        if not (isinstance(node.func.value, ast.Name) and node.func.value.id in loggers):
            continue

        kw_names = {k.arg for k in node.keywords}
        if None in kw_names:  # **kwargs splat -> can't verify statically; exempt
            continue

        loc = f"{path}:{node.lineno}"
        # 1) event name = first positional string literal
        if not node.args or not (
            isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str)
        ):
            problems.append(f"{loc}: first arg must be a string-literal event name (no f-strings)")
        # 2) system + subsystem present
        missing = {"system", "subsystem"} - kw_names
        if missing:
            problems.append(f"{loc}: log call missing {', '.join(sorted(missing))}=")
    return problems


def _excluded(p: Path) -> bool:
    parts = set(p.parts)
    return "tests" in parts or "migrations" in parts or p.name.startswith("test_")


def iter_paths(args: list[str]):
    roots = [Path(a) for a in args] or [Path("backend")]
    for root in roots:
        if root.is_dir():
            yield from (p for p in sorted(root.rglob("*.py")) if not _excluded(p))
        elif root.suffix == ".py" and not _excluded(root):
            yield root


def main(argv: list[str]) -> int:
    problems: list[str] = []
    for p in iter_paths(argv):
        problems.extend(check_file(p))
    for line in problems:
        print(line)
    if problems:
        print(f"\n{len(problems)} logging-taxonomy violation(s).", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
