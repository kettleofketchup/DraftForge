"""Discord bot HTTP interaction endpoints."""

import json
from typing import Any

from celery import Task
from django.conf import settings
from django.http import HttpRequest, JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from kombu.exceptions import KombuError

from discordbot import dm_ledger
from discordbot.activity_ids import decode_draft_launch
from discordbot.custom_ids import LEADERSHIP_REVIEW_PREFIX, LeadershipScoreId
from discordbot.internal_client.leadership_actions import SAVE_FAILED
from discordbot.models import DraftActivityChannel
from discordbot.tasks import complete_activity_launch, complete_review_click
from telemetry.logging import get_logger

log = get_logger(__name__)


def verify_discord_signature(request: HttpRequest) -> bool:
    """Verify Discord interaction signature using Ed25519.

    Discord sends:
    - X-Signature-Ed25519: The signature
    - X-Signature-Timestamp: The timestamp
    - Body: The raw request body

    Returns True if signature is valid, False otherwise.
    """
    try:
        from nacl.signing import VerifyKey

        # PyNaCl 1.6+ uses BadSignatureError, older versions use BadSignature
        try:
            from nacl.exceptions import BadSignatureError as BadSignature
        except ImportError:
            from nacl.exceptions import BadSignature
    except ImportError as e:
        log.error("pynacl_missing", system="discord", subsystem="views", error=str(e))
        return False

    public_key = getattr(settings, "DISCORD_PUBLIC_KEY", None)
    if not public_key:
        log.error("discord_public_key_missing", system="discord", subsystem="views")
        return False

    signature = request.headers.get("X-Signature-Ed25519")
    timestamp = request.headers.get("X-Signature-Timestamp")

    if not signature or not timestamp:
        log.warning("signature_headers_missing", system="discord", subsystem="views")
        return False

    try:
        verify_key = VerifyKey(bytes.fromhex(public_key))
        message = timestamp.encode() + request.body
        verify_key.verify(message, bytes.fromhex(signature))
        return True
    except BadSignature:
        log.warning("signature_invalid", system="discord", subsystem="views")
        return False
    except Exception as e:
        log.error(
            "signature_verify_error", system="discord", subsystem="views", error=str(e)
        )
        return False


@csrf_exempt
@require_POST
def discord_interactions(request: HttpRequest) -> JsonResponse:
    """Handle Discord HTTP interactions.

    This endpoint receives interaction webhooks from Discord when configured
    as the Interactions Endpoint URL in the Discord Developer Portal.

    Discord interaction types:
    - Type 1: PING - Discord verifying endpoint, respond with PONG
    - Type 2: APPLICATION_COMMAND - Slash command invoked
    - Type 3: MESSAGE_COMPONENT - Button/select menu clicked
    - Type 4: APPLICATION_COMMAND_AUTOCOMPLETE - Autocomplete request
    - Type 5: MODAL_SUBMIT - Modal form submitted
    """
    # Verify the request is from Discord
    if not verify_discord_signature(request):
        return JsonResponse({"error": "Invalid signature"}, status=401)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    interaction_type = data.get("type")

    # Type 1: PING - Discord is verifying the endpoint
    if interaction_type == 1:
        log.info("ping_received", system="discord", subsystem="views")
        return JsonResponse({"type": 1})  # PONG

    # Type 2: APPLICATION_COMMAND - Slash command
    if interaction_type == 2:
        return handle_application_command(data)

    # Type 3: MESSAGE_COMPONENT - Button/select interaction
    if interaction_type == 3:
        return handle_message_component(data)

    # Type 5: MODAL_SUBMIT
    if interaction_type == 5:
        return handle_modal_submit(data)

    log.warning(
        "interaction_type_unhandled",
        system="discord",
        subsystem="views",
        interaction_type=interaction_type,
    )
    return JsonResponse({"type": 4, "data": {"content": "Unknown interaction type"}})


def handle_application_command(data: dict) -> JsonResponse:
    """Handle slash command interactions."""
    command_name = data.get("data", {}).get("name")
    user = data.get("member", {}).get("user", {}) or data.get("user", {})
    username = user.get("username", "Unknown")

    log.info(
        "slash_command_received",
        system="discord",
        subsystem="views",
        command_name=command_name,
        discord_username=username,
    )

    # Respond with deferred message - actual handling done by gateway bot
    # This is useful for commands that need database access or complex processing
    return JsonResponse(
        {
            "type": 5,  # DEFERRED_CHANNEL_MESSAGE_WITH_SOURCE
        }
    )


ACTIVITY_LAUNCH_TASK_EXPIRES_S = 14 * 60
STALE_COMPONENT_MESSAGE = "❌ This menu is out of date."


def _ephemeral(content: str) -> JsonResponse:
    return JsonResponse({"type": 4, "data": {"flags": 64, "content": content}})


def _enqueue_within_ack(task: Task, *, args: list[Any], argsrepr: str) -> None:
    """Enqueue so a disconnected Redis broker cannot eat Discord's 3s ack window."""
    app = task.app
    transport = dict(app.conf.broker_transport_options or {})
    transport.update(socket_connect_timeout=0.5, socket_timeout=0.5)
    with app.connection_for_write(
        connect_timeout=0.5, transport_options=transport
    ) as connection:
        task.apply_async(
            args=args,
            argsrepr=argsrepr,
            # Interaction tokens live 15 minutes; a busy or
            # restarting worker must still answer within that window.
            expires=ACTIVITY_LAUNCH_TASK_EXPIRES_S,
            retry=False,
            connection=connection,
        )


def _handle_review_click(data: dict, custom_id: str, user: dict) -> JsonResponse:
    try:
        score = LeadershipScoreId.decode(custom_id)
    except ValueError:
        return _ephemeral(STALE_COMPONENT_MESSAGE)
    message = data.get("message") or {}
    payload = {
        "application_id": str(data.get("application_id", "")),
        "interaction_token": str(data.get("token", "")),
        "click": {
            "discord_user_id": str(user.get("id", "")),
            "discord_message_id": str(message.get("id", "")),
            "discord_channel_id": str(
                data.get("channel_id") or message.get("channel_id") or ""
            ),
            "interaction_id": str(data.get("id", "")),
            "snapshot_id": score.snapshot_id,
            "trait_id": score.trait_id,
            "score": score.score,
        },
    }
    try:
        _enqueue_within_ack(
            complete_review_click,
            args=[payload],
            argsrepr="[redacted leadership review click]",
        )
    except (KombuError, OSError):
        return _ephemeral(SAVE_FAILED)
    return JsonResponse({"type": 6})


def _record_dm_click(data: dict, custom_id: str, user: dict) -> None:
    if data.get("guild_id") or custom_id.startswith(LEADERSHIP_REVIEW_PREFIX):
        return
    message_id = str((data.get("message") or {}).get("id") or "")
    discord_user_id = str(user.get("id") or "")
    if not message_id or not discord_user_id:
        return
    try:
        dm_ledger.record_click(
            discord_message_id=message_id,
            discord_user_id=discord_user_id,
            now=timezone.now(),
        )
    except Exception:
        log.warning(
            "dm_click_record_failed", system="discord", subsystem="dm", exc_info=True
        )


def handle_message_component(data: dict) -> JsonResponse:
    """Handle button/select menu interactions."""
    custom_id = data.get("data", {}).get("custom_id", "")
    user = data.get("member", {}).get("user", {}) or data.get("user", {})
    username = user.get("username", "Unknown")
    _record_dm_click(data, custom_id, user)

    log.info(
        "component_interaction_received",
        system="discord",
        subsystem="views",
        custom_id=custom_id,
        discord_username=username,
    )

    if LeadershipScoreId.matches(custom_id):
        return _handle_review_click(data, custom_id, user)

    if custom_id.startswith("draft_activity:") and custom_id != "draft_activity:launch":
        draft = decode_draft_launch(custom_id)
        if draft is None:
            return JsonResponse(
                {
                    "type": 4,
                    "data": {
                        "flags": 64,
                        "content": "This draft notification is out of date.",
                    },
                }
            )
        if not getattr(settings, "DISCORD_ACTIVITY_ENABLED", False):
            return JsonResponse(
                {
                    "type": 4,
                    "data": {
                        "flags": 64,
                        "content": "Discord Activities are disabled. Open the draft in your browser.",
                    },
                }
            )
        # Defer immediately: REST voice lookup and invite creation can exceed
        # Discord's three-second deadline. Never log the interaction token.

        try:
            _enqueue_within_ack(
                complete_activity_launch,
                args=[
                    str(data.get("application_id", "")),
                    str(data.get("token", "")),
                    str(user.get("id", "")),
                    draft[0],
                    draft[1],
                ],
                argsrepr="[redacted Discord Activity interaction]",
            )
        except (KombuError, OSError):
            return JsonResponse(
                {
                    "type": 4,
                    "data": {
                        "flags": 64,
                        "content": "Could not prepare the Activity. Please try again shortly.",
                    },
                }
            )
        return JsonResponse({"type": 5, "data": {"flags": 64}})

    if custom_id == "draft_activity:launch" and getattr(
        settings, "DISCORD_ACTIVITY_ENABLED", False
    ):
        if DraftActivityChannel.objects.filter(
            guild_id=data.get("guild_id", ""), channel_id=data.get("channel_id", "")
        ).exists():
            return JsonResponse({"type": 12})
        return JsonResponse(
            {
                "type": 4,
                "data": {
                    "flags": 64,
                    "content": "Launch this button from its configured server voice channel, or use your draft notification.",
                },
            }
        )

    # Acknowledge the interaction
    return JsonResponse(
        {
            "type": 6,  # DEFERRED_UPDATE_MESSAGE
        }
    )


def handle_modal_submit(data: dict) -> JsonResponse:
    """Handle modal form submissions."""
    custom_id = data.get("data", {}).get("custom_id", "")
    user = data.get("member", {}).get("user", {}) or data.get("user", {})
    username = user.get("username", "Unknown")

    log.info(
        "modal_submit_received",
        system="discord",
        subsystem="views",
        custom_id=custom_id,
        discord_username=username,
    )

    return JsonResponse(
        {
            "type": 6,  # DEFERRED_UPDATE_MESSAGE
        }
    )
