"""Internal API endpoints that wrap events.discord signup handlers.

The Discord bot process must not touch the ORM directly (overlay/page-cache
divergence between containers means writes from the bot are invisible to
Daphne). These endpoints are thin POST wrappers around the existing
``handle_*`` functions in ``events/discord/handlers.py`` so the bot can call
them over HTTP and the backend remains the sole writer.

Each endpoint:
  * authenticates with the InternalServiceAuth token,
  * validates the JSON body via a pydantic request schema
    (``discordbot/schemas.py``),
  * delegates to the canonical handler,
  * returns the handler's dict as JSON (``200`` on success, even when the
    handler signals a logical "error" outcome — those are domain results,
    not HTTP failures).

Do NOT inline business logic here. Edit ``handlers.py`` instead.
"""

from pydantic import ValidationError
from rest_framework import status
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
)
from rest_framework.response import Response

from app.auth import InternalServiceAuth, IsInternalService
from discordbot.schemas import (
    BattleCupSubmitRequest,
    DeclineButtonRequest,
    NotifyButtonRequest,
    PreviousRankSubmitRequest,
    RankMedalSelectRequest,
    RankStatusSelectRequest,
    SavePositionsRequest,
    ScreenshotUploadRequest,
    SignupButtonRequest,
    SignupModalSubmitRequest,
    TentativeButtonRequest,
)
from telemetry.logging import get_logger

log = get_logger(__name__)

_auth = [InternalServiceAuth]
_perm = [IsInternalService]


def _bad_request(exc: ValidationError) -> Response:
    """Render a pydantic ValidationError as a 400 JSON response."""
    return Response(
        {"error": "invalid_request", "detail": exc.errors()},
        status=status.HTTP_400_BAD_REQUEST,
    )


@api_view(["POST"])
@authentication_classes(_auth)
@permission_classes(_perm)
def signup_button(request):
    """Wrap handle_signup_button. Body: event_id, discord_user_id, discord_username?."""
    from events.discord.handlers import handle_signup_button

    try:
        body = SignupButtonRequest.model_validate(request.data)
    except ValidationError as exc:
        return _bad_request(exc)
    result = handle_signup_button(**body.model_dump())
    return Response(result)


@api_view(["POST"])
@authentication_classes(_auth)
@permission_classes(_perm)
def signup_modal_submit(request):
    """Wrap handle_signup_modal_submit. Body: event_id, discord_user_id, game_type, values."""
    from events.discord.handlers import handle_signup_modal_submit

    try:
        body = SignupModalSubmitRequest.model_validate(request.data)
    except ValidationError as exc:
        return _bad_request(exc)
    result = handle_signup_modal_submit(**body.model_dump())
    return Response(result)


@api_view(["POST"])
@authentication_classes(_auth)
@permission_classes(_perm)
def rank_status_select(request):
    """Wrap handle_rank_status_select. Returns {} since the handler returns None."""
    from events.discord.handlers import handle_rank_status_select

    try:
        body = RankStatusSelectRequest.model_validate(request.data)
    except ValidationError as exc:
        return _bad_request(exc)
    handle_rank_status_select(**body.model_dump())
    return Response({})


@api_view(["POST"])
@authentication_classes(_auth)
@permission_classes(_perm)
def rank_medal_select(request):
    """Wrap handle_rank_medal_select. Body: event_id, discord_user_id, medal."""
    from events.discord.handlers import handle_rank_medal_select

    try:
        body = RankMedalSelectRequest.model_validate(request.data)
    except ValidationError as exc:
        return _bad_request(exc)
    result = handle_rank_medal_select(**body.model_dump())
    return Response(result)


@api_view(["POST"])
@authentication_classes(_auth)
@permission_classes(_perm)
def previous_rank_submit(request):
    """Wrap handle_previous_rank_submit. Body: event_id, discord_user_id, medal, date_text."""
    from events.discord.handlers import handle_previous_rank_submit

    try:
        body = PreviousRankSubmitRequest.model_validate(request.data)
    except ValidationError as exc:
        return _bad_request(exc)
    result = handle_previous_rank_submit(**body.model_dump())
    return Response(result)


@api_view(["POST"])
@authentication_classes(_auth)
@permission_classes(_perm)
def battle_cup_submit(request):
    """Wrap handle_battle_cup_submit. Body: event_id, discord_user_id, tier."""
    from events.discord.handlers import handle_battle_cup_submit

    try:
        body = BattleCupSubmitRequest.model_validate(request.data)
    except ValidationError as exc:
        return _bad_request(exc)
    result = handle_battle_cup_submit(**body.model_dump())
    return Response(result)


@api_view(["POST"])
@authentication_classes(_auth)
@permission_classes(_perm)
def screenshot_upload(request):
    """Wrap handle_screenshot_upload. Body: event_id, discord_user_id, screenshot_type, attachment_url."""
    from events.discord.handlers import handle_screenshot_upload

    try:
        body = ScreenshotUploadRequest.model_validate(request.data)
    except ValidationError as exc:
        return _bad_request(exc)
    result = handle_screenshot_upload(**body.model_dump())
    return Response(result)


@api_view(["POST"])
@authentication_classes(_auth)
@permission_classes(_perm)
def notify_button(request):
    """Wrap handle_notify_button. Body: event_id, discord_user_id."""
    from events.discord.handlers import handle_notify_button

    try:
        body = NotifyButtonRequest.model_validate(request.data)
    except ValidationError as exc:
        return _bad_request(exc)
    result = handle_notify_button(**body.model_dump())
    return Response(result)


@api_view(["POST"])
@authentication_classes(_auth)
@permission_classes(_perm)
def decline_button(request):
    """Wrap handle_decline_button. Body: event_id, discord_user_id."""
    from events.discord.handlers import handle_decline_button

    try:
        body = DeclineButtonRequest.model_validate(request.data)
    except ValidationError as exc:
        return _bad_request(exc)
    result = handle_decline_button(**body.model_dump())
    return Response(result)


@api_view(["POST"])
@authentication_classes(_auth)
@permission_classes(_perm)
def tentative_button(request):
    """Wrap handle_tentative_button. Body: event_id, discord_user_id, discord_username?."""
    from events.discord.handlers import handle_tentative_button

    try:
        body = TentativeButtonRequest.model_validate(request.data)
    except ValidationError as exc:
        return _bad_request(exc)
    result = handle_tentative_button(**body.model_dump())
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

    try:
        body = SavePositionsRequest.model_validate(request.data)
    except ValidationError as exc:
        return _bad_request(exc)

    try:
        event = Event.objects.select_related("organization").get(pk=body.event_id)
    except Event.DoesNotExist:
        return Response({"action": "error", "message": "Event not found."})

    org_user, _user = _get_org_user(event, body.discord_user_id)
    if not org_user:
        return Response({"action": "error", "message": "User not found."})

    try:
        apply_signup_input(
            org_user=org_user,
            event=event,
            patch=SignupInputPatch(positions=body.positions),
        )
    except DjangoValidationError as exc:
        msg = exc.messages[0] if hasattr(exc, "messages") else str(exc)
        return Response({"action": "error", "message": msg})

    return Response({"action": "positions_saved", "positions": body.positions})
