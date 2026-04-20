"""Internal API endpoints for Steam/match sync operations.

All endpoints require InternalServiceAuth (X-Internal-Token header).
"""

from django.utils import timezone
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
)
from rest_framework.response import Response

from app.auth import InternalServiceAuth, IsInternalService
from app.cache_utils import invalidate_after_commit

_auth = [InternalServiceAuth]
_perm = [IsInternalService]

SYNC_STATE_ALLOWED_FIELDS = {"is_syncing", "last_match_id", "failed_match_ids"}


@api_view(["GET", "PATCH"])
@authentication_classes(_auth)
@permission_classes(_perm)
def steam_sync_state(request, league_id):
    """GET: return (or create) sync state for a league. PATCH: update allowed fields."""
    from steam.models import LeagueSyncState

    if request.method == "GET":
        state, _created = LeagueSyncState.objects.get_or_create(league_id=league_id)
        return Response({
            "league_id": state.league_id,
            "is_syncing": state.is_syncing,
            "last_match_id": state.last_match_id,
            "last_sync_at": state.last_sync_at.isoformat() if state.last_sync_at else None,
            "failed_match_ids": state.failed_match_ids,
        })

    # PATCH
    state = LeagueSyncState.objects.get(league_id=league_id)
    for field in SYNC_STATE_ALLOWED_FIELDS:
        if field in request.data:
            setattr(state, field, request.data[field])
    state.last_sync_at = timezone.now()
    state.save()
    invalidate_after_commit(state)
    return Response({
        "league_id": state.league_id,
        "is_syncing": state.is_syncing,
        "last_match_id": state.last_match_id,
        "last_sync_at": state.last_sync_at.isoformat() if state.last_sync_at else None,
        "failed_match_ids": state.failed_match_ids,
    })
