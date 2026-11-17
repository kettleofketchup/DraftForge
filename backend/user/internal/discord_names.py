"""Internal endpoints for the Discord name sync worker (app/tasks/discord_name_sync.py)."""

from typing import Any

from rest_framework import status
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
)
from rest_framework.request import Request
from rest_framework.response import Response

from app.auth import InternalServiceAuth, IsInternalService
from app.models import Organization
from discordbot.services.member_names import MemberNames
from org.activity import active_org_ids, guild_sync_lock, release_guild_sync_lock
from org.discord_names import apply_guild_member_names
from telemetry.logging import get_logger

log = get_logger(__name__)

MAX_MEMBERS = 50_000
_SCOPES = ("active", "all")
_NAME_FIELDS = ("username", "nick", "global_name")


def _bad_request(error: str) -> Response:
    return Response({"error": error}, status=status.HTTP_400_BAD_REQUEST)


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


@api_view(["GET"])
@authentication_classes([InternalServiceAuth])
@permission_classes([IsInternalService])
def list_discord_name_sync_targets(request: Request) -> Response:
    scope = request.query_params.get("scope", "active")
    if scope not in _SCOPES:
        return _bad_request("scope must be 'active' or 'all'")
    raw_org_id = request.query_params.get("org_id")
    org_id: int | None = None
    if raw_org_id is not None:
        try:
            org_id = int(raw_org_id)
        except ValueError:
            return _bad_request("org_id must be an integer")
    lock = request.query_params.get("lock") == "1"

    orgs = (
        Organization.objects.nocache()
        .filter(discord_server_id__isnull=False)
        .exclude(discord_server_id="")
        .order_by("pk")
    )
    if org_id is not None:
        guild_id = (
            Organization.objects.nocache()
            .filter(pk=org_id)
            .values_list("discord_server_id", flat=True)
            .first()
        )
        if not guild_id:
            return Response([])
        orgs = orgs.filter(discord_server_id=guild_id)

    pairs = list(orgs.values_list("pk", "discord_server_id"))
    if scope == "active":
        active = active_org_ids(pk for pk, _ in pairs)
        pairs = [(pk, guild) for pk, guild in pairs if pk in active]

    if lock:
        locked: dict[str, bool] = {}
        for _, guild in pairs:
            if guild not in locked:
                locked[guild] = guild_sync_lock(guild)
        skipped = sum(1 for taken in locked.values() if not taken)
        pairs = [(pk, guild) for pk, guild in pairs if locked[guild]]
        if skipped:
            log.info(
                "name_sync_targets_guilds_locked",
                system="discord",
                subsystem="name_sync",
                skipped=skipped,
            )

    log.debug(
        "name_sync_targets_listed",
        system="discord",
        subsystem="name_sync",
        scope=scope,
        count=len(pairs),
    )
    return Response([{"org_id": pk, "guild_id": guild} for pk, guild in pairs])


def _validated_members(raw: object) -> tuple[list[MemberNames], str | None]:
    if not isinstance(raw, list):
        return [], "members must be a list"
    if len(raw) > MAX_MEMBERS:
        return [], f"members exceeds {MAX_MEMBERS}"
    members: list[MemberNames] = []
    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            return [], f"members[{i}] must be an object"
        discord_id = item.get("discord_id")
        if not isinstance(discord_id, str) or not discord_id:
            return [], f"members[{i}].discord_id must be a non-empty string"
        for field in _NAME_FIELDS:
            value = item.get(field)
            if value is not None and not isinstance(value, str):
                return [], f"members[{i}].{field} must be a string or null"
        members.append(
            MemberNames(
                discord_id=discord_id,
                username=item.get("username"),
                nick=item.get("nick"),
                global_name=item.get("global_name"),
            )
        )
    return members, None


def _validated_body(
    data: Any,
) -> tuple[tuple[list[int], bool, float | None, list[MemberNames]] | None, str | None]:
    org_ids = data.get("org_ids")
    if not isinstance(org_ids, list) or not all(_is_int(v) for v in org_ids):
        return None, "org_ids must be a list of integers"
    complete = data.get("complete")
    if not isinstance(complete, bool):
        return None, "complete must be a boolean"
    fetched_at = data.get("fetched_at")
    if fetched_at is not None and (
        isinstance(fetched_at, bool) or not isinstance(fetched_at, (int, float))
    ):
        return None, "fetched_at must be a number or null"
    members, error = _validated_members(data.get("members"))
    if error is not None:
        return None, error
    return (
        org_ids,
        complete,
        float(fetched_at) if fetched_at is not None else None,
        members,
    ), None


@api_view(["POST"])
@authentication_classes([InternalServiceAuth])
@permission_classes([IsInternalService])
def bulk_update_member_names(request: Request) -> Response:
    data = request.data
    if not isinstance(data, dict):
        return _bad_request("body must be an object")
    guild_id = data.get("guild_id")
    if not isinstance(guild_id, str) or not guild_id:
        return _bad_request("guild_id must be a non-empty string")
    try:
        parsed, error = _validated_body(data)
        if parsed is None:
            log.warning(
                "name_sync_bulk_update_invalid_payload",
                system="discord",
                subsystem="name_sync",
                guild_id=guild_id,
                error=error,
            )
            return _bad_request(error or "invalid body")
        org_ids, complete, fetched_at, members = parsed
        result = apply_guild_member_names(
            guild_id, org_ids, members, complete=complete, fetched_at=fetched_at
        )
    finally:
        release_guild_sync_lock(guild_id)
    return Response(result.as_dict())
