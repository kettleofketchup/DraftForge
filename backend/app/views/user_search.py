"""User search API view."""

from django.db.models import Exists, OuterRef, Q
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from app.models import CustomUser
from app.serializers import TournamentUserSerializer
from league.models import League, LeagueUser
from org.models import Organization, OrgUser
from org.permissions import has_org_staff_access
from org.user_search import user_name_q
from user.querysets import with_user_profiles


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def search_users(request: Request) -> Response:
    """
    Search users by username, nickname, Discord names, or Steam ID.

    Query params:
    - q: Search query (min 3 characters)
    - org_id: Optional org ID; also matches that org's server nicknames,
      ranks its members first and annotates membership (org staff only)
    - league_id: Optional league ID for membership annotation

    Returns max 20 results.
    """
    query = request.query_params.get("q", "").strip()

    if len(query) < 3:
        return Response(
            {"error": "Search query must be at least 3 characters"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    org: Organization | None = None
    org_id = request.query_params.get("org_id")
    if org_id:
        try:
            org = Organization.objects.get(pk=int(org_id))
        except (Organization.DoesNotExist, ValueError):
            org = None

    if org and not has_org_staff_access(request.user, org):
        return Response(
            {"error": "You do not have access to this organization"},
            status=status.HTTP_403_FORBIDDEN,
        )

    q_filter = user_name_q(query, org_id=org.pk if org else None)
    if query.isdigit():
        q_filter |= Q(steamid=int(query)) | Q(steam_account_id=int(query))

    users_qs = with_user_profiles(CustomUser.objects.all(), dota=True).filter(q_filter)
    if org:
        users_qs = users_qs.annotate(
            is_org_member=Exists(
                OrgUser.objects.filter(user=OuterRef("pk"), organization=org)
            )
        ).order_by("-is_org_member", "username")
    data = TournamentUserSerializer(users_qs[:20], many=True).data

    if org:
        league = None
        league_id = request.query_params.get("league_id")
        if league_id:
            try:
                league = League.objects.get(pk=int(league_id))
            except (League.DoesNotExist, ValueError):
                pass

        user_ids = [u["pk"] for u in data]

        league_member_ids = set()
        if league:
            league_member_ids = set(
                LeagueUser.objects.filter(
                    league=league, user_id__in=user_ids
                ).values_list("user_id", flat=True)
            )

        org_nicknames: dict[int, str | None] = dict(
            OrgUser.objects.filter(organization=org, user_id__in=user_ids).values_list(
                "user_id", "guild_nickname"
            )
        )
        org_member_ids = set(org_nicknames)

        other_org_map = {}
        remaining_ids = set(user_ids) - org_member_ids - league_member_ids
        if remaining_ids:
            other_memberships = (
                OrgUser.objects.filter(user_id__in=remaining_ids)
                .select_related("organization")
                .values_list("user_id", "organization__name")
            )
            for uid, org_name in other_memberships:
                if uid not in other_org_map:
                    other_org_map[uid] = org_name

        for user_data in data:
            uid = user_data["pk"]
            user_data["guildNickname"] = org_nicknames.get(uid)
            if uid in league_member_ids:
                user_data["membership"] = "league"
                user_data["membership_label"] = league.name if league else ""
            elif uid in org_member_ids:
                user_data["membership"] = "org"
                user_data["membership_label"] = org.name
            elif uid in other_org_map:
                user_data["membership"] = "other_org"
                user_data["membership_label"] = other_org_map[uid]
            else:
                user_data["membership"] = None
                user_data["membership_label"] = None

    return Response(data)
