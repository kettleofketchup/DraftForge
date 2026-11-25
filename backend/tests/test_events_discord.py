"""
Test-only endpoints for Discord event lifecycle E2E testing.

- discord_status: Whether the stack can post to Discord at all
- simulate_discord_signup: Drives the full signup handler chain
- verify_discord_messages: Reads back signup/announcement embeds from Discord
"""

import logging
from uuid import uuid4

import requests
from django.conf import settings
from django.views.decorators.csrf import csrf_exempt
from rest_framework import status
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
)
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response

from common.game import GameType
from common.utils import isTestEnvironment
from discordbot.dm import DMRequest, send_dm
from discordbot.dm_keys import test_notification_key
from discordbot.models import DMKind, DMStatus, DMSubject
from discordbot.utils import (
    DISCORD_API_BASE,
    DiscordAuthError,
    _get_headers,
    _rate_limited_request,
)
from events.discord.embeds import build_subscriber_dm_embed
from events.models import Event
from org.mmr import OrgMmrError, set_org_mmr
from org.models import OrgUser

log = logging.getLogger(__name__)


def _auth_failed_response() -> Response:
    return Response(
        {
            "error": "discord_auth_failed",
            "detail": "Discord rejected the bot token (401)",
        },
        status=status.HTTP_503_SERVICE_UNAVAILABLE,
    )


def discord_auth_failure() -> Response | None:
    """503 when Discord rejects the configured bot token, else None."""
    if not settings.DISCORD_BOT_TOKEN:
        return None
    try:
        _rate_limited_request(
            "GET", f"{DISCORD_API_BASE}/users/@me", headers=_get_headers()
        )
    except DiscordAuthError:
        return _auth_failed_response()
    except requests.RequestException:
        return None
    return None


@csrf_exempt
@api_view(["GET"])
@authentication_classes([])
@permission_classes([AllowAny])
def discord_status(request: Request) -> Response:
    """TEST ONLY: whether this stack has a Discord bot token to post with."""
    if not isTestEnvironment(request):
        return Response({"detail": "Not Found"}, status=status.HTTP_404_NOT_FOUND)
    return Response({"bot_token_configured": bool(settings.DISCORD_BOT_TOKEN)})


@csrf_exempt
@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
def simulate_discord_signup(request, event_pk):
    """TEST ONLY: Simulate full Discord signup flow."""
    if not isTestEnvironment(request):
        return Response({"detail": "Not Found"}, status=status.HTTP_404_NOT_FOUND)

    from events.discord.handlers import (
        handle_battle_cup_submit,
        handle_rank_medal_select,
        handle_signup_button,
        handle_signup_modal_submit,
    )

    data = request.data
    discord_user_id = data.get("discord_user_id", "")
    discord_username = data.get("discord_username", "")

    # Step 1: Click signup button
    result = handle_signup_button(event_pk, discord_user_id, discord_username)
    if result["action"] == "signed_up":
        return Response({"step": "direct_signup", "result": result})
    if result["action"] == "error":
        return Response({"step": "signup_button", "result": result}, status=400)
    if result["action"] != "needs_modal":
        return Response(
            {"step": "signup_button", "result": result, "error": "unexpected action"},
            status=400,
        )

    # Step 2: Submit modal
    values = {
        "friend_id": data.get("friend_id", ""),
        "positions": data.get("positions", []),
        "rank_status": data.get("rank_status", "active"),
    }
    result = handle_signup_modal_submit(
        event_pk, discord_user_id, values=values, game_type=result["game_type"]
    )
    if result["action"] == "error":
        return Response({"step": "modal_submit", "result": result}, status=400)
    if result["action"] == "signed_up":
        return Response({"step": "modal_direct_signup", "result": result})
    if result["action"] not in ("needs_rank_details", "needs_rank_status"):
        return Response(
            {"step": "modal_submit", "result": result, "error": "unexpected action"},
            status=400,
        )

    # Step 3: Rank details
    rank_status = data.get("rank_status", "active")
    if rank_status in ("active", "previous"):
        medal = data.get("rank_medal", "Legend 3")
        result = handle_rank_medal_select(event_pk, discord_user_id, medal)
    elif rank_status == "never":
        tier = data.get("battle_cup_tier", "5")
        result = handle_battle_cup_submit(event_pk, discord_user_id, str(tier))
    else:
        return Response(
            {"step": "rank_details", "error": f"unknown rank_status: {rank_status}"},
            status=400,
        )

    if result.get("action") == "error":
        return Response({"step": "rank_details", "result": result}, status=400)
    if result.get("action") == "needs_screenshot":
        return Response({"step": "needs_screenshot", "result": result})

    return Response({"step": "completed", "result": result})


@csrf_exempt
@api_view(["GET"])
@authentication_classes([])
@permission_classes([AllowAny])
def verify_discord_messages(request, event_pk):
    """TEST ONLY: Verify Discord messages for an event."""
    if not isTestEnvironment(request):
        return Response({"detail": "Not Found"}, status=status.HTTP_404_NOT_FOUND)

    from discordbot.models import DiscordEvent
    from discordbot.test_utils import fetch_message, get_test_bot_tokens

    try:
        discord_event = DiscordEvent.objects.get(event_id=event_pk)
    except DiscordEvent.DoesNotExist:
        return Response({"has_discord": False})

    result = {
        "has_discord": True,
        "signup_message": None,
        "announcement": None,
        "has_test_bots": bool(get_test_bot_tokens()),
    }

    def _message_data(msg):
        """Extract verification data from a Discord message."""
        if not msg:
            return None
        data = {
            "id": msg["id"],
            "embeds": len(msg.get("embeds", [])),
            "components": len(msg.get("components", [])),
            "has_buttons": any(
                c.get("type") == 2
                for row in msg.get("components", [])
                for c in row.get("components", [])
            ),
            "button_labels": [
                c.get("label")
                for row in msg.get("components", [])
                for c in row.get("components", [])
                if c.get("type") == 2
            ],
            "reactions": [
                {"emoji": r["emoji"]["name"], "count": r["count"]}
                for r in msg.get("reactions", [])
            ],
        }
        if msg.get("embeds"):
            e = msg["embeds"][0]
            data["embed_title"] = e.get("title", "")
            data["embed_description"] = e.get("description", "")
            data["embed_fields"] = [
                {"name": f["name"], "value": f["value"]} for f in e.get("fields", [])
            ]
        return data

    # Check signup message
    try:
        sm = discord_event.signup_message
        if sm and sm.has_posted and sm.message_id:
            channel = sm.thread_id or sm.channel_id
            msg = fetch_message(channel, sm.message_id)
            result["signup_message"] = _message_data(msg)
    except Exception as e:
        result["signup_message_error"] = str(e)

    # Check announcement
    try:
        ann = discord_event.announcement
        if ann and ann.has_posted and ann.message_id:
            channel = ann.thread_id or ann.channel_id
            msg = fetch_message(channel, ann.message_id)
            result["announcement"] = _message_data(msg)
    except Exception as e:
        result["announcement_error"] = str(e)

    return Response(result)


@csrf_exempt
@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
def send_test_notification(request: Request, event_pk: int) -> Response:
    """TEST ONLY: Send event notification DM to a specific Discord user."""
    if not isTestEnvironment(request):
        return Response({"detail": "Not Found"}, status=status.HTTP_404_NOT_FOUND)

    discord_user_id = str(request.data.get("discord_user_id", "") or "")
    if not discord_user_id:
        return Response({"error": "discord_user_id required"}, status=400)

    try:
        event = Event.objects.select_related(
            "event_repeater",
            "organization",
        ).get(pk=event_pk)
    except Event.DoesNotExist:
        return Response({"error": "Event not found"}, status=404)

    dm_data = build_subscriber_dm_embed(event)
    embed = dm_data["embed"]
    components = dm_data.get("components")
    try:
        outcome = send_dm(
            DMRequest(
                kind=DMKind.TEST_NOTIFICATION,
                idempotency_key=test_notification_key(
                    event_pk=event_pk,
                    discord_id=discord_user_id,
                    request_id=uuid4().hex,
                ),
                discord_user_id=discord_user_id,
                organization_id=event.organization_id,
                subject=(DMSubject.EVENT, event_pk),
                embed=embed,
                components=components,
            )
        )
    except DiscordAuthError:
        return _auth_failed_response()

    if outcome.status in (DMStatus.SENT, DMStatus.SKIPPED_TEST_MODE):
        return Response(
            {
                "success": True,
                "message_id": outcome.message_id or "test-fake-message-id",
                "embed": embed,
                "components": components,
            }
        )
    if outcome.status == "ledger_unavailable":
        return Response(
            {"error": "dm_ledger_unavailable"},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    auth_failure = discord_auth_failure()
    if auth_failure is not None:
        return auth_failure
    return Response(
        {"success": False, "error": "Failed to send DM. User may have DMs disabled."},
        status=500,
    )


@csrf_exempt
@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
def set_org_user_approved_mmr(request: Request, org_pk: int, user_pk: int) -> Response:
    """TEST ONLY: Set the org MMR of (org_pk, user_pk) for one game.

    Body: {"mmr": int, "game_type"?: int (default Dota 2)}
    """
    if not isTestEnvironment(request):
        return Response({"detail": "Not Found"}, status=status.HTTP_404_NOT_FOUND)

    try:
        mmr = int(request.data.get("mmr"))
        game_type = int(request.data.get("game_type", GameType.DOTA2))
    except (TypeError, ValueError):
        return Response(
            {"detail": "mmr and game_type must be integers"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        org_user = OrgUser.objects.get(organization_id=org_pk, user_id=user_pk)
    except OrgUser.DoesNotExist:
        return Response(
            {"detail": f"OrgUser org={org_pk} user={user_pk} not found"},
            status=status.HTTP_404_NOT_FOUND,
        )

    try:
        set_org_mmr(org_user, game_type, mmr, mark_verified=False)
    except OrgMmrError as e:
        return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    return Response(
        {"org_pk": org_pk, "user_pk": user_pk, "mmr": mmr, "game_type": game_type}
    )
