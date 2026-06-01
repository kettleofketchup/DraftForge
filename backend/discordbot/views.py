"""Discord bot HTTP interaction endpoints."""

import json

from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from telemetry.logging import get_logger

log = get_logger(__name__)


def verify_discord_signature(request) -> bool:
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
def discord_interactions(request):
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


def handle_message_component(data: dict) -> JsonResponse:
    """Handle button/select menu interactions."""
    custom_id = data.get("data", {}).get("custom_id", "")
    user = data.get("member", {}).get("user", {}) or data.get("user", {})
    username = user.get("username", "Unknown")

    log.info(
        "component_interaction_received",
        system="discord",
        subsystem="views",
        custom_id=custom_id,
        discord_username=username,
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
