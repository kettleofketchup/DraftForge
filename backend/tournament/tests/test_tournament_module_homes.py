import importlib

from django.test import SimpleTestCase

INTERNAL_CLIENT_NAMES = (
    "create_herodraft_for_game",
    "get_auto_herodraft_games",
    "get_match_participants",
    "get_tournament_for_task",
    "get_tournament_participants",
)

TOURNAMENT_SCHEMA_NAMES = (
    "TournamentParticipantSchema",
    "TournamentTaskSchema",
    "GameWithoutHeroDraftSchema",
    "AutoHeroDraftGameSchema",
)


class TournamentModuleHomeTests(SimpleTestCase):
    def test_listing_cache_prefix_unchanged(self) -> None:
        listing = importlib.import_module("tournament.listing")
        self.assertEqual(listing.TOURNAMENTS_LIST_CACHE_PREFIX, "tournaments_list_v6")

    def test_internal_client_lives_in_tournament(self) -> None:
        client = importlib.import_module("tournament.internal_client")
        for name in INTERNAL_CLIENT_NAMES:
            with self.subTest(name=name):
                self.assertEqual(
                    getattr(client, name).__module__, "tournament.internal_client"
                )

    def test_internal_client_not_reexported_from_app(self) -> None:
        package = importlib.import_module("app.internal_client")
        for name in INTERNAL_CLIENT_NAMES:
            with self.subTest(name=name):
                self.assertFalse(hasattr(package, name))
                self.assertNotIn(name, package.__all__)

    def test_schemas_live_in_tournament(self) -> None:
        schemas = importlib.import_module("tournament.schemas")
        for name in TOURNAMENT_SCHEMA_NAMES:
            with self.subTest(name=name):
                self.assertEqual(
                    getattr(schemas, name).__module__, "tournament.schemas"
                )

    def test_schema_definitions_owned_by_tournament(self) -> None:
        schemas = importlib.import_module("tournament.schemas")
        for name in TOURNAMENT_SCHEMA_NAMES:
            with self.subTest(name=name):
                self.assertEqual(
                    getattr(schemas, name).__module__, "tournament.schemas"
                )

    def test_domain_helpers_live_in_tournament(self) -> None:
        cases = {
            "tournament.state": "tournament_state_queryset",
            "tournament.listing": "parse_tournament_list_params",
            "tournament.buckets": "tournament_bucket_cutoff",
            "tournament.functions": "serialize_tournament",
        }
        for module_name, name in cases.items():
            with self.subTest(module=module_name):
                module = importlib.import_module(module_name)
                self.assertEqual(getattr(module, name).__module__, module_name)
