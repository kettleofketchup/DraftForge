"""Internal API endpoints that wrap events.discord signup handlers.

The Discord bot process must not touch the ORM directly (overlay/page-cache
divergence between containers means writes from the bot are invisible to
Daphne). These endpoints are thin POST wrappers around the existing
``handle_*`` functions in ``events/discord/handlers.py`` so the bot can call
them over HTTP and the backend remains the sole writer.

Each endpoint:
  * authenticates with the InternalServiceAuth token,
  * validates required JSON body fields,
  * delegates to the canonical handler,
  * returns the handler's dict as JSON (``200`` on success, even when the
    handler signals a logical "error" outcome — those are domain results,
    not HTTP failures).

Do NOT inline business logic here. Edit ``handlers.py`` instead.
"""

from rest_framework import status
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
)
from rest_framework.response import Response

from app.auth import InternalServiceAuth, IsInternalService
from telemetry.logging import get_logger

log = get_logger(__name__)

_auth = [InternalServiceAuth]
_perm = [IsInternalService]


def _validate_required(data, fields):
    """Return 400 Response if required fields are missing, else None."""
    missing = [f for f in fields if f not in data or data[f] is None]
    if missing:
        return Response(
            {"error": f"Missing required fields: {missing}"},
            status=status.HTTP_400_BAD_REQUEST,
        )
    return None


@api_view(["POST"])
@authentication_classes(_auth)
@permission_classes(_perm)
def signup_button(request):
    """Wrap handle_signup_button. Body: event_id, discord_user_id, discord_username?."""
    from events.discord.handlers import handle_signup_button

    err = _validate_required(request.data, ["event_id", "discord_user_id"])
    if err:
        return err
    result = handle_signup_button(
        event_id=int(request.data["event_id"]),
        discord_user_id=request.data["discord_user_id"],
        discord_username=request.data.get("discord_username"),
    )
    return Response(result)


@api_view(["POST"])
@authentication_classes(_auth)
@permission_classes(_perm)
def signup_modal_submit(request):
    """Wrap handle_signup_modal_submit. Body: event_id, discord_user_id, game_type, values."""
    from events.discord.handlers import handle_signup_modal_submit

    err = _validate_required(
        request.data, ["event_id", "discord_user_id", "game_type", "values"]
    )
    if err:
        return err
    result = handle_signup_modal_submit(
        event_id=int(request.data["event_id"]),
        discord_user_id=request.data["discord_user_id"],
        game_type=request.data["game_type"],
        values=request.data["values"] or {},
    )
    return Response(result)


@api_view(["POST"])
@authentication_classes(_auth)
@permission_classes(_perm)
def rank_status_select(request):
    """Wrap handle_rank_status_select. Returns {} since the handler returns None."""
    from events.discord.handlers import handle_rank_status_select

    err = _validate_required(
        request.data, ["event_id", "discord_user_id", "rank_status"]
    )
    if err:
        return err
    handle_rank_status_select(
        event_id=int(request.data["event_id"]),
        discord_user_id=request.data["discord_user_id"],
        rank_status=request.data["rank_status"],
    )
    return Response({})


@api_view(["POST"])
@authentication_classes(_auth)
@permission_classes(_perm)
def rank_medal_select(request):
    """Wrap handle_rank_medal_select. Body: event_id, discord_user_id, medal."""
    from events.discord.handlers import handle_rank_medal_select

    err = _validate_required(request.data, ["event_id", "discord_user_id", "medal"])
    if err:
        return err
    result = handle_rank_medal_select(
        event_id=int(request.data["event_id"]),
        discord_user_id=request.data["discord_user_id"],
        medal=request.data["medal"],
    )
    return Response(result)


@api_view(["POST"])
@authentication_classes(_auth)
@permission_classes(_perm)
def previous_rank_submit(request):
    """Wrap handle_previous_rank_submit. Body: event_id, discord_user_id, medal, date_text."""
    from events.discord.handlers import handle_previous_rank_submit

    err = _validate_required(request.data, ["event_id", "discord_user_id", "medal"])
    if err:
        return err
    result = handle_previous_rank_submit(
        event_id=int(request.data["event_id"]),
        discord_user_id=request.data["discord_user_id"],
        medal=request.data["medal"],
        date_text=request.data.get("date_text", ""),
    )
    return Response(result)


@api_view(["POST"])
@authentication_classes(_auth)
@permission_classes(_perm)
def battle_cup_submit(request):
    """Wrap handle_battle_cup_submit. Body: event_id, discord_user_id, tier."""
    from events.discord.handlers import handle_battle_cup_submit

    err = _validate_required(request.data, ["event_id", "discord_user_id", "tier"])
    if err:
        return err
    result = handle_battle_cup_submit(
        event_id=int(request.data["event_id"]),
        discord_user_id=request.data["discord_user_id"],
        tier=request.data["tier"],
    )
    return Response(result)


@api_view(["POST"])
@authentication_classes(_auth)
@permission_classes(_perm)
def screenshot_upload(request):
    """Wrap handle_screenshot_upload. Body: event_id, discord_user_id, screenshot_type, attachment_url."""
    from events.discord.handlers import handle_screenshot_upload

    err = _validate_required(
        request.data,
        ["event_id", "discord_user_id", "screenshot_type", "attachment_url"],
    )
    if err:
        return err
    result = handle_screenshot_upload(
        event_id=int(request.data["event_id"]),
        discord_user_id=request.data["discord_user_id"],
        screenshot_type=request.data["screenshot_type"],
        attachment_url=request.data["attachment_url"],
    )
    return Response(result)


@api_view(["POST"])
@authentication_classes(_auth)
@permission_classes(_perm)
def notify_button(request):
    """Wrap handle_notify_button. Body: event_id, discord_user_id."""
    from events.discord.handlers import handle_notify_button

    err = _validate_required(request.data, ["event_id", "discord_user_id"])
    if err:
        return err
    result = handle_notify_button(
        event_id=int(request.data["event_id"]),
        discord_user_id=request.data["discord_user_id"],
    )
    return Response(result)


@api_view(["POST"])
@authentication_classes(_auth)
@permission_classes(_perm)
def decline_button(request):
    """Wrap handle_decline_button. Body: event_id, discord_user_id."""
    from events.discord.handlers import handle_decline_button

    err = _validate_required(request.data, ["event_id", "discord_user_id"])
    if err:
        return err
    result = handle_decline_button(
        event_id=int(request.data["event_id"]),
        discord_user_id=request.data["discord_user_id"],
    )
    return Response(result)


@api_view(["POST"])
@authentication_classes(_auth)
@permission_classes(_perm)
def tentative_button(request):
    """Wrap handle_tentative_button. Body: event_id, discord_user_id, discord_username?."""
    from events.discord.handlers import handle_tentative_button

    err = _validate_required(request.data, ["event_id", "discord_user_id"])
    if err:
        return err
    result = handle_tentative_button(
        event_id=int(request.data["event_id"]),
        discord_user_id=request.data["discord_user_id"],
        discord_username=request.data.get("discord_username"),
    )
    return Response(result)


@api_view(["POST"])
@authentication_classes(_auth)
@permission_classes(_perm)
def save_positions(request):
    """Persist Dota positions chosen via PositionConfirmButton.

    Mirrors the ORM block previously inlined in components.py: looks up the
    OrgUser for (event, discord_user_id) and pushes ``positions`` through
    ``apply_signup_input`` so the same validation/cache-invalidation runs.

    Body: event_id, discord_user_id, positions (list[int]).
    """
    from django.core.exceptions import ValidationError as DjangoValidationError

    from events.discord.handlers import _get_org_user
    from events.models import Event
    from events.schemas import SignupInputPatch
    from events.services import apply_signup_input

    err = _validate_required(
        request.data, ["event_id", "discord_user_id", "positions"]
    )
    if err:
        return err

    try:
        event = Event.objects.select_related("organization").get(
            pk=int(request.data["event_id"])
        )
    except Event.DoesNotExist:
        return Response({"action": "error", "message": "Event not found."})

    org_user, _user = _get_org_user(event, request.data["discord_user_id"])
    if not org_user:
        return Response({"action": "error", "message": "User not found."})

    try:
        positions_int = [int(v) for v in request.data["positions"]]
    except (TypeError, ValueError):
        return Response({"action": "error", "message": "Invalid positions."})

    try:
        apply_signup_input(
            org_user=org_user,
            event=event,
            patch=SignupInputPatch(positions=positions_int),
        )
    except DjangoValidationError as exc:
        msg = exc.messages[0] if hasattr(exc, "messages") else str(exc)
        return Response({"action": "error", "message": msg})

    return Response({"action": "positions_saved", "positions": positions_int})
