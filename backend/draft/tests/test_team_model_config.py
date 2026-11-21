from cacheops.conf import model_profile
from django.conf import settings
from django.test import SimpleTestCase

from draft.models import Draft, DraftEvent, DraftOptions, DraftRound


class TeamModelConfigTests(SimpleTestCase):
    def test_tables_and_labels(self) -> None:
        for model, table in (
            (Draft, "app_draft"),
            (DraftRound, "app_draftround"),
            (DraftEvent, "app_draftevent"),
            (DraftOptions, "app_draftoptions"),
        ):
            with self.subTest(model=model.__name__):
                self.assertEqual(
                    (model._meta.app_label, model._meta.db_table), ("draft", table)
                )

    def test_cacheops_profiles(self) -> None:
        if not getattr(settings, "CACHEOPS", None):
            self.skipTest("CACHEOPS is empty (DISABLE_CACHE)")
        for model in (Draft, DraftRound, DraftOptions):
            with self.subTest(model=model.__name__):
                self.assertIsNotNone(model_profile(model))
        self.assertIsNone(model_profile(DraftEvent))
