from cacheops.conf import model_profile
from django.test import SimpleTestCase

from draft.models import DraftTeam, HeroDraft, HeroDraftEvent, HeroDraftRound


class HeroModelConfigTests(SimpleTestCase):
    def test_tables_and_labels(self) -> None:
        for model, table in (
            (HeroDraft, "app_herodraft"),
            (DraftTeam, "app_draftteam"),
            (HeroDraftRound, "app_herodraftround"),
            (HeroDraftEvent, "app_herodraftevent"),
        ):
            with self.subTest(model=model.__name__):
                self.assertEqual(
                    (model._meta.app_label, model._meta.db_table), ("draft", table)
                )

    def test_cacheops_profiles(self) -> None:
        self.assertIsNotNone(model_profile(HeroDraft))
        self.assertIsNotNone(model_profile(DraftTeam))
        self.assertIsNone(model_profile(HeroDraftRound))
        self.assertIsNone(model_profile(HeroDraftEvent))
