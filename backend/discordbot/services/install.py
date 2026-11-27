"""Connect an organization to its Discord server through the bot install flow."""

import re
from typing import Any, Final, TypedDict
from urllib.parse import urlencode

import requests
from django.conf import settings
from django.core import signing
from django.core.cache import cache
from django.http import HttpRequest, HttpResponseRedirect, JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_GET
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request

from discordbot.install_schemas import (
    DiscordBotStatus,
    DiscordConnectError,
    DiscordInstallLink,
)
from discordbot.services.discord_members import DISCORD_HTTP_TIMEOUT_S
from discordbot.services.users import (
    BOT_ACCESS_CACHE_TTL,
    bot_access_cache_key,
    check_bot_guild_access,
)
from org.models import Organization
from org.permissions import has_org_admin_access, has_org_staff_access
from telemetry.logging import get_logger

log = get_logger(__name__)

STATE_SALT: Final = "discordbot.install"
STATE_MAX_AGE_S: Final = 15 * 60
CALLBACK_PATH: Final = "/api/discord/install/callback/"
INSTALL_PARAMS_CACHE_KEY: Final = "discord_app_install_params"
INSTALL_PARAMS_CACHE_TTL: Final = 60 * 60
DEFAULT_SCOPES: Final = ("bot", "applications.commands")
DEFAULT_PERMISSIONS: Final = "68672"
GUILD_ID_RE: Final = re.compile(r"^\d{17,20}$")


class InstallParams(TypedDict):
    app_id: str
    scopes: list[str]
    permissions: str


def callback_url() -> str:
    return f"{settings.SITE_URL.rstrip('/')}{CALLBACK_PATH}"


def _bot_headers() -> dict[str, str]:
    return {"Authorization": f"Bot {settings.DISCORD_BOT_TOKEN}"}


def install_params() -> InstallParams | None:
    """The bot application's id and default install scopes/permissions."""
    cached: InstallParams | None = cache.get(INSTALL_PARAMS_CACHE_KEY)
    if cached is not None:
        return cached
    if not settings.DISCORD_BOT_TOKEN:
        return None
    try:
        response = requests.get(
            f"{settings.DISCORD_API_BASE_URL}/applications/@me",
            headers=_bot_headers(),
            timeout=DISCORD_HTTP_TIMEOUT_S,
        )
    except requests.exceptions.RequestException:
        log.warning(
            "install_params_fetch_failed",
            system="discord",
            subsystem="install",
            exc_info=True,
        )
        return None
    if response.status_code != 200:
        log.warning(
            "install_params_fetch_failed",
            system="discord",
            subsystem="install",
            status=response.status_code,
        )
        return None

    data: dict[str, Any] = response.json()
    configured: dict[str, Any] = data.get("install_params") or {}
    scopes = list(configured.get("scopes") or DEFAULT_SCOPES)
    if "bot" not in scopes:
        scopes.insert(0, "bot")
    params: InstallParams = {
        "app_id": str(data["id"]),
        "scopes": scopes,
        "permissions": str(configured.get("permissions") or DEFAULT_PERMISSIONS),
    }
    cache.set(INSTALL_PARAMS_CACHE_KEY, params, timeout=INSTALL_PARAMS_CACHE_TTL)
    return params


def fetch_bot_guild(guild_id: str) -> dict[str, Any] | None:
    """The guild as the bot sees it, or None when the bot is not in it."""
    if not settings.DISCORD_BOT_TOKEN:
        return None
    try:
        response = requests.get(
            f"{settings.DISCORD_API_BASE_URL}/guilds/{guild_id}",
            headers=_bot_headers(),
            timeout=DISCORD_HTTP_TIMEOUT_S,
        )
    except requests.exceptions.RequestException:
        return None
    if response.status_code != 200:
        return None
    return response.json()


def build_install_url(org: Organization, user_pk: int, params: InstallParams) -> str:
    state = signing.dumps({"org": org.pk, "user": user_pk}, salt=STATE_SALT)
    query: dict[str, str] = {
        "client_id": params["app_id"],
        "scope": " ".join(params["scopes"]),
        "permissions": params["permissions"],
        "response_type": "code",
        "redirect_uri": callback_url(),
        "state": state,
    }
    if org.discord_server_id:
        query["guild_id"] = org.discord_server_id
    return f"https://discord.com/oauth2/authorize?{urlencode(query)}"


def bot_guild_name(guild_id: str) -> str | None:
    cache_key = f"discord_bot_guild_name_{guild_id}"
    cached: str | None = cache.get(cache_key)
    if cached is not None:
        return cached
    guild = fetch_bot_guild(guild_id)
    name: str | None = guild.get("name") if guild else None
    if name:
        cache.set(cache_key, name, timeout=BOT_ACCESS_CACHE_TTL)
    return name


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def check_discord_bot_status(request: Request, pk: int) -> JsonResponse:
    """Whether the DraftForge bot can see the org's Discord server, and its name."""
    org = get_object_or_404(Organization, pk=pk)
    if not has_org_staff_access(request.user, org):
        return JsonResponse({"error": "Permission denied"}, status=403)
    if not org.discord_server_id:
        status = DiscordBotStatus(has_bot=False, reason="no_server_configured")
    else:
        has_bot = check_bot_guild_access(org.discord_server_id)
        status = DiscordBotStatus(
            has_bot=has_bot,
            guild_name=bot_guild_name(org.discord_server_id) if has_bot else None,
        )
    return JsonResponse(status.model_dump(mode="json"))


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def discord_install_link(request: Request, pk: int) -> JsonResponse:
    org = get_object_or_404(Organization, pk=pk)
    if not has_org_admin_access(request.user, org):
        return JsonResponse(
            {"error": "Only organization admins can connect Discord."}, status=403
        )
    params = install_params()
    if params is None:
        return JsonResponse(
            {"error": "Discord is unavailable right now. Try again shortly."},
            status=503,
        )
    link = DiscordInstallLink(url=build_install_url(org, request.user.pk, params))
    return JsonResponse(link.model_dump(mode="json"))


def _redirect(
    org_pk: int | None, error: DiscordConnectError | None = None
) -> HttpResponseRedirect:
    if org_pk is None:
        return HttpResponseRedirect(
            f"/organizations?{urlencode({'discord': 'error', 'reason': error})}"
        )
    query: dict[str, str] = {"settings": "discord"}
    if error is None:
        query["discord"] = "connected"
    else:
        query["discord"] = "error"
        query["reason"] = error.value
    return HttpResponseRedirect(f"/organizations/{org_pk}?{urlencode(query)}")


@require_GET
def discord_install_callback(request: HttpRequest) -> HttpResponseRedirect:
    """Discord redirects here after the bot is added (or the prompt is cancelled)."""
    try:
        state: dict[str, int] = signing.loads(
            request.GET.get("state", ""), salt=STATE_SALT, max_age=STATE_MAX_AGE_S
        )
        org_pk = int(state["org"])
        user_pk = int(state["user"])
    except (signing.BadSignature, KeyError, TypeError, ValueError):
        return _redirect(None, DiscordConnectError.EXPIRED)

    if request.GET.get("error"):
        return _redirect(org_pk, DiscordConnectError.CANCELLED)

    org = Organization.objects.filter(pk=org_pk).first()
    if (
        org is None
        or not request.user.is_authenticated
        or request.user.pk != user_pk
        or not has_org_admin_access(request.user, org)
    ):
        return _redirect(org_pk, DiscordConnectError.FORBIDDEN)

    guild_id = request.GET.get("guild_id", "")
    if not GUILD_ID_RE.match(guild_id):
        return _redirect(org_pk, DiscordConnectError.INVALID_SERVER)

    if fetch_bot_guild(guild_id) is None:
        log.warning(
            "install_bot_missing",
            system="discord",
            subsystem="install",
            org_id=org_pk,
            guild_id=guild_id,
        )
        return _redirect(org_pk, DiscordConnectError.BOT_MISSING)

    previous = org.discord_server_id
    org.discord_server_id = guild_id
    org.save(update_fields=["discord_server_id"])
    cache.delete(bot_access_cache_key(guild_id))
    log.info(
        "install_connected",
        system="discord",
        subsystem="install",
        org_id=org_pk,
        guild_id=guild_id,
        previous_guild_id=previous,
        user_id=user_pk,
    )
    return _redirect(org_pk)
