from collections.abc import Callable

from discordbot.models import DMKind


def signup_reminder_key(*, event_id: int, user_pk: int) -> str:
    return f"signup_reminder:event:{event_id}:user:{user_pk}"


def tournament_draft_link_key(*, task_id: str, discord_id: str) -> str:
    return f"tournament_draft_link:run:{task_id}:discord:{discord_id}"


def tournament_herodraft_link_key(*, task_id: str, discord_id: str) -> str:
    return f"tournament_herodraft_link:run:{task_id}:discord:{discord_id}"


def lobby_info_key(*, game_lobby_id: int, task_id: str, discord_id: str) -> str:
    return f"lobby_info:lobby:{game_lobby_id}:run:{task_id}:discord:{discord_id}"


def signup_confirmation_key(*, interaction_id: int | str) -> str:
    return f"signup_confirmation:interaction:{interaction_id}"


def test_notification_key(*, event_pk: int, discord_id: str, request_id: str) -> str:
    return f"test_notification:event:{event_pk}:discord:{discord_id}:req:{request_id}"


test_notification_key.__test__ = False  # type: ignore[attr-defined]


KEY_BUILDERS: dict[DMKind, Callable[..., str]] = {
    DMKind.SIGNUP_REMINDER: signup_reminder_key,
    DMKind.TOURNAMENT_DRAFT_LINK: tournament_draft_link_key,
    DMKind.TOURNAMENT_HERODRAFT_LINK: tournament_herodraft_link_key,
    DMKind.LOBBY_INFO: lobby_info_key,
    DMKind.SIGNUP_CONFIRMATION: signup_confirmation_key,
    DMKind.TEST_NOTIFICATION: test_notification_key,
}
