from __future__ import annotations

from typing import Protocol, runtime_checkable

from django.utils import timezone

from common.game import GameType
from league.models import League
from lobby.bot_access.schemas import BotAccessSnapshot, ServiceState, ServiceStatus


@runtime_checkable
class BotAccessProvider(Protocol):
    game_type: GameType | None
    supported: bool
    provider: str

    def external_league_id(self, league: League) -> str | None: ...

    def snapshot(self, external_league_id: str) -> BotAccessSnapshot: ...

    def refresh(self, external_league_id: str) -> BotAccessSnapshot: ...


def empty_snapshot(
    provider: BotAccessProvider,
    external_league_id: str | None,
    status: ServiceStatus,
    *,
    code: str | None = None,
    retryable: bool = False,
) -> BotAccessSnapshot:
    return BotAccessSnapshot(
        game_type=None if provider.game_type is None else int(provider.game_type),
        supported=provider.supported,
        provider=provider.provider,
        external_league_id=external_league_id,
        service=ServiceState(status=status, code=code, retryable=retryable),
        bots=[],
        held_count=0,
        checked_at=timezone.now(),
    )


class UnsupportedBotAccess:
    game_type: GameType | None = None
    supported: bool = False
    provider: str = "unsupported"

    def external_league_id(self, league: League) -> str | None:
        return None

    def snapshot(self, external_league_id: str) -> BotAccessSnapshot:
        return empty_snapshot(self, external_league_id, "unsupported")

    def refresh(self, external_league_id: str) -> BotAccessSnapshot:
        return empty_snapshot(self, external_league_id, "unsupported")
