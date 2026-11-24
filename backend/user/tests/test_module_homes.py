import importlib

from django.test import SimpleTestCase


class UserModuleHomeTests(SimpleTestCase):
    def test_user_payload_definitions_have_user_homes(self) -> None:
        definitions = {
            "user.serializers": (
                "UserPkField",
                "PositionsSerializer",
                "TournamentUserSerializer",
                "UserSerializer",
            ),
            "user.schemas": ("TournamentUserSchema",),
            "user.cache": ("serialize_users_core",),
        }
        for module_name, names in definitions.items():
            with self.subTest(module=module_name):
                module = importlib.import_module(module_name)
                for name in names:
                    self.assertEqual(getattr(module, name).__module__, module_name)
