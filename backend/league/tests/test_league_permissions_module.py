import importlib

from django.test import SimpleTestCase

import app.permissions_tournament

MOVED = (
    "has_league_admin_access",
    "has_league_staff_access",
    "_is_league_member",
    "can_view_league_members",
    "can_view_league_members_from_payload",
    "IsLeagueAdmin",
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
        for name in NOT_REIMPORTED:
            with self.subTest(name=name):
                self.assertFalse(hasattr(app.permissions_tournament, name))

    def test_event_staff_helper_stays_in_app(self) -> None:
        self.assertEqual(
            app.permissions_tournament.has_event_staff_access.__module__,
            "app.permissions_tournament",
        )
