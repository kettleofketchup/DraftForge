"""Backend CI groups partition Django's package-based module discovery."""

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
GROUPS = ("app", "migrations-draft", "migrations-user", "rest")


def discovered_modules() -> set[str]:
    modules: set[str] = set()
    for path in BACKEND.rglob("test*.py"):
        parents = path.relative_to(BACKEND).parents
        if all(
            (BACKEND / parent / "__init__.py").is_file()
            for parent in parents
            if parent != Path(".")
        ):
            modules.add(".".join(path.relative_to(BACKEND).with_suffix("").parts))
    return modules


def labels_for(group: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["just", "ci::backend-test-labels", group],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def group_modules(group: str, discovered: set[str]) -> set[str]:
    result = labels_for(group)
    assert result.returncode == 0, result.stderr
    modules: set[str] = set()
    for label in result.stdout.split():
        expanded = {m for m in discovered if m == label or m.startswith(f"{label}.")}
        assert (
            expanded or (BACKEND / label / "__init__.py").is_file()
        ), f"{group}: undiscoverable label {label}"
        modules.update(expanded)
    return modules


def test_groups_partition_discovered_modules() -> None:
    discovered = discovered_modules()
    covered: set[str] = set()
    for group in GROUPS:
        modules = group_modules(group, discovered)
        assert not covered & modules, f"{group}: duplicate modules {covered & modules}"
        covered.update(modules)
    assert covered == discovered


def test_org_and_user_migration_tests_in_migrations_user() -> None:
    discovered = discovered_modules()
    user = group_modules("migrations-user", discovered)
    draft = group_modules("migrations-draft", discovered)
    expected = {
        m
        for m in discovered
        if m.split(".")[0] in {"org", "user"} and "migration" in m.split(".")[-1]
    }
    assert {
        "org.tests.test_organization_move_migration",
        "user.tests.test_migration",
    } <= expected
    assert user == expected
    assert not draft & expected
    assert draft == {
        m
        for m in discovered
        if m.split(".")[0] not in {"app", "org", "user"}
        and "migration" in m.split(".")[-1]
    }


def test_unknown_group_exits_2() -> None:
    result = labels_for("migrations")
    assert result.returncode == 2
    assert "app, migrations-draft, migrations-user or rest" in result.stderr
