#!/usr/bin/env python3
"""Changelog fragments: validate changelog.d/ and assemble it into CHANGELOG.md.

    scripts/changelog.py check                  # every fragment rule; exit 1 on a problem
    scripts/changelog.py assemble VERSION DATE  # write ## [VERSION] - DATE, print paths
    scripts/changelog.py has-label NAME         # exit 0 if the PR has NAME, 1 if not, 2 on API error

PRs add files under changelog.d/<section>/ and never edit CHANGELOG.md, so a branch
that merges after a release cannot drop its notes under the version already released.
Stdlib only, so CI runs it on the bare runner python3. Tests: scripts/test_changelog.py.
"""

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from collections.abc import Mapping
from pathlib import Path
from typing import Any

POINTER = "<!-- Do not edit. Unreleased changes live in changelog.d/; `just version::set` assembles them here. -->"
FRAGMENT_DIR = "changelog.d"
NO_CHANGES = "- No notable changes."

SLUG = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
VERSION_RE = re.compile(r"\d+\.\d+\.\d+")
DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
RELEASE_HEADING = re.compile(r"^## \[([^\]]+)\]")
SUB_HEADING = re.compile(r"^### (.+?)\s*$")
LINK_DEFINITION = re.compile(r"^\[[^\]]+\]:\s")
FENCE = re.compile(r"^\s*(```|~~~)")

Section = dict[str, Any]
Released = list[tuple[str, str, list[str]]]


class ChangelogError(Exception):
    pass


def sections(root: Path) -> list[Section]:
    path = Path(root) / FRAGMENT_DIR / "sections.json"
    return json.loads(path.read_text(encoding="utf-8"))


def fragment_paths(root: Path) -> list[str]:
    """Tracked fragment paths. git ls-files, not a walk: ignored debris must not count."""
    known = {s["dir"] for s in sections(root)}
    return sorted(p for p in _tracked(root) if _is_fragment(p, known))


def _tracked(root: Path) -> list[str]:
    out = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-z", "--", FRAGMENT_DIR],
        check=True,
        capture_output=True,
    ).stdout
    return [p for p in out.decode().split("\0") if p]


def _is_fragment(path: str, known: set[str]) -> bool:
    parts = path.split("/")
    return (
        len(parts) == 3
        and parts[1] in known
        and parts[2].endswith(".md")
        and bool(SLUG.match(parts[2][:-3]))
    )


def _drop_fences(lines: list[str]) -> list[str]:
    kept, inside = [], False
    for line in lines:
        if FENCE.match(line):
            inside = not inside
        elif not inside:
            kept.append(line)
    return kept


def _collapse(text: str) -> str:
    return " ".join(text.split())


def _bullets(lines: list[str]) -> list[str]:
    """Top-level bullets, continuation lines joined, whitespace collapsed."""
    found: list[str] = []
    is_open = False
    for line in _drop_fences(lines):
        if line.startswith("- "):
            found.append(line[2:])
            is_open = True
        elif is_open and line.startswith(" ") and line.strip():
            found[-1] += " " + line
        elif line.strip():
            is_open = False  # an unindented non-bullet line ends the bullet
    return [_collapse(b) for b in found if b.strip()]


def released(text: str) -> Released:
    """(version, heading, body lines) for every ### block under a released ## [X.Y.Z]."""
    blocks: Released = []
    version = heading = None
    for line in text.splitlines():
        release = RELEASE_HEADING.match(line)
        if release:
            name = release.group(1)
            version = name if VERSION_RE.fullmatch(name) else None
            heading = None
            continue
        sub = SUB_HEADING.match(line)
        if sub and version:
            heading = sub.group(1)
            blocks.append((version, heading, []))
            continue
        if version and heading:
            blocks[-1][2].append(line)
    return blocks


def _check_fragment(
    path: str, raw: bytes, section: Section, history: Released
) -> list[str]:
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return [f"{path}:1: not valid UTF-8"]
    if not text.strip():
        return [f"{path}:1: empty fragment"]
    lines = text.splitlines()
    problems: list[str] = []
    first = True
    inside = False
    for n, line in enumerate(lines, 1):
        if not line.strip():
            continue
        if not section["prose"]:
            if first and not line.startswith("- "):
                problems.append(
                    f"{path}:{n}: a {section['heading']} fragment must start with a '- ' bullet"
                )
            elif not first and not line.startswith(("- ", "  ")):
                problems.append(
                    f"{path}:{n}: start a new '- ' bullet or indent the continuation 2 spaces"
                )
        first = False
        if FENCE.match(line):
            inside = not inside
            continue
        if inside:
            continue
        stripped = line.lstrip()
        if stripped.startswith("#"):
            problems.append(
                f"{path}:{n}: no headings in a fragment; the section comes from its directory"
            )
        elif stripped.startswith("<!--"):
            problems.append(f"{path}:{n}: no HTML comments in a fragment")
        elif LINK_DEFINITION.match(stripped):
            problems.append(
                f"{path}:{n}: no link-reference definitions; use an inline link"
            )
    if inside:
        problems.append(f"{path}:{len(lines)}: unclosed code fence")
    if problems:
        return problems
    return _check_resurrection(path, lines, section, history)


def _check_resurrection(
    path: str, lines: list[str], section: Section, history: Released
) -> list[str]:
    hint = (
        "a release already consumed this fragment; delete the file "
        "(a genuinely new note needs a new slug)"
    )
    if section["prose"]:
        mine = _collapse("\n".join(_drop_fences(lines)))
        if not mine:
            return []
        for version, heading, body in history:
            if heading == section["heading"] and mine in _collapse(
                "\n".join(_drop_fences(body))
            ):
                return [f"{path}:1: released in {version}: {hint}"]
        return []
    shipped: dict[str, str] = {}
    for version, _heading, body in history:
        for bullet in _bullets(body):
            shipped.setdefault(bullet, version)
    for bullet in _bullets(lines):
        if bullet in shipped:
            return [f"{path}:1: released in {shipped[bullet]}: {hint}"]
    return []


def check(root: Path) -> list[str]:
    root = Path(root)
    try:
        config = sections(root)
    except (OSError, ValueError) as exc:
        return [f"{FRAGMENT_DIR}/sections.json:1: unreadable ({exc})"]
    by_dir = {s["dir"]: s for s in config}
    # No CHANGELOG.md (a branch that predates it): nothing released, nothing to resurrect.
    changelog = root / "CHANGELOG.md"
    history = (
        released(changelog.read_text(encoding="utf-8")) if changelog.exists() else []
    )
    problems: list[str] = []
    for path in sorted(_tracked(root)):
        if path in (f"{FRAGMENT_DIR}/sections.json", f"{FRAGMENT_DIR}/README.md"):
            continue
        if not _is_fragment(path, set(by_dir)):
            problems.append(
                f"{path}:1: not a fragment; use {FRAGMENT_DIR}/<section>/<slug>.md, sections: "
                + ", ".join(by_dir)
                + ", slug ^[a-z0-9][a-z0-9._-]*$"
            )
            continue
        full = root / path
        if not full.exists():
            problems.append(f"{path}:1: tracked but missing from the working tree")
            continue
        section = by_dir[path.split("/")[1]]
        problems += _check_fragment(path, full.read_bytes(), section, history)
    return problems


def render(root: Path, paths: list[str]) -> str:
    """The release body: sections.json order, fragments by code-point filename order."""
    root = Path(root)
    parts = []
    for section in sections(root):
        prefix = f"{FRAGMENT_DIR}/{section['dir']}/"
        mine = sorted(
            (p for p in paths if p.startswith(prefix)),
            key=lambda p: p.rsplit("/", 1)[1],
        )
        texts = [(root / p).read_text(encoding="utf-8").strip() for p in mine]
        texts = [t for t in texts if t]
        if texts:
            joined = ("\n\n" if section["prose"] else "\n").join(texts)
            parts.append(f"### {section['heading']}\n\n{joined}")
    return "\n\n".join(parts) or NO_CHANGES


def assemble(root: Path, version: str, date: str) -> list[str]:
    """Write ## [version] - date from the fragments; return the consumed paths.

    Deletes nothing: the caller removes the returned paths in the release commit.
    """
    root = Path(root)
    if not VERSION_RE.fullmatch(version):
        raise ChangelogError(f"version '{version}' is not MAJOR.MINOR.PATCH")
    if not DATE_RE.fullmatch(date):
        raise ChangelogError(f"date '{date}' is not YYYY-MM-DD")
    problems = check(root)
    if problems:
        raise ChangelogError("changelog.d/ fails check:\n" + "\n".join(problems))

    path = root / "CHANGELOG.md"
    text = path.read_text(encoding="utf-8")
    if re.search(rf"^## \[{re.escape(version)}\]", text, re.M):
        raise ChangelogError(
            f"CHANGELOG.md already has a [{version}] section; refusing to add a second."
        )
    match = re.search(r"^## \[Unreleased\][^\n]*\n", text, re.M)
    if not match:
        raise ChangelogError("CHANGELOG.md has no '## [Unreleased]' heading.")
    rest = text[match.end() :]
    nxt = re.search(r"^## \[", rest, re.M)
    body, tail = (rest[: nxt.start()], rest[nxt.start() :]) if nxt else (rest, "")
    if body.strip() not in ("", POINTER):
        raise ChangelogError(
            "CHANGELOG.md's [Unreleased] has content besides the pointer comment. "
            "Move it into a changelog.d/ fragment first; the release will not discard it."
        )

    paths = fragment_paths(root)
    section = f"## [{version}] - {date}\n\n{render(root, paths)}\n"
    new = text[: match.start()] + f"## [Unreleased]\n\n{POINTER}\n\n{section}"
    new += f"\n{tail}" if tail else ""
    path.write_text(new, encoding="utf-8")
    return paths


def has_label(name: str, env: Mapping[str, str] | None = None) -> bool:
    """Read the PR's labels live, so a re-run after labelling sees the new label."""
    env = os.environ if env is None else env
    event = json.loads(Path(env["GITHUB_EVENT_PATH"]).read_text(encoding="utf-8"))
    pr = event["pull_request"]
    token = env.get("GH_TOKEN") or env.get("GITHUB_TOKEN")
    if not token:
        print(
            "has-label: no GH_TOKEN; using the event payload's labels "
            "(frozen at trigger time)",
            file=sys.stderr,
        )
        return any(label["name"] == name for label in pr.get("labels", []))
    api = env.get("GITHUB_API_URL", "https://api.github.com").rstrip("/")
    url = f"{api}/repos/{env['GITHUB_REPOSITORY']}/issues/{pr['number']}/labels?per_page=100"
    if not url.startswith(("https://", "http://")):
        raise ChangelogError(f"refusing non-HTTP API URL {url!r}")
    request = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        labels = json.load(response)
    return any(label["name"] == name for label in labels)


# --- release: called by `inv version.set` (scripts/version.py) -----------------

RELEASE_PATHS: tuple[str, ...] = (
    "pyproject.toml",
    "docker/.env.prod",
    "docker/.env.release",
    "CHANGELOG.md",
    FRAGMENT_DIR,
)
# Also in just/ci.just (push exemption, resurrection --grep); keep the two in sync.
RELEASE_SUBJECT_RE = re.compile(r"^Updated version to [0-9]+\.[0-9]+\.[0-9]+$")


def release_subject(version: str) -> str:
    return f"Updated version to {version}"


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, text=True, check=False
    )


def release_preflight(
    root: Path,
    version: str,
    tag_version: bool = True,
    remote: str = "origin",
    branch: str = "main",
) -> None:
    """Refuse a release that could half-happen. Touches no file; raises ChangelogError."""
    root = Path(root)
    if not VERSION_RE.fullmatch(version):
        raise ChangelogError(f"version '{version}' is not MAJOR.MINOR.PATCH")
    if not tag_version:
        raise ChangelogError(
            "refusing to commit and push a release without a tag (no images would be "
            "built); use --no-commit for a local version bump"
        )
    if not (root / "CHANGELOG.md").exists():
        raise ChangelogError("CHANGELOG.md is missing; restore it from main")
    current = _git(root, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    if current != branch:
        raise ChangelogError(
            f"releases are cut from {branch} (on '{current}'); git switch {branch}"
        )
    if _git(root, "status", "--porcelain", "--untracked-files=no").stdout.strip():
        raise ChangelogError(
            "uncommitted changes to tracked files; commit or stash them first"
        )
    untracked = _git(
        root, "ls-files", "--others", "--exclude-standard", "--", FRAGMENT_DIR
    ).stdout.splitlines()
    if untracked:
        raise ChangelogError(
            "untracked files under changelog.d/ would miss the release: "
            + ", ".join(untracked)
            + "; commit or remove them"
        )
    fetch = _git(root, "fetch", "--tags", remote)
    if fetch.returncode != 0:
        raise ChangelogError(
            f"git fetch --tags {remote} failed: {fetch.stderr.strip()}"
        )
    head = _git(root, "rev-parse", "HEAD").stdout.strip()
    upstream = _git(root, "rev-parse", "-q", "--verify", f"{remote}/{branch}")
    if upstream.stdout.strip() != head:
        raise ChangelogError(
            f"HEAD is not {remote}/{branch}; update {branch} and retry"
        )
    # Remote first: the fetch above also copies a remote-only tag locally.
    remote_tag = _git(root, "ls-remote", "--tags", remote, f"refs/tags/{version}")
    if remote_tag.returncode != 0:
        raise ChangelogError(
            f"git ls-remote {remote} failed: {remote_tag.stderr.strip()}"
        )
    if remote_tag.stdout.strip():
        raise ChangelogError(f"tag {version} already exists on {remote}")
    local_tag = _git(root, "rev-parse", "-q", "--verify", f"refs/tags/{version}")
    if local_tag.returncode == 0:
        raise ChangelogError(
            f"tag {version} already exists locally (a leftover from a --no-commit run "
            f"can be removed with: git tag -d {version})"
        )


def assemble_release(root: Path, version: str, date: str) -> list[str]:
    """Assemble ## [version] - date and git rm the consumed fragments (staged)."""
    root = Path(root)
    paths = assemble(root, version, date)
    text = (root / "CHANGELOG.md").read_text(encoding="utf-8")
    if not re.search(rf"^## \[{re.escape(version)}\] - {re.escape(date)}$", text, re.M):
        raise ChangelogError(
            f"CHANGELOG.md has no '## [{version}] - {date}' section after assembling"
        )
    if paths:  # git rm with no paths is an error
        rm = _git(root, "rm", "-q", "--", *paths)
        if rm.returncode != 0:
            raise ChangelogError(
                f"git rm of consumed fragments failed: {rm.stderr.strip()}"
            )
    return paths


def rollback_release(root: Path) -> None:
    """Restore index and work tree for RELEASE_PATHS; nothing else is touched."""
    result = _git(root, "checkout", "HEAD", "--", *RELEASE_PATHS)
    if result.returncode != 0:
        raise ChangelogError(f"rollback failed: {result.stderr.strip()}")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--root", type=Path, default=Path(__file__).resolve().parents[1]
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check")
    asm = sub.add_parser("assemble")
    asm.add_argument("version")
    asm.add_argument("date")
    lab = sub.add_parser("has-label")
    lab.add_argument("name")
    args = parser.parse_args(argv)

    try:
        if args.cmd == "check":
            problems = check(args.root)
            for problem in problems:
                print(problem)
            if problems:
                print(
                    f"{len(problems)} changelog fragment problem(s); "
                    f"see {FRAGMENT_DIR}/README.md",
                    file=sys.stderr,
                )
            return 1 if problems else 0
        if args.cmd == "assemble":
            for path in assemble(args.root, args.version, args.date):
                print(path)
            return 0
        return 0 if has_label(args.name) else 1
    except urllib.error.HTTPError as exc:
        print(f"has-label: API error {exc.code}: {exc.reason}", file=sys.stderr)
        return 2
    except (urllib.error.URLError, TimeoutError) as exc:
        print(f"has-label: API error: {getattr(exc, 'reason', exc)}", file=sys.stderr)
        return 2
    except ChangelogError as exc:
        print(f"changelog.py: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
