"""CSV import views for bulk-adding users to organizations and tournaments."""

import logging

from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from app.models import (
    CustomUser,
    Organization,
    OrgLog,
    PositionsModel,
    Team,
    Tournament,
)
from app.permissions_org import has_org_staff_access
from app.serializers import TournamentUserSerializer
from org.models import OrgUser

log = logging.getLogger(__name__)

MAX_ROWS = 500
STEAM_ID_64_MIN = 76561197960265728  # Smallest valid Steam64 ID


def _parse_int(value, field_name):
    """Parse a string to int, returning (value, error)."""
    if value is None or value == "":
        return None, None
    try:
        return int(value), None
    except (ValueError, TypeError):
        return None, f"Invalid {field_name}: {value}"


def _resolve_user_for_csv_row(row):
    """
    Resolve or create a user from a CSV row.

    Returns (user, created, warning, error) tuple.
    - user: CustomUser instance or None
    - created: bool - True if a new stub user was created
    - warning: str or None - conflict warning message
    - error: str or None - error message (user will be None)
    """
    steam_id_str = row.get("steam_friend_id")
    discord_id_str = row.get("discord_id")

    steam_id, steam_err = _parse_int(steam_id_str, "steam_friend_id")
    if steam_err:
        return None, False, None, steam_err

    # Clean discord_id (strip whitespace, treat empty as None)
    discord_id = str(discord_id_str).strip() if discord_id_str else None
    if discord_id == "" or discord_id == "None":
        discord_id = None

    if steam_id is None and discord_id is None:
        return (
            None,
            False,
            None,
            "No identifier provided (need steam_friend_id or discord_id)",
        )

    warning = None
    user = None
    created = False

    # Lookup by both identifiers
    steam_user = (
        CustomUser.objects.filter(steamid=steam_id).first() if steam_id else None
    )
    discord_user = (
        CustomUser.objects.filter(discordId=discord_id).first() if discord_id else None
    )

    # Conflict detection: both identifiers resolve to different users
    if steam_user and discord_user and steam_user.pk != discord_user.pk:
        warning = (
            f"Steam ID {steam_id} belongs to user #{steam_user.pk} but "
            f"Discord ID {discord_id} belongs to user #{discord_user.pk} — "
            f"using Steam match"
        )
        user = steam_user
    elif steam_user:
        user = steam_user
        # Warn if user's discord doesn't match provided discord
        if discord_id and user.discordId and user.discordId != discord_id:
            warning = (
                f"Steam ID {steam_id} is already linked to Discord ID "
                f"{user.discordId} — provided Discord ID {discord_id} was ignored"
            )
    elif discord_user:
        user = discord_user
        # Warn if user's steam doesn't match provided steam
        if steam_id and user.steamid and user.steamid != steam_id:
            warning = (
                f"Discord ID {discord_id} is already linked to Steam ID "
                f"{user.steamid} — provided Steam ID {steam_id} was ignored"
            )

    # Create stub user if no match (with retry for race conditions)
    if user is None:
        try:
            with transaction.atomic():
                positions = PositionsModel.objects.create()
                user = CustomUser(positions=positions)
                if steam_id is not None:
                    user.steamid = steam_id
                    user.username = f"steam_{steam_id}"
                if discord_id is not None:
                    user.discordId = discord_id
                    if not user.username:
                        user.username = f"discord_{discord_id}"
                user.save()
                created = True
        except IntegrityError:
            # Race condition: another row created the same user — retry lookup
            if steam_id is not None:
                user = CustomUser.objects.filter(steamid=steam_id).first()
            if user is None and discord_id is not None:
                user = CustomUser.objects.filter(discordId=discord_id).first()
            if user is None:
                return None, False, None, "Failed to create user (conflict)"

    return user, created, warning, None


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def import_csv_org(request, org_id):
    """
    Bulk-import users to an organization from parsed CSV data.

    Expects JSON: {"rows": [{"steam_friend_id": "...", "discord_id": "...", "base_mmr": 5000}, ...]}
    """
    org = get_object_or_404(Organization, pk=org_id)

    if not has_org_staff_access(request.user, org):
        return Response(
            {"error": "You do not have permission"},
            status=status.HTTP_403_FORBIDDEN,
        )

    rows = request.data.get("rows", [])
    if not isinstance(rows, list):
        return Response(
            {"error": "rows must be a list"},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if len(rows) > MAX_ROWS:
        return Response(
            {"error": f"Too many rows (max {MAX_ROWS})"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    results = []
    summary = {"added": 0, "skipped": 0, "created": 0, "errors": 0}

    for i, row in enumerate(rows):
        if not isinstance(row, dict):
            results.append(
                {"row": i + 1, "status": "error", "reason": "Invalid row format"}
            )
            summary["errors"] += 1
            continue
        user, created, warning, error = _resolve_user_for_csv_row(row)

        if error:
            results.append({"row": i + 1, "status": "error", "reason": error})
            summary["errors"] += 1
            continue

        # Parse base_mmr
        base_mmr, mmr_err = _parse_int(row.get("base_mmr"), "base_mmr")
        if mmr_err:
            results.append({"row": i + 1, "status": "error", "reason": mmr_err})
            summary["errors"] += 1
            continue

        # Try to create OrgUser (savepoint needed for SQLite IntegrityError recovery)
        try:
            with transaction.atomic():
                org_user = OrgUser.objects.create(
                    user=user,
                    organization=org,
                    mmr=base_mmr or 0,
                )
        except IntegrityError:
            results.append(
                {
                    "row": i + 1,
                    "status": "skipped",
                    "reason": "Already a member",
                    "user": TournamentUserSerializer(user).data,
                }
            )
            summary["skipped"] += 1
            continue

        if created:
            summary["created"] += 1

        result = {
            "row": i + 1,
            "status": "added",
            "user": TournamentUserSerializer(user).data,
            "created": created,
        }
        if warning:
            result["warning"] = warning

        results.append(result)
        summary["added"] += 1

        # Log the action
        OrgLog.objects.create(
            organization=org,
            actor=request.user,
            action="add_member",
            target_user=user,
        )

    return Response({"summary": summary, "results": results})
