import ast
import os
import subprocess
import sys
import textwrap
from pathlib import Path

from django.test import SimpleTestCase

BACKEND_DIR = Path(__file__).resolve().parents[2]
CONDUCT_DIR = BACKEND_DIR / "org" / "conduct"

LOW_LAYER = {
    "constants",
    "gate",
    "scoring",
    "queries",
    "enforcement",
    "capture",
    "lifecycle",
}
HIGH_LAYER = {
    "finalize",
    "sources",
    "services",
    "attendance",
    "serializers",
    "views",
    "urls",
}
ALLOWED_PREFIXES = (
    "app",
    "events.constants",
    "events.models",
    "events.capacity",
    "events.ready_check_constants",
    "org.models",
    "org.models_conduct",
    "org.features",
    "org.feature_keys",
    "telemetry",
    *(f"org.conduct.{name}" for name in LOW_LAYER),
)
FORBIDDEN = (
    "events.services",
    "events.admission",
    "events.eligibility",
    "events.completion",
    "events.reopen",
    "events.views",
    *(f"org.conduct.{name}" for name in HIGH_LAYER),
)


def _matches(name: str, prefix: str) -> bool:
    return name == prefix or name.startswith(f"{prefix}.")


def _conduct_modules() -> list[str]:
    return sorted(
        path.stem for path in CONDUCT_DIR.glob("*.py") if path.stem != "__init__"
    )


def _imported_names(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(), filename=str(path))
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                raise AssertionError(f"{path.name}: relative import not allowed")
            if node.module is None:
                raise AssertionError(f"{path.name}: bare relative import")
            names.append(node.module)
    return names


def _allowed(name: str) -> bool:
    if any(_matches(name, prefix) for prefix in FORBIDDEN):
        return False
    if name.split(".")[0] in sys.stdlib_module_names:
        return True
    if _matches(name, "django"):
        return True
    return any(_matches(name, prefix) for prefix in ALLOWED_PREFIXES)


class ConductLayeringTest(SimpleTestCase):
    def test_every_module_is_classified(self) -> None:
        self.assertFalse(LOW_LAYER & HIGH_LAYER)
        for module in _conduct_modules():
            with self.subTest(module=module):
                self.assertIn(module, LOW_LAYER | HIGH_LAYER)

    def test_low_layer_imports_allow_listed(self) -> None:
        for module in _conduct_modules():
            if module not in LOW_LAYER:
                continue
            for name in _imported_names(CONDUCT_DIR / f"{module}.py"):
                with self.subTest(module=module, imported=name):
                    self.assertTrue(_allowed(name), f"{module} imports {name}")

    def test_fresh_interpreter_imports(self) -> None:
        targets = ["events.services", "events.completion", "events.reopen"]
        if (CONDUCT_DIR / "views.py").exists():
            targets.append("org.conduct.views")
        code = textwrap.dedent(
            f"""
            import importlib
            import sys
            sys.path.insert(0, {str(BACKEND_DIR)!r})
            import django
            django.setup()
            for name in {targets!r}:
                importlib.import_module(name)
            """
        )
        result = subprocess.run(
            [sys.executable, "-I", "-c", code],
            env={**os.environ, "DJANGO_SETTINGS_MODULE": "backend.settings"},
            cwd=BACKEND_DIR,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
