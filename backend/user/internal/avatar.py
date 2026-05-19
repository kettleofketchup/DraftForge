"""Internal endpoints for batched Discord-avatar refresh.

Worker flow (see `app/tasks/avatar_refresh.py::refresh_avatars_batched`):

  1. GET  /api/internal/users/discord-linked/      list candidate users
  2. GET  /api/internal/orgs/discord-guild-ids/    list guilds to fetch
  3. (worker calls Discord guild-members API directly per guild)
  4. POST /api/internal/users/avatars/bulk-update/ send diffed updates

These endpoints live in the `user` app so they can grow without bloating
`app/views/internal.py`. All require InternalServiceAuth.
"""

from cacheops import invalidate_model
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
)
from rest_framework.response import Response

from app.auth import InternalServiceAuth, IsInternalService
from telemetry.logging import get_logger

log = get_logger(__name__)

_auth = [InternalServiceAuth]
_perm = [IsInternalService]


@api_view(["GET"])
@authentication_classes(_auth)
@permission_classes(_perm)
def list_discord_linked_users(request):
    """Return every Discord-linked CustomUser as a flat list.

    Unlike list_users_for_avatar_check (which is paged for per-user
    refresh), this endpoint exists for the batched refresh task that
    builds a single discord_id→avatar_hash map in memory. Returns the
    four fields the task needs (pk, discord_id, avatar, username).
    """
    User = get_user_model()
    rows = list(
        User.objects.filter(discordId__isnull=False)
        .exclude(discordId="")
        .values("pk", "discordId", "avatar", "username")
    )
    log.debug(
        "avatars_discord_linked_listed",
        system="avatars",
        subsystem="endpoint",
        count=len(rows),
    )
    return Response(
        [
            {
                "pk": r["pk"],
                "discord_id": r["discordId"],
                "avatar": r["avatar"],
                "username": r["username"],
            }
            for r in rows
        ]
    )


@api_view(["GET"])
@authentication_classes(_auth)
@permission_classes(_perm)
def list_discord_guild_ids(request):
    """Return distinct Discord guild IDs across all Organizations.

    Used by batched avatar refresh to know which guilds to call
    `get_discord_members_data` against.
    """
    from app.models import Organization

    # Organization has Meta.ordering — leaving it in the queryset would
    # add the ordering columns to the SELECT and defeat .distinct().
    guild_ids = list(
        Organization.objects.filter(discord_server_id__isnull=False)
        .exclude(discord_server_id="")
        .order_by()
        .values_list("discord_server_id", flat=True)
        .distinct()
    )
    log.debug(
        "avatars_discord_guilds_listed",
        system="avatars",
        subsystem="endpoint",
        count=len(guild_ids),
    )
    return Response({"guild_ids": guild_ids})


def _validated_avatar_updates(raw):
    """Return (cleaned_list, error_response) for a bulk-avatar-update body.

    Cleans `raw` into a flat list of `{pk: int, avatar: str|None}`.
    Each item must be a dict with an integer `pk`. Any failure returns
    a 400 Response and an empty list — never a partially-built result.
    """
    cleaned = []
    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            return [], Response(
                {"error": f"updates[{i}] must be an object"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        # bool is a subclass of int in Python — reject it explicitly so
        # `{"pk": True}` doesn't sneak through as pk=1.
        pk = item.get("pk")
        if not isinstance(pk, int) or isinstance(pk, bool):
            return [], Response(
                {"error": f"updates[{i}].pk must be an integer"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        cleaned.append({"pk": pk, "avatar": item.get("avatar")})
    return cleaned, None


@api_view(["POST"])
@authentication_classes(_auth)
@permission_classes(_perm)
def bulk_update_user_avatars(request):
    """Bulk-update avatar hashes by user pk.

    Body: {"updates": [{"pk": <int>, "avatar": <str|null>}, ...]}

    Performs a single bulk_update with batch_size=500 and per-row
    `invalidate_obj` calls (bulk_update bypasses signals so cacheops
    needs an explicit nudge). Per-row instead of `invalidate_model` so
    we only evict rows that actually changed — CustomUser is a hot
    model, and a model-wide wipe on every daily avatar refresh would
    cold-start every authenticated request's user cache. The per-row
    cost is one tiny Redis DEL per user; for the typical 5–50 changed
    avatars per daily run that's cheaper than scanning + deleting all
    User-tagged cache keys.
    """
    User = get_user_model()
    updates = request.data.get("updates")
    if not isinstance(updates, list):
        return Response(
            {"error": "updates must be a list of {pk, avatar} objects"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if not updates:
        return Response({"updated": 0})

    # Validate every item *before* building any User instances or hitting
    # the DB. Avoids "we got through 9 items then bailed on item 10."
    cleaned, err = _validated_avatar_updates(updates)
    if err is not None:
        log.warning(
            "avatars_bulk_update_invalid_payload",
            system="avatars",
            subsystem="endpoint",
            count=len(updates),
        )
        return err

    to_update = [User(pk=u["pk"], avatar=u["avatar"]) for u in cleaned]
    User.objects.bulk_update(to_update, ["avatar"], batch_size=500)
    # Per-row invalidation: only evict the users that changed instead of
    # wiping the whole CustomUser cache. See docstring for rationale.
    from cacheops import invalidate_obj

    for u in to_update:
        invalidate_obj(u)
    log.info(
        "avatars_bulk_updated",
        system="avatars",
        subsystem="endpoint",
        updated=len(to_update),
    )
    return Response({"updated": len(to_update)})
