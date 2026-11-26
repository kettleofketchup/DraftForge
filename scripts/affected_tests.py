"""Pick the backend test labels and Vitest files a branch's changes can reach.

Backend: reverse import closure over backend/ (ast, no Django import), plus
whole-app labels for code Django reaches by name rather than by import (apps,
signals, tasks, admin, urls/routing, management commands, migrations). Shared
config escalates to the full suite. Frontend: `vitest related` on the changed
sources, or the full suite when test config changes.

This narrows iteration runs only; the full suite stays the merge gate.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import subprocess
import sys
from collections.abc import Iterable, Iterator
from dataclasses import asdict, dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKEND = "backend"
FRONTEND = "frontend"

ALL = "ALL"

BACKEND_FULL = (
    re.compile(r"^backend/backend/"),
    re.compile(r"^backend/(conftest\.py|pytest\.ini|manage\.py|__init__\.py)$"),
    re.compile(r"^backend/tests/__init__\.py$"),
    re.compile(r"^(pyproject\.toml|poetry\.lock)$"),
    re.compile(r"^backend/(Dockerfile|requirements[^/]*\.txt)$"),
    re.compile(r"^docker/\.env\.test$"),
    re.compile("^" + re.escape("docker/docker-compose.test.yaml") + "$"),
)
# Modules Django loads by name; a change there reaches the owning app's tests.
BY_NAME = re.compile(
    r"(^|\.)(apps|signals|receivers|handlers|tasks|admin|urls|routing|consumers)(\.|$)"
    r"|\.signals\.|\.management\.commands\."
)
ROUTED = re.compile(r"(^|\.)(urls|routing)$")
BOUNDARIES = "tests.test_app_boundaries"
CELERY_SETTINGS = "app.tests.test_celery_settings"
CELERY_TRIGGER = re.compile(r"(^|\.)(models|apps|signals|receivers|tasks)(\.|$)")

FRONTEND_FULL = (
    re.compile(
        r"^frontend/(vitest\.config\.ts|vitest\.setup\.ts|vite\.config\.ts"
        r"|package(-lock)?\.json|tsconfig[^/]*\.json)$"
    ),
)
FRONTEND_SOURCE = re.compile(r"^frontend/(app|tests/unit)/.+\.(ts|tsx|js|jsx)$")


@dataclass
class Plan:
    backend: list[str] | str = field(default_factory=list)
    vitest: list[str] | str = field(default_factory=list)
    scripts: bool = False
    reasons: list[str] = field(default_factory=list)


def changed_files(base: str, root: Path = ROOT) -> list[str]:
    def git(*args: str) -> list[str]:
        out = subprocess.run(
            ["git", "-C", str(root), *args], capture_output=True, text=True, check=True
        ).stdout
        return [line for line in out.splitlines() if line]

    merge_base = git("merge-base", base, "HEAD")[0]
    files = set(git("diff", "--name-only", merge_base))
    files |= set(git("ls-files", "--others", "--exclude-standard"))
    return sorted(files)


def _is_package_dir(d: Path, backend: Path) -> bool:
    while d != backend:
        if not (d / "__init__.py").is_file():
            return False
        d = d.parent
    return True


def backend_modules(backend: Path) -> dict[str, Path]:
    mods: dict[str, Path] = {}
    for path in backend.rglob("*.py"):
        rel = path.relative_to(backend)
        if not _is_package_dir(path.parent, backend) or path.parent == backend:
            continue
        parts = list(rel.with_suffix("").parts)
        if parts[-1] == "__init__":
            parts.pop()
        mods[".".join(parts)] = path
    return mods


def module_of(rel_path: str) -> str | None:
    if not rel_path.startswith(f"{BACKEND}/") or not rel_path.endswith(".py"):
        return None
    parts = rel_path[len(BACKEND) + 1 : -3].split("/")
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts) or None


def _prefixes(name: str) -> Iterator[str]:
    parts = name.split(".")
    for i in range(1, len(parts) + 1):
        yield ".".join(parts[:i])


def imports_of(module: str, path: Path, known: dict[str, Path]) -> set[str]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (SyntaxError, UnicodeDecodeError):
        return set()
    is_pkg = path.name == "__init__.py"
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                found.update(_prefixes(alias.name))
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                pkg = module.split(".")
                if not is_pkg:
                    pkg = pkg[:-1]
                pkg = pkg[: len(pkg) - (node.level - 1)] if node.level > 1 else pkg
                base = ".".join([*pkg, *([node.module] if node.module else [])])
            else:
                base = node.module or ""
            if not base:
                continue
            found.update(_prefixes(base))
            for alias in node.names:
                found.add(f"{base}.{alias.name}")
    return {m for m in found if m in known and m != module}


def reverse_graph(known: dict[str, Path]) -> dict[str, set[str]]:
    rev: dict[str, set[str]] = {m: set() for m in known}
    for mod, path in known.items():
        for dep in imports_of(mod, path, known):
            rev[dep].add(mod)
    return rev


def closure(seeds: Iterable[str], rev: dict[str, set[str]]) -> set[str]:
    seen = set(seeds)
    stack = list(seen)
    while stack:
        for importer in rev.get(stack.pop(), ()):
            if importer not in seen:
                seen.add(importer)
                stack.append(importer)
    return seen


def is_test_module(module: str, known: dict[str, Path]) -> bool:
    """A test*.py file Django's discovery would run (not a package or helper)."""
    path = known.get(module)
    return path is not None and path.name.startswith("test")


def _app(module: str) -> str:
    return module.split(".")[0]


def _collapse(labels: set[str]) -> list[str]:
    """Drop labels already covered by a broader one (`org` covers `org.tests.x`)."""
    out = sorted(labels, key=lambda s: (s.count("."), s))
    kept: list[str] = []
    for label in out:
        if not any(label == k or label.startswith(f"{k}.") for k in kept):
            kept.append(label)
    return sorted(kept)


def plan_backend(changed: list[str], root: Path, reasons: list[str]) -> list[str] | str:
    full = [f for f in changed if any(p.search(f) for p in BACKEND_FULL)]
    if full:
        reasons.append(
            f"backend: full suite, shared config changed ({', '.join(full[:5])})"
        )
        return ALL
    backend = root / BACKEND
    seeds = {m for f in changed if (m := module_of(f))}
    migrations = {
        f.split("/")[1] for f in changed if re.match(r"^backend/[^/]+/migrations/", f)
    }
    if not seeds and not migrations:
        return []
    known = backend_modules(backend)
    reach = closure(seeds, reverse_graph(known))
    labels = {m for m in reach if is_test_module(m, known) and m in known}
    apps: set[str] = set()
    for m in reach:
        if ROUTED.search(m) and _app(m) != "backend":
            apps.add(_app(m))
    for m in seeds:
        if BY_NAME.search(m):
            apps.add(_app(m))
        cmd = re.search(r"\.management\.commands\.([^.]+)$", m)
        if cmd:
            labels |= _tests_mentioning(cmd.group(1), known)
    for app in migrations:
        apps.add(app)
        labels |= {m for m in known if is_test_module(m, known) and "migration" in m}
    apps = {
        a for a in apps if any(is_test_module(m, known) and _app(m) == a for m in known)
    }
    if apps:
        reasons.append(
            f"backend: whole apps loaded by name or routing: {', '.join(sorted(apps))}"
        )
    labels |= apps
    if seeds:
        labels.add(BOUNDARIES)
    if any(CELERY_TRIGGER.search(m) for m in seeds):
        labels.add(CELERY_SETTINGS)
    return _collapse({label for label in labels if label in known or label in apps})


def _tests_mentioning(word: str, known: dict[str, Path]) -> set[str]:
    pat = re.compile(rf"""["']{re.escape(word)}["']""")
    return {
        m
        for m, p in known.items()
        if is_test_module(m, known)
        and pat.search(p.read_text(encoding="utf-8", errors="ignore"))
    }


def plan_vitest(changed: list[str], root: Path, reasons: list[str]) -> list[str] | str:
    full = [f for f in changed if any(p.search(f) for p in FRONTEND_FULL)]
    if full:
        reasons.append(f"vitest: full suite, config changed ({', '.join(full)})")
        return ALL
    return sorted(
        f[len(FRONTEND) + 1 :]
        for f in changed
        if FRONTEND_SOURCE.match(f) and (root / f).is_file()
    )


def plan(changed: list[str], root: Path = ROOT) -> Plan:
    p = Plan()
    p.backend = plan_backend(changed, root, p.reasons)
    p.vitest = plan_vitest(changed, root, p.reasons)
    p.scripts = any(f.startswith(("scripts/", "just/", "justfile")) for f in changed)
    return p


def _show(value: list[str] | str) -> str:
    if value == ALL:
        return ALL
    return " ".join(value) if value else "NONE"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--base", default="origin/main")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--run", action="store_true", help="run the selected tests")
    ap.add_argument(
        "files", nargs="*", help="changed paths (default: git diff vs --base)"
    )
    ns = ap.parse_args(argv)
    p = plan(ns.files or changed_files(ns.base))
    if ns.json:
        print(json.dumps(asdict(p)))
        return 0
    print(f"backend: {_show(p.backend)}")
    print(f"vitest: {_show(p.vitest)}")
    print(f"scripts: {'yes' if p.scripts else 'no'}")
    for r in p.reasons:
        print(f"# {r}", file=sys.stderr)
    sys.stdout.flush()
    return run(p) if ns.run else 0


def commands(p: Plan, just: str = "just") -> list[tuple[list[str], Path]]:
    cmds: list[tuple[list[str], Path]] = []
    if p.backend == ALL:
        cmds.append(([just, "test::backend::all"], ROOT))
    elif p.backend:
        labels = " ".join(p.backend)
        cmds.append(
            (
                [
                    just,
                    "test::run",
                    f"python manage.py test --parallel auto -v 1 {labels}",
                ],
                ROOT,
            )
        )
    if p.vitest == ALL:
        cmds.append((["npx", "vitest", "run"], ROOT / FRONTEND))
    elif p.vitest:
        cmds.append((["npx", "vitest", "related", "--run", *p.vitest], ROOT / FRONTEND))
    if p.scripts:
        cmds.append(([just, "test::slots-unit"], ROOT))
        cmds.append(([just, "test::affected-unit"], ROOT))
    return cmds


def run(p: Plan) -> int:
    failed: list[str] = []
    for argv, cwd in commands(p):
        print(f"==> {' '.join(argv)}", flush=True)
        if subprocess.run(argv, cwd=cwd).returncode != 0:
            failed.append(argv[1])
    if failed:
        print(f"affected tests FAILED: {', '.join(failed)}", file=sys.stderr)
        return 1
    print("affected tests passed (the full suites still run in Verify and CI)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
