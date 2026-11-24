from __future__ import annotations

import re
import time
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from django.conf import settings
from django.utils import timezone

from common.game import GameType
from league.models import League
from lobby.bot_access.base import empty_snapshot
from lobby.bot_access.schemas import (
    AccessNote,
    AccessState,
    BotAccessRow,
    BotAccessSnapshot,
    BotIdentity,
    BotStatus,
    PlatformLink,
    RefreshOutcome,
    RowRefresh,
    ServiceState,
)
from lobby.client import (
    DotaLobbyClient,
    DotaLobbyError,
    DotaLobbyNotConfigured,
    DotaLobbyUnavailable,
)
from lobby.schemas import BotLeagues, BotView, LeagueView
from telemetry.logging import get_logger

log = get_logger(__name__)

MIN_BOT_CALL_SECONDS = 1.0
STEAM_ID_RE = re.compile(r"^7656119\d{10}$")
STEAM_ID_MIN = 76561197960265728
CONNECTING_STATES = frozenset(
    {
        "connecting",
        "logging_on",
        "authenticating",
        "steam_online",
        "gc_hello",
        "gc_queued",
        "gc_ready",
    }
)
OFFLINE_STATES = frozenset(
    {
        "disconnected",
        "backoff",
        "cooling_down",
        "needs_attention",
        "suspended",
        "stopped",
    }
)


def bot_status(bot: BotView) -> BotStatus:
    if bot.ready:
        if bot.lobby:
            return "busy"
        return "connecting" if bot.lobby_stale else "available"
    if bot.state in CONNECTING_STATES:
        return "connecting"
    if bot.state in OFFLINE_STATES:
        return "offline"
    return "unknown"


def steam_identity(steam_id: str | None) -> BotIdentity | None:
    if not steam_id or not STEAM_ID_RE.match(steam_id) or int(steam_id) < STEAM_ID_MIN:
        return None
    return BotIdentity(
        kind="steam",
        value=steam_id,
        profile_url=f"https://steamcommunity.com/profiles/{steam_id}",
    )


def league_admin_link(league_id: int) -> PlatformLink:
    return PlatformLink(
        kind="league_admin_portal",
        url=f"https://www.dota2.com/league/{int(league_id)}/admins",
    )


def _parse_league_id(external_league_id: str) -> int | None:
    try:
        league_id = int(external_league_id)
    except (TypeError, ValueError):
        return None
    return league_id if league_id > 0 else None


def _key(name: str) -> str:
    return name.lower()


@dataclass
class _Access:
    access: AccessState
    note: AccessNote | None = None
    checked_at: datetime | None = None


class DotaBotAccess:
    game_type: GameType | None = GameType.DOTA2
    supported: bool = True
    provider: str = "dota2"

    def __init__(
        self,
        client_factory: Callable[[], DotaLobbyClient] = DotaLobbyClient,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._client_factory = client_factory
        self._clock = clock

    def external_league_id(self, league: League) -> str | None:
        if league.steam_league_id is None:
            return None
        return str(league.steam_league_id)

    def snapshot(self, external_league_id: str) -> BotAccessSnapshot:
        ready = self._prepare(external_league_id)
        if isinstance(ready, BotAccessSnapshot):
            return ready
        client, league_id = ready
        return self._snapshot(client, league_id, None)

    def refresh(self, external_league_id: str) -> BotAccessSnapshot:
        ready = self._prepare(external_league_id)
        if isinstance(ready, BotAccessSnapshot):
            return ready
        client, league_id = ready
        refresh_by_name: dict[str, RowRefresh] = {}
        try:
            result = client.refresh_leagues()
        except DotaLobbyError as exc:
            self._log_failure(league_id, "refresh_leagues", exc)
            outcome = _refresh_outcome(exc)
        else:
            outcome = "ok"
            for item in result.results:
                refresh_by_name[_key(item.bot)] = _row_refresh(item.status)
        counts = Counter(refresh_by_name.values())
        log.info(
            "bot_access_refreshed",
            system="lobby",
            subsystem="bot_access",
            league_id=league_id,
            outcome=outcome,
            ok=counts["ok"],
            failed=counts["failed"],
            not_ready=counts["not_ready"],
        )
        snap = self._snapshot(client, league_id, refresh_by_name)
        snap.refresh_outcome = outcome
        return snap

    def _prepare(
        self, external_league_id: str
    ) -> tuple[DotaLobbyClient, int] | BotAccessSnapshot:
        league_id = _parse_league_id(external_league_id)
        if league_id is None:
            return empty_snapshot(self, external_league_id, "league_not_linked")
        if not settings.DOTA_LOBBY_ENABLED:
            return empty_snapshot(self, external_league_id, "disabled")
        try:
            client = self._client_factory()
        except DotaLobbyNotConfigured:
            return empty_snapshot(self, external_league_id, "not_configured")
        return client, league_id

    def _snapshot(
        self,
        client: DotaLobbyClient,
        league_id: int,
        refresh_by_name: dict[str, RowRefresh] | None,
    ) -> BotAccessSnapshot:
        external_id = str(league_id)
        try:
            bots = client.list_bots()
        except DotaLobbyError as exc:
            self._log_failure(league_id, "list_bots", exc)
            unavailable = isinstance(exc, DotaLobbyUnavailable) or exc.retryable
            snap = empty_snapshot(
                self,
                external_id,
                "unavailable" if unavailable else "error",
                code=exc.code,
                retryable=exc.retryable,
            )
            snap.league_link = league_admin_link(league_id)
            return snap

        view: LeagueView | None = None
        all_unknown = False
        try:
            view = client.get_league(league_id, retry=False)
        except DotaLobbyError as exc:
            listed = any(league_id in b.leagues for b in bots)
            if exc.status == 404 and not listed:
                view = LeagueView(league_id=league_id)
            else:
                self._log_failure(league_id, "get_league", exc)
                all_unknown = exc.status == 404

        if view is not None:
            holders = {_key(h.bot): h for h in view.holders}
            stale = {_key(b.name) for b in view.bots if b.stale}
            is_holder = {_key(b.name): _key(b.name) in holders for b in bots}
        else:
            holders, stale = {}, set()
            is_holder = {_key(b.name): league_id in b.leagues for b in bots}

        deadline: float | None = None
        refresh_map = {_key(k): v for k, v in (refresh_by_name or {}).items()}
        seen_unknown: set[str] = set()
        rows: list[tuple[tuple[bool, str, str], BotAccessRow]] = []
        for bot in bots:
            key = _key(bot.name)
            if view is None:
                if all_unknown or league_id not in bot.leagues:
                    result = _Access("unknown")
                else:
                    result = _Access("unverified")
            else:
                holder = holders.get(key)
                if holder is not None and holder.source == "gc" and holder.verified:
                    if key in stale:
                        result = _Access(
                            "unverified", "not_rechecked", holder.refreshed_at
                        )
                    else:
                        result = _Access("verified", None, holder.refreshed_at)
                else:
                    if deadline is None:
                        deadline = self._clock() + client.timeout
                    inventory = self._bot_leagues(client, league_id, bot, deadline)
                    result = _from_inventory(
                        bot,
                        league_id,
                        inventory,
                        config_holder=holder is not None and holder.source == "config",
                    )

            status: BotStatus | None = None
            if is_holder[key]:
                status = bot_status(bot)
                if status == "unknown" and bot.state not in seen_unknown:
                    seen_unknown.add(bot.state)
                    log.info(
                        "bot_access_unknown_bot_state",
                        system="lobby",
                        subsystem="bot_access",
                        state=bot.state,
                    )

            identity = steam_identity(bot.steam_id)
            sort_key = (identity is None, identity.value if identity else "", bot.name)
            rows.append(
                (
                    sort_key,
                    BotAccessRow(
                        position=0,
                        identity=identity,
                        status=status,
                        access=result.access,
                        access_note=result.note,
                        access_checked_at=result.checked_at,
                        refresh=refresh_map.get(key),
                    ),
                )
            )

        rows.sort(key=lambda pair: pair[0])
        ordered: list[BotAccessRow] = []
        for position, (_, row) in enumerate(rows, start=1):
            row.position = position
            ordered.append(row)
        held = _held_count(rows, is_holder)
        return BotAccessSnapshot(
            game_type=int(GameType.DOTA2),
            supported=True,
            provider=self.provider,
            external_league_id=external_id,
            service=ServiceState(status="ok"),
            bots=ordered,
            held_count=held,
            league_link=league_admin_link(league_id),
            checked_at=timezone.now(),
        )

    def _bot_leagues(
        self, client: DotaLobbyClient, league_id: int, bot: BotView, deadline: float
    ) -> BotLeagues | None:
        remaining = deadline - self._clock()
        if remaining < MIN_BOT_CALL_SECONDS:
            return None
        try:
            return client.get_bot_leagues(bot.name, timeout=remaining)
        except DotaLobbyError as exc:
            self._log_failure(league_id, "get_bot_leagues", exc)
            return None

    def _log_failure(self, league_id: int, action: str, exc: DotaLobbyError) -> None:
        log.warning(
            "bot_access_upstream_failed",
            system="lobby",
            subsystem="bot_access",
            league_id=league_id,
            action=action,
            code=exc.code,
            upstream_status=exc.status,
            retryable=exc.retryable,
        )


def _refresh_outcome(exc: DotaLobbyError) -> RefreshOutcome:
    if exc.status == 409 and exc.code == "invalid_state":
        return "not_supported_upstream"
    if isinstance(exc, DotaLobbyUnavailable) and exc.detail == "ReadTimeout":
        return "timed_out"
    return "unavailable"


def _row_refresh(status: str) -> RowRefresh:
    if status == "ok":
        return "ok"
    if status == "not_ready":
        return "not_ready"
    return "failed"


def _from_inventory(
    bot: BotView,
    league_id: int,
    inventory: BotLeagues | None,
    *,
    config_holder: bool,
) -> _Access:
    if inventory is None:
        return _Access("unknown")
    ok_at = inventory.refresh.ok_at
    if ok_at is None:
        return _Access("unverified" if league_id in bot.leagues else "unknown")
    entries = [e for e in inventory.leagues if e.league_id == league_id]
    gc_entry = next((e for e in entries if e.source == "gc" and e.verified), None)
    if gc_entry is not None:
        if gc_entry.stale:
            return _Access("unverified", "not_rechecked", gc_entry.refreshed_at)
        return _Access("verified", None, gc_entry.refreshed_at or ok_at)
    if any(e.source == "gc" and e.stale for e in inventory.leagues):
        return _Access("unknown", "not_rechecked", ok_at)
    config_held = config_holder or any(e.source == "config" for e in entries)
    return _Access("missing", "allowed_unverified" if config_held else None, ok_at)


def _held_count(
    rows: list[tuple[tuple[bool, str, str], BotAccessRow]],
    is_holder: dict[str, bool],
) -> int:
    return sum(
        1
        for (_, _, name), row in rows
        if is_holder[_key(name)] and row.access in ("verified", "unverified")
    )
