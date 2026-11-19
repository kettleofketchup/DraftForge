import ast
import sys
from dataclasses import replace
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase
from pydantic import BaseModel

from opsnotices.registry import (
    NoticeCategory,
    NoticeDetail,
    NoticeRegistryError,
    NoticeSeverity,
    NoticeType,
    UnknownNoticeType,
    all_notice_types,
    get_notice_type,
    isolated_registry,
    register_notice_type,
    render_detail,
    validate_registry,
)
from opsnotices.tests.types import AlertPayload, register_test_types


def _make(key: str = "test.sample", **overrides: object) -> NoticeType[AlertPayload]:
    base: NoticeType[AlertPayload] = NoticeType(
        key=key,
        label="Sample",
        description="Sample type",
        category=NoticeCategory.URGENT,
        default_severity=NoticeSeverity.WARNING,
        payload=AlertPayload,
        summary=lambda p: f"Member {p.member_id}",
        sample_payload=lambda: AlertPayload(member_id=1, reason="x"),
    )
    return replace(base, **overrides)


class RegistryTests(SimpleTestCase):
    def test_key_regex_accepts_and_rejects(self) -> None:
        with isolated_registry():
            register_notice_type(_make("rsvp.staff_changed"))
            register_notice_type(_make("ready_check.stalled"))
            for bad in ("Rsvp.x", "rsvp", "rsvp.x.y", "1a.b", "rsvp.X"):
                with self.subTest(key=bad), self.assertRaises(NoticeRegistryError):
                    register_notice_type(_make(bad))

    def test_duplicate_key_raises(self) -> None:
        with isolated_registry():
            register_notice_type(_make("test.dup"))
            with self.assertRaises(NoticeRegistryError):
                register_notice_type(_make("test.dup"))

    def test_unknown_key_raises_unknown_notice_type(self) -> None:
        with isolated_registry(), self.assertRaises(UnknownNoticeType):
            get_notice_type("test.missing")

    def test_all_notice_types_sorted_by_key(self) -> None:
        with isolated_registry():
            register_test_types()
            keys = [nt.key for nt in all_notice_types()]
            self.assertEqual(
                keys, ["test.alert", "test.chore", "test.log", "test.nodedupe"]
            )

    def test_validate_registry_empty_ok(self) -> None:
        with isolated_registry():
            validate_registry()

    def test_validate_registry_accepts_test_types(self) -> None:
        with isolated_registry():
            register_test_types()
            validate_registry()

    def test_validate_registry_rejects_summary_over_150_and_empty_summary(
        self,
    ) -> None:
        for summary in ("x" * 151, ""):
            with self.subTest(length=len(summary)), isolated_registry():
                register_notice_type(_make(summary=lambda p, s=summary: s))
                with self.assertRaises(NoticeRegistryError):
                    validate_registry()
        with isolated_registry():
            register_notice_type(_make(summary=lambda p: "x" * 150))
            validate_registry()

    def test_validate_registry_rejects_sample_not_validating(self) -> None:
        class Other(BaseModel):
            other: str

        with isolated_registry():
            register_notice_type(_make(sample_payload=lambda: Other(other="x")))
            with self.assertRaises(NoticeRegistryError):
                validate_registry()

    def test_validate_registry_rejects_detail_not_noticedetail(self) -> None:
        with isolated_registry():
            register_notice_type(_make(detail=lambda p: {"title": "x"}))
            with self.assertRaises(NoticeRegistryError):
                validate_registry()

    def test_validate_registry_rejects_auto_resolves_without_dedupe_hook(
        self,
    ) -> None:
        with isolated_registry():
            register_notice_type(_make(auto_resolves=True))
            with self.assertRaises(NoticeRegistryError):
                validate_registry()
        with isolated_registry():
            register_notice_type(
                _make(auto_resolves=True, dedupe_key=lambda p: f"m:{p.member_id}")
            )
            validate_registry()

    def test_render_detail_defaults_to_label_title(self) -> None:
        nt = _make()
        payload = AlertPayload(member_id=1, reason="x")
        self.assertEqual(render_detail(nt, payload), NoticeDetail(title="Sample"))
        custom = NoticeDetail(title="Custom")
        self.assertEqual(
            render_detail(replace(nt, detail=lambda p: custom), payload), custom
        )

    def test_severity_rank_order(self) -> None:
        self.assertLess(NoticeSeverity.INFO.rank, NoticeSeverity.WARNING.rank)
        self.assertLess(NoticeSeverity.WARNING.rank, NoticeSeverity.CRITICAL.rank)

    def test_isolated_registry_restores(self) -> None:
        with isolated_registry():
            register_notice_type(_make("test.outer"))
            with isolated_registry():
                register_notice_type(_make("test.inner"))
                self.assertEqual([nt.key for nt in all_notice_types()], ["test.inner"])
            self.assertEqual([nt.key for nt in all_notice_types()], ["test.outer"])
            with self.assertRaises(UnknownNoticeType):
                get_notice_type("test.inner")

    def test_registered_types_well_formed(self) -> None:
        # Runs on the real registry populated by ready(); must not be wrapped in isolated_registry().
        for nt in all_notice_types():
            with self.subTest(key=nt.key):
                self.assertIsInstance(nt.category, NoticeCategory)
                self.assertIsInstance(nt.default_severity, NoticeSeverity)
                self.assertTrue(issubclass(nt.payload, BaseModel))
        validate_registry()

    def test_registry_and_ops_notices_modules_are_pure(self) -> None:
        base: Path = settings.BASE_DIR_PATH
        files = [
            base / "opsnotices" / "__init__.py",
            base / "opsnotices" / "registry.py",
            *sorted(base.glob("*/ops_notices.py")),
        ]
        allowed = set(sys.stdlib_module_names) | {
            "pydantic",
            "typing_extensions",
            "opsnotices",
        }
        for path in files:
            tree = ast.parse(path.read_text(), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    names = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom):
                    self.assertEqual(node.level, 0, f"{path}: relative import")
                    names = [node.module or ""]
                else:
                    continue
                for name in names:
                    with self.subTest(path=str(path), module=name):
                        self.assertIn(name.split(".")[0], allowed)
                        if name.split(".")[0] == "opsnotices":
                            self.assertEqual(name, "opsnotices.registry")
