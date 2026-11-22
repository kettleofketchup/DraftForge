from django.db.models.signals import (
    ModelSignal,
    m2m_changed,
    post_save,
    pre_delete,
    pre_save,
)
from django.test import TestCase

from app.models import Game, Team, Tournament


def _receiver_qualnames(signal: ModelSignal, sender: type) -> list[str]:
    sync_receivers, _async_receivers = signal._live_receivers(sender)
    return [receiver.__qualname__ for receiver in sync_receivers]


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
