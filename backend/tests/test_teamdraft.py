"""Test endpoints for team-draft timer E2E testing (TEST ONLY)."""

import time
from datetime import timedelta

from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
)
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from app.models import Draft
from app.tasks.draft_tick import (
    HEARTBEAT_STALE_SECONDS,
    captain_channel_key,
    conn_count_key,
    get_redis_client,
    heartbeat_key,
    lock_key,
    stop_tick_broadcaster,
)
from app.tasks.teamdraft_tick import PREFIX, captain_conn_key
from common.utils import isTestEnvironment
from telemetry.logging import get_logger

log = get_logger(__name__)


def clear_teamdraft_redis(draft_id: int, captain_ids: list[int]) -> None:
    stop_tick_broadcaster(PREFIX, draft_id)
    r = get_redis_client()
    keys = [conn_count_key(PREFIX, draft_id), lock_key(PREFIX, draft_id)]
    for uid in captain_ids:
        keys.extend(
            [
                heartbeat_key(PREFIX, draft_id, uid),
                captain_channel_key(PREFIX, draft_id, uid),
                captain_conn_key(draft_id, uid),
            ]
        )
    r.delete(*keys)


@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
def expire_draft_clock(request, draft_pk: int) -> Response:
    """Backdate the active round's started_at by `ms` (default 120000)."""
    if not isTestEnvironment(request):
        return Response({"detail": "Not Found"}, status=status.HTTP_404_NOT_FOUND)

    draft = get_object_or_404(Draft, pk=draft_pk)
    ms = int(request.data.get("ms", 120000))
    active = draft.active_round
    if active is None or active.started_at is None:
        return Response(
            {"error": "No active round with a started clock"},
            status=status.HTTP_400_BAD_REQUEST,
        )
    active.started_at = active.started_at - timedelta(milliseconds=ms)
    active.save(update_fields=["started_at"])
    log.info(
        "test_draft_clock_expired",
        system="teamdraft",
        subsystem="test",
        draft_id=draft.pk,
        pick_number=active.pick_number,
        ms=ms,
    )
    return Response({"started_at": active.started_at.isoformat()})


@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
def stale_draft_heartbeat(request, draft_pk: int) -> Response:
    """Make a captain's heartbeat stale: delete the key or backdate it."""
    if not isTestEnvironment(request):
        return Response({"detail": "Not Found"}, status=status.HTTP_404_NOT_FOUND)

    get_object_or_404(Draft, pk=draft_pk)
    user_pk = int(request.data["user_pk"])
    mode = request.data.get("mode", "delete")
    if mode not in ("delete", "backdate"):
        return Response(
            {"error": "mode must be 'delete' or 'backdate'"},
            status=status.HTTP_400_BAD_REQUEST,
        )
    r = get_redis_client()
    key = heartbeat_key(PREFIX, draft_pk, user_pk)
    if mode == "delete":
        r.delete(key)
    else:
        r.set(key, str(time.time() - HEARTBEAT_STALE_SECONDS - 1))
    return Response({"stale": True})
