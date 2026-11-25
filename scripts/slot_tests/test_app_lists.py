"""Keep the hand-maintained Django app lists in step with every app that has migrations."""

import re
from pathlib import Path

from scripts.slot_tests import test_just_recipes
from scripts.slot_tests._helpers import ROOT


def _apps_with_migrations(root: Path) -> list[str]:
    return sorted(
        init.parent.parent.name
        for init in (root / "backend").glob("*/migrations/__init__.py")
    )


def _mod_just_apps(root: Path) -> list[str]:
    text = (root / "just/db/mod.just").read_text()
    match = re.search(r'^apps := "([^"]*)"', text, re.MULTILINE)
    assert match, 'no `apps := "..."` line in just/db/mod.just'
    return match.group(1).split()


def test_apps_with_migrations_are_in_makemigrations_list() -> None:
    missing = set(_apps_with_migrations(ROOT)) - set(_mod_just_apps(ROOT))
    assert not missing, f"add to just/db/mod.just apps: {sorted(missing)}"


def test_just_recipes_apps_matches_mod_just() -> None:
    assert test_just_recipes.APPS == _mod_just_apps(ROOT)
