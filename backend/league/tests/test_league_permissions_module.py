import importlib

from django.test import SimpleTestCase

MOVED = (
    "has_league_admin_access",
    "has_league_staff_access",
    "_is_league_member",
    "can_view_league_members",
    "can_view_league_members_from_payload",
    "IsLeagueAdmin",
    "check_lobby_steam_league_id",
    "_lobby_league_error",
)
NOT_REIMPORTED = (
    "_is_league_member",
    "can_view_league_members",
    "can_view_league_members_from_payload",
    "IsLeagueAdmin",
)


class LeaguePermissionsModuleTests(SimpleTestCase):
    def test_league_helpers_live_in_league(self) -> None:
        module = importlib.import_module("league.permissions")
        for name in MOVED:
            with self.subTest(name=name):
                self.assertEqual(getattr(module, name).__module__, "league.permissions")
        tournament_permissions = importlib.import_module("tournament.permissions")
        for name in NOT_REIMPORTED:
            with self.subTest(name=name):
                self.assertFalse(hasattr(tournament_permissions, name))

    def test_event_staff_helper_lives_in_events(self) -> None:
        module = importlib.import_module("events.permissions")
        self.assertEqual(module.has_event_staff_access.__module__, "events.permissions")
