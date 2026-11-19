from django.apps import apps
from django.test import SimpleTestCase

from config.installed_apps import MODEL_APPS


class DraftAppConfigTests(SimpleTestCase):
    def test_draft_is_installed(self) -> None:
        self.assertEqual(apps.get_app_config("draft").name, "draft")

    def test_draft_registered_before_app(self) -> None:
        self.assertLess(
            MODEL_APPS.index("draft.apps.DraftConfig"), MODEL_APPS.index("app")
        )
