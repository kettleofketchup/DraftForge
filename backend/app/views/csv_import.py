"""CSV import views for bulk-adding users to organizations and tournaments."""

import logging

from cacheops import invalidate_obj
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
from league.models import LeagueUser
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


POSITION_FIELDS = ("carry", "mid", "offlane", "soft_support", "hard_support")
# Maps position number (1-5) to field name
POSITION_NUM_TO_FIELD = {
    1: "carry",
    2: "mid",
    3: "offlane",
    4: "soft_support",
    5: "hard_support",
}


def _parse_positions(value):
    """Parse ranked positions string (e.g. '1:3:2').

    Format: colon-separated position numbers (1-5) in preference order.
    Position numbers: 1=carry, 2=mid, 3=offlane, 4=soft_support, 5=hard_support
    First listed = highest preference (5), second = 4, etc.
    Unlisted positions default to 0.

    Example: '1:3:2' → carry=5, offlane=4, mid=3, soft_support=0, hard_support=0

    Returns (dict, error) tuple.
    """
    if not value or str(value).strip() == "":
        return None, None
    parts = str(value).strip().split(":")
    if len(parts) > 5:
        return None, f"Too many positions (max 5, got {len(parts)})"
    try:
        pos_nums = [int(p) for p in parts]
    except (ValueError, TypeError):
        return None, f"Invalid positions: {value}"
    if any(p < 1 or p > 5 for p in pos_nums):
        return None, "Position numbers must be between 1 and 5"
    if len(set(pos_nums)) != len(pos_nums):
        return None, "Duplicate position numbers"

    # Convert ranked list to field values: first listed gets 5, second gets 4, etc.
    result = {f: 0 for f in POSITION_FIELDS}
    for rank, pos_num in enumerate(pos_nums):
        field = POSITION_NUM_TO_FIELD[pos_num]
        result[field] = 5 - rank  # rank 0 → 5, rank 1 → 4, etc.
    return result, None


def _update_positions_if_empty(user, positions_dict):
    """Update user positions only if all current values are 0 (default)."""
    if not positions_dict or not user.positions:
        return
    if all(getattr(user.positions, f) == 0 for f in POSITION_FIELDS):
        for field, value in positions_dict.items():
            setattr(user.positions, field, value)
        user.positions.save()


def _resolve_user_for_csv_row(row):
    """
    Resolve or create a user from a CSV row.

    Returns (user, created, error, conflict_users) tuple.
    - user: CustomUser instance or None
    - created: bool - True if a new stub user was created
    - error: str or None - error message (user will be None)
    - conflict_users: list[CustomUser] or None - users involved in ID conflict
    """
    steam_id_str = row.get("steam_friend_id")
    discord_id_str = row.get("discord_id")
    discord_username_str = row.get("discord_username")

    steam_id, steam_err = _parse_int(steam_id_str, "steam_friend_id")
    if steam_err:
        return None, False, steam_err, None

    # Clean discord_id (strip whitespace, treat empty as None)
    discord_id = str(discord_id_str).strip() if discord_id_str else None
    if discord_id == "" or discord_id == "None":
        discord_id = None

    # Clean discord_username
    discord_username = (
        str(discord_username_str).strip() if discord_username_str else None
    )
    if discord_username == "" or discord_username == "None":
        discord_username = None

    if steam_id is None and discord_id is None and discord_username is None:
        return (
            None,
            False,
            "No identifier provided (need steam_friend_id, discord_id, or discord_username)",
            None,
        )

    user = None
    created = False

    # Lookup by identifiers
    steam_user = (
        CustomUser.objects.filter(steamid=steam_id).first() if steam_id else None
    )
    discord_user = (
        CustomUser.objects.filter(discordId=discord_id).first() if discord_id else None
    )
    # Lookup by discord_username if no discord_id match
    if discord_user is None and discord_username:
        discord_user = CustomUser.objects.filter(
            discordUsername__iexact=discord_username
        ).first()

    # Conflict: both identifiers resolve to different users
    if steam_user and discord_user and steam_user.pk != discord_user.pk:
        steam_name = steam_user.nickname or steam_user.username or f"#{steam_user.pk}"
        discord_name = (
            discord_user.nickname or discord_user.username or f"#{discord_user.pk}"
        )
        return (
            None,
            False,
            f"Steam ID and Discord ID belong to different users: "
            f"{steam_name} (Steam) vs {discord_name} (Discord)",
            [steam_user, discord_user],
        )
    elif steam_user:
        user = steam_user
        # Conflict: user's discord doesn't match provided discord
        if discord_id and user.discordId and user.discordId != discord_id:
            name = user.nickname or user.username or f"#{user.pk}"
            return (
                None,
                False,
                f"{name} is already linked to a different Discord account",
                [steam_user],
            )
    elif discord_user:
        user = discord_user
        # Conflict: user's steam doesn't match provided steam
        if steam_id and user.steamid and user.steamid != steam_id:
            name = user.nickname or user.username or f"#{user.pk}"
            return (
                None,
                False,
                f"{name} is already linked to a different Steam account",
                [discord_user],
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
                elif discord_username is not None:
                    user.discordUsername = discord_username
                    if not user.username:
                        user.username = f"discord_{discord_username}"
                # Set nickname from 'name' column if provided
                name = row.get("name")
                if name:
                    name = str(name).strip()
                    if name:
                        user.nickname = name
                user.save()
                created = True
        except IntegrityError:
            # Race condition: another row created the same user — retry lookup
            if steam_id is not None:
                user = CustomUser.objects.filter(steamid=steam_id).first()
            if user is None and discord_id is not None:
                user = CustomUser.objects.filter(discordId=discord_id).first()
            if user is None and discord_username is not None:
                user = CustomUser.objects.filter(
                    discordUsername__iexact=discord_username
                ).first()
            if user is None:
                return None, False, "Failed to create user (conflict)", None

    return user, created, None, None


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def import_csv_org(request, org_id):
    """
    Bulk-import users to an organization from parsed CSV data.

    Expects JSON: {"rows": [{"steam_friend_id": "...", "discord_id": "...", "mmr": 5000}, ...]}
    """
    org = get_object_or_404(Organization, pk=org_id)

    if not (
        request.user.is_staff
        or request.user.is_superuser
        or has_org_staff_access(request.user, org)
    ):
        return Response(
            {"error": "You do not have permission"},
            status=status.HTTP_403_FORBIDDEN,
        )

    rows = request.data.get("rows", [])
    update_mmr = bool(request.data.get("update_mmr", False))
    log.info(
        "CSV org import: update_mmr=%s, raw=%r, rows=%d",
        update_mmr,
        request.data.get("update_mmr"),
        len(rows) if isinstance(rows, list) else 0,
    )

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
    summary = {"added": 0, "skipped": 0, "created": 0, "errors": 0, "updated": 0}

    for i, row in enumerate(rows):
        if not isinstance(row, dict):
            results.append(
                {"row": i + 1, "status": "error", "reason": "Invalid row format"}
            )
            summary["errors"] += 1
            continue
        user, created, error, conflict_users = _resolve_user_for_csv_row(row)

        if error:
            err_result = {"row": i + 1, "status": "error", "reason": error}
            if conflict_users:
                err_result["conflict_users"] = [
                    TournamentUserSerializer(u).data for u in conflict_users
                ]
            results.append(err_result)
            summary["errors"] += 1
            continue

        # Parse base_mmr
        base_mmr, mmr_err = _parse_int(row.get("mmr"), "mmr")
        if mmr_err:
            results.append({"row": i + 1, "status": "error", "reason": mmr_err})
            summary["errors"] += 1
            continue

        # Parse positions
        positions_dict, pos_err = _parse_positions(row.get("positions"))
        if pos_err:
            results.append({"row": i + 1, "status": "error", "reason": pos_err})
            summary["errors"] += 1
            continue

        # Set nickname from CSV 'name' column if user has no nickname
        csv_name = (row.get("name") or "").strip()
        if csv_name and not user.nickname:
            user.nickname = csv_name
            user.save(update_fields=["nickname"])

        # Update positions if user has all defaults (zeros)
        _update_positions_if_empty(user, positions_dict)

        # Try to create OrgUser (savepoint needed for SQLite IntegrityError recovery)
        try:
            with transaction.atomic():
                OrgUser.objects.create(
                    user=user,
                    organization=org,
                    mmr=base_mmr or 0,
                )
        except IntegrityError:
            log.info(
                "Row %d: existing member, update_mmr=%s, base_mmr=%r",
                i + 1,
                update_mmr,
                base_mmr,
            )
            if update_mmr and base_mmr is not None:
                OrgUser.objects.filter(user=user, organization=org).update(mmr=base_mmr)
                results.append(
                    {
                        "row": i + 1,
                        "status": "updated",
                        "reason": f"MMR updated to {base_mmr}",
                        "user": TournamentUserSerializer(user).data,
                    }
                )
                summary["updated"] += 1
            else:
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


def _update_mmr_for_target(user, org, league, mmr_target, base_mmr):
    """Update MMR at the specified target level (organization or league)."""
    if mmr_target == "league" and league and org:
        org_user = OrgUser.objects.filter(user=user, organization=org).first()
        if org_user:
            LeagueUser.objects.update_or_create(
                user=user,
                league=league,
                defaults={"org_user": org_user, "mmr": base_mmr},
            )
    elif org:
        OrgUser.objects.filter(user=user, organization=org).update(mmr=base_mmr)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def import_csv_tournament(request, tournament_id):
    """
    Bulk-import users to a tournament from parsed CSV data.

    Expects JSON: {"rows": [{"steam_friend_id": "...", "discord_id": "...", "mmr": 5000, "team_name": "..."}, ...]}
    """
    tournament = get_object_or_404(
        Tournament.objects.select_related("league__organization"), pk=tournament_id
    )

    # Check access via league's org
    has_access = False
    if tournament.league and tournament.league.organization:
        has_access = has_org_staff_access(request.user, tournament.league.organization)
    if not has_access and not request.user.is_superuser and not request.user.is_staff:
        return Response(
            {"error": "You do not have permission"},
            status=status.HTTP_403_FORBIDDEN,
        )

    org = tournament.league.organization if tournament.league else None
    league = tournament.league
    rows = request.data.get("rows", [])
    update_mmr = bool(request.data.get("update_mmr", False))
    mmr_target = request.data.get(
        "mmr_target", "organization"
    )  # "organization" | "league"
    log.info(
        "CSV tournament import: update_mmr=%s, mmr_target=%s, raw_update_mmr=%r, rows=%d",
        update_mmr,
        mmr_target,
        request.data.get("update_mmr"),
        len(rows) if isinstance(rows, list) else 0,
    )

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
    if mmr_target == "league" and not league:
        return Response(
            {"error": "Tournament has no league for league-level MMR"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    results = []
    summary = {"added": 0, "skipped": 0, "created": 0, "errors": 0, "updated": 0}

    # Cache for team_name -> Team (get_or_create within this import)
    team_cache = {}

    for i, row in enumerate(rows):
        if not isinstance(row, dict):
            results.append(
                {"row": i + 1, "status": "error", "reason": "Invalid row format"}
            )
            summary["errors"] += 1
            continue
        user, created, error, conflict_users = _resolve_user_for_csv_row(row)

        if error:
            err_result = {"row": i + 1, "status": "error", "reason": error}
            if conflict_users:
                err_result["conflict_users"] = [
                    TournamentUserSerializer(u).data for u in conflict_users
                ]
            results.append(err_result)
            summary["errors"] += 1
            continue

        # Parse base_mmr
        base_mmr, mmr_err = _parse_int(row.get("mmr"), "mmr")
        if mmr_err:
            results.append({"row": i + 1, "status": "error", "reason": mmr_err})
            summary["errors"] += 1
            continue

        # Parse positions
        positions_dict, pos_err = _parse_positions(row.get("positions"))
        if pos_err:
            results.append({"row": i + 1, "status": "error", "reason": pos_err})
            summary["errors"] += 1
            continue

        # Set nickname from CSV 'name' column if user has no nickname
        csv_name = (row.get("name") or "").strip()
        if csv_name and not user.nickname:
            user.nickname = csv_name
            user.save(update_fields=["nickname"])

        # Update positions if user has all defaults (zeros)
        _update_positions_if_empty(user, positions_dict)

        # Check if already in tournament
        if tournament.users.filter(pk=user.pk).exists():
            if update_mmr and base_mmr is not None:
                _update_mmr_for_target(user, org, league, mmr_target, base_mmr)
                results.append(
                    {
                        "row": i + 1,
                        "status": "updated",
                        "reason": f"MMR updated to {base_mmr} ({mmr_target})",
                        "user": TournamentUserSerializer(user).data,
                    }
                )
                summary["updated"] += 1
            else:
                results.append(
                    {
                        "row": i + 1,
                        "status": "skipped",
                        "reason": "Already in tournament",
                        "user": TournamentUserSerializer(user).data,
                    }
                )
                summary["skipped"] += 1
            continue

        # Create OrgUser if tournament has an org (savepoint for SQLite)
        if org:
            try:
                with transaction.atomic():
                    OrgUser.objects.create(
                        user=user, organization=org, mmr=base_mmr or 0
                    )
            except IntegrityError:
                # Already a member of the org -- update MMR if provided
                if base_mmr is not None:
                    OrgUser.objects.filter(user=user, organization=org).update(
                        mmr=base_mmr
                    )

        # For league-level MMR, also create/update LeagueUser
        if league and mmr_target == "league" and base_mmr is not None:
            org_user = OrgUser.objects.filter(user=user, organization=org).first()
            if org_user:
                LeagueUser.objects.update_or_create(
                    user=user,
                    league=league,
                    defaults={"org_user": org_user, "mmr": base_mmr},
                )

        # Add to tournament
        tournament.users.add(user)

        # Handle team assignment
        team_name = (row.get("team_name") or "").strip()
        team_captain = bool(row.get("team_captain"))
        if team_name:
            if team_name not in team_cache:
                team, _ = Team.objects.get_or_create(
                    name=team_name,
                    tournament=tournament,
                )
                team_cache[team_name] = team
            team_cache[team_name].members.add(user)
            if team_captain:
                team_cache[team_name].captain = user
                team_cache[team_name].save(update_fields=["captain"])

        if created:
            summary["created"] += 1

        result = {
            "row": i + 1,
            "status": "added",
            "user": TournamentUserSerializer(user).data,
            "created": created,
        }
        if team_name:
            result["team"] = team_name

        results.append(result)
        summary["added"] += 1

        # Log the action (for the org that owns this tournament)
        if org:
            OrgLog.objects.create(
                organization=org,
                actor=request.user,
                action="add_member",
                target_user=user,
            )

    # Invalidate tournament cache so refreshed data reflects MMR changes
    invalidate_obj(tournament)

    return Response({"summary": summary, "results": results})
