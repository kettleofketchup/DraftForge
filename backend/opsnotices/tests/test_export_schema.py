import ast
import importlib.util
import io
import tempfile
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from django.apps import apps
from django.conf import settings
from django.test import SimpleTestCase

from opsnotices import export_schema
from opsnotices.models import OpsNotice
from opsnotices.registry import all_notice_types, isolated_registry
from opsnotices.tests.types import register_test_types


class ExportSchemaTests(SimpleTestCase):
    def test_render_deterministic(self) -> None:
        with isolated_registry():
            register_test_types()
            first = export_schema.render(all_notice_types())
            second = export_schema.render(all_notice_types())
        self.assertEqual(first, second)

    def test_render_empty_registry(self) -> None:
        with isolated_registry():
            output = export_schema.render(all_notice_types())
        self.assertTrue(output.startswith("// GENERATED FILE - DO NOT EDIT.\n"))
        self.assertIn("// Regenerate with: just py::gen-notice-types\n", output)
        self.assertIn(
            "export const NOTICE_KEYS = [] as const satisfies readonly string[];",
            output,
        )
        self.assertIn(
            "export const NOTICE_TYPES: readonly NoticeTypeMeta[] = [];", output
        )
        self.assertNotIn("z.enum(NOTICE_KEYS)", output)
        for name in (
            "NOTICE_CATEGORIES",
            "NoticeCategorySchema",
            "NOTICE_SEVERITIES",
            "NoticeSeveritySchema",
            "NOTICE_STATES",
            "NoticeStateSchema",
            "NOTICE_DELIVERY_STATES",
            "NoticeDeliveryStateSchema",
            "NoticeTypeMetaSchema",
        ):
            self.assertIn(f"export const {name} ", output)
        self.assertIn(
            "export const NOTICE_SEVERITIES = ['info', 'warning', 'critical'] as const;",
            output,
        )

    def test_render_with_sample_types(self) -> None:
        with isolated_registry():
            register_test_types()
            output = export_schema.render(all_notice_types())
        keys_block = output.split("export const NOTICE_KEYS = [", 1)[1].split(
            "] as const satisfies readonly string[];", 1
        )[0]
        keys = [
            line.strip().rstrip(",").strip("'")
            for line in keys_block.splitlines()
            if line.strip()
        ]
        self.assertEqual(
            keys, ["test.alert", "test.chore", "test.log", "test.nodedupe"]
        )
        types_block = output.split("export const NOTICE_TYPES", 1)[1]
        self.assertLess(
            types_block.index("key: 'test.alert'"),
            types_block.index("key: 'test.nodedupe'"),
        )
        alert = types_block.split("key: 'test.alert'", 1)[1].split("},", 1)[0]
        self.assertIn("category: 'urgent',", alert)
        self.assertIn("defaultSeverity: 'warning',", alert)
        self.assertIn("autoResolves: false,", alert)
        self.assertIn("dedupes: true,", alert)
        nodedupe = types_block.split("key: 'test.nodedupe'", 1)[1].split("},", 1)[0]
        self.assertIn("dedupes: false,", nodedupe)

    def test_check_mode_exit_codes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, isolated_registry():
            register_test_types()
            out = Path(tmp) / "noticeTypes.generated.ts"
            self.assertEqual(export_schema.main(["--out", str(out)]), 0)
            stdout = io.StringIO()
            with redirect_stdout(stdout), redirect_stderr(io.StringIO()):
                self.assertEqual(export_schema.main(["--out", str(out), "--check"]), 0)
            self.assertEqual(stdout.getvalue(), "")

            out.write_text(
                out.read_text(encoding="utf-8").replace(
                    "dedupes: true", "dedupes: false", 1
                ),
                encoding="utf-8",
            )
            stdout = io.StringIO()
            with redirect_stdout(stdout), redirect_stderr(io.StringIO()):
                self.assertEqual(export_schema.main(["--out", str(out), "--check"]), 1)
            self.assertIn("-    dedupes: false,", stdout.getvalue())
            self.assertIn("+    dedupes: true,", stdout.getvalue())

            missing = Path(tmp) / "missing.ts"
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                self.assertEqual(
                    export_schema.main(["--out", str(missing), "--check"]), 1
                )

    def test_exporter_state_tuples_match_model(self) -> None:
        self.assertEqual(export_schema.NOTICE_STATES, tuple(OpsNotice.State.values))
        self.assertEqual(
            export_schema.NOTICE_DELIVERY_STATES,
            tuple(OpsNotice.DeliveryState.values),
        )

    def test_runtime_and_exporter_discover_same_modules(self) -> None:
        runtime = sorted(
            f"{config.name}.ops_notices"
            for config in apps.get_app_configs()
            if importlib.util.find_spec(f"{config.name}.ops_notices") is not None
        )
        self.assertEqual(export_schema.discover(), runtime)

    def test_exporter_has_no_django_imports(self) -> None:
        base: Path = settings.BASE_DIR_PATH
        path = base / "opsnotices" / "export_schema.py"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imported: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                self.assertEqual(node.level, 0, "relative import in exporter")
                imported.append(node.module or "")
        offenders = [
            name
            for name in imported
            if name.split(".")[0] in {"django", "rest_framework"}
            or (name.startswith("opsnotices.") and name != "opsnotices.registry")
        ]
        self.assertEqual(offenders, [])
