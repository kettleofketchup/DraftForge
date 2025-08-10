import json
from datetime import timedelta

import requests
from django.contrib.auth import login
from django.contrib.auth import logout as auth_logout
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, HttpResponseBadRequest, JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from rest_framework import generics, permissions, status, viewsets
from rest_framework.decorators import api_view, permission_classes
from rest_framework.generics import GenericAPIView
from rest_framework.permissions import AllowAny, IsAdminUser, IsAuthenticated
from rest_framework.response import Response
from rest_framework.reverse import reverse
from social_core.backends.oauth import BaseOAuth1, BaseOAuth2

# Create your views here.
from social_django.models import USER_MODEL  # fix: skip
from social_django.models import AbstractUserSocialAuth, DjangoStorage
from social_django.utils import load_strategy, psa

from backend import settings

from .decorators import render_to
from .models import CustomUser, Draft, DraftRound, Team, Tournament
from .permissions import IsStaff
from .serializers import (
    DraftRoundSerializer,
    DraftSerializer,
    GameSerializer,
    TeamSerializer,
    TournamentSerializer,
    UserSerializer,
)
from .utils.avatar_utils import refresh_user_avatar


def logout(request):
    """Logs out user"""
    auth_logout(request)
    return redirect("/")


@render_to("home.html")
def home(request):
    """Home view, displays login mechanism"""
    if request.user.is_authenticated:
        return redirect("done")
    return None


@login_required
@render_to("home.html")
def done(request):
    """Login complete view, displays user data"""
    return


@render_to("home.html")
def validation_sent(request):
    """Email validation sent confirmation page"""
    return {
        "validation_sent": True,
        "email": request.session.get("email_validation_address"),
    }


@render_to("home.html")
def require_email(request):
    """Email required page"""
    strategy = load_strategy()
    partial_token = request.GET.get("partial_token")
    partial = strategy.partial_load(partial_token)
    return {
        "email_required": True,
        "partial_backend_name": partial.backend,
        "partial_token": partial_token,
    }


@render_to("home.html")
def require_country(request):
    """Country required page"""
    strategy = load_strategy()
    partial_token = request.GET.get("partial_token")
    partial = strategy.partial_load(partial_token)
    return {
        "country_required": True,
        "partial_backend_name": partial.backend,
        "partial_token": partial_token,
    }


@render_to("home.html")
def require_city(request):
    """City required page"""
    strategy = load_strategy()
    partial_token = request.GET.get("partial_token")
    partial = strategy.partial_load(partial_token)
    return {
        "city_required": True,
        "partial_backend_name": partial.backend,
        "partial_token": partial_token,
    }


@psa("social:complete")
def ajax_auth(request, backend):
    """AJAX authentication endpoint"""
    if isinstance(request.backend, BaseOAuth1):
        token = {
            "oauth_token": request.REQUEST.get("access_token"),
            "oauth_token_secret": request.REQUEST.get("access_token_secret"),
        }
    elif isinstance(request.backend, BaseOAuth2):
        token = request.REQUEST.get("access_token")
    else:
        raise HttpResponseBadRequest("Wrong backend type")
    user = request.backend.do_auth(token, ajax=True)
    login(request, user)
    data = {"id": user.id, "username": user.username}
    return HttpResponse(json.dumps(data), mimetype="application/json")


from django.contrib.auth.models import User

from .models import CustomUser
from .serializers import UserSerializer


@permission_classes((IsStaff,))
class UserView(viewsets.ModelViewSet):
    serializer_class = UserSerializer
    queryset = CustomUser.objects.all()
    http_method_names = [
        "get",
        "post",
        "put",
        "patch",
        "delete",
        "head",
        "options",
        "trace",
    ]

    def patch(self, request, *args, **kwargs):
        return self.partial_update(request, *args, **kwargs)

    def get_permissions(self):
        self.permission_classes = [IsStaff]
        if self.request.method == "GET":
            self.permission_classes = [AllowAny]
        return super(UserView, self).get_permissions()

    @permission_classes((IsAdminUser,))
    def delete(self, request, *args, **kwargs):
        try:
            user = self.get_object()
            user.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        except CustomUser.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)


@permission_classes((IsStaff,))
class TournamentView(viewsets.ModelViewSet):
    serializer_class = TournamentSerializer
    queryset = Tournament.objects.all()
    http_method_names = [
        "get",
        "post",
        "put",
        "patch",
        "delete",
        "head",
        "options",
        "trace",
    ]

    @permission_classes((IsStaff,))
    def patch(self, request, *args, **kwargs):
        print(request.data)
        return self.partial_update(request, *args, **kwargs)

    def get_permissions(self):
        self.permission_classes = [IsStaff]
        if self.request.method == "GET":
            self.permission_classes = [AllowAny]
        return super(TournamentView, self).get_permissions()


@permission_classes((IsStaff,))
class TournamentView(viewsets.ModelViewSet):
    serializer_class = TournamentSerializer
    queryset = Tournament.objects.all()
    http_method_names = [
        "get",
        "post",
        "put",
        "patch",
        "delete",
        "head",
        "options",
        "trace",
    ]

    @permission_classes((IsStaff,))
    def patch(self, request, *args, **kwargs):
        print(request.data)
        return self.partial_update(request, *args, **kwargs)

    def get_permissions(self):
        self.permission_classes = [IsStaff]
        if self.request.method == "GET":
            self.permission_classes = [AllowAny]
        return super(TournamentView, self).get_permissions()


class TeamView(viewsets.ModelViewSet):
    serializer_class = TeamSerializer
    queryset = Team.objects.all()
    http_method_names = [
        "get",
        "post",
        "put",
        "patch",
        "delete",
        "head",
        "options",
        "trace",
    ]

    def get_permissions(self):
        self.permission_classes = [IsStaff]
        if self.request.method == "GET":
            self.permission_classes = [AllowAny]
        return super(TeamView, self).get_permissions()

    def patch(self, request, *args, **kwargs):
        return self.partial_update(request, *args, **kwargs)


@permission_classes((IsStaff,))
class DraftView(viewsets.ModelViewSet):
    serializer_class = DraftSerializer
    queryset = Draft.objects.all()
    http_method_names = [
        "get",
        "post",
        "put",
        "patch",
        "delete",
        "head",
        "options",
        "trace",
    ]

    @permission_classes((IsStaff,))
    def patch(self, request, *args, **kwargs):
        print(request.data)
        return self.partial_update(request, *args, **kwargs)

    def get_permissions(self):
        self.permission_classes = [IsStaff]
        if self.request.method == "GET":
            self.permission_classes = [AllowAny]
        return super(DraftView, self).get_permissions()


@permission_classes((IsStaff,))
class DraftRoundView(viewsets.ModelViewSet):
    serializer_class = DraftRoundSerializer
    queryset = DraftRound.objects.all()
    http_method_names = [
        "get",
        "post",
        "put",
        "patch",
        "delete",
        "head",
        "options",
        "trace",
    ]

    @permission_classes((IsStaff,))
    def patch(self, request, *args, **kwargs):
        print(request.data)
        return self.partial_update(request, *args, **kwargs)

    def get_permissions(self):
        self.permission_classes = [IsStaff]
        if self.request.method == "GET":
            self.permission_classes = [AllowAny]
        return super(DraftRoundView, self).get_permissions()


class UserCreateView(generics.CreateAPIView):
    serializer_class = UserSerializer
    permission_classes = [IsStaff]


@api_view(["GET"])
@permission_classes((AllowAny,))
def current_user(request):

    user = request.user
    if request.user.is_authenticated:

        return Response(
            {
                "username": user.username,
                "avatarUrl": user.avatarUrl,
                "is_staff": user.is_staff,
                "is_superuser": user.is_superuser,
            }
        )
    else:
        return Response()


from django.core.cache import cache


@api_view(["GET"])
@permission_classes([AllowAny])
def get_discord_members(request):
    guild_id = (
        settings.DISCORD_GUILD_ID
    )  # Add your Discord server (guild) ID in settings
    bot_token = settings.DISCORD_BOT_TOKEN  # Add your bot token in settings

    url = f"{settings.DISCORD_API_BASE_URL}/guilds/{guild_id}/members"
    headers = {"Authorization": f"Bot {bot_token}"}
    after = None
    limit = 1000
    members = []
    cache_key = f"discord_members_{guild_id}"
    cached_members = cache.get(cache_key)

    if cached_members:
        return JsonResponse({"members": cached_members}, safe=True)

    while True:
        params = {"limit": limit}
        if after:
            params["after"] = after

        try:
            response = requests.get(url, headers=headers, params=params)
            response.raise_for_status()
            page = response.json()
            if not page:
                break
            after = page[-1]["user"]["id"]
            members.extend(page)
            if len(page) < limit:
                break
        except requests.exceptions.RequestException as e:
            return JsonResponse({"error": str(e)}, status=500)

    cache.set(cache_key, members, timeout=15)
    return JsonResponse({"members": members}, safe=True)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_user_guilds(request):
    access_token = request.user.social_auth.get(provider="discord").extra_data[
        "access_token"
    ]
    url = "https://discord.com/api/users/@me/guilds"
    headers = {"Authorization": f"Bearer {access_token}"}
    cache_key = f"discord_guilds"
    cached_guilds = cache.get(cache_key)
    if cached_guilds:
        return JsonResponse({"guilds": cached_guilds}, safe=True)

    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        guilds = response.json()
        cache.set(cache_key, guilds, timeout=5)
        return JsonResponse({"guilds": guilds}, safe=True)
    except requests.exceptions.RequestException as e:
        return JsonResponse({"error": str(e)}, status=500)


@api_view(["GET"])
@permission_classes([IsStaff])
def get_discord_voice_channel_activity(request):
    """
    Fetches all voice channels in the configured Discord guild that have active members.
    Returns a list of voice channels, each with its name, ID, and a list of member objects.
    """
    try:
        guild_id = settings.DISCORD_GUILD_ID
        bot_token = settings.DISCORD_BOT_TOKEN
        api_base_url = settings.DISCORD_API_BASE_URL
    except AttributeError as e:
        return JsonResponse(
            {"error": f"Discord API setting missing in Django settings: {e.name}"},
            status=500,
        )
    cache_key = f"voice_activity_{guild_id}"

    cached_voice_activity = cache.get(cache_key)
    if cached_voice_activity:
        return JsonResponse({"voice_activity": cached_voice_activity}, safe=True)

    headers = {"Authorization": f"Bot {bot_token}"}

    active_channels_data = []
    voice_channels_map = {}  # To store {channel_id: channel_name}

    try:
        # 1. Fetch all guild channels to identify voice channels and their names
        channels_url = f"{api_base_url}/guilds/{guild_id}/channels"
        response_channels = requests.get(channels_url, headers=headers)
        response_channels.raise_for_status()
        all_channels = response_channels.json()
        print(all_channels)
        for channel in all_channels:
            if channel.get("type") == 2:  # GUILD_VOICE type
                voice_channels_map[channel.get("id")] = channel.get(
                    "name", "Unknown Voice Channel"
                )

        # 2. Fetch guild resource, which includes the 'voice_states' array
        # The 'voice_states' array contains information about users in voice channels,
        # including their 'member' object.
        guild_url = f"{api_base_url}/guilds/{guild_id}"
        response_guild = requests.get(guild_url, headers=headers)
        response_guild.raise_for_status()
        guild_data = response_guild.json()
        print("Voice Channels Map:")
        print(voice_channels_map)
        # 3. Process voice_states to group members by channel
        # This temporary dictionary will hold {channel_id: [member_obj1, member_obj2]}
        members_in_channel_temp = {}
        print(f"guild_data: {guild_data.keys()}")

        for voice_state in guild_data.get("voice_states", []):
            channel_id = voice_state.get("channel_id")
            # The 'member' field in voice_state is a Guild Member object
            member_object = voice_state.get("member")
            print(member_object)
            # Ensure the user is in a voice channel we know and member data is present
            if channel_id and member_object and channel_id in voice_channels_map:
                if channel_id not in members_in_channel_temp:
                    members_in_channel_temp[channel_id] = []
                members_in_channel_temp[channel_id].append(member_object)
        print(f"members: {members_in_channel_temp}")
        # 4. Format the final output list
        for channel_id, members_list in members_in_channel_temp.items():
            # Only include channels that actually have members in them
            if members_list:
                active_channels_data.append(
                    {
                        "channel_id": channel_id,
                        "channel_name": voice_channels_map[channel_id],
                        "members": members_list,
                    }
                )
        cache.set(cache_key, active_channels_data, timeout=15)
        return JsonResponse({"active_voice_channels": active_channels_data}, safe=True)

    except requests.exceptions.RequestException as e:
        return JsonResponse(
            {"error": f"Error communicating with Discord API: {str(e)}"}, status=500
        )
    except Exception as e:

        # Catch any other unexpected errors during processing
        return JsonResponse(
            {"error": f"An unexpected error occurred: {str(e)}"}, status=500
        )


class GameCreateView(generics.CreateAPIView):
    serializer_class = GameSerializer
    permission_classes = [IsStaff]


from django.db import transaction


class TeamCreateView(generics.CreateAPIView):
    serializer_class = TeamSerializer
    permission_classes = [IsStaff]

    @transaction.atomic
    def perform_create(self, serializer):
        serializer.save()


class TournamentCreateView(generics.CreateAPIView):
    serializer_class = TournamentSerializer
    permission_classes = [IsStaff]


class DraftCreateView(generics.CreateAPIView):
    serializer_class = DraftSerializer
    permission_classes = [IsStaff]


class DraftRoundCreateView(generics.CreateAPIView):
    serializer_class = DraftRoundSerializer
    permission_classes = [IsStaff]


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def refresh_avatar(request):
    """
    Refresh the current user's Discord avatar by fetching the latest from Discord API.
    """
    try:
        user = request.user
        if not user.discordId:
            return Response(
                {"error": "User does not have a Discord ID associated"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Use force_refresh=True to always fetch from Discord
        result = refresh_user_avatar(user.id)

        if result["success"]:
            return Response(
                {
                    "message": result["message"],
                    "updated": result["updated"],
                    "avatar_url": result["avatar_url"],
                },
                status=status.HTTP_200_OK,
            )
        else:
            return Response(
                {"error": result["message"]}, status=status.HTTP_400_BAD_REQUEST
            )

    except Exception as e:
        return Response(
            {"error": f"Failed to refresh avatar: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(["POST"])
@permission_classes([IsAdminUser])
def refresh_user_avatar_admin(request, user_id):
    """
    Admin endpoint to refresh any user's Discord avatar.
    """
    try:
        result = refresh_user_avatar(user_id)

        if result["success"]:
            return Response(
                {
                    "message": result["message"],
                    "updated": result["updated"],
                    "avatar_url": result["avatar_url"],
                },
                status=status.HTTP_200_OK,
            )
        else:
            return Response(
                {"error": result["message"]}, status=status.HTTP_400_BAD_REQUEST
            )

    except Exception as e:
        return Response(
            {"error": f"Failed to refresh avatar: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(["POST"])
@permission_classes([AllowAny])
def refresh_all_avatars(request):
    """
    Refreshes the avatars for all users in the database.
    This is a public endpoint but is rate-limited to once per hour.
    """
    cache_key = "avatar_refresh_last_run"
    last_run = cache.get(cache_key)

    if last_run and (timezone.now() - last_run < timedelta(hours=1)):
        return Response(
            {"message": "Avatar refresh can only be run once per hour."},
            status=status.HTTP_200_OK,
        )

    updated_count = 0
    users = CustomUser.objects.all()
    for user in users:
        if user.check_and_update_avatar():
            updated_count += 1

    cache.set(cache_key, timezone.now(), timeout=3600)  # Cache for 1 hour

    return Response(
        {"message": f"Avatar refresh complete. {updated_count} avatars updated."},
        status=status.HTTP_200_OK,
    )
