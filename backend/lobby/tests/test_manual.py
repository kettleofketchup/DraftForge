from io import StringIO
from unittest import mock

from django.contrib.admin.sites import AdminSite
from django.core.management import CommandError, call_command
from django.test import RequestFactory, TestCase

from app.models import DotaLobbyMode
from lobby import services, states
from lobby.admin import GameLobbyAdmin
from lobby.models import GameLobby
from lobby.tests.helpers import lobby_settings, make_game, make_tournament, make_user


@lobby_settings
@mock.patch("lobby.tasks.close_dota_lobby.delay")
@mock.patch("lobby.tasks.create_dota_lobby.delay")
class ManualTriggerTests(TestCase):
    def setUp(self):
        self.game = make_game(make_tournament(dota_lobby_mode=DotaLobbyMode.MANUAL))
        self.staff = make_user()
        self.admin = GameLobbyAdmin(GameLobby, AdminSite())
        self.request = RequestFactory().post("/")
        self.request.user = self.staff

    def test_command_queues_manual_create(self, create_delay, close_delay):
        out = StringIO()
        with self.captureOnCommitCallbacks(execute=True):
            call_command("create_dota_lobby", str(self.game.pk), stdout=out)
        create_delay.assert_called_once_with(
            self.game.pk, trigger="manual", user_id=None, allow_missing=False
        )
        self.assertIn("Lobby requested", out.getvalue())

    def test_command_reports_ineligible(self, create_delay, close_delay):
        self.game.dire_team.members.add(make_user(steam=False))
        with self.assertRaisesMessage(CommandError, "missing_steam_ids"):
            call_command("create_dota_lobby", str(self.game.pk))
        with self.captureOnCommitCallbacks(execute=True):
            call_command("create_dota_lobby", str(self.game.pk), "--allow-missing")
        create_delay.assert_called_once()

    def test_admin_retry_after_timeout(self, create_delay, close_delay):
        row = services.claim_lobby(self.game.pk, trigger="manual").game_lobby
        row.state = states.TIMED_OUT
        row.save()
        with (
            mock.patch.object(self.admin, "message_user"),
            self.captureOnCommitCallbacks(execute=True),
        ):
            self.admin.create_new_lobby(
                self.request, GameLobby.objects.filter(pk=row.pk)
            )
        create_delay.assert_called_once_with(
            self.game.pk, trigger="manual", user_id=self.staff.pk, allow_missing=False
        )

    def test_admin_close(self, create_delay, close_delay):
        row = services.claim_lobby(self.game.pk, trigger="manual").game_lobby
        row.lobby_id = "lob_1"
        row.state = states.READY
        row.save()
        with (
            mock.patch.object(self.admin, "message_user"),
            self.captureOnCommitCallbacks(execute=True),
        ):
            self.admin.close_lobbies(self.request, GameLobby.objects.all())
        row.refresh_from_db()
        self.assertEqual((row.state, row.state_reason), ("closed", "closed_by_staff"))
        close_delay.assert_called_once_with(row.pk, "lob_1")
