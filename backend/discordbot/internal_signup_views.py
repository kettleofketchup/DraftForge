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
    RankFlowStateRequest,
    RankMedalSelectRequest,
    RankStatusSelectRequest,
    SavePositionsRequest,
    ScreenshotUploadRequest,
    SetPositionRequest,
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
    log.info(
        "internal_signup_button_processed",
        system="discord",
        subsystem="dispatch",
        tags=["events", "signup"],
        tags_csv="events,signup",
        event_id=body.event_id,
        discord_user_id=body.discord_user_id,
        action=result.get("action"),
    )
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
    log.info(
        "internal_signup_modal_submit_processed",
        system="discord",
        subsystem="dispatch",
        tags=["events", "signup"],
        tags_csv="events,signup",
        event_id=body.event_id,
        discord_user_id=body.discord_user_id,
        action=result.get("action"),
    )
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
    log.info(
        "internal_rank_status_select_processed",
        system="discord",
        subsystem="dispatch",
        tags=["events", "signup"],
        tags_csv="events,signup",
        event_id=body.event_id,
        discord_user_id=body.discord_user_id,
        action=None,
    )
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
    log.info(
        "internal_rank_medal_select_processed",
        system="discord",
        subsystem="dispatch",
        tags=["events", "signup"],
        tags_csv="events,signup",
        event_id=body.event_id,
        discord_user_id=body.discord_user_id,
        action=result.get("action"),
    )
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
    log.info(
        "internal_previous_rank_submit_processed",
        system="discord",
        subsystem="dispatch",
        tags=["events", "signup"],
        tags_csv="events,signup",
        event_id=body.event_id,
        discord_user_id=body.discord_user_id,
        action=result.get("action"),
    )
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
    log.info(
        "internal_battle_cup_submit_processed",
        system="discord",
        subsystem="dispatch",
        tags=["events", "signup"],
        tags_csv="events,signup",
        event_id=body.event_id,
        discord_user_id=body.discord_user_id,
        action=result.get("action"),
    )
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
    log.info(
        "internal_screenshot_upload_processed",
        system="discord",
        subsystem="dispatch",
        tags=["events", "signup"],
        tags_csv="events,signup",
        event_id=body.event_id,
        discord_user_id=body.discord_user_id,
        action=result.get("action"),
    )
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
    log.info(
        "internal_notify_button_processed",
        system="discord",
        subsystem="dispatch",
        tags=["events", "signup"],
        tags_csv="events,signup",
        event_id=body.event_id,
        discord_user_id=body.discord_user_id,
        action=result.get("action"),
    )
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
    log.info(
        "internal_decline_button_processed",
        system="discord",
        subsystem="dispatch",
        tags=["events", "signup"],
        tags_csv="events,signup",
        event_id=body.event_id,
        discord_user_id=body.discord_user_id,
        action=result.get("action"),
    )
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
    log.info(
        "internal_tentative_button_processed",
        system="discord",
        subsystem="dispatch",
        tags=["events", "signup"],
        tags_csv="events,signup",
        event_id=body.event_id,
        discord_user_id=body.discord_user_id,
        action=result.get("action"),
    )
    return Response(result)


@api_view(["POST"])
@authentication_classes(_auth)
@permission_classes(_perm)
def save_positions(request):
    """Wrap handle_save_positions. Body: event_id, discord_user_id, positions (list[int])."""
    from events.discord.handlers import handle_save_positions

    try:
        body = SavePositionsRequest.model_validate(request.data)
    except ValidationError as exc:
        return _bad_request(exc)
    result = handle_save_positions(**body.model_dump())
    log.info(
        "internal_save_positions_processed",
        system="discord",
        subsystem="dispatch",
        tags=["events", "signup"],
        tags_csv="events,signup",
        event_id=body.event_id,
        discord_user_id=body.discord_user_id,
        positions=body.positions,
        action=result.get("action"),
    )
    return Response(result)


@api_view(["POST"])
@authentication_classes(_auth)
@permission_classes(_perm)
def set_position(request):
    """Wrap handle_set_position. Body: event_id, discord_user_id, position (1..5)."""
    from events.discord.handlers import handle_set_position

    try:
        body = SetPositionRequest.model_validate(request.data)
    except ValidationError as exc:
        return _bad_request(exc)
    result = handle_set_position(**body.model_dump())
    log.info(
        "internal_set_position_processed",
        system="discord",
        subsystem="dispatch",
        tags=["events", "signup"],
        tags_csv="events,signup",
        event_id=body.event_id,
        discord_user_id=body.discord_user_id,
        position=body.position,
        action=result.get("action"),
    )
    return Response(result)


@api_view(["POST"])
@authentication_classes(_auth)
@permission_classes(_perm)
def rank_flow_state(request):
    """Wrap handle_get_rank_flow_state. Body: event_id, discord_user_id.

    Returns rank_status / require_screenshot / min_mmr for the pos_confirm
    flow to render the next RankDetailsView.
    """
    from events.discord.handlers import handle_get_rank_flow_state

    try:
        body = RankFlowStateRequest.model_validate(request.data)
    except ValidationError as exc:
        return _bad_request(exc)
    result = handle_get_rank_flow_state(**body.model_dump())
    log.info(
        "internal_rank_flow_state_processed",
        system="discord",
        subsystem="dispatch",
        tags=["events", "signup"],
        tags_csv="events,signup",
        event_id=body.event_id,
        discord_user_id=body.discord_user_id,
        action=result.get("error") or "ok",
    )
    return Response(result)
