#!/usr/bin/env python3
"""Shellcheck every recipe in the justfile and its modules (`just ci::shellcheck`).

Each recipe is rendered with `just --dry-run --no-deps`, so interpolations are
evaluated the way just would run them, then checked with the shell it runs
under: the shebang interpreter, or the module's `set shell` for linewise
recipes (sh when unset). Recipes for other interpreters are listed as skipped.
Required parameters get the placeholder value "x".

Stdlib only: CI runs this on the bare runner python3, without the project venv.
Usage: python3 scripts/shellcheck_just.py [--root DIR] [--verbose] [recipe ...]
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SHELLS = {"sh", "bash", "dash", "ksh"}
PLACEHOLDER = "x"


@dataclass(frozen=True)
class Recipe:
    namepath: str
    source: str
    shebang: bool
    shell: str | None
    args: tuple[str, ...]


@dataclass(frozen=True)
class Finding:
    recipe: Recipe
    line: int
    level: str
    code: str
    message: str
    text: str


def _interpreter(command: str) -> str:
    parts = command.split()
    if not parts:
        return ""
    name = Path(parts[0]).name
    if name == "env":
        rest = [p for p in parts[1:] if not p.startswith("-")]
        name = Path(rest[0]).name if rest else ""
    return name


def _module_shell(settings: dict) -> str:
    shell = settings.get("shell")
    return _interpreter(shell["command"]) if shell else "sh"


def _placeholder_args(parameters: list[dict]) -> tuple[str, ...]:
    args: list[str] = []
    for p in parameters:
        if p["kind"] == "plus" or (p["kind"] == "singular" and p["default"] is None):
            args.append(PLACEHOLDER)
    return tuple(args)


def _walk(module: dict, source: str, root: Path) -> Iterator[Recipe]:
    src = module.get("source") or source
    try:
        rel = str(Path(src).resolve().relative_to(root.resolve()))
    except ValueError:
        rel = src
    shell = _module_shell(module["settings"])
    for recipe in module["recipes"].values():
        script = any(
            (isinstance(a, dict) and "script" in a) or a == "script"
            for a in recipe["attributes"]
        )
        yield Recipe(
            namepath=recipe["namepath"],
            source=rel,
            shebang=recipe["shebang"] or script,
            shell=None if recipe["shebang"] or script else shell,
            args=_placeholder_args(recipe["parameters"]),
        )
    for sub in module["modules"].values():
        yield from _walk(sub, src, root)


def recipes(just: str, root: Path = ROOT) -> list[Recipe]:
    dump = subprocess.run(
        [just, "--dump", "--dump-format", "json"],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return sorted(
        _walk(json.loads(dump), str(root / "justfile"), root), key=lambda r: r.namepath
    )


def render(just: str, recipe: Recipe, root: Path = ROOT) -> str:
    result = subprocess.run(
        [just, "--dry-run", "--no-deps", "--yes", recipe.namepath, *recipe.args],
        cwd=root,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"exit {result.returncode}")
    return result.stderr


def dialect(recipe: Recipe, body: str) -> str:
    if recipe.shebang:
        first = body.splitlines()[0] if body else ""
        return _interpreter(first[2:]) if first.startswith("#!") else ""
    return recipe.shell or "sh"


def check(recipe: Recipe, body: str, shell: str, shellcheck: str) -> list[Finding]:
    script = body if recipe.shebang else f"#!/usr/bin/env {shell}\n{body}"
    lines = script.splitlines()
    offset = 0 if recipe.shebang else 1
    with tempfile.NamedTemporaryFile("w", suffix=".sh", delete=False) as tmp:
        tmp.write(script)
        path = tmp.name
    try:
        result = subprocess.run(
            [shellcheck, f"--shell={shell}", "--format=json1", path],
            capture_output=True,
            text=True,
        )
    finally:
        os.unlink(path)
    if result.returncode not in (0, 1):
        raise RuntimeError(result.stderr.strip() or f"shellcheck exit {result.returncode}")
    out: list[Finding] = []
    for c in json.loads(result.stdout or '{"comments": []}')["comments"]:
        n = c["line"]
        out.append(
            Finding(
                recipe=recipe,
                line=n - offset,
                level=c["level"],
                code=f"SC{c['code']}",
                message=c["message"],
                text=lines[n - 1].strip() if 0 < n <= len(lines) else "",
            )
        )
    return out


def report(f: Finding) -> str:
    where = f"{f.recipe.source}: {f.recipe.namepath} (recipe line {f.line})"
    if os.environ.get("GITHUB_ACTIONS") == "true":
        return (
            f"::error file={f.recipe.source},title=shellcheck {f.code}::"
            f"{f.recipe.namepath} line {f.line}: {f.message}"
        )
    return f"{where}: {f.level} {f.code}: {f.message}\n    {f.text}"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("recipes", nargs="*", help="only these namepaths")
    parser.add_argument("--root", type=Path, default=ROOT, help="directory of the justfile")
    parser.add_argument("--verbose", action="store_true")
    ns = parser.parse_args(argv)

    just = os.environ.get("JUST", "just")
    shellcheck = os.environ.get("SHELLCHECK", "shellcheck")
    for tool in (just, shellcheck):
        if not shutil.which(tool):
            print(f"error: {tool} not found on PATH", file=sys.stderr)
            return 2

    selected = recipes(just, ns.root)
    if ns.recipes:
        wanted = set(ns.recipes)
        selected = [r for r in selected if r.namepath in wanted]
        missing = wanted - {r.namepath for r in selected}
        if missing:
            print(f"error: no recipe {', '.join(sorted(missing))}", file=sys.stderr)
            return 2

    findings: list[Finding] = []
    errors: list[str] = []
    skipped: list[str] = []
    checked = 0
    for recipe in selected:
        try:
            body = render(just, recipe, ns.root)
            shell = dialect(recipe, body)
            if shell not in SHELLS:
                skipped.append(f"{recipe.namepath} ({shell or 'no interpreter'})")
                continue
            findings += check(recipe, body, shell, shellcheck)
            checked += 1
        except (RuntimeError, json.JSONDecodeError) as exc:
            errors.append(f"{recipe.source}: {recipe.namepath}: {exc}")
        if ns.verbose:
            print(f"checked {recipe.namepath}", file=sys.stderr)

    for f in findings:
        print(report(f))
    for e in errors:
        print(f"error: {e}", file=sys.stderr)
    if skipped:
        print(f"skipped (not a shell): {', '.join(skipped)}", file=sys.stderr)
    version = subprocess.run(
        [shellcheck, "--version"], capture_output=True, text=True
    ).stdout.split("version:")[-1].split()[0]
    print(
        f"shellcheck {version}: {checked} recipes checked, "
        f"{len(findings)} finding(s), {len(errors)} render error(s)",
        file=sys.stderr,
    )
    return 1 if findings or errors else 0


if __name__ == "__main__":
    sys.exit(main())
