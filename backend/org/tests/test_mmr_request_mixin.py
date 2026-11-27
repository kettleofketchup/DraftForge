from pathlib import Path
from unittest import TestResult, TestSuite

from django.conf import settings
from django.core.cache import caches
from django.test import SimpleTestCase, override_settings

from org.tests.mmr_request_mixin import LOCMEM_CACHES, MmrRequestTestMixin


class MmrRequestMixinLifecycleTests(SimpleTestCase):
    def test_nested_class_overrides_restore_settings(self) -> None:
        self.check_lifecycle()

    def test_nested_cache_override_is_preserved(self) -> None:
        self.check_lifecycle(override_cache=True)

    def test_failed_test_restores_settings(self) -> None:
        self.check_lifecycle(fail_test=True)

    def test_failed_class_setup_restores_settings(self) -> None:
        self.check_lifecycle(fail_setup=True)

    def check_lifecycle(
        self,
        *,
        fail_test: bool = False,
        fail_setup: bool = False,
        override_cache: bool = False,
    ) -> None:
        original_caches = settings.CACHES
        original_media_root = settings.MEDIA_ROOT
        original_token = getattr(settings, "INTERNAL_SERVICE_TOKEN", None)
        original_backend = type(caches["default"])
        expected_caches = (
            {"default": {**LOCMEM_CACHES["default"], "LOCATION": "nested-cache"}}
            if override_cache
            else LOCMEM_CACHES
        )
        nested_settings: dict[str, object] = {
            "INTERNAL_SERVICE_TOKEN": "lifecycle-probe"
        }
        if override_cache:
            nested_settings["CACHES"] = expected_caches
        outer = self

        @override_settings(**nested_settings)
        class NestedCase(MmrRequestTestMixin, SimpleTestCase):
            @classmethod
            def setUpClass(cls) -> None:
                super().setUpClass()
                if fail_setup:
                    raise RuntimeError("class setup failed")

            def test_settings(self) -> None:
                outer.assertEqual(settings.CACHES, expected_caches)
                outer.assertEqual(settings.MEDIA_ROOT, self.media_root)
                outer.assertEqual(settings.INTERNAL_SERVICE_TOKEN, "lifecycle-probe")
                outer.assertTrue(Path(self.media_root).is_dir())
                if fail_test:
                    self.fail("test failed")

        result = TestResult()
        # Restore the real backend even when exercising the broken lifecycle.
        with override_settings(CACHES=original_caches, MEDIA_ROOT=original_media_root):
            TestSuite([NestedCase("test_settings")]).run(result)
            self.assertEqual(len(result.errors), int(fail_setup), result.errors)
            self.assertEqual(len(result.failures), int(fail_test), result.failures)
            self.assertEqual(settings.CACHES, original_caches)
            self.assertEqual(settings.MEDIA_ROOT, original_media_root)
            self.assertEqual(
                getattr(settings, "INTERNAL_SERVICE_TOKEN", None), original_token
            )
            self.assertIs(type(caches["default"]), original_backend)
            self.assertFalse(Path(NestedCase.media_root).exists())
