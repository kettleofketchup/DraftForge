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
# Two consumer patterns share this single cache:
#   1. Admin member search / add-to-tournament — admins searching a
#      Discord member who joined recently force a refresh via the
#      `refresh_discord_members` endpoint (5-min cooldown). That repaves
#      the cache, so subsequent searches AND the daily avatar refresh
#      (item 2) see the new member without their own Discord call.
#   2. Daily avatar refresh — the `refresh_avatars_batched` Celery task
#      reads this cache to update the User.avatar column for any
#      Discord-linked user. Daily cadence is enough; admin-triggered
#      refreshes (item 1) cover the "user joined since yesterday" gap.
#
# The 15-second TTL this used to have (sub-request burst dedup only) was
# replaced when we made the cache load-bearing for the daily avatar
# task — that task needs the cache to actually hold data between
# admin-triggered fills, not for 15 seconds.
DISCORD_MEMBER_CACHE_TTL_S = 60 * 60  # 1 hour


def get_discord_members_data(guild_id=None):
    """Get Discord guild members as a raw list (cache-backed).

    Args:
        guild_id: Discord guild ID. Defaults to settings.DISCORD_GUILD_ID.
    """
    if guild_id is None:
        guild_id = settings.DISCORD_GUILD_ID
    bot_token = settings.DISCORD_BOT_TOKEN

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
            response = requests.get(url, headers=headers, params=params)
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
