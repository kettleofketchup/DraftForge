#!/usr/bin/env python3
"""Changelog fragments: validate changelog.d/ and assemble it into CHANGELOG.md.

    scripts/changelog.py check           # every fragment rule; exit 1 on a problem
    scripts/changelog.py slug [BRANCH]   # the conventional fragment slug (default: current branch)
    scripts/changelog.py has-label NAME  # exit 0 if the PR has NAME, 1 if not, 2 on API error

The release (`just version::set`, scripts/version.py) calls release_preflight(),
fragment_paths() and release(); there is deliberately no CLI for assembling, since
that would leave the consumed fragments in place.

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
from collections.abc import Callable, Mapping
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
# An ATX heading: 1-6 '#' then whitespace or end of line. "#302 was the cause" is not one.
ATX_HEADING = re.compile(r"#{1,6}(\s|$)")
# A setext underline; under a text line it turns that line into an h1/h2.
SETEXT_UNDERLINE = re.compile(r"(=+|-+)\s*$")
# Also in just/ci.just (push exemption); keep the two in sync.
RELEASE_SUBJECT_RE = re.compile(r"^Updated version to [0-9]+\.[0-9]+\.[0-9]+$")
# A prose fragment shorter than this is not compared with released text: one short
# sentence ("Run the migrations.") legitimately recurs across releases. A consumed
# fragment restored at its old path is still caught by released_paths().
PROSE_MATCH_MIN = 60
# Same idea for bullets: "- Updated dependencies." may appear in every release.
BULLET_MATCH_MIN = 40

Section = dict[str, Any]
Released = list[tuple[str, str, list[str]]]


class ChangelogError(Exception):
    pass


def sections(root: Path) -> list[Section]:
    path = Path(root) / FRAGMENT_DIR / "sections.json"
    return json.loads(path.read_text(encoding="utf-8"))


def fragment_paths(root: Path) -> list[str]:
    """Tracked fragment paths: what a release consumes (its preflight refuses untracked)."""
    known = {s["dir"] for s in sections(root)}
    return sorted(p for p in _tracked(root) if _is_fragment(p, known))


def _ls(root: Path, *flags: str) -> list[str]:
    """git ls-files, not a walk: ignored debris must not count."""
    out = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-z", *flags, "--", FRAGMENT_DIR],
        check=True,
        capture_output=True,
    ).stdout
    return [p for p in out.decode().split("\0") if p]


def _tracked(root: Path) -> list[str]:
    return _ls(root)


def _untracked(root: Path) -> list[str]:
    """Not yet git-added and not ignored: checked so a bad fragment fails before commit."""
    return _ls(root, "--others", "--exclude-standard")


def suggest_slug(name: str) -> str:
    """Lowercase; each run outside [a-z0-9._-] becomes '-'; leading . _ - dropped."""
    slug = re.sub(r"[^a-z0-9._-]+", "-", name.lower()).lstrip("._-")
    return slug or "note"


def _shown(path: str) -> str:
    """path for output: escaped if it holds a newline or other unprintable character,
    so a crafted filename cannot start a line of its own (e.g. a ::workflow command)."""
    return path if path.isprintable() else ascii(path)


def _name_problem(path: str, known: list[str]) -> str | None:
    """Why path is not changelog.d/<section>/<slug>.md, with a suggested name."""
    if not path.isprintable():
        return "the file name has control or unprintable characters; rename it"
    parts = path.split("/")
    listed = ", ".join(known)
    if len(parts) != 3:
        where = "directly in" if len(parts) == 2 else "nested too deep in"
        stem = parts[-1].rsplit(".", 1)[0]
        return (
            f"{where} {FRAGMENT_DIR}/; a fragment is {FRAGMENT_DIR}/<section>/"
            f"{suggest_slug(stem)}.md (sections: {listed})"
        )
    section, name = parts[1], parts[2]
    if section not in known:
        return f"unknown section '{section}'; use one of: {listed}"
    if not name.endswith(".md"):
        stem = name.rsplit(".", 1)[0]
        return (
            f"extension must be .md; rename to "
            f"{FRAGMENT_DIR}/{section}/{suggest_slug(stem)}.md"
        )
    stem = name[:-3]
    if SLUG.match(stem):
        return None
    bad = sorted({c for c in stem if not re.fullmatch(r"[a-z0-9._-]", c)})
    if bad:
        why = "invalid character(s) " + " ".join(repr(c) for c in bad)
    else:
        why = "must start with a lowercase letter or digit"
    return (
        f"slug '{stem}': {why} (allowed: a-z 0-9 . _ -); rename to "
        f"{FRAGMENT_DIR}/{section}/{suggest_slug(stem)}.md"
    )


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


def _bullets(lines: list[str]) -> list[tuple[int, str]]:
    """(line number, text) of top-level bullets; continuations joined, whitespace collapsed."""
    found: list[tuple[int, str]] = []
    is_open = inside = False
    for n, line in enumerate(lines, 1):
        if FENCE.match(line):
            inside = not inside
            continue
        if inside:
            continue
        if line.startswith("- "):
            found.append((n, line[2:]))
            is_open = True
        elif is_open and line.startswith(" ") and line.strip():
            found[-1] = (found[-1][0], found[-1][1] + " " + line)
        elif line.strip():
            is_open = False  # an unindented non-bullet line ends the bullet
    return [(n, _collapse(b)) for n, b in found if b.strip()]


def _paragraphs(lines: list[str]) -> list[str]:
    """Blank-line separated blocks, whitespace collapsed so rewrapping does not matter."""
    blocks: list[str] = []
    current: list[str] = []
    for line in [*lines, ""]:
        if line.strip():
            current.append(line)
        elif current:
            blocks.append(_collapse(" ".join(current)))
            current = []
    return blocks


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


def released_paths(root: Path) -> dict[str, tuple[str, str]]:
    """Fragment path -> (version, short sha) of the latest release commit that removed it.

    Needs full history (CI checks out with fetch-depth 0); a shallow clone finds less.
    """
    result = subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "log",
            "--diff-filter=D",
            "-E",
            f"--grep={RELEASE_SUBJECT_RE.pattern}",
            "--name-only",
            "--format=%x00%h %s",
            "--",
            FRAGMENT_DIR,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:  # e.g. a repo with no commits yet
        return {}
    found: dict[str, tuple[str, str]] = {}
    for chunk in result.stdout.split("\0")[1:]:
        lines = [line.strip() for line in chunk.strip().splitlines() if line.strip()]
        if not lines:
            continue
        sha, _, subject = lines[0].partition(" ")
        for path in lines[1:]:
            found.setdefault(path, (subject.rsplit(" ", 1)[-1], sha))
    return found


def _unreleased_problems(text: str) -> list[str]:
    """[Unreleased] holds only the pointer; the release refuses anything else."""
    match = re.search(r"^## \[Unreleased\][^\n]*\n", text, re.M)
    if not match:
        return ["CHANGELOG.md:1: no '## [Unreleased]' heading; restore it from main"]
    first = text[: match.end()].count("\n") + 1
    for n, line in enumerate(text[match.end() :].splitlines(), first):
        if line.startswith("## ["):
            break
        if line.strip() and line.strip() != POINTER:
            return [
                f"CHANGELOG.md:{n}: [Unreleased] must hold only the pointer comment; "
                f"move these lines into {FRAGMENT_DIR}/<section>/<branch-slug>.md "
                "and revert the CHANGELOG.md hunk"
            ]
    return []


def _content(line: str, prose: bool) -> tuple[int, str]:
    """(indent relative to the block the line belongs to, the line without it).

    A prose fragment's block is the top level; a bullet fragment's is the list item,
    whose content starts 2 columns in. 4 or more columns of relative indent is an
    indented code block (or a lazy continuation), never a heading.
    """
    if not prose and line.startswith(("- ", "  ")):
        line = line[2:]
    stripped = line.lstrip(" ")
    return len(line) - len(stripped), stripped


def _check_fragment(
    path: str, raw: bytes, section: Section, history: Released
) -> list[str]:
    try:
        # utf-8-sig: a BOM from a Windows editor would otherwise hide the leading '- '.
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return [f"{path}:1: not valid UTF-8"]
    if not text.strip():
        return [f"{path}:1: empty fragment"]
    lines = text.splitlines()
    problems: list[str] = []
    first = True
    inside = False
    previous = ""  # the open paragraph's last line; a blank line or a fence closes it
    for n, line in enumerate(lines, 1):
        if not line.strip():
            previous = ""
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
            previous = ""
            continue
        if inside:
            continue
        indent, stripped = _content(line, section["prose"])
        after_text = bool(previous)
        # An indented line continues an open paragraph but cannot start one (code).
        previous = line if indent <= 3 or after_text else ""
        if indent > 3:
            continue
        if ATX_HEADING.match(stripped) or (
            after_text and SETEXT_UNDERLINE.match(stripped)
        ):
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
    """Content a release already shipped, e.g. a consumed fragment restored under a new name."""
    if section["prose"]:
        mine = _paragraphs(lines)
        if not _drop_fences(lines) or len(" ".join(mine)) < PROSE_MATCH_MIN:
            return []
        size = len(mine)
        for version, heading, body in history:
            if heading != section["heading"]:
                continue
            theirs = _paragraphs(body)
            if any(theirs[i : i + size] == mine for i in range(len(theirs) - size + 1)):
                return [
                    f"{path}:1: this note is identical to one released in {version}; "
                    "if a release already consumed it, delete the file, otherwise reword it"
                ]
        return []
    shipped: dict[str, str] = {}
    for version, _heading, body in history:
        for _n, bullet in _bullets(body):
            shipped.setdefault(bullet, version)
    problems = []
    for n, bullet in _bullets(lines):
        if len(bullet) >= BULLET_MATCH_MIN and bullet in shipped:
            quote = bullet if len(bullet) <= 70 else bullet[:67] + "..."
            problems.append(
                f"{path}:{n}: this bullet is identical to one released in "
                f'{shipped[bullet]} ("{quote}"); remove or reword it'
            )
    return problems


def check(root: Path) -> list[str]:
    """Every rule, over tracked and untracked (not ignored) files under changelog.d/."""
    root = Path(root)
    try:
        config = sections(root)
    except (OSError, ValueError) as exc:
        return [f"{FRAGMENT_DIR}/sections.json:1: unreadable ({exc})"]
    by_dir = {s["dir"]: s for s in config}
    problems: list[str] = []
    # No CHANGELOG.md (a branch that predates it): nothing released, nothing to resurrect.
    changelog = root / "CHANGELOG.md"
    history: Released = []
    if changelog.exists():
        text = changelog.read_text(encoding="utf-8")
        history = released(text)
        problems += _unreleased_problems(text)
    gone = released_paths(root)
    for path in sorted(set(_tracked(root)) | set(_untracked(root))):
        if path in (f"{FRAGMENT_DIR}/sections.json", f"{FRAGMENT_DIR}/README.md"):
            continue
        shown = _shown(path)
        misnamed = _name_problem(path, list(by_dir))
        if misnamed:
            problems.append(f"{shown}:1: {misnamed}")
            parts = path.split("/")
            # A misnamed .md in a known section still gets its content checked, so
            # one round of fixes covers both.
            if not (len(parts) == 3 and parts[1] in by_dir and path.endswith(".md")):
                continue
        full = root / path
        if not full.exists():
            problems.append(f"{shown}:1: tracked but missing from the working tree")
            continue
        if path in gone:
            version, sha = gone[path]
            slug = path.rsplit("/", 1)[1].removesuffix(".md")
            problems.append(
                f"{shown}:1: this path was already released in {version} ({sha}). "
                "If it is the same note, delete it; if it is a new note, rename the "
                f"file, e.g. {slug}-2.md"
            )
            continue
        section = by_dir[path.split("/")[1]]
        problems += _check_fragment(shown, full.read_bytes(), section, history)
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
        # Trailing spaces would trip the release commit's trailing-whitespace hook.
        # utf-8-sig: a BOM would land mid-file as an invisible U+FEFF.
        raw = [(root / p).read_text(encoding="utf-8-sig").strip() for p in mine]
        texts = ["\n".join(line.rstrip() for line in t.splitlines()) for t in raw]
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


# --- release: called by `just version::set` (scripts/version.py) -----------------

VERSION_FILES: tuple[str, ...] = (
    "pyproject.toml",
    "docker/.env.prod",
    "docker/.env.release",
)
# FRAGMENT_DIR's deletions are staged by assemble_release's git rm.
RELEASE_PATHS: tuple[str, ...] = (*VERSION_FILES, "CHANGELOG.md", FRAGMENT_DIR)


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


def release_commit_tag_push(
    root: Path, version: str, remote: str = "origin", branch: str = "main"
) -> None:
    """Commit the assembled release, tag it, push branch then tag.

    Undoes everything before the branch push on failure; raises ChangelogError.
    """
    root = Path(root)
    add = _git(root, "add", "--", *VERSION_FILES, "CHANGELOG.md")
    if add.returncode != 0:
        rollback_release(root)
        raise ChangelogError(f"git add failed: {add.stderr.strip()}; rolled back")
    commit = _git(
        root, "commit", "-q", "-m", release_subject(version), "--", *RELEASE_PATHS
    )
    if commit.returncode != 0:
        rollback_release(root)
        detail = (commit.stderr or commit.stdout).strip()
        raise ChangelogError(f"git commit failed: {detail}; rolled back")
    tag = _git(root, "tag", version)
    if tag.returncode != 0:
        _git(root, "reset", "--keep", "HEAD~1")
        raise ChangelogError(
            f"git tag {version} failed: {tag.stderr.strip()}; commit undone"
        )
    push = _git(root, "push", remote, branch)
    if push.returncode != 0:
        _git(root, "tag", "-d", version)
        _git(root, "reset", "--keep", "HEAD~1")
        raise ChangelogError(
            f"the push of {branch} was rejected ({push.stderr.strip()}); tag and "
            f"commit undone. Update {branch} and retry. A ruleset on {branch} rejects "
            "this push unless the releaser is on its bypass list."
        )
    push_tag = _git(root, "push", remote, f"refs/tags/{version}")
    if push_tag.returncode != 0:
        raise ChangelogError(
            f"{branch} is pushed but tag {version} is not ({push_tag.stderr.strip()}), "
            f"so no images were built. Recover with: git push {remote} refs/tags/{version}"
        )


def release(
    root: Path,
    version: str,
    date: str,
    write_version_files: Callable[[], None],
    remote: str = "origin",
    branch: str = "main",
) -> list[str]:
    """The release after release_preflight(): rewrite the version files, assemble,
    commit, tag, push. Returns the consumed fragment paths.

    Any failure before the push of branch restores RELEASE_PATHS; raises ChangelogError.
    """
    root = Path(root)
    try:
        write_version_files()
        consumed = assemble_release(root, version, date)
    except Exception as exc:  # the writer may raise OSError, ValueError, ...
        try:
            rollback_release(root)
        except ChangelogError as undo:
            raise ChangelogError(
                f"{exc}; {undo}. Restore by hand with: git checkout HEAD -- "
                + " ".join(RELEASE_PATHS)
            ) from exc
        raise ChangelogError(f"{exc}; rolled back, nothing committed") from exc
    release_commit_tag_push(root, version, remote, branch)
    return consumed


def current_branch(root: Path) -> str:
    return _git(root, "branch", "--show-current").stdout.strip()


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--root", type=Path, default=Path(__file__).resolve().parents[1]
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check")
    slug = sub.add_parser("slug")
    slug.add_argument("branch", nargs="?")
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
        if args.cmd == "slug":
            print(suggest_slug(args.branch or current_branch(args.root)))
            return 0
    except ChangelogError as exc:
        print(f"changelog.py: {exc}", file=sys.stderr)
        return 1
    # has-label: exit 1 means "label absent", so every other failure must be 2.
    try:
        return 0 if has_label(args.name) else 1
    except urllib.error.HTTPError as exc:
        print(f"has-label: API error {exc.code}: {exc.reason}", file=sys.stderr)
        return 2
    except (urllib.error.URLError, TimeoutError) as exc:
        print(f"has-label: API error: {getattr(exc, 'reason', exc)}", file=sys.stderr)
        return 2
    except (ChangelogError, OSError, ValueError, KeyError) as exc:
        # e.g. RemoteDisconnected, a bad JSON body, or an unset GITHUB_* variable.
        print(f"has-label: error: {exc!r}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
