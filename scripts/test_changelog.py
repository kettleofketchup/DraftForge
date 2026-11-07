#!/usr/bin/env python3
"""Tests for scripts/changelog.py. Stdlib only: `python3 scripts/test_changelog.py`.

CI runs this on the bare runner python3, so it must never import invoke,
scripts/version.py or the root paths module.
"""

import contextlib
import importlib.util
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
FIXTURE = HERE / "testdata" / "changelog"
SCRIPT = HERE / "changelog.py"

_spec = importlib.util.spec_from_file_location("changelog", SCRIPT)
changelog = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(changelog)

POINTER = changelog.POINTER

SECTIONS = [
    {"dir": "upgrading", "heading": "Upgrading", "prose": True},
    {"dir": "added", "heading": "Added", "prose": False},
    {"dir": "changed", "heading": "Changed", "prose": False},
    {"dir": "fixed", "heading": "Fixed", "prose": False},
]

BASE_CHANGELOG = f"""# Changelog

Preamble.

## [Unreleased]

{POINTER}

## [0.2.0] - 2026-10-02

### Upgrading

Run the migrations after rollout.

```
just db::migrate::all
```

Verify. Every value must be `0`:

### Changed

- **Released bullet.** It wraps
  onto a second line.

## [0.1.0] - 2026-10-01

### Added

- First thing.
"""

# Hosted runners have no git identity, and a developer's config may sign commits.
GIT_ENV = {
    "GIT_AUTHOR_NAME": "Changelog Tests",
    "GIT_AUTHOR_EMAIL": "changelog-tests@example.invalid",
    "GIT_COMMITTER_NAME": "Changelog Tests",
    "GIT_COMMITTER_EMAIL": "changelog-tests@example.invalid",
}
GIT_FLAGS = ["-c", "commit.gpgsign=false", "-c", "tag.gpgsign=false"]


def git(root, *args):
    return subprocess.run(
        ["git", *GIT_FLAGS, "-C", str(root), *args],
        check=True,
        capture_output=True,
        text=True,
        env={**os.environ, **GIT_ENV},
    )


def refused(call, pattern):
    message = None
    try:
        call()
    except changelog.ChangelogError as exc:
        message = str(exc)
    assert message is not None, f"expected a ChangelogError matching {pattern!r}"
    assert re.search(pattern, message), message


class Repo:
    """A scratch git repo shaped like the real one."""

    def __init__(self, changelog_text=BASE_CHANGELOG, sections=SECTIONS):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        git(self.root, "init", "-q", "-b", "main")
        (self.root / "changelog.d").mkdir()
        self.write("changelog.d/sections.json", json.dumps(sections))
        self.write("changelog.d/README.md", "how-to\n")
        if changelog_text is not None:
            self.write("CHANGELOG.md", changelog_text)

    def write(self, rel, text, add=True):
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        if add:
            git(self.root, "add", "--", rel)
        return path

    def fragment(self, rel, text):
        return self.write(f"changelog.d/{rel}", text)

    def problems(self):
        return changelog.check(self.root)

    def text(self):
        return (self.root / "CHANGELOG.md").read_text(encoding="utf-8")

    def close(self):
        self.tmp.cleanup()


class RepoCase(unittest.TestCase):
    def setUp(self):
        self.repo = Repo()
        self.addCleanup(self.repo.close)

    def expect_problem(self, needle):
        problems = self.repo.problems()
        assert any(needle in p for p in problems), f"{needle!r} not in {problems}"

    def expect_clean(self):
        assert self.repo.problems() == []


class AssembleTests(RepoCase):
    def test_sections_follow_sections_json_order_with_their_headings(self):
        self.repo.fragment("fixed/b.md", "- A fix.\n")
        self.repo.fragment("added/a.md", "- A feature.\n")
        self.repo.fragment("upgrading/m.md", "Migrate first.\n")
        changelog.assemble(self.repo.root, "0.3.0", "2026-10-03")
        body = (
            self.repo.text()
            .split("## [0.3.0] - 2026-10-03\n", 1)[1]
            .split("\n## [", 1)[0]
        )
        headings = re.findall(r"^### (.+)$", body, re.M)
        assert headings == ["Upgrading", "Added", "Fixed"]

    def test_section_is_inserted_after_unreleased_and_before_the_last_release(self):
        self.repo.fragment("added/a.md", "- A feature.\n")
        changelog.assemble(self.repo.root, "0.3.0", "2026-10-03")
        want = (
            f"## [Unreleased]\n\n{POINTER}\n\n## [0.3.0] - 2026-10-03\n\n"
            "### Added\n\n- A feature.\n\n## [0.2.0]"
        )
        assert want in self.repo.text()

    def test_bullet_fragments_join_contiguously_and_prose_with_a_blank_line(self):
        self.repo.fragment("added/a.md", "- One.\n\n")
        self.repo.fragment("added/b.md", "\n- Two.\n")
        self.repo.fragment("upgrading/a.md", "First note.\n")
        self.repo.fragment("upgrading/b.md", "Second note.\n")
        body = changelog.render(
            self.repo.root, changelog.fragment_paths(self.repo.root)
        )
        assert "### Added\n\n- One.\n- Two." in body
        assert "### Upgrading\n\nFirst note.\n\nSecond note." in body

    def test_fragments_sort_by_code_point_not_locale(self):
        self.repo.fragment("changed/a.md", "- from a.md\n")
        self.repo.fragment("changed/a-b.md", "- from a-b.md\n")
        body = changelog.render(
            self.repo.root, changelog.fragment_paths(self.repo.root)
        )
        assert body.index("from a-b.md") < body.index("from a.md")

    def test_output_is_deterministic(self):
        self.repo.fragment("changed/z.md", "- Z.\n")
        self.repo.fragment("changed/y.md", "- Y.\n")
        paths = changelog.fragment_paths(self.repo.root)
        assert changelog.render(self.repo.root, paths) == changelog.render(
            self.repo.root, list(reversed(paths))
        )

    def test_crlf_fragment_renders_without_carriage_returns(self):
        self.repo.fragment("added/a.md", "- One\r\n  wrapped.\r\n- Two.\r\n")
        body = changelog.render(
            self.repo.root, changelog.fragment_paths(self.repo.root)
        )
        assert "\r" not in body
        assert "### Added\n\n- One\n  wrapped.\n- Two." in body

    def test_zero_fragments_writes_a_placeholder_body(self):
        consumed = changelog.assemble(self.repo.root, "0.3.0", "2026-10-03")
        assert consumed == []
        assert (
            "## [0.3.0] - 2026-10-03\n\n- No notable changes.\n\n## [0.2.0]"
            in self.repo.text()
        )

    def test_returns_consumed_paths_and_deletes_nothing(self):
        path = self.repo.fragment("added/a.md", "- A feature.\n")
        assert changelog.assemble(self.repo.root, "0.3.0", "2026-10-03") == [
            "changelog.d/added/a.md"
        ]
        assert path.exists()

    def test_refuses_a_version_that_already_has_a_section(self):
        refused(
            lambda: changelog.assemble(self.repo.root, "0.2.0", "2026-10-03"),
            "already has",
        )

    def test_refuses_bad_version_and_date(self):
        refused(
            lambda: changelog.assemble(self.repo.root, "v0.3", "2026-10-03"), "MAJOR"
        )
        refused(
            lambda: changelog.assemble(self.repo.root, "0.3.0", "03/10/2026"), "YYYY"
        )

    def test_refuses_a_hand_edited_unreleased_body(self):
        self.repo.write(
            "CHANGELOG.md",
            BASE_CHANGELOG.replace(POINTER, POINTER + "\n\n- Sneaked in."),
        )
        refused(
            lambda: changelog.assemble(self.repo.root, "0.3.0", "2026-10-03"),
            "Unreleased",
        )

    def test_refuses_when_check_fails(self):
        self.repo.fragment("added/a.md", "Not a bullet.\n")
        before = self.repo.text()
        refused(
            lambda: changelog.assemble(self.repo.root, "0.3.0", "2026-10-03"),
            "fails check",
        )
        assert self.repo.text() == before

    def test_cli_prints_consumed_paths(self):
        self.repo.fragment("added/a.md", "- A.\n")
        self.repo.fragment("fixed/b.md", "- B.\n")
        out = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--root",
                str(self.repo.root),
                "assemble",
                "0.3.0",
                "2026-10-03",
            ],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        assert out.splitlines() == ["changelog.d/added/a.md", "changelog.d/fixed/b.md"]


class CheckTests(RepoCase):
    def test_a_well_formed_tree_is_clean(self):
        self.repo.fragment(
            "added/a.md", "- **Lead.** Body that\n  wraps.\n  - nested\n- Second.\n"
        )
        self.repo.fragment(
            "upgrading/a.md", "Prose line.\n\n```\njust db::migrate::all\n```\n"
        )
        self.expect_clean()

    def test_crlf_fragment_is_clean(self):
        self.repo.fragment("added/a.md", "- One\r\n  wrapped.\r\n- Two.\r\n")
        self.expect_clean()

    def test_empty_fragment(self):
        self.repo.fragment("added/a.md", "  \n\n")
        self.expect_problem("changelog.d/added/a.md:1: empty")

    def test_not_utf8(self):
        path = self.repo.root / "changelog.d/added/a.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"- caf\xe9\n")
        git(self.repo.root, "add", "--", "changelog.d/added/a.md")
        self.expect_problem("UTF-8")

    def test_bullet_section_must_open_with_a_bullet(self):
        self.repo.fragment("added/a.md", "Prose.\n")
        self.expect_problem("changelog.d/added/a.md:1:")

    def test_bullet_section_rejects_an_unindented_continuation(self):
        self.repo.fragment("added/a.md", "- One.\nloose line\n")
        self.expect_problem("changelog.d/added/a.md:2:")

    def test_heading_line_is_rejected(self):
        self.repo.fragment("upgrading/a.md", "Note.\n\n### Sneaky heading\n")
        self.expect_problem("changelog.d/upgrading/a.md:3:")

    def test_html_comment_is_rejected(self):
        self.repo.fragment("upgrading/a.md", "Note.\n<!-- hidden -->\n")
        self.expect_problem("changelog.d/upgrading/a.md:2:")

    def test_link_reference_definition_is_rejected(self):
        self.repo.fragment(
            "upgrading/a.md", "See [x].\n\n[x]: https://example.invalid\n"
        )
        self.expect_problem("changelog.d/upgrading/a.md:3:")

    def test_inline_link_is_allowed(self):
        self.repo.fragment("added/a.md", "- See [the docs](https://example.invalid).\n")
        self.expect_clean()

    def test_hash_line_inside_a_fence_passes(self):
        self.repo.fragment(
            "upgrading/a.md",
            "Run:\n\n```bash\n# a shell comment\njust db::migrate::all\n```\n",
        )
        self.expect_clean()

    def test_unclosed_fence_fails(self):
        self.repo.fragment("upgrading/a.md", "Run:\n\n```bash\njust db::migrate::all\n")
        self.expect_problem("unclosed")

    def test_unknown_section_dir(self):
        self.repo.fragment("misc/a.md", "- X.\n")
        self.expect_problem("changelog.d/misc/a.md")

    def test_stray_file_at_the_top(self):
        self.repo.fragment("notes.txt", "x\n")
        self.expect_problem("changelog.d/notes.txt")

    def test_bad_slug(self):
        self.repo.fragment("added/Feat_X.md", "- X.\n")
        self.expect_problem("changelog.d/added/Feat_X.md")

    def test_enumerates_tracked_files_only(self):
        self.repo.write(".gitignore", "*~\n")
        self.repo.write("changelog.d/added/x.md~", "junk\n", add=False)
        self.repo.write("changelog.d/added/untracked.txt", "junk\n", add=False)
        self.expect_clean()
        assert changelog.fragment_paths(self.repo.root) == []

    def test_missing_changelog_is_clean(self):
        repo = Repo(changelog_text=None)
        self.addCleanup(repo.close)
        repo.fragment("added/a.md", "- A feature.\n")
        assert changelog.check(repo.root) == []

    def test_cli_exits_1_and_prints_problems(self):
        self.repo.fragment("added/a.md", "Prose.\n")
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--root", str(self.repo.root), "check"],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 1
        assert "changelog.d/added/a.md:1:" in result.stdout + result.stderr


class ResurrectionTests(RepoCase):
    def test_a_released_bullet_fails_and_names_the_version(self):
        self.repo.fragment(
            "changed/old.md",
            "- **Released bullet.** It wraps onto a\n  second line.\n",
        )
        self.expect_problem("0.2.0")

    def test_the_same_bullet_under_unreleased_does_not_count(self):
        bullet = "- **Released bullet.** It wraps onto a second line."
        text = BASE_CHANGELOG.replace("- **Released bullet.**", "- **Other.**").replace(
            POINTER, POINTER + "\n\n### Changed\n\n" + bullet
        )
        self.repo.write("CHANGELOG.md", text)
        self.repo.fragment("changed/new.md", bullet + "\n")
        self.expect_clean()
        assert not any(
            "Released bullet" in "\n".join(body)
            for _, _, body in changelog.released(self.repo.text())
        )

    def test_a_whole_consumed_upgrading_fragment_fails(self):
        self.repo.fragment(
            "upgrading/old.md",
            "Run the migrations after rollout.\n\n```\njust db::migrate::all\n```\n\n"
            "Verify. Every value must be `0`:\n",
        )
        self.expect_problem("0.2.0")

    def test_new_prose_repeating_a_short_released_paragraph_passes(self):
        self.repo.fragment(
            "upgrading/new.md",
            "Backfill the new column.\n\nVerify. Every value must be `0`:\n",
        )
        self.expect_clean()

    def test_a_fence_only_fragment_is_not_checked(self):
        self.repo.fragment("upgrading/new.md", "```\njust db::migrate::all\n```\n")
        self.expect_clean()


class FixtureTests(unittest.TestCase):
    """scripts/testdata/changelog/ pins one assembled release body."""

    def test_assemble_matches_the_fixture(self):
        sections = json.loads((FIXTURE / "sections.json").read_text(encoding="utf-8"))
        repo = Repo(sections=sections)
        self.addCleanup(repo.close)
        for path in sorted(FIXTURE.rglob("*.md")):
            rel = path.relative_to(FIXTURE)
            if len(rel.parts) == 2:
                repo.fragment(rel.as_posix(), path.read_text(encoding="utf-8"))
        changelog.assemble(repo.root, "9.9.9", "2026-10-09")
        body = (
            repo.text()
            .split("## [9.9.9] - 2026-10-09\n\n", 1)[1]
            .split("\n\n## [0.2.0]", 1)[0]
        )
        assert body == (FIXTURE / "expected.md").read_text(encoding="utf-8").strip()


class _Labels(BaseHTTPRequestHandler):
    seen = {}

    def do_GET(self):
        _Labels.seen = {"path": self.path, "auth": self.headers.get("Authorization")}
        body = json.dumps([{"name": "changelog:edit"}, {"name": "bug"}]).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


class _Forbidden(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(403, "Forbidden")
        self.end_headers()

    def log_message(self, *args):
        pass


def serve(handler, case):
    server = HTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    case.addCleanup(server.server_close)
    case.addCleanup(server.shutdown)
    return server


class HasLabelTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.event = Path(self.tmp.name) / "event.json"
        self.event.write_text(
            json.dumps({"pull_request": {"number": 42, "labels": [{"name": "frozen"}]}})
        )

    def env(self, server):
        return {
            "GITHUB_EVENT_PATH": str(self.event),
            "GITHUB_REPOSITORY": "org/repo",
            "GITHUB_API_URL": f"http://127.0.0.1:{server.server_port}",
            "GH_TOKEN": "t0ken",
        }

    def test_reads_labels_live_from_the_api(self):
        env = self.env(serve(_Labels, self))
        assert changelog.has_label("changelog:edit", env)
        assert not changelog.has_label("frozen", env)
        assert _Labels.seen["path"].startswith("/repos/org/repo/issues/42/labels")
        assert _Labels.seen["auth"] == "Bearer t0ken"

    def test_without_a_token_falls_back_to_the_payload(self):
        env = {"GITHUB_EVENT_PATH": str(self.event)}
        err = io.StringIO()
        # Captured so the CI log does not read as if the real gate fell back.
        with contextlib.redirect_stderr(err):
            assert changelog.has_label("frozen", env)
            assert not changelog.has_label("changelog:edit", env)
        assert "no GH_TOKEN" in err.getvalue()

    def test_api_error_exits_2_not_1(self):
        # Exit 1 means "label absent"; an unreadable API must not say that.
        env = self.env(serve(_Forbidden, self))
        err = io.StringIO()
        with mock.patch.dict(os.environ, env), contextlib.redirect_stderr(err):
            code = changelog.main(["has-label", "changelog:edit"])
        assert code == 2
        assert "has-label: API error 403: Forbidden" in err.getvalue()


class CommittedRepoTests(unittest.TestCase):
    def test_unreleased_body_is_only_the_pointer(self):
        text = (REPO / "CHANGELOG.md").read_text(encoding="utf-8")
        body = text.split("## [Unreleased]\n", 1)[1].split("\n## [", 1)[0]
        assert body.strip() == POINTER

    def test_committed_fragments_pass_check(self):
        if not shutil.which("git") or not (REPO / ".git").exists():
            self.skipTest("not a git checkout")
        assert changelog.check(REPO) == []


if __name__ == "__main__":
    os.environ.setdefault("GIT_CONFIG_NOSYSTEM", "1")
    unittest.main()
