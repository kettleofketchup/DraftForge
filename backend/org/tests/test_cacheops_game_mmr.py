from django.conf import settings
from django.test import SimpleTestCase


class GameMmrCacheopsConfigTest(SimpleTestCase):
    def test_cacheops_lists_game_mmr(self) -> None:
        self.assertEqual(
            settings.CACHEOPS["org.orgusergamemmr"],
            {"ops": "all", "timeout": 3600},
        )
