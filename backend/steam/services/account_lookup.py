import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from typing import Any, Final

import requests
from django.conf import settings
from django.core.cache import cache
from django.db import connection

from app.models import CustomUser
from steam.utils.steam_api_caller import SteamAPI
from telemetry.logging import get_logger

log = get_logger(__name__)

STEAM_ACCOUNT_FOUND_TTL: Final[int] = 60 * 60
STEAM_ACCOUNT_MISSING_TTL: Final[int] = 15 * 60
STEAM_ACCOUNT_LOOKUP_TIMEOUT: Final[tuple[float, float]] = (1.0, 1.5)
STEAM_ACCOUNT_LOOKUP_BUDGET_S: Final[float] = 2.0
USER_LOOKUP_LIMIT: Final[int] = 10
GLOBAL_LOOKUP_LIMIT: Final[int] = 60

_USER_BUDGET_TTL: Final[int] = 60 * 60
_GLOBAL_BUDGET_TTL: Final[int] = 120

_executor: Final[ThreadPoolExecutor] = ThreadPoolExecutor(
    max_workers=4, thread_name_prefix="steam-lookup"
)


class SteamLookupRateLimited(Exception):
    pass


class _LookupFailed(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def cached_exists_key(account_id: int) -> str:
    return f"steam_account_exists:{account_id}"


def _cached(account_id: int) -> bool | None:
    value = cache.get(cached_exists_key(account_id))
    return value if isinstance(value, bool) else None


def _charge(key: str, ttl: int) -> int:
    cache.add(key, 0, ttl)
    try:
        return cache.incr(key)
    except ValueError:
        cache.set(key, 1, ttl)
        return 1


def _fetch(account_id: int) -> dict[str, Any] | None:
    return SteamAPI().get_player_summaries(
        account_id + CustomUser.STEAM_ID_64_BASE,
        timeout=STEAM_ACCOUNT_LOOKUP_TIMEOUT,
    )


def _interpret(payload: Any) -> bool:
    if payload is None:
        raise _LookupFailed("http_error")
    if not isinstance(payload, dict):
        raise _LookupFailed("malformed_response")
    response = payload.get("response")
    players = response.get("players") if isinstance(response, dict) else None
    if not isinstance(players, list):
        raise _LookupFailed("malformed_response")
    return bool(players)


def _lookup_uncached(account_id: int) -> bool | None:
    used = _charge(
        f"steam_lookup_budget:global:{int(time.time() // 60)}", _GLOBAL_BUDGET_TTL
    )
    if used > GLOBAL_LOOKUP_LIMIT:
        log.warning(
            "steam_account_lookup_budget_exhausted",
            system="steam",
            subsystem="account_lookup",
            account_id=account_id,
            reason="global_limit",
        )
        return None

    try:
        future = _executor.submit(_fetch, account_id)
        try:
            payload = future.result(timeout=STEAM_ACCOUNT_LOOKUP_BUDGET_S)
        except FutureTimeout as exc:
            raise _LookupFailed("timeout") from exc
        except requests.exceptions.JSONDecodeError as exc:
            raise _LookupFailed("invalid_json") from exc
        except ValueError as exc:
            raise _LookupFailed("missing_api_key") from exc
        except Exception as exc:
            raise _LookupFailed(type(exc).__name__) from exc
        exists = _interpret(payload)
    except _LookupFailed as exc:
        log.warning(
            "steam_account_lookup_failed",
            system="steam",
            subsystem="account_lookup",
            account_id=account_id,
            reason=exc.reason,
        )
        return None

    cache.set(
        cached_exists_key(account_id),
        exists,
        STEAM_ACCOUNT_FOUND_TTL if exists else STEAM_ACCOUNT_MISSING_TTL,
    )
    log.debug(
        "steam_account_lookup_result",
        system="steam",
        subsystem="account_lookup",
        account_id=account_id,
        exists=exists,
    )
    return exists


def _in_atomic(account_id: int) -> bool:
    if not connection.in_atomic_block:
        return False
    log.error(
        "steam_account_lookup_in_atomic",
        system="steam",
        subsystem="account_lookup",
        account_id=account_id,
        reason="in_atomic_block",
    )
    return True


def steam_account_exists(account_id: int, *, cache_only: bool = False) -> bool | None:
    if not settings.STEAM_ACCOUNT_LOOKUP_ENABLED:
        return None
    cached = _cached(account_id)
    if cached is not None:
        return cached
    if cache_only or _in_atomic(account_id):
        return None
    return _lookup_uncached(account_id)


def ensure_steam_account_exists(
    account_id: int, *, budget_user: CustomUser
) -> bool | None:
    if not settings.STEAM_ACCOUNT_LOOKUP_ENABLED:
        return None
    cached = _cached(account_id)
    if cached is not None:
        return cached
    if _in_atomic(account_id):
        return None
    used = _charge(f"steam_lookup_budget:user:{budget_user.pk}", _USER_BUDGET_TTL)
    if used > USER_LOOKUP_LIMIT:
        log.warning(
            "steam_account_lookup_rate_limited",
            system="steam",
            subsystem="account_lookup",
            account_id=account_id,
            user_id=budget_user.pk,
            reason="user_limit",
        )
        raise SteamLookupRateLimited
    return _lookup_uncached(account_id)
