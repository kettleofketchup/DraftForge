from django.conf import settings
from django.test import SimpleTestCase, override_settings

from org.tests.mmr_request_mixin import MmrRequestTestMixin


class MmrRequestTestMixinLifecycleTests(SimpleTestCase):
    def test_decorated_class_restores_cache_settings(self) -> None:
        original_caches = settings.CACHES
        original_media_root = settings.MEDIA_ROOT

        @override_settings(INTERNAL_SERVICE_TOKEN="test-token")
        class DecoratedFixture(MmrRequestTestMixin, SimpleTestCase):
            pass

        DecoratedFixture.setUpClass()
        try:
            self.assertNotEqual(settings.MEDIA_ROOT, original_media_root)
        finally:
            DecoratedFixture.tearDownClass()
            DecoratedFixture.doClassCleanups()

        self.assertEqual(settings.CACHES, original_caches)
        self.assertEqual(settings.MEDIA_ROOT, original_media_root)
