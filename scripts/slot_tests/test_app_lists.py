"""Keep the hand-maintained Django app lists in step with MODEL_APPS."""

import ast
import re
from pathlib import Path

from scripts.slot_tests import test_just_recipes
from scripts.slot_tests._helpers import ROOT


def _model_apps_with_migrations(root: Path) -> list[str]:
    source = (root / "backend/config/installed_apps.py").read_text()
    for node in ast.parse(source).body:
        target = node.target if isinstance(node, ast.AnnAssign) else None
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
        if isinstance(target, ast.Name) and target.id == "MODEL_APPS":
            entries: list[str] = ast.literal_eval(node.value)
            labels = [entry.split(".", 1)[0] for entry in entries]
            return [
                label
                for label in labels
                if (root / "backend" / label / "migrations/__init__.py").is_file()
            ]
    raise AssertionError("MODEL_APPS not found in backend/config/installed_apps.py")


def _mod_just_apps(root: Path) -> list[str]:
    text = (root / "just/db/mod.just").read_text()
    match = re.search(r'^apps := "([^"]*)"', text, re.MULTILINE)
    assert match, 'no `apps := "..."` line in just/db/mod.just'
    return match.group(1).split()


def test_model_apps_with_migrations_are_in_makemigrations_list() -> None:
    missing = set(_model_apps_with_migrations(ROOT)) - set(_mod_just_apps(ROOT))
    assert not missing, f"add to just/db/mod.just apps: {sorted(missing)}"


def test_just_recipes_apps_matches_mod_just() -> None:
    assert test_just_recipes.APPS == _mod_just_apps(ROOT)
