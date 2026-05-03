"""
Test-only endpoints for Discord event lifecycle E2E testing.

- simulate_discord_signup: Drives the full signup handler chain
- verify_discord_messages: Reads back signup/announcement embeds from Discord
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

from common.utils import isTestEnvironment

log = logging.getLogger(__name__)


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
        "unverified_friend_id": data.get("friend_id", ""),
        "positions": data.get("positions", []),
        "rank_status": data.get("rank_status", "active"),
    }
    result = handle_signup_modal_submit(event_pk, discord_user_id, 1, values)
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
def send_test_notification(request, event_pk):
    """TEST ONLY: Send event notification DM to a specific Discord user."""
    if not isTestEnvironment(request):
        return Response({"detail": "Not Found"}, status=status.HTTP_404_NOT_FOUND)

    from discordbot.utils import sync_send_dm
    from events.discord.embeds import build_subscriber_dm_embed
    from events.models import Event

    discord_user_id = request.data.get("discord_user_id", "")
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
    result = sync_send_dm(discord_user_id, embed=embed, components=components)

    if result:
        return Response(
            {
                "success": True,
                "message_id": result.get("id"),
                "embed": embed,
                "components": components,
            }
        )
    return Response(
        {"success": False, "error": "Failed to send DM. User may have DMs disabled."},
        status=500,
    )


@csrf_exempt
@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
def set_org_user_approved_mmr(request, org_pk: int, user_pk: int):
    """TEST ONLY: Set OrgUser.mmr for (org_pk, user_pk) and invalidate cacheops.

    Body: {"mmr": int}
    """
    if not isTestEnvironment(request):
        return Response({"detail": "Not Found"}, status=status.HTTP_404_NOT_FOUND)

    from cacheops import invalidate_obj
    from org.models import OrgUser

    try:
        mmr = int(request.data.get("mmr"))
    except (TypeError, ValueError):
        return Response(
            {"detail": "mmr must be an integer"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        org_user = OrgUser.objects.get(organization_id=org_pk, user_id=user_pk)
    except OrgUser.DoesNotExist:
        return Response(
            {"detail": f"OrgUser org={org_pk} user={user_pk} not found"},
            status=status.HTTP_404_NOT_FOUND,
        )

    org_user.mmr = mmr
    org_user.save(update_fields=["mmr"])
    invalidate_obj(org_user)

    return Response({"org_pk": org_pk, "user_pk": user_pk, "mmr": mmr})
