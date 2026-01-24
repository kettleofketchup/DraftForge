# views_test_auth.py
import logging
import random
import token

from django.conf import settings
from django.contrib.auth import get_user_model
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
    if user.social_auth.filter(provider="discord").exists():

        if user.social_auth.get(provider="discord").extra_data.get("sessionid"):
            log.debug(
                f"Social auth has extra data: {user.social_auth.get(provider='discord').extra_data}"
            )
            return

    # Fake Discord user ID
    log.debug("getting or creating ")
    login
    social, created = UserSocialAuth.objects.get_or_create(
        user=user,
        provider="discord",
        uid=user.discordId,
        extra_data={
            "access_token": "cypress",
            "refresh_token": "cypress",
            "expires": 9999999999,  # far future
            "sessionid": "cypress",
            "csrftoken": "cypress",
        },
    )
    with transaction.atomic():
        log.debug("saving social auth")
        if created:
            social.save()
        user.save()


def createTestSuperUser() -> tuple[CustomUser, bool]:
    assert isTestEnvironment() == True
    uid = "243497113906970625"
    user, created = CustomUser.objects.get_or_create(
        username="kettleofketchup",
        discordId=uid,
        discordUsername="kettleofketchup",
    )
    if created:
        user.set_password("cypress")
        user.mmr = random.randint(2000, 6000)
        user.save()
    create_social_auth(user)

    if created or not user.is_superuser:
        user.is_staff = True

        user.is_superuser = True
        with transaction.atomic():
            user.check_and_update_avatar()
            user.save()

    return user, created


def createTestStaffUser() -> tuple[CustomUser, bool]:
    assert isTestEnvironment() == True
    uid = "702582402668560454"
    user, created = CustomUser.objects.get_or_create(
        username="hurk_",
        discordId=uid,
        discordUsername="hurk_",
    )
    if created:
        user.set_password("cypress")
        user.mmr = random.randint(2000, 6000)
        user.save()
    create_social_auth(user)

    if created or not user.is_staff:
        user.is_staff = True
        user.is_superuser = False
        with transaction.atomic():
            user.check_and_update_avatar()
            user.save()
    return user, created


from django.contrib.auth import login


def createTestUser() -> tuple[CustomUser, bool]:
    assert isTestEnvironment() == True
    uid = "198618246868500481"
    user, created = CustomUser.objects.get_or_create(
        username="bucketoffish55",
        discordId=uid,
        discordUsername="bucketoffish55",
    )

    if created:
        user.set_password("cypress")
        user.mmr = random.randint(2000, 6000)
        user.save()
    create_social_auth(user)

    if created or not user.is_superuser:
        user.is_staff = False
        user.is_superuser = False
        with transaction.atomic():
            user.check_and_update_avatar()
            user.save()

    return user, created


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
