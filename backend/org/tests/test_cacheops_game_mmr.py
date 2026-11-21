import pathlib

from django.conf import settings
from django.test import SimpleTestCase


class GameMmrCacheopsConfigTest(SimpleTestCase):
    def test_cacheops_lists_game_mmr(self) -> None:
        self.assertEqual(
            settings.CACHEOPS["org.orgusergamemmr"],
            {"ops": "all", "timeout": 3600},
        )


BACKEND_ROOT = pathlib.Path(__file__).resolve().parents[2]


class GameMmrCachedAsGuardrailTest(SimpleTestCase):
    def test_mmr_module_has_no_event_defaults(self) -> None:
        source = (BACKEND_ROOT / "org" / "mmr.py").read_text()
        self.assertNotIn("OrgEventDefaults", source)
        self.assertNotIn("event_defaults", source)
