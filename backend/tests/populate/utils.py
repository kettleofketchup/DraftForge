"""
Utility functions for test database population.
"""

import os
import random
import re
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any, Final

import redis
from cacheops.redis import redis_client as cacheops_redis
from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from django.db.models import Q, QuerySet

from app.models import CustomUser, GameType
from discordbot.services.users import get_discord_members_data
from events.models import Event, EventSignup, SignupLedgerEntry
from league.models import League, LeagueUser
from org.mmr import LEAGUE_GAME, org_mmr_for, validate_org_mmr
from org.models import Organization, OrgUser, OrgUserGameMmr, PromoSend
from org.standing import api as standing
from user.models import PositionsModel

from .avatars import apply_committed_avatars
from .constants import (
    BRACKET_STEAM_ID_BASE,
    BRACKET_USER_COUNT,
    DTX_ORG_NAME,
    MOCK_USERNAMES,
    TOURNAMENT_USERS,
)

if TYPE_CHECKING:
    from league.models import LeagueUser

RESERVED_STEAM_ACCOUNT_IDS: Final[range] = range(
    BRACKET_STEAM_ID_BASE, BRACKET_STEAM_ID_BASE + BRACKET_USER_COUNT
)


def generate_mock_discord_members(count=100):
    """
    Generate mock Discord member data for testing when Discord API is unavailable.
    Returns data in the same format as get_discord_members_data().
    """
    members = []
    used_usernames = set()

    for i in range(count):
        if i < len(MOCK_USERNAMES):
            username = MOCK_USERNAMES[i]
        else:
            username = f"player_{i}"

        if username in used_usernames:
            username = f"{username}_{i}"
        used_usernames.add(username)

        # Generate a fake Discord ID (snowflake format - 18 digit number)
        # Use 200... range to avoid conflict with test auth users (100...)
        discord_id = str(200000000000000000 + i)

        member = {
            "user": {
                "id": discord_id,
                "username": username,
                "avatar": None,
                "discriminator": "0",
                "global_name": username.replace("_", " ").title(),
            },
            "nick": None,
            "joined_at": "2024-01-01T00:00:00.000000+00:00",
        }
        members.append(member)

    return members


def unused_steam_account_id(taken: set[int] | None = None) -> int:
    """Draw a Friend ID that no user holds yet.

    steam_account_id is UNIQUE. Drawing 1..1_000_000 unchecked for ~100 users
    per populate is a birthday problem, and the losing draw aborts the whole
    run with `IntegrityError: UNIQUE constraint failed:
    app_customuser.steam_account_id`. CI hits this whenever a models.py edit
    busts the test-db image hash and every job falls back to a fresh populate.

    Pass one `taken` set across a run to load the held ids once; the drawn id
    is added to it. Ids reserved for the bracket scenario are never drawn.
    """
    if taken is None:
        taken = set(
            CustomUser.objects.exclude(steam_account_id=None).values_list(
                "steam_account_id", flat=True
            )
        )
    while True:
        candidate = random.randint(1, 1_000_000)
        if candidate not in taken and candidate not in RESERVED_STEAM_ACCOUNT_IDS:
            taken.add(candidate)
            return candidate


def create_user(
    user_data: dict[str, Any],
    organization: Organization | None = None,
    taken_steam_ids: set[int] | None = None,
) -> CustomUser:
    """
    Create a user from Discord data.

    Args:
        user_data: Discord user data dict
        organization: Optional Organization to create OrgUser for
        taken_steam_ids: Friend IDs already held, shared across a populate run
    """
    user, created = CustomUser.objects.get_or_create(discordId=user_data["user"]["id"])
    if not created:
        if organization:
            ensure_org_user(user, organization)
        return user

    mmr = random.randint(200, 6000)
    with transaction.atomic():
        print("creating user", user_data["user"]["username"])
        user.createFromDiscordData(user_data)
        positions = PositionsModel.objects.create()
        positions.carry = random.randint(0, 5)
        positions.mid = random.randint(0, 5)
        positions.offlane = random.randint(0, 5)
        positions.soft_support = random.randint(0, 5)
        positions.hard_support = random.randint(0, 5)
        positions.save()
        # All mock users get a Friend ID for testing
        user.steam_account_id = unused_steam_account_id(taken_steam_ids)

        user.positions = positions
        user.save()

        # Create OrgUser for organization-scoped MMR
        if organization:
            ensure_org_user(user, organization, mmr=mmr)

    return user


def ensure_org_user(
    user: CustomUser,
    organization: Organization,
    mmr: int | None = None,
    guild_nickname: str | None = None,
    game_mmrs: dict[int, int] | None = None,
) -> OrgUser:
    """Ensure OrgUser exists for user in organization.

    `mmr` is the Dota 2 org MMR. A None value, or a game absent from
    `game_mmrs`, leaves that game as it is; an explicit 0 clears it.
    A None guild_nickname leaves an existing server nickname as it is.
    """
    wanted: dict[int, int] = dict(game_mmrs or {})
    if mmr is not None:
        wanted[GameType.DOTA2] = mmr
    for game_type, value in wanted.items():
        validate_org_mmr(game_type, value)
    org_user, created = OrgUser.objects.get_or_create(
        user=user,
        organization=organization,
        defaults={"guild_nickname": guild_nickname},
    )
    if (
        not created
        and guild_nickname is not None
        and org_user.guild_nickname != guild_nickname
    ):
        org_user.guild_nickname = guild_nickname
        org_user.save(update_fields=["guild_nickname"])
    for game_type, value in wanted.items():
        if value:
            OrgUserGameMmr.objects.update_or_create(
                org_user=org_user, game_type=game_type, defaults={"mmr": value}
            )
        else:
            OrgUserGameMmr.objects.filter(
                org_user=org_user, game_type=game_type
            ).delete()
    return org_user


def delete_events(events: QuerySet[Event]) -> int:
    """Delete events with their signup ledger rows, which a plain delete orphans."""
    pks = list(events.values_list("pk", flat=True))
    SignupLedgerEntry.objects.filter(event_id__in=pks).purge()
    return Event.objects.nocache().filter(pk__in=pks).delete()[0]


def delete_event_signups(event: Event) -> int:
    """Delete an event's signups with its signup ledger rows."""
    SignupLedgerEntry.objects.filter(event=event).purge()
    return EventSignup.objects.nocache().filter(event=event).delete()[0]


def delete_ledger_for_users(pks: Iterable[int]) -> None:
    """Drop these users' ledger rows and promo sends so the users can be deleted.

    Standing ledger rows are RESTRICT: deleting a user whose OrgUser holds
    them raises RestrictedError.
    """
    pks = list(pks)
    for blockers in standing.deletion_blockers(pks):
        blockers.delete()
    PromoSend.objects.nocache().filter(
        Q(sender_id__in=pks) | Q(recipient_id__in=pks)
    ).delete()


def ensure_league_user(
    user: CustomUser, org_user: OrgUser, league: League
) -> "LeagueUser":
    """Ensure LeagueUser exists for user in league."""

    league_user, created = LeagueUser.objects.get_or_create(
        user=user,
        org_user=org_user,
        league=league,
        defaults={"mmr": org_mmr_for(org_user.organization_id, user.pk, LEAGUE_GAME)},
    )
    return league_user


# One script, so no cache miss can interleave: a SCAN-then-DEL could delete a
# fresh conj key while missing the result key it guards, leaving that result
# with no invalidator until its timeout.
_DELETE_MATCHING_LUA = """
local keys = redis.call('KEYS', ARGV[1])
for i = 1, #keys, 5000 do
    redis.call('DEL', unpack(keys, i, math.min(i + 4999, #keys)))
end
return #keys
"""
_GLOB_SPECIAL = re.compile(r"([*?\[\]\\])")


def _glob_escape(value: str) -> str:
    return _GLOB_SPECIAL.sub(r"\\\1", value)


def flush_redis_cache() -> None:
    """Drop cached query results after population.

    Reset endpoints call this while other drafts run on the same Redis, so it
    deletes only cacheops and Django cache keys. A FLUSHALL would also wipe the
    channel-layer groups, draft connection counts, heartbeats, tick locks and
    the Celery broker, silently stopping other drafts' broadcasts and ticks.
    """
    if os.environ.get("DISABLE_CACHE", "").lower() in ("true", "1", "yes"):
        return
    try:
        prefix: str = settings.CACHEOPS_PREFIX(None)
        deleted = int(
            cacheops_redis.eval(_DELETE_MATCHING_LUA, 0, _glob_escape(prefix) + "*")
        )
        if hasattr(cache, "delete_pattern"):
            cache.delete_pattern("*")
        print(f"Redis query cache flushed ({deleted} cacheops keys)")
    except (redis.exceptions.ConnectionError, redis.exceptions.TimeoutError) as e:
        print(f"Redis not available, skipping cache flush: {e}")
    except Exception as e:
        print(f"Warning: Failed to flush Redis cache: {e}")


def test_user_to_dict(test_user):
    """Convert TestUser Pydantic model to dict format for backward compatibility."""
    result = {
        "steam_id": test_user.steam_id,
        "mmr": test_user.mmr or 3000,
        "discord_id": test_user.discord_id,
    }
    if test_user.pk is not None:
        result["pk"] = test_user.pk
    if test_user.positions:
        result["positions"] = {
            "carry": test_user.positions.carry,
            "mid": test_user.positions.mid,
            "offlane": test_user.positions.offlane,
            "soft_support": test_user.positions.soft_support,
            "hard_support": test_user.positions.hard_support,
        }
    return result


# Legacy dict format for backward compatibility
REAL_TOURNAMENT_USERS = {
    username: test_user_to_dict(user) for username, user in TOURNAMENT_USERS.items()
}


def get_or_create_demo_user(username, user_data, organization=None):
    """Get or create a user for demo tournaments with real position data."""

    steam_account_id = user_data.get("steam_id")  # 32-bit Friend ID
    pos_data = user_data.get("positions", {})
    mmr = user_data.get("mmr", 3000)
    explicit_pk = user_data.get("pk")

    if explicit_pk:
        user = CustomUser.objects.filter(pk=explicit_pk).first()
    else:
        user = None

    if not user:
        user = CustomUser.objects.filter(discordId=user_data["discord_id"]).first()
    if not user:
        user = CustomUser.objects.filter(username=username).first()
    if not user and steam_account_id:
        user = CustomUser.objects.filter(steam_account_id=steam_account_id).first()

    if not user:
        positions = PositionsModel.objects.create(
            carry=pos_data.get("carry", 3),
            mid=pos_data.get("mid", 3),
            offlane=pos_data.get("offlane", 3),
            soft_support=pos_data.get("soft_support", 3),
            hard_support=pos_data.get("hard_support", 3),
        )
        create_kwargs = {
            "discordId": user_data["discord_id"],
            "username": username,
            "steam_account_id": steam_account_id,
            "positions": positions,
        }
        if explicit_pk:
            create_kwargs["pk"] = explicit_pk
        user = CustomUser.objects.create(**create_kwargs)
    else:
        if steam_account_id and user.steam_account_id != steam_account_id:
            user.steam_account_id = steam_account_id
        if pos_data and user.positions:
            user.positions.carry = pos_data.get("carry", user.positions.carry)
            user.positions.mid = pos_data.get("mid", user.positions.mid)
            user.positions.offlane = pos_data.get("offlane", user.positions.offlane)
            user.positions.soft_support = pos_data.get(
                "soft_support", user.positions.soft_support
            )
            user.positions.hard_support = pos_data.get(
                "hard_support", user.positions.hard_support
            )
            user.positions.save()
        user.save()

    # Ensure OrgUser exists for DTX organization
    if organization is None:
        organization = Organization.objects.filter(name=DTX_ORG_NAME).first()
    if organization:
        ensure_org_user(user, organization, mmr=mmr)

    apply_committed_avatars([user])
    return user


_discord_avatar_cache: dict[str, str] | None = None


def _get_discord_avatar_cache() -> dict[str, str]:
    """Fetch all guild members once and cache discord_id -> avatar_hash mapping."""
    global _discord_avatar_cache
    if _discord_avatar_cache is not None:
        return _discord_avatar_cache

    try:
        members = get_discord_members_data()
        _discord_avatar_cache = {}
        for member in members:
            user_data = member.get("user", {})
            discord_id = user_data.get("id")
            avatar_hash = user_data.get("avatar")
            if discord_id and avatar_hash:
                _discord_avatar_cache[discord_id] = avatar_hash
        print(f"  Cached {len(_discord_avatar_cache)} Discord avatars from bulk fetch")
    except Exception as e:
        print(f"  Discord API unavailable for avatars: {e}")
        _discord_avatar_cache = {}

    return _discord_avatar_cache


def fetch_discord_avatars_for_users(users: Iterable[CustomUser]) -> None:
    """Apply committed avatars, then any newer ones from the live guild fetch.

    The live fetch only sets non-empty hashes, so it never wipes a committed one.
    """
    users = list(users)
    apply_committed_avatars(users)
    avatar_map = _get_discord_avatar_cache()
    if not avatar_map:
        return

    updated = 0
    for user in users:
        if not user.discordId:
            continue
        avatar_hash = avatar_map.get(user.discordId)
        if avatar_hash and user.avatar != avatar_hash:
            # avatar is a property over base_profile.avatar; the setter
            # persists via bp.save(update_fields=["avatar"]) internally, so an
            # explicit CustomUser.save(update_fields=["avatar"]) crashes since
            # `avatar` is no longer a model field.
            user.avatar = avatar_hash
            updated += 1
    if updated:
        print(f"  Updated {updated} avatars")


@contextmanager
def without_task_publishing() -> Iterator[None]:
    """Send task publishes to an in-memory broker that nothing consumes.

    Populate seeds rows; signals it trips (an org's Discord server id, say)
    must not queue jobs on a real broker, which the host often cannot reach.
    CELERY_BROKER_WRITE_URL outranks every other broker setting.
    """
    saved = os.environ.get("CELERY_BROKER_WRITE_URL")
    os.environ["CELERY_BROKER_WRITE_URL"] = "memory://"
    try:
        yield
    finally:
        if saved is None:
            del os.environ["CELERY_BROKER_WRITE_URL"]
        else:
            os.environ["CELERY_BROKER_WRITE_URL"] = saved


# Backwards compatibility aliases (with underscore prefix)
_ensure_org_user = ensure_org_user
_ensure_league_user = ensure_league_user
_flush_redis_cache = flush_redis_cache
_test_user_to_dict = test_user_to_dict
_get_or_create_demo_user = get_or_create_demo_user
_fetch_discord_avatars_for_users = fetch_discord_avatars_for_users
