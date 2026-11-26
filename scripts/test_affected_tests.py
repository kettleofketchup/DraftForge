from pathlib import Path

import pytest

from scripts.affected_tests import ALL, plan


def _write(root: Path, files: dict[str, str]) -> None:
    for rel, body in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    _write(
        tmp_path,
        {
            "backend/org/__init__.py": "",
            "backend/org/models.py": "",
            "backend/org/services.py": "from org.models import Org\n",
            "backend/org/views.py": "from .services import run\n",
            "backend/org/urls.py": "from org import views\n",
            "backend/org/apps.py": "",
            "backend/org/management/__init__.py": "",
            "backend/org/management/commands/__init__.py": "",
            "backend/org/management/commands/sync_orgs.py": "",
            "backend/org/migrations/__init__.py": "",
            "backend/org/migrations/0002_x.py": "",
            "backend/org/tests/__init__.py": "",
            "backend/org/tests/helpers.py": "from org.services import run\n",
            "backend/org/tests/test_services.py": "from org.tests.helpers import x\n",
            "backend/org/tests/test_api.py": "client.get('/api/org/')\n",
            "backend/org/tests/test_command.py": "call_command('sync_orgs')\n",
            "backend/user/__init__.py": "",
            "backend/user/util.py": "",
            "backend/user/tests/__init__.py": "",
            "backend/user/tests/test_util.py": "import user.util\n",
            "backend/user/tests/test_user_migrations.py": "",
            "backend/user/tests/test_cross.py": 'call_command("sync_orgs")\n',
            "backend/tests/__init__.py": "",
            "backend/tests/test_app_boundaries.py": "",
            "backend/app/__init__.py": "",
            "backend/app/tests/__init__.py": "",
            "backend/app/tests/test_celery_settings.py": "",
            "frontend/app/lib/a.ts": "",
        },
    )
    return tmp_path


def test_helper_change_selects_importing_tests_not_the_helper(repo: Path) -> None:
    assert plan(["backend/org/tests/helpers.py"], repo).backend == [
        "org.tests.test_services",
        "tests.test_app_boundaries",
    ]


def test_routed_code_pulls_in_its_whole_app(repo: Path) -> None:
    for changed in ("backend/org/views.py", "backend/org/services.py"):
        assert plan([changed], repo).backend == ["org", "tests.test_app_boundaries"]


def test_unrelated_app_change_stays_narrow(repo: Path) -> None:
    p = plan(["backend/user/util.py"], repo)
    assert p.backend == ["tests.test_app_boundaries", "user.tests.test_util"]


def test_models_change_adds_celery_settings(repo: Path) -> None:
    assert plan(["backend/org/models.py"], repo).backend == [
        "app.tests.test_celery_settings",
        "org",
        "tests.test_app_boundaries",
    ]


def test_management_command_runs_its_app_and_tests_calling_it_by_name(
    repo: Path,
) -> None:
    assert plan(["backend/org/management/commands/sync_orgs.py"], repo).backend == [
        "org",
        "tests.test_app_boundaries",
        "user.tests.test_cross",
    ]


def test_migration_runs_app_and_migration_tests(repo: Path) -> None:
    assert plan(["backend/org/migrations/0002_x.py"], repo).backend == [
        "org",
        "tests.test_app_boundaries",
        "user.tests.test_user_migrations",
    ]


@pytest.mark.parametrize(
    "path",
    [
        "backend/backend/settings.py",
        "backend/conftest.py",
        "poetry.lock",
        "docker/.env.test",
    ],
)
def test_shared_config_runs_everything(repo: Path, path: str) -> None:
    assert plan([path], repo).backend == ALL


def test_non_backend_change_runs_no_backend_tests(repo: Path) -> None:
    assert plan(["docs/x.md"], repo).backend == []


def test_vitest_related_files_and_full_on_config(repo: Path) -> None:
    assert plan(["frontend/app/lib/a.ts", "frontend/app/gone.ts"], repo).vitest == [
        "app/lib/a.ts"
    ]
    assert plan(["frontend/vitest.setup.ts"], repo).vitest == ALL


def test_scripts_flag(repo: Path) -> None:
    assert plan(["just/test/mod.just"], repo).scripts
    assert not plan(["frontend/app/lib/a.ts"], repo).scripts
