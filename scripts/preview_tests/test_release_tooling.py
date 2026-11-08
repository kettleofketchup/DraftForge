"""Regression guards: the app release tooling must stay clear of the chart.

The release tooling commits `Updated version to X` straight to main. If it ever
touched helm/, every app release would trip the chart version-bump check.
The labeler must never set the queue's own labels.
"""
import shutil
import tempfile
import unittest
from pathlib import Path

from scripts.preview_tests import _util

RELEASE_TOOLING = [
    _util.REPO_ROOT / "scripts" / "sync_version.py",
    _util.REPO_ROOT / "scripts" / "version.py",
    _util.REPO_ROOT / "just" / "version.just",
]
LABELER = _util.REPO_ROOT / ".github" / "labeler.yml"
QUEUE_LABELS = ("preview-env", "no-preview")


def files_containing(paths, needle):
    """Return the paths whose text contains `needle`, case-insensitively."""
    needle = needle.lower()
    return [p for p in paths if needle in Path(p).read_text().lower()]


class ReleaseToolingTest(unittest.TestCase):
    def test_release_tooling_never_touches_helm(self):
        self.assertEqual(files_containing(RELEASE_TOOLING, "helm"), [])

    def test_labeler_ignores_preview_labels(self):
        for label in QUEUE_LABELS:
            with self.subTest(label=label):
                self.assertEqual(files_containing([LABELER], label), [])

    def test_helper_detects_helm_reference(self):
        with tempfile.TemporaryDirectory() as tmp:
            copy = Path(tmp) / "version.py"
            shutil.copyfile(RELEASE_TOOLING[1], copy)
            self.assertEqual(files_containing([copy], "helm"), [])
            with open(copy, "a") as f:
                f.write("# HELM\n")
            self.assertEqual(files_containing([copy], "helm"), [copy])


if __name__ == "__main__":
    unittest.main()
