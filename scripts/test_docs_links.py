#!/usr/bin/env python3
"""Builds the MkDocs site and fails on any broken link or anchor: `python3 scripts/test_docs_links.py`.

Needs the project venv (`./dev`); skipped without it.
"""

import re
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
MKDOCS = REPO / ".venv" / "bin" / "mkdocs"

LINK_PROBLEM_RE = re.compile(
    r"^(WARNING|INFO)\s+-\s+Doc file .*("
    r"contains a link .* not found among documentation files"
    r"|contains an unrecognized relative link"
    r"|does not contain an anchor"
    r")"
)


def build_log() -> str:
    with tempfile.TemporaryDirectory() as site_dir:
        result = subprocess.run(
            [str(MKDOCS), "build", "--site-dir", site_dir],
            cwd=REPO,
            capture_output=True,
            text=True,
            check=False,
        )
    if result.returncode != 0:
        raise AssertionError(f"mkdocs build failed:\n{result.stdout}{result.stderr}")
    return result.stdout + result.stderr


@unittest.skipUnless(MKDOCS.exists(), "project venv with mkdocs not found; run ./dev")
class DocsLinksTest(unittest.TestCase):
    def test_build_has_no_broken_links_or_anchors(self) -> None:
        problems = [
            line for line in build_log().splitlines() if LINK_PROBLEM_RE.match(line)
        ]
        self.assertEqual(problems, [], "\n" + "\n".join(problems))


if __name__ == "__main__":
    unittest.main()
