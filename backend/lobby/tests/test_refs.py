from unittest.mock import patch

from django.test import SimpleTestCase

from lobby.refs import build_external_ref, parse_external_ref


class ExternalRefTests(SimpleTestCase):
    def test_round_trip(self):
        ref = build_external_ref(42, prefix="game")
        self.assertEqual(ref, "game:42")
        self.assertEqual(parse_external_ref(ref, prefix="game"), 42)

    def test_default_prefix_from_environment(self):
        with patch.dict("os.environ", {"DOTA_LOBBY_REF_PREFIX": "staging"}):
            self.assertEqual(build_external_ref(7), "staging:7")
            self.assertEqual(parse_external_ref("staging:7"), 7)
            self.assertIsNone(parse_external_ref("game:7"))

    def test_foreign_and_malformed_refs(self):
        for ref in (
            "staging:42",
            "game",
            "game:",
            "game:abc",
            "game:-1",
            "game:007",
            "game:4 2",
            "x:game:42",
            ":42",
            "game:４２",
        ):
            with self.subTest(ref=ref):
                self.assertIsNone(parse_external_ref(ref, prefix="game"))

    def test_prefix_with_dots(self):
        self.assertEqual(parse_external_ref("df.staging:3", prefix="df.staging"), 3)

    def test_rejects_non_positive_pk(self):
        with self.assertRaises(ValueError):
            build_external_ref(0, prefix="game")
