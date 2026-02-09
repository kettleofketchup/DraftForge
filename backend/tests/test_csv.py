"""
Test endpoints for CSV import E2E testing (TEST ONLY).

Provides a reset endpoint to restore CSV import test data to its initial
state between Playwright test runs.
"""

import logging

from django.views.decorators.csrf import csrf_exempt
from rest_framework import status
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
)
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from app.models import (
    CustomUser,
    Organization,
    OrgLog,
    PositionsModel,
    Team,
    Tournament,
)
from common.utils import isTestEnvironment
from league.models import LeagueUser
from org.models import OrgUser
from tests.data.organizations import CSV_ORG_NAME
from tests.data.tournaments import CSV_IMPORT_TOURNAMENT
from tests.data.users import ADMIN_USER, CSV_IMPORT_USERS

log = logging.getLogger(__name__)

# PKs of known CSV test users (should NOT be deleted during reset)
CSV_USER_PKS = {u.pk for u in CSV_IMPORT_USERS}


@csrf_exempt
@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
def reset_csv_import(request):
    """
    Reset CSV import test data to its initial populated state.

    This endpoint:
    1. Removes all OrgUsers from CSV Import Org (except admin)
    2. Clears CSV Import Tournament users and teams
    3. Deletes stub users created during import
    4. Deletes OrgLog entries for CSV org
    5. Re-creates the 5 CSV test users
    """
    if not isTestEnvironment(request):
        return Response({"detail": "Not Found"}, status=status.HTTP_404_NOT_FOUND)

    csv_org = Organization.objects.filter(name=CSV_ORG_NAME).first()
    if not csv_org:
        return Response(
            {"error": f"Organization '{CSV_ORG_NAME}' not found"},
            status=status.HTTP_404_NOT_FOUND,
        )

    csv_tournament = Tournament.objects.filter(name=CSV_IMPORT_TOURNAMENT.name).first()

    # 1. Delete OrgUsers from CSV org (except admin)
    deleted_org_users = OrgUser.objects.filter(organization=csv_org).exclude(
        user__pk=ADMIN_USER.pk
    )
    # Collect user PKs before deleting OrgUsers (for LeagueUser cleanup)
    org_user_pks = set(deleted_org_users.values_list("user__pk", flat=True))
    org_user_count = deleted_org_users.count()

    # Delete LeagueUsers that were created for these org users
    if csv_org.default_league:
        LeagueUser.objects.filter(
            league=csv_org.default_league, user__pk__in=org_user_pks
        ).delete()

    deleted_org_users.delete()

    # 2. Clear tournament users and teams
    tournament_user_count = 0
    team_count = 0
    if csv_tournament:
        tournament_user_count = csv_tournament.users.count()
        csv_tournament.users.clear()
        team_count = Team.objects.filter(tournament=csv_tournament).count()
        Team.objects.filter(tournament=csv_tournament).delete()

    # 3. Delete stub users created during import (not in known CSV user PKs)
    # Stubs have usernames like steam_76561198899999901
    stub_users = CustomUser.objects.filter(username__startswith="steam_").exclude(
        pk__in=CSV_USER_PKS
    )
    stub_count = stub_users.count()
    stub_users.delete()

    # 4. Delete OrgLog entries for CSV org
    OrgLog.objects.filter(organization=csv_org).delete()

    # 5. Re-create CSV test users (in case they were modified)
    for user_data in CSV_IMPORT_USERS:
        existing = CustomUser.objects.filter(pk=user_data.pk).first()
        if existing:
            # Reset to original state
            existing.username = user_data.username
            existing.nickname = user_data.nickname
            existing.discordId = user_data.discord_id
            existing.steamid = user_data.get_steam_id_64()
            existing.save()
        else:
            positions = PositionsModel.objects.create()
            user = CustomUser(
                pk=user_data.pk,
                username=user_data.username,
                nickname=user_data.nickname,
                discordId=user_data.discord_id,
                steamid=user_data.get_steam_id_64(),
                positions=positions,
            )
            user.set_unusable_password()
            user.save()

    return Response(
        {
            "success": True,
            "reset": {
                "org_users_removed": org_user_count,
                "tournament_users_cleared": tournament_user_count,
                "teams_deleted": team_count,
                "stub_users_deleted": stub_count,
                "csv_users_ensured": len(CSV_IMPORT_USERS),
            },
        }
    )
