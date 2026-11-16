"""Celery-safe helper for fetching cached Discord guild members.

Lives in its own module (instead of inside `discordbot.services.users`)
because `users.py` is a DRF views module — its top-level imports pull in
`app.models`, `social_django.models`, cacheops decorators, etc. Loading
those modules touches `connections['default']`, which on the Celery
worker hits `settings_celery.DATABASES = {}` and raises
`ImproperlyConfigured`. The `refresh_avatars_batched` task needs this
helper but must NOT pull in the ORM-heavy DRF module.

Keep this module's imports limited to `requests`, `django.core.cache`,
and `django.conf.settings`.
"""

import requests
from django.conf import settings
from django.core.cache import cache

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


def get_discord_members_data(guild_id=None):
    """Get Discord guild members as a raw list (cache-backed).

    Args:
        guild_id: Discord guild ID. Defaults to settings.DISCORD_GUILD_ID.
    """
    if guild_id is None:
        guild_id = settings.DISCORD_GUILD_ID
    bot_token = settings.DISCORD_BOT_TOKEN
    # Skip if Discord bot token is not configured (e.g., in CI): the request
    # can only fail, and an empty result is not cached.
    if not bot_token:
        return []

    cache_key = f"discord_members_{guild_id}"
    cached_members = cache.get(cache_key)
    if cached_members:
        return cached_members

    url = f"{settings.DISCORD_API_BASE_URL}/guilds/{guild_id}/members"
    headers = {"Authorization": f"Bot {bot_token}"}
    after = None
    limit = 1000
    members: list = []

    while True:
        params = {"limit": limit}
        if after:
            params["after"] = after

        try:
            response = requests.get(
                url, headers=headers, params=params, timeout=DISCORD_HTTP_TIMEOUT_S
            )
            response.raise_for_status()
            page = response.json()
            if not page:
                break
            after = page[-1]["user"]["id"]
            members.extend(page)
            if len(page) < limit:
                break
        except requests.exceptions.RequestException as e:
            raise Exception(f"Discord API error: {str(e)}")

    cache.set(cache_key, members, timeout=DISCORD_MEMBER_CACHE_TTL_S)
    return members
