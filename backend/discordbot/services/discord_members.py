"""Celery-safe helper for fetching cached Discord guild members.

Lives in its own module (instead of inside `discordbot.services.users`)
because `users.py` is a DRF views module — its top-level imports pull in
`app.models`, `social_django.models`, cacheops decorators, etc. Loading
those modules touches `connections['default']`, which on the Celery
worker hits `settings_celery.DATABASES = {}` and raises
`ImproperlyConfigured`. The `refresh_avatars_batched` task needs this
helper but must NOT pull in the ORM-heavy DRF module.

Keep this module's imports limited to `requests`, `time`,
`django.core.cache`, `django.conf.settings` and `telemetry.logging`.
"""

import time

import requests
from django.conf import settings
from django.core.cache import cache

from telemetry.logging import get_logger

log = get_logger(__name__)

# Cache architecture for guild members:
#
#   `discord_members_<guild_id>` — full member list per guild, paginated
#   from Discord and cached for DISCORD_MEMBER_CACHE_TTL_S (1 hour).
#
# The cache is per process backend: Daphne uses the Redis default cache,
# celery workers (config.settings_celery, no CACHES) use process-local
# LocMem, so the two never share entries.
#   1. Admin member search / add-to-tournament (Daphne) — admins searching
#      a Discord member who joined recently force a refresh via the
#      `refresh_discord_members` endpoint (5-min cooldown).
#   2. Daily avatar refresh — the `refresh_avatars_batched` Celery task
#      fetches through this helper in the worker; its LocMem entry only
#      saves repeat fetches within that worker process.
DISCORD_MEMBER_CACHE_TTL_S = 60 * 60  # 1 hour

# Per-request bound for Discord REST calls. Without one, a request whose TCP
# handshake is dropped (filtered egress) blocks its caller indefinitely.
DISCORD_HTTP_TIMEOUT_S = 10

DISCORD_MAX_RETRY_AFTER_S = 10.0


class DiscordMembersFetchError(Exception):
    pass


def _retry_after_s(response: requests.Response) -> float | None:
    try:
        body = response.json()
    except ValueError:
        body = None
    if isinstance(body, dict) and body.get("retry_after") is not None:
        try:
            return float(body["retry_after"])
        except (TypeError, ValueError):
            pass
    header = response.headers.get("Retry-After")
    if header is None:
        return None
    try:
        return float(header)
    except ValueError:
        return None


def _get_page(
    url: str, headers: dict[str, str], params: dict[str, int | str], guild_id: str
) -> list[dict]:
    retried = False
    while True:
        try:
            response = requests.get(
                url, headers=headers, params=params, timeout=DISCORD_HTTP_TIMEOUT_S
            )
        except requests.exceptions.RequestException as e:
            raise DiscordMembersFetchError(f"Discord API error: {e}") from e

        if response.status_code == 429:
            wait_s = _retry_after_s(response)
            if retried or wait_s is None or wait_s > DISCORD_MAX_RETRY_AFTER_S:
                raise DiscordMembersFetchError(
                    f"Discord API rate limited (retry_after={wait_s})"
                )
            log.warning(
                "discord_members_rate_limited",
                system="discord",
                subsystem="members",
                guild_id=guild_id,
                retry_after_s=wait_s,
            )
            time.sleep(wait_s)
            retried = True
            continue

        try:
            response.raise_for_status()
            return response.json()
        except (requests.exceptions.RequestException, ValueError) as e:
            raise DiscordMembersFetchError(f"Discord API error: {e}") from e


def get_discord_members_data(
    guild_id: str | None = None,
    *,
    force: bool = False,
    write_cache: bool = True,
) -> list[dict]:
    """Get Discord guild members as a raw list (cache-backed).

    `force=True` skips the cache read; `write_cache=False` skips the cache
    write. Beat name syncs pass `write_cache=False`, so the admin search
    cache refreshes only through `refresh_discord_members`.

    A 429 is retried once when Retry-After is at most
    DISCORD_MAX_RETRY_AFTER_S. Any page failure raises
    DiscordMembersFetchError and nothing is cached.
    """
    if guild_id is None:
        guild_id = settings.DISCORD_GUILD_ID
    bot_token = settings.DISCORD_BOT_TOKEN
    # Skip if Discord bot token is not configured (e.g., in CI): the request
    # can only fail, and an empty result is not cached.
    if not bot_token:
        return []

    cache_key = f"discord_members_{guild_id}"
    if not force:
        cached_members = cache.get(cache_key)
        if cached_members:
            return cached_members

    url = f"{settings.DISCORD_API_BASE_URL}/guilds/{guild_id}/members"
    headers = {"Authorization": f"Bot {bot_token}"}
    after: str | None = None
    limit = 1000
    members: list[dict] = []

    while True:
        params: dict[str, int | str] = {"limit": limit}
        if after:
            params["after"] = after

        page = _get_page(url, headers, params, str(guild_id))
        if not page:
            break
        after = page[-1]["user"]["id"]
        members.extend(page)
        if len(page) < limit:
            break

    if write_cache:
        cache.set(cache_key, members, timeout=DISCORD_MEMBER_CACHE_TTL_S)
    return members
