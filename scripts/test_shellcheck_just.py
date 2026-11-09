#!/usr/bin/env python3
"""Tests for scripts/shellcheck_just.py against a fixture justfile.

Stdlib only (the `shellcheck` CI job runs it on the bare runner):
    python3 -m unittest scripts/test_shellcheck_just.py
"""

import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent / "shellcheck_just.py"

ROOT_JUSTFILE = """\
set shell := ["bash", "-euo", "pipefail", "-c"]

mod sub 'sub.just'

target := "a b"

clean:
    echo "{{target}}"

unquoted-var:
    for f in *.txt; do rm $f; done

needs-arg name:
    echo "{{name}}"

broken-shebang:
    #!/usr/bin/env bash
    cd /tmp
    echo `date`

python-recipe:
    #!/usr/bin/env python3
    import os; print(os.getcwd())
"""

SUB_JUST = """\
# No `set shell`, so linewise recipes run under sh.
bashism:
    [[ -n "$HOME" ]] && echo yes
"""


class ShellcheckJustTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory()
        root = Path(cls.tmp.name)
        (root / "justfile").write_text(ROOT_JUSTFILE)
        (root / "sub.just").write_text(SUB_JUST)
        cls.result = subprocess.run(
            [sys.executable, "-I", str(SCRIPT), "--root", str(root)],
            capture_output=True,
            text=True,
            env={"PATH": __import__("os").environ["PATH"]},
        )
        cls.out = cls.result.stdout

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def findings_for(self, namepath: str) -> list[str]:
        return [line for line in self.out.splitlines() if f": {namepath} (" in line]

    def test_fails_when_any_recipe_has_findings(self) -> None:
        self.assertEqual(self.result.returncode, 1, self.result.stderr)

    def test_clean_recipe_has_no_findings(self) -> None:
        self.assertEqual(self.findings_for("clean"), [])

    def test_linewise_recipe_is_checked(self) -> None:
        self.assertTrue(
            any("SC2086" in f for f in self.findings_for("unquoted-var")), self.out
        )

    def test_required_parameter_gets_a_placeholder(self) -> None:
        self.assertEqual(self.findings_for("needs-arg"), [])
        self.assertNotIn("needs-arg", self.result.stderr)

    def test_shebang_recipe_is_checked_with_its_interpreter(self) -> None:
        codes = " ".join(self.findings_for("broken-shebang"))
        self.assertIn("SC2164", codes)
        self.assertIn("SC2006", codes)

    def test_module_without_set_shell_is_checked_as_sh(self) -> None:
        self.assertTrue(
            any("SC3010" in f for f in self.findings_for("sub::bashism")), self.out
        )

    def test_non_shell_shebang_is_skipped(self) -> None:
        self.assertEqual(self.findings_for("python-recipe"), [])
        self.assertIn("python-recipe (python3)", self.result.stderr)

    def test_findings_name_the_module_source(self) -> None:
        self.assertTrue(
            any(f.startswith("sub.just: sub::bashism") for f in self.out.splitlines()),
            self.out,
        )


if __name__ == "__main__":
    unittest.main()
