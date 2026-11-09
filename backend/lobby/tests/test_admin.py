from django.contrib.admin.sites import AdminSite
from django.test import RequestFactory, TestCase

from app.models import Game
from lobby.admin import GameLobbyAdmin
from lobby.models import GameLobby


class GameLobbyAdminTests(TestCase):
    def setUp(self):
        self.admin = GameLobbyAdmin(GameLobby, AdminSite())
        self.request = RequestFactory().get("/")
        game = Game.objects.create()
        self.lobby = GameLobby.objects.create(
            game=game, external_ref=f"game:{game.pk}", lobby_id="lob_a"
        )

    def test_lifecycle_fields_not_editable(self):
        form_fields = self.admin.get_form(self.request, self.lobby).base_fields
        for field in (
            "state",
            "ended",
            "last_seq",
            "lobby_id",
            "external_ref",
            "password_key_id",
        ):
            with self.subTest(field=field):
                self.assertNotIn(field, form_fields)
                self.assertIn(field, self.admin.get_readonly_fields(self.request))

    def test_no_adding_by_hand(self):
        self.assertFalse(self.admin.has_add_permission(self.request))
