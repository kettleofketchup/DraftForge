from django.contrib.admin.sites import AdminSite
from django.contrib.auth.models import Permission
from django.test import RequestFactory, TestCase

from app.models import CustomUser, Game
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

    def _staff(self, *codenames):
        user = CustomUser.objects.create_user(
            username=f"lobby_admin_{'_'.join(codenames)}", password="x", is_staff=True
        )
        user.user_permissions.set(
            Permission.objects.filter(
                content_type__app_label="lobby", codename__in=codenames
            )
        )
        # Fresh instance: permissions are cached per user object.
        return CustomUser.objects.get(pk=user.pk)

    def test_view_only_staff_get_no_lobby_actions(self):
        request = RequestFactory().get("/")
        request.user = self._staff("view_gamelobby")
        actions = self.admin.get_actions(request)
        self.assertNotIn("create_new_lobby", actions)
        self.assertNotIn("close_lobbies", actions)

    def test_staff_who_can_change_get_lobby_actions(self):
        request = RequestFactory().get("/")
        request.user = self._staff("view_gamelobby", "change_gamelobby")
        actions = self.admin.get_actions(request)
        self.assertIn("create_new_lobby", actions)
        self.assertIn("close_lobbies", actions)
