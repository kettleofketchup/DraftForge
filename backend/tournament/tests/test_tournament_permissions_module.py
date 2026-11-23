import importlib

from django.test import SimpleTestCase

TOURNAMENT_PERMISSION_NAMES = (
    "can_edit_tournament",
    "can_create_team",
    "_league_change_error",
    "check_tournament_league_change",
    "can_manage_game",
    "CanEditTournament",
    "CanEditTeam",
    "CanManageGame",
    "IsTournamentStaff",
)


class TournamentPermissionsModuleTests(SimpleTestCase):
    def test_names_live_in_tournament_permissions(self) -> None:
        module = importlib.import_module("tournament.permissions")
        for name in TOURNAMENT_PERMISSION_NAMES:
            with self.subTest(name=name):
                self.assertEqual(
                    getattr(module, name).__module__, "tournament.permissions"
                )

    def test_request_user_lives_in_app_permissions(self) -> None:
        module = importlib.import_module("app.permissions")
        self.assertEqual(module.request_user.__module__, "app.permissions")
