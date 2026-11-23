from django.core.management import get_commands
from django.db.models.signals import (
    ModelSignal,
    m2m_changed,
    post_save,
    pre_delete,
    pre_save,
)
from django.test import TestCase

from tournament.models import Game, Team, Tournament


def _receiver_qualnames(signal: ModelSignal, sender: type) -> list[str]:
    sync_receivers, _async_receivers = signal._live_receivers(sender)
    return [receiver.__qualname__ for receiver in sync_receivers]


def _receiver_modules(signal: ModelSignal, sender: type) -> list[str]:
    sync_receivers, _async_receivers = signal._live_receivers(sender)
    return [receiver.__module__ for receiver in sync_receivers]


class SignalOrderTest(TestCase):
    def test_game_post_save(self) -> None:
        self.assertEqual(
            _receiver_qualnames(post_save, Game),
            [
                "ManagerMixin._post_save",
                "sync_tournament_on_game_result",
                "lobby_on_game_saved",
            ],
        )

    def test_game_pre_save(self) -> None:
        self.assertEqual(
            _receiver_qualnames(pre_save, Game),
            [
                "ManagerMixin._pre_save",
                "reset_herodraft_on_team_change",
                "track_game_winner_change",
            ],
        )

    def test_game_pre_delete(self) -> None:
        self.assertEqual(
            _receiver_qualnames(pre_delete, Game), ["lobby_on_game_deleted"]
        )

    def test_team_members_m2m_changed(self) -> None:
        self.assertEqual(
            _receiver_qualnames(m2m_changed, Team.members.through),
            [
                "herodraft_chat_roster_tenure",
                "handle_team_member_removal",
                "invalidate_m2m",
            ],
        )

    def test_tournament_users_m2m_changed(self) -> None:
        self.assertEqual(
            _receiver_qualnames(m2m_changed, Tournament.users.through),
            [
                "handle_tournament_user_removal",
                "handle_tournament_user_addition",
                "invalidate_m2m",
            ],
        )

    def test_receivers_live_in_moved_modules(self) -> None:
        cases = [
            (
                post_save,
                Game,
                ["cacheops.query", "tournament.signals", "lobby.signals"],
            ),
            (
                pre_save,
                Game,
                ["cacheops.query", "draft.signals", "tournament.signals"],
            ),
            (pre_delete, Game, ["lobby.signals"]),
            (
                m2m_changed,
                Team.members.through,
                ["draft.signals", "tournament.signals", "cacheops.query"],
            ),
            (
                m2m_changed,
                Tournament.users.through,
                ["tournament.signals", "tournament.signals", "cacheops.query"],
            ),
        ]
        for signal, sender, modules in cases:
            with self.subTest(sender=sender.__name__):
                self.assertEqual(_receiver_modules(signal, sender), modules)


class TournamentCommandsTest(TestCase):
    def test_commands_resolve_to_tournament(self) -> None:
        commands = get_commands()
        for name in (
            "audit_team_leadership",
            "import_prod_tournament",
            "sync_prod_tournaments",
        ):
            with self.subTest(command=name):
                self.assertEqual(commands[name], "tournament")
