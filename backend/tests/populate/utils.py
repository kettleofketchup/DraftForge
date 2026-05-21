"""
Utility functions for test database population.
"""

import random

from django.db import transaction

from app.models import CustomUser, PositionsModel

from .constants import DTX_ORG_NAME, MOCK_USERNAMES, TOURNAMENT_USERS


def generate_mock_discord_members(count=100):
    """
    Generate mock Discord member data for testing when Discord API is unavailable.
    Returns data in the same format as get_discord_members_data().
    """
    members = []
    used_usernames = set()

    for i in range(count):
        # Pick a unique username
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
                "avatar": None,  # No avatar for mock users
                "discriminator": "0",
                "global_name": username.replace("_", " ").title(),
            },
            "nick": None,
            "joined_at": "2024-01-01T00:00:00.000000+00:00",
        }
        members.append(member)

    return members


def create_user(user_data, organization=None):
    """
    Create a user from Discord data.

    Args:
        user_data: Discord user data dict
        organization: Optional Organization to create OrgUser for
    """
    user, created = CustomUser.objects.get_or_create(discordId=user_data["user"]["id"])
    if not created:
        # Ensure OrgUser exists for existing user
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
        user.steam_account_id = random.randint(1, 1000000)

        user.positions = positions
        user.save()

        # Create OrgUser for organization-scoped MMR
        if organization:
            ensure_org_user(user, organization, mmr=mmr)

    return user


def ensure_org_user(user, organization, mmr=None):
    """Ensure OrgUser exists for user in organization."""
    from org.models import OrgUser

    org_user, created = OrgUser.objects.get_or_create(
        user=user,
        organization=organization,
        defaults={"mmr": mmr if mmr is not None else 0},
    )
    if not created and mmr is not None and org_user.mmr != mmr:
        org_user.mmr = mmr
        org_user.save()
    return org_user


def ensure_league_user(user, org_user, league):
    """Ensure LeagueUser exists for user in league."""
    from league.models import LeagueUser

    league_user, created = LeagueUser.objects.get_or_create(
        user=user, org_user=org_user, league=league, defaults={"mmr": org_user.mmr}
    )
    return league_user


def flush_redis_cache():
    """Flush Redis cache to ensure fresh data after population."""
    import os

    if os.environ.get("DISABLE_CACHE", "").lower() in ("true", "1", "yes"):
        return

    try:
        import redis
        from django.conf import settings

        redis_url = getattr(settings, "CACHEOPS_REDIS", None)
        if redis_url:
            # Parse redis URL or use dict config with short timeout to avoid hanging
            if isinstance(redis_url, str):
                client = redis.from_url(
                    redis_url, socket_timeout=2, socket_connect_timeout=2
                )
            else:
                # Add timeout to dict config
                config = {**redis_url, "socket_timeout": 2, "socket_connect_timeout": 2}
                client = redis.Redis(**config)
            client.flushall()
            print("Redis cache flushed successfully")
        else:
            print("No CACHEOPS_REDIS configured, skipping cache flush")
    except Exception as e:
        # Import redis exceptions only if redis is available
        try:
            import redis as redis_module

            if isinstance(e, redis_module.exceptions.ConnectionError):
                print(f"Redis not available, skipping cache flush: {e}")
                return
            if isinstance(e, redis_module.exceptions.TimeoutError):
                print(f"Redis timeout, skipping cache flush: {e}")
                return
        except ImportError:
            pass
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
    from app.models import Organization

    steam_account_id = user_data.get("steam_id")  # 32-bit Friend ID
    pos_data = user_data.get("positions", {})
    mmr = user_data.get("mmr", 3000)
    explicit_pk = user_data.get("pk")

    # If explicit pk is set, use pk-based lookup first
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
        # Create new user with real position data
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
        # Update existing user with latest data
        if steam_account_id and user.steam_account_id != steam_account_id:
            user.steam_account_id = steam_account_id
        # Update positions if provided
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

    return user


_discord_avatar_cache: dict[str, str] | None = None


def _get_discord_avatar_cache() -> dict[str, str]:
    """Fetch all guild members once and cache discord_id -> avatar_hash mapping."""
    global _discord_avatar_cache
    if _discord_avatar_cache is not None:
        return _discord_avatar_cache

    try:
        from discordbot.services.users import get_discord_members_data

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


def fetch_discord_avatars_for_users(users):
    """Update avatars for users using cached bulk guild member data."""
    avatar_map = _get_discord_avatar_cache()
    if not avatar_map:
        return

    updated = 0
    for user in users:
        if not user.discordId:
            continue
        avatar_hash = avatar_map.get(user.discordId)
        if avatar_hash and user.avatar != avatar_hash:
            # T1.5+: avatar is a property over base_profile.avatar; the setter
            # persists via bp.save(update_fields=["avatar"]) internally, so an
            # explicit CustomUser.save(update_fields=["avatar"]) crashes since
            # `avatar` is no longer a model field.
            user.avatar = avatar_hash
            updated += 1
    if updated:
        print(f"  Updated {updated} avatars")


# Backwards compatibility aliases (with underscore prefix)
_ensure_org_user = ensure_org_user
_ensure_league_user = ensure_league_user
_flush_redis_cache = flush_redis_cache
_test_user_to_dict = test_user_to_dict
_get_or_create_demo_user = get_or_create_demo_user
_fetch_discord_avatars_for_users = fetch_discord_avatars_for_users
