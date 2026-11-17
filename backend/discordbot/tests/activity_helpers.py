from typing import ClassVar

from discordbot.activity_intent import intent_key
from discordbot.utils import redis_client


class ClearIntentsMixin:
    intent_user_ids: ClassVar[tuple[str, ...]] = ("101", "102", "103", "777")

    def setUp(self) -> None:
        super().setUp()  # type: ignore[misc]
        keys = [intent_key(i) for i in self.intent_user_ids]
        redis_client.delete(*keys)
        self.addCleanup(redis_client.delete, *keys)  # type: ignore[attr-defined]
