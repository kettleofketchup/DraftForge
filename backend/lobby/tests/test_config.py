"""config.dota_lobby: environment parsing shared by both settings modules."""

from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase

from config.dota_lobby import DotaLobbyConfig


class DotaLobbyConfigTests(SimpleTestCase):
    def test_defaults_are_off(self):
        config = DotaLobbyConfig.from_env({})
        self.assertFalse(config.enabled)
        self.assertFalse(config.is_configured)
        self.assertEqual(config.url, "")
        self.assertEqual(config.api_key, "")
        self.assertEqual(config.webhook_secrets, ())
        self.assertEqual(config.timeout_seconds, 15.0)
        self.assertEqual(config.ref_prefix, "game")
        self.assertEqual(config.webhook_tolerance_seconds, 300)
        self.assertEqual(config.region, "")

    def test_values(self):
        config = DotaLobbyConfig.from_env(
            {
                "DOTA_LOBBY_ENABLED": "true",
                "DOTA_LOBBY_URL": " http://dota-lobby:8080/v1/ ",
                "DOTA_LOBBY_API_KEY": "dummy-key",
                "DOTA_LOBBY_WEBHOOK_SECRET": "new-secret, old-secret,,",
                "DOTA_LOBBY_TIMEOUT_SECONDS": "20",
                "DOTA_LOBBY_REF_PREFIX": "staging",
                "DOTA_LOBBY_WEBHOOK_TOLERANCE_SECONDS": "120",
                "DOTA_LOBBY_REGION": "europe",
            }
        )
        self.assertTrue(config.enabled)
        self.assertTrue(config.is_configured)
        self.assertEqual(config.url, "http://dota-lobby:8080")
        self.assertEqual(config.webhook_secrets, ("new-secret", "old-secret"))
        self.assertEqual(config.timeout_seconds, 20.0)
        self.assertEqual(config.ref_prefix, "staging")
        self.assertEqual(config.webhook_tolerance_seconds, 120)
        self.assertEqual(config.region, "europe")

    def test_secrets_not_in_repr(self):
        config = DotaLobbyConfig.from_env(
            {
                "DOTA_LOBBY_API_KEY": "dummy-key",
                "DOTA_LOBBY_WEBHOOK_SECRET": "dummy-secret",
            }
        )
        self.assertNotIn("dummy-key", repr(config))
        self.assertNotIn("dummy-secret", repr(config))

    def test_rejects_bad_numbers(self):
        for key in (
            "DOTA_LOBBY_TIMEOUT_SECONDS",
            "DOTA_LOBBY_WEBHOOK_TOLERANCE_SECONDS",
        ):
            for value in ("abc", "0", "-5"):
                with self.subTest(key=key, value=value):
                    with self.assertRaises(ImproperlyConfigured):
                        DotaLobbyConfig.from_env({key: value})

    def test_rejects_bad_prefix(self):
        for prefix in ("game:prod", "has space", "x" * 65):
            with self.subTest(prefix=prefix):
                with self.assertRaises(ImproperlyConfigured):
                    DotaLobbyConfig.from_env({"DOTA_LOBBY_REF_PREFIX": prefix})

    def test_settings_modules_expose_the_same_values(self):
        from django.conf import settings

        import config.settings_celery as celery_settings

        names = [n for n in dir(celery_settings) if n.startswith("DOTA_LOBBY_")]
        self.assertEqual(len(names), 8)
        for name in names:
            with self.subTest(name=name):
                self.assertEqual(
                    getattr(settings, name), getattr(celery_settings, name)
                )
