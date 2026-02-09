# views_test_auth.py
#
# Reference: docs/testing/auth/fixtures.md
# If you update these fixtures, also update the documentation!
#
import logging
import random

from django.db import transaction
from django.views.decorators.csrf import csrf_exempt
from rest_framework import status
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
)
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from social_django.models import UserSocialAuth

from app.models import CustomUser
from common.utils import isTestEnvironment

# Import test user configuration
from tests.data.users import (
    ADMIN_USER,
    CLAIMABLE_USER,
    LEAGUE_ADMIN_USER,
    LEAGUE_STAFF_USER,
    ORG_ADMIN_USER,
    ORG_STAFF_USER,
    REGULAR_USER,
    STAFF_USER,
    USER_CLAIMER,
)

log = logging.getLogger(__name__)


def get_social_token(user, provider="discord"):
    try:
        social = user.social_auth.get(provider=provider)
    except UserSocialAuth.DoesNotExist:
        log.warning("Social Auth Doesn't exist")
        return None
    # Access token
    access_token = social.extra_data.get("access_token")

    # If provider supports refresh tokens:
    refresh_token = social.extra_data.get("refresh_token")
    expires_at = social.extra_data.get("expires")
    csrftoken = social.extra_data.get("csrftoken")
    sessionid = social.extra_data.get("sessionid")

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "expires_at": expires_at,
        "csrftoken": csrftoken,
        "sessionid": sessionid,
    }


from django.db import transaction
from social_django.models import UserSocialAuth


def create_social_auth(user):
    if not user.discordId:
        log.debug(
            f"User {user.username} has no discordId, skipping social auth creation"
        )
        return

    if user.social_auth.filter(provider="discord").exists():
        if user.social_auth.get(provider="discord").extra_data.get("sessionid"):
            log.debug(
                f"Social auth has extra data: {user.social_auth.get(provider='discord').extra_data}"
            )
            return

    # Fake Discord user ID
    log.debug(f"Getting or creating social auth for user {user.username}")
    social, created = UserSocialAuth.objects.update_or_create(
        user=user,
        provider="discord",
        defaults={
            "uid": user.discordId,
            "extra_data": {
                "access_token": "cypress",
                "refresh_token": "cypress",
                "expires": 9999999999,  # far future
                "sessionid": "cypress",
                "csrftoken": "cypress",
            },
        },
    )
    with transaction.atomic():
        log.debug("saving social auth")
        if created:
            social.save()
        user.save()


def createTestSuperUser() -> tuple[CustomUser, bool]:
    """
    Get or create admin test user.
    Uses PK from tests/data/users.py to match populate_test_auth_users().
    """
    assert isTestEnvironment() == True

    # Try to find by PK first (matches populated user)
    user = CustomUser.objects.filter(pk=ADMIN_USER.pk).first()
    if user:
        create_social_auth(user)
        return user, False

    # Create with specific PK if not found
    user = CustomUser(
        pk=ADMIN_USER.pk,
        username=ADMIN_USER.username,
        discordId=ADMIN_USER.discord_id,
        discordUsername=ADMIN_USER.username,
        steamid=ADMIN_USER.get_steam_id_64(),
        is_staff=ADMIN_USER.is_staff,
        is_superuser=ADMIN_USER.is_superuser,
        mmr=random.randint(2000, 6000),
    )
    user.set_password("cypress")
    user.save()

    create_social_auth(user)
    return user, True


def createTestStaffUser() -> tuple[CustomUser, bool]:
    """
    Get or create staff test user.
    Uses PK from tests/data/users.py to match populate_test_auth_users().
    """
    assert isTestEnvironment() == True

    # Try to find by PK first (matches populated user)
    user = CustomUser.objects.filter(pk=STAFF_USER.pk).first()
    if user:
        create_social_auth(user)
        return user, False

    # Create with specific PK if not found
    user = CustomUser(
        pk=STAFF_USER.pk,
        username=STAFF_USER.username,
        discordId=STAFF_USER.discord_id,
        discordUsername=STAFF_USER.username,
        steamid=STAFF_USER.get_steam_id_64(),
        is_staff=STAFF_USER.is_staff,
        is_superuser=STAFF_USER.is_superuser,
        mmr=random.randint(2000, 6000),
    )
    user.set_password("cypress")
    user.save()

    create_social_auth(user)
    return user, True


from django.contrib.auth import login


def createTestUser() -> tuple[CustomUser, bool]:
    """
    Get or create regular test user.
    Uses PK from tests/data/users.py to match populate_test_auth_users().
    """
    assert isTestEnvironment() == True

    # Try to find by PK first (matches populated user)
    user = CustomUser.objects.filter(pk=REGULAR_USER.pk).first()
    if user:
        create_social_auth(user)
        return user, False

    # Create with specific PK if not found
    user = CustomUser(
        pk=REGULAR_USER.pk,
        username=REGULAR_USER.username,
        discordId=REGULAR_USER.discord_id,
        discordUsername=REGULAR_USER.username,
        steamid=REGULAR_USER.get_steam_id_64(),
        is_staff=REGULAR_USER.is_staff,
        is_superuser=REGULAR_USER.is_superuser,
        mmr=random.randint(2000, 6000),
    )
    user.set_password("cypress")
    user.save()

    create_social_auth(user)
    return user, True


# Claimable user: HAS Steam ID, NO Discord ID, NO username (manually added by org)
# Reference: docs/testing/auth/fixtures.md
def createClaimableTestUser() -> tuple[CustomUser, bool]:
    """
    Get or create claimable test user.
    Uses PK from tests/data/users.py to match populate_test_auth_users().

    - NO username (null) - uses steamid as unique identifier
    - NO Discord ID (cannot log in)
    - HAS Steam ID (the unique identifier for this profile)
    - HAS nickname (for display)

    This simulates a user manually added by an org admin with just their Steam ID.
    The claim feature allows a logged-in user to merge this profile into their own.
    """
    assert isTestEnvironment() == True

    # Try to find by PK first (matches populated user)
    user = CustomUser.objects.filter(pk=CLAIMABLE_USER.pk).first()
    if user:
        return user, False

    # Create with specific PK if not found
    user = CustomUser(
        pk=CLAIMABLE_USER.pk,
        username=CLAIMABLE_USER.username,  # None
        discordId=CLAIMABLE_USER.discord_id,  # None
        discordUsername=None,
        steamid=CLAIMABLE_USER.get_steam_id_64(),
        nickname=CLAIMABLE_USER.nickname or "Claimable Profile",
        mmr=CLAIMABLE_USER.mmr or 4500,
    )
    user.set_unusable_password()
    user.save()

    # Do NOT create social auth - this user cannot log in
    return user, True


# User Claimer: Has Discord ID, NO Steam ID initially (will claim a profile with steamid)
# Reference: docs/testing/auth/fixtures.md
def createUserClaimerTestUser() -> tuple[CustomUser, bool]:
    """
    Get or create user claimer test user.
    Uses PK from tests/data/users.py to match populate_test_auth_users().

    - HAS Discord ID (can log in)
    - NO Steam ID (will claim a profile that has one)
    - Used to test the claim/merge flow
    """
    assert isTestEnvironment() == True

    # Try to find by PK first (matches populated user)
    user = CustomUser.objects.filter(pk=USER_CLAIMER.pk).first()
    if user:
        create_social_auth(user)
        return user, False

    # Create with specific PK if not found
    user = CustomUser(
        pk=USER_CLAIMER.pk,
        username=USER_CLAIMER.username,
        discordId=USER_CLAIMER.discord_id,
        discordUsername=USER_CLAIMER.username,
        nickname=USER_CLAIMER.nickname or "User Claimer",
        steamid=USER_CLAIMER.get_steam_id_64(),  # None
        mmr=random.randint(2000, 6000),
    )
    user.set_password("cypress")
    user.save()

    create_social_auth(user)
    return user, True


# OrgAdmin: Organization administrator
def createOrgAdminTestUser() -> tuple[CustomUser, bool]:
    """
    Get or create org admin test user.
    Uses PK from tests/data/users.py to match populate_test_auth_users().
    """
    assert isTestEnvironment() == True

    # Try to find by PK first (matches populated user)
    user = CustomUser.objects.filter(pk=ORG_ADMIN_USER.pk).first()
    if user:
        create_social_auth(user)
        return user, False

    # Create with specific PK if not found
    user = CustomUser(
        pk=ORG_ADMIN_USER.pk,
        username=ORG_ADMIN_USER.username,
        discordId=ORG_ADMIN_USER.discord_id,
        discordUsername=ORG_ADMIN_USER.username,
        nickname=ORG_ADMIN_USER.nickname or "Org Admin Tester",
        steamid=ORG_ADMIN_USER.get_steam_id_64(),
        mmr=random.randint(2000, 6000),
    )
    user.set_password("cypress")
    user.save()

    create_social_auth(user)
    return user, True


# OrgStaff: Organization staff member
def createOrgStaffTestUser() -> tuple[CustomUser, bool]:
    """
    Get or create org staff test user.
    Uses PK from tests/data/users.py to match populate_test_auth_users().
    """
    assert isTestEnvironment() == True

    # Try to find by PK first (matches populated user)
    user = CustomUser.objects.filter(pk=ORG_STAFF_USER.pk).first()
    if user:
        create_social_auth(user)
        return user, False

    # Create with specific PK if not found
    user = CustomUser(
        pk=ORG_STAFF_USER.pk,
        username=ORG_STAFF_USER.username,
        discordId=ORG_STAFF_USER.discord_id,
        discordUsername=ORG_STAFF_USER.username,
        nickname=ORG_STAFF_USER.nickname or "Org Staff Tester",
        steamid=ORG_STAFF_USER.get_steam_id_64(),
        mmr=random.randint(2000, 6000),
    )
    user.set_password("cypress")
    user.save()

    create_social_auth(user)
    return user, True


# LeagueAdmin: League administrator
def createLeagueAdminTestUser() -> tuple[CustomUser, bool]:
    """
    Get or create league admin test user.
    Uses PK from tests/data/users.py to match populate_test_auth_users().
    """
    assert isTestEnvironment() == True

    # Try to find by PK first (matches populated user)
    user = CustomUser.objects.filter(pk=LEAGUE_ADMIN_USER.pk).first()
    if user:
        create_social_auth(user)
        return user, False

    # Create with specific PK if not found
    user = CustomUser(
        pk=LEAGUE_ADMIN_USER.pk,
        username=LEAGUE_ADMIN_USER.username,
        discordId=LEAGUE_ADMIN_USER.discord_id,
        discordUsername=LEAGUE_ADMIN_USER.username,
        nickname=LEAGUE_ADMIN_USER.nickname or "League Admin Tester",
        steamid=LEAGUE_ADMIN_USER.get_steam_id_64(),
        mmr=random.randint(2000, 6000),
    )
    user.set_password("cypress")
    user.save()

    create_social_auth(user)
    return user, True


# LeagueStaff: League staff member
def createLeagueStaffTestUser() -> tuple[CustomUser, bool]:
    """
    Get or create league staff test user.
    Uses PK from tests/data/users.py to match populate_test_auth_users().
    """
    assert isTestEnvironment() == True

    # Try to find by PK first (matches populated user)
    user = CustomUser.objects.filter(pk=LEAGUE_STAFF_USER.pk).first()
    if user:
        create_social_auth(user)
        return user, False

    # Create with specific PK if not found
    user = CustomUser(
        pk=LEAGUE_STAFF_USER.pk,
        username=LEAGUE_STAFF_USER.username,
        discordId=LEAGUE_STAFF_USER.discord_id,
        discordUsername=LEAGUE_STAFF_USER.username,
        nickname=LEAGUE_STAFF_USER.nickname or "League Staff Tester",
        steamid=LEAGUE_STAFF_USER.get_steam_id_64(),
        mmr=random.randint(2000, 6000),
    )
    user.set_password("cypress")
    user.save()

    create_social_auth(user)
    return user, True


def return_tokens(user):
    tokens = get_social_token(user)
    log.debug(tokens)
    return Response({"social_tokens": tokens})


from django.test import Client


@csrf_exempt
@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
def login_admin(request):
    if not isTestEnvironment(request):
        return Response({"detail": "Not Found"}, status=status.HTTP_404_NOT_FOUND)

    user, created = createTestSuperUser()

    login(
        request, user, backend="django.contrib.auth.backends.ModelBackend"
    )  # attaches user to request + session middleware
    return return_tokens(user)


@csrf_exempt
@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
def login_staff(request):
    if not isTestEnvironment(request):
        return Response({"detail": "Not Found"}, status=status.HTTP_404_NOT_FOUND)

    user, created = createTestStaffUser()
    login(
        request, user, backend="django.contrib.auth.backends.ModelBackend"
    )  # attaches user to request + session middleware
    return return_tokens(user)


@csrf_exempt
@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
def login_user(request):
    if not isTestEnvironment(request):
        return Response({"detail": "Not Found"}, status=status.HTTP_404_NOT_FOUND)

    user, created = createTestUser()
    login(
        request, user, backend="django.contrib.auth.backends.ModelBackend"
    )  # attaches user to request + session middleware

    return return_tokens(user)


# Login as user claimer (has Discord + Steam ID matching claimable_profile)
@csrf_exempt
@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
def login_user_claimer(request):
    """
    Login as user_claimer - for testing claim/merge flow.
    This user has the same Steam ID as claimable_profile.
    Also ensures claimable_profile exists.
    """
    if not isTestEnvironment(request):
        return Response({"detail": "Not Found"}, status=status.HTTP_404_NOT_FOUND)

    # Ensure the claimable user exists first
    createClaimableTestUser()

    # Login as the claimer
    user, created = createUserClaimerTestUser()
    login(request, user, backend="django.contrib.auth.backends.ModelBackend")
    return return_tokens(user)


# OrgAdmin login
@csrf_exempt
@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
def login_org_admin(request):
    """Login as organization admin test user."""
    if not isTestEnvironment(request):
        return Response({"detail": "Not Found"}, status=status.HTTP_404_NOT_FOUND)

    user, created = createOrgAdminTestUser()

    # Make this user an admin of org 1 (DTX) if not already
    from app.models import Organization

    org = Organization.objects.filter(pk=1).first()
    if org and user not in org.admins.all():
        org.admins.add(user)

    login(request, user, backend="django.contrib.auth.backends.ModelBackend")
    return return_tokens(user)


# OrgStaff login
@csrf_exempt
@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
def login_org_staff(request):
    """Login as organization staff test user."""
    if not isTestEnvironment(request):
        return Response({"detail": "Not Found"}, status=status.HTTP_404_NOT_FOUND)

    user, created = createOrgStaffTestUser()

    # Make this user staff of org 1 (DTX) if not already
    from app.models import Organization

    org = Organization.objects.filter(pk=1).first()
    if org and user not in org.staff.all():
        org.staff.add(user)

    login(request, user, backend="django.contrib.auth.backends.ModelBackend")
    return return_tokens(user)


# LeagueAdmin login
@csrf_exempt
@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
def login_league_admin(request):
    """Login as league admin test user."""
    if not isTestEnvironment(request):
        return Response({"detail": "Not Found"}, status=status.HTTP_404_NOT_FOUND)

    user, created = createLeagueAdminTestUser()

    # Make this user an admin of league 1 if not already
    from league.models import League

    league = League.objects.filter(pk=1).first()
    if league and user not in league.admins.all():
        league.admins.add(user)

    login(request, user, backend="django.contrib.auth.backends.ModelBackend")
    return return_tokens(user)


# LeagueStaff login
@csrf_exempt
@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
def login_league_staff(request):
    """Login as league staff test user."""
    if not isTestEnvironment(request):
        return Response({"detail": "Not Found"}, status=status.HTTP_404_NOT_FOUND)

    user, created = createLeagueStaffTestUser()

    # Make this user staff of league 1 if not already
    from league.models import League

    league = League.objects.filter(pk=1).first()
    if league and user not in league.staff.all():
        league.staff.add(user)

    login(request, user, backend="django.contrib.auth.backends.ModelBackend")
    return return_tokens(user)


@csrf_exempt
@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
def login_as_user(request):
    """
    TEST ONLY: Login as any user by primary key.

    This endpoint only works when TEST_MODE environment is set.
    Used by Cypress tests to login as specific users (e.g., captains).

    Request body:
        user_pk: int - Primary key of user to login as

    Returns:
        200: Success with user data
        400: Missing user_pk
        404: Not in test mode or user not found
    """
    if not isTestEnvironment(request):
        return Response({"detail": "Not Found"}, status=status.HTTP_404_NOT_FOUND)

    user_pk = request.data.get("user_pk")
    if not user_pk:
        return Response(
            {"error": "user_pk is required"}, status=status.HTTP_400_BAD_REQUEST
        )

    try:
        user = CustomUser.objects.get(pk=user_pk)
    except CustomUser.DoesNotExist:
        return Response({"error": "User not found"}, status=status.HTTP_404_NOT_FOUND)

    login(request, user, backend="django.contrib.auth.backends.ModelBackend")

    from app.serializers import UserSerializer

    return Response({"success": True, "user": UserSerializer(user).data})


@csrf_exempt
@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
def login_as_discord_id(request):
    """
    Login as a user by their Discord ID (TEST ONLY).

    This endpoint is only available when TEST_ENDPOINTS=true.
    Discord IDs are stable across populate runs, unlike PKs.

    Request body:
        discord_id: str - The Discord ID of the user to login as

    Returns:
        200: Login successful with user data
        404: User not found
    """
    if not isTestEnvironment(request):
        return Response({"detail": "Not Found"}, status=status.HTTP_404_NOT_FOUND)

    discord_id = request.data.get("discord_id")
    if not discord_id:
        return Response(
            {"error": "discord_id is required"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    user = CustomUser.objects.filter(discordId=discord_id).first()
    if not user:
        return Response(
            {"error": f"User with Discord ID {discord_id} not found"},
            status=status.HTTP_404_NOT_FOUND,
        )

    login(request, user, backend="django.contrib.auth.backends.ModelBackend")

    response = Response(
        {
            "success": True,
            "user": {
                "pk": user.pk,
                "username": user.username,
                "discordUsername": user.discordUsername,
                "discordId": user.discordId,
                "mmr": user.mmr,
            },
        },
        status=status.HTTP_200_OK,
    )

    # Set cookies in response headers for Cypress
    response["CookieSessionId"] = request.session.session_key
    response["CookieCsrfToken"] = request.META.get("CSRF_COOKIE", "")

    return response


@api_view(["GET"])
@permission_classes([AllowAny])
def get_tournament_by_key(request, key: str):
    """
    TEST ONLY: Get tournament by test config key.

    This endpoint only works when TEST_MODE environment is set.
    Used by Cypress tests to get tournament data by config key.

    Path params:
        key: str - Test tournament config key (e.g., 'draft_captain_turn')

    Returns:
        200: Tournament data
        404: Not in test mode or tournament not found
    """
    if not isTestEnvironment(request):
        return Response({"detail": "Not Found"}, status=status.HTTP_404_NOT_FOUND)

    from app.models import Tournament
    from app.serializers import TournamentSerializer
    from tests.helpers.tournament_config import TEST_KEY_TO_NAME

    tournament_name = TEST_KEY_TO_NAME.get(key)
    if not tournament_name:
        return Response(
            {"error": f"Unknown tournament key: {key}"},
            status=status.HTTP_404_NOT_FOUND,
        )

    try:
        tournament = Tournament.objects.get(name=tournament_name)
    except Tournament.DoesNotExist:
        return Response(
            {
                "error": f"Tournament '{tournament_name}' not found. Run populate_test_tournaments() first."
            },
            status=status.HTTP_404_NOT_FOUND,
        )

    return Response(TournamentSerializer(tournament).data)


@csrf_exempt
@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
def create_claimable_user(request):
    """
    TEST ONLY: Create a user without Discord or Steam ID that can be claimed.

    This endpoint is used by Playwright tests to test the "Claim Profile" feature.
    Creates a user with only username, nickname, and MMR - no discordId or steamid.

    Request body (optional):
        username: str - Username for the user (default: generated)
        nickname: str - Nickname for the user (default: generated)
        mmr: int - MMR value (default: random 2000-6000)

    Returns:
        200: Created user data
        404: Not in test mode
    """
    if not isTestEnvironment(request):
        return Response({"detail": "Not Found"}, status=status.HTTP_404_NOT_FOUND)

    import uuid

    # Generate unique identifiers if not provided
    unique_id = str(uuid.uuid4())[:8]
    username = request.data.get("username", f"claimable_{unique_id}")
    nickname = request.data.get("nickname", f"Claimable User {unique_id}")
    mmr = request.data.get("mmr", random.randint(2000, 6000))

    # Create user without Discord or Steam
    user = CustomUser.objects.create(
        username=username,
        nickname=nickname,
        mmr=mmr,
        discordId=None,
        discordUsername=None,
        steamid=None,
    )
    user.set_unusable_password()
    user.save()

    from app.serializers import UserSerializer

    return Response(
        {
            "success": True,
            "user": UserSerializer(user).data,
        },
        status=status.HTTP_201_CREATED,
    )


@api_view(["GET"])
@permission_classes([AllowAny])
def get_user_org_membership(request, user_pk: int):
    """
    TEST ONLY: Get OrgUser and LeagueUser records for a user.

    This endpoint is used by Playwright tests to verify that adding a user
    to a tournament correctly creates OrgUser and LeagueUser records.

    Path params:
        user_pk: int - Primary key of the user

    Returns:
        200: User membership data including org_users and league_users
        404: Not in test mode or user not found
    """
    if not isTestEnvironment(request):
        return Response({"detail": "Not Found"}, status=status.HTTP_404_NOT_FOUND)

    try:
        user = CustomUser.objects.get(pk=user_pk)
    except CustomUser.DoesNotExist:
        return Response(
            {"error": f"User with pk {user_pk} not found"},
            status=status.HTTP_404_NOT_FOUND,
        )

    from league.models import LeagueUser
    from org.models import OrgUser

    org_users = OrgUser.objects.filter(user=user).select_related("organization")
    league_users = LeagueUser.objects.filter(user=user).select_related(
        "league", "org_user"
    )

    return Response(
        {
            "user": {
                "pk": user.pk,
                "username": user.username,
                "discordId": user.discordId,
            },
            "org_users": [
                {
                    "pk": ou.pk,
                    "organization_pk": ou.organization.pk,
                    "organization_name": ou.organization.name,
                    "mmr": ou.mmr,
                }
                for ou in org_users
            ],
            "league_users": [
                {
                    "pk": lu.pk,
                    "league_pk": lu.league.pk,
                    "league_name": lu.league.name,
                    "org_user_pk": lu.org_user.pk,
                    "mmr": lu.mmr,
                }
                for lu in league_users
            ],
        }
    )


@csrf_exempt
@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
def reset_org_admin_team(request, org_pk: int):
    """
    TEST ONLY: Reset organization admin team to known state.

    Resets admins to only ORG_ADMIN_USER and staff to only ORG_STAFF_USER.
    Used by Playwright tests to ensure consistent state between test runs.
    """
    if not isTestEnvironment(request):
        return Response({"detail": "Not Found"}, status=status.HTTP_404_NOT_FOUND)

    from app.models import Organization

    try:
        org = Organization.objects.get(pk=org_pk)
    except Organization.DoesNotExist:
        return Response(
            {"error": f"Organization with pk {org_pk} not found"},
            status=status.HTTP_404_NOT_FOUND,
        )

    # Reset admins to only ORG_ADMIN_USER
    org_admin = CustomUser.objects.filter(pk=ORG_ADMIN_USER.pk).first()
    org.admins.clear()
    if org_admin:
        org.admins.add(org_admin)

    # Reset staff to only ORG_STAFF_USER
    org_staff = CustomUser.objects.filter(pk=ORG_STAFF_USER.pk).first()
    org.staff.clear()
    if org_staff:
        org.staff.add(org_staff)

    # Invalidate cacheops cache — M2M .clear()/.add() may not auto-invalidate
    try:
        from cacheops import invalidate_obj

        invalidate_obj(org)
    except ImportError:
        pass

    return Response(
        {
            "success": True,
            "admins": [{"pk": u.pk, "username": u.username} for u in org.admins.all()],
            "staff": [{"pk": u.pk, "username": u.username} for u in org.staff.all()],
        }
    )


@csrf_exempt
@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
def create_claim_request(request):
    """
    TEST ONLY: Create a profile claim request for testing the admin claims flow.

    This endpoint creates a pending claim request that can be approved/rejected
    by an org admin in the Claims tab.

    Request body:
        organization_id: int - Organization ID for the claim request
        claimer_username: str (optional) - Username for claimer (default: generated)
        target_steamid: int (optional) - Steam ID for target profile (default: generated)
        target_nickname: str (optional) - Nickname for target profile

    Returns:
        201: Created claim request data
        404: Not in test mode or organization not found
    """
    if not isTestEnvironment(request):
        return Response({"detail": "Not Found"}, status=status.HTTP_404_NOT_FOUND)

    import uuid

    from app.models import Organization, ProfileClaimRequest

    organization_id = request.data.get("organization_id", 1)
    try:
        organization = Organization.objects.get(pk=organization_id)
    except Organization.DoesNotExist:
        return Response(
            {"error": f"Organization with pk {organization_id} not found"},
            status=status.HTTP_404_NOT_FOUND,
        )

    # Generate unique identifiers
    unique_id = str(uuid.uuid4())[:8]
    claimer_username = request.data.get("claimer_username", f"claimer_{unique_id}")
    target_steamid = request.data.get(
        "target_steamid", random.randint(76561198000000000, 76561198999999999)
    )
    target_nickname = request.data.get("target_nickname", f"Target Profile {unique_id}")

    # Create the claimer user (has Discord, no Steam)
    # Discord IDs are snowflakes (large integers)
    test_discord_id = str(random.randint(100000000000000000, 999999999999999999))
    claimer = CustomUser.objects.create(
        username=claimer_username,
        nickname=claimer_username,
        discordId=test_discord_id,
        discordUsername=claimer_username,
        steamid=None,
    )
    claimer.set_unusable_password()
    claimer.save()

    # Create the target user (has Steam, no Discord)
    target_user = CustomUser.objects.create(
        username=None,
        nickname=target_nickname,
        discordId=None,
        steamid=target_steamid,
        mmr=random.randint(2000, 6000),
    )
    target_user.set_unusable_password()
    target_user.save()

    # Create the claim request
    claim_request = ProfileClaimRequest.objects.create(
        claimer=claimer,
        target_user=target_user,
        organization=organization,
        status=ProfileClaimRequest.Status.PENDING,
    )

    from org.serializers import ProfileClaimRequestSerializer

    return Response(
        {
            "success": True,
            "claim_request": ProfileClaimRequestSerializer(claim_request).data,
        },
        status=status.HTTP_201_CREATED,
    )
