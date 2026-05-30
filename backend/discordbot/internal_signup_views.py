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
from rest_framework.request import Request
from rest_framework.response import Response

from app.auth import InternalServiceAuth, IsInternalService
from discordbot.bot_handlers import (
    check_site_admin,
    create_legacy_event,
    remove_legacy_rsvp,
    set_legacy_rsvp,
)
from discordbot.schemas import (
    BattleCupSubmitRequest,
    CheckSiteAdminRequest,
    DeclineButtonRequest,
    LegacyEventCreateRequest,
    LegacyRsvpRemoveRequest,
    LegacyRsvpSetRequest,
    NotifyButtonRequest,
    PreviousRankSubmitRequest,
    RankFlowStateRequest,
    RankMedalSelectRequest,
    RankStatusSelectRequest,
    ReactionCancelRequest,
    ReactionSignupRequest,
    SavePositionsRequest,
    ScreenshotUploadRequest,
    SetPositionRequest,
    SignupButtonRequest,
    SignupModalSubmitRequest,
    TentativeButtonRequest,
)
from events.discord.handlers import (
    handle_battle_cup_submit,
    handle_decline_button,
    handle_get_rank_flow_state,
    handle_notify_button,
    handle_previous_rank_submit,
    handle_rank_medal_select,
    handle_rank_status_select,
    handle_save_positions,
    handle_screenshot_upload,
    handle_set_position,
    handle_signup_button,
    handle_signup_modal_submit,
    handle_tentative_button,
)
from events.discord.reactions import handle_reaction_cancel, handle_reaction_signup
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
def signup_button(request: Request) -> Response:
    """Wrap handle_signup_button. Body: event_id, discord_user_id, discord_username?."""
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
def signup_modal_submit(request: Request) -> Response:
    """Wrap handle_signup_modal_submit. Body: event_id, discord_user_id, game_type, values."""
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
def rank_status_select(request: Request) -> Response:
    """Wrap handle_rank_status_select. Returns {} since the handler returns None."""
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
def rank_medal_select(request: Request) -> Response:
    """Wrap handle_rank_medal_select. Body: event_id, discord_user_id, medal."""
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
def previous_rank_submit(request: Request) -> Response:
    """Wrap handle_previous_rank_submit. Body: event_id, discord_user_id, medal, date_text."""
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
def battle_cup_submit(request: Request) -> Response:
    """Wrap handle_battle_cup_submit. Body: event_id, discord_user_id, tier."""
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
def screenshot_upload(request: Request) -> Response:
    """Wrap handle_screenshot_upload. Body: event_id, discord_user_id, screenshot_type, attachment_url."""
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
def notify_button(request: Request) -> Response:
    """Wrap handle_notify_button. Body: event_id, discord_user_id."""
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
def decline_button(request: Request) -> Response:
    """Wrap handle_decline_button. Body: event_id, discord_user_id."""
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
def tentative_button(request: Request) -> Response:
    """Wrap handle_tentative_button. Body: event_id, discord_user_id, discord_username?."""
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
def save_positions(request: Request) -> Response:
    """Wrap handle_save_positions. Body: event_id, discord_user_id, positions (list[int])."""
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
def set_position(request: Request) -> Response:
    """Wrap handle_set_position. Body: event_id, discord_user_id, position (1..5)."""
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
def rank_flow_state(request: Request) -> Response:
    """Wrap handle_get_rank_flow_state. Body: event_id, discord_user_id.

    Returns rank_status / require_screenshot / min_mmr for the pos_confirm
    flow to render the next RankDetailsView.
    """
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


# ---------------------------------------------------------------------------
# Bot-control endpoints: /event admin check, reaction signups/cancels, legacy
# ScheduledEvent RSVPs, and /event slash-command create. These migrate the
# remaining ORM call surfaces in ``discordbot/bot.py`` off the bot process.
# ---------------------------------------------------------------------------


@api_view(["POST"])
@authentication_classes(_auth)
@permission_classes(_perm)
def check_site_admin_view(request: Request) -> Response:
    """Resolve a Discord ID to {is_admin, is_linked} for the /event check."""
    try:
        body = CheckSiteAdminRequest.model_validate(request.data)
    except ValidationError as exc:
        return _bad_request(exc)
    result = check_site_admin(**body.model_dump())
    log.info(
        "internal_check_site_admin_processed",
        system="discord",
        subsystem="dispatch",
        tags=["bot", "admin"],
        tags_csv="bot,admin",
        discord_user_id=body.discord_user_id,
        is_linked=result.get("is_linked"),
        is_admin=result.get("is_admin"),
    )
    return Response(result)


@api_view(["POST"])
@authentication_classes(_auth)
@permission_classes(_perm)
def reaction_signup_view(request: Request) -> Response:
    """Wrap events.discord.reactions.handle_reaction_signup over HTTP."""
    try:
        body = ReactionSignupRequest.model_validate(request.data)
    except ValidationError as exc:
        return _bad_request(exc)
    success, detail = handle_reaction_signup(
        body.discord_message_id, body.discord_user_id
    )
    log.info(
        "internal_reaction_signup_processed",
        system="discord",
        subsystem="dispatch",
        tags=["events", "reaction"],
        tags_csv="events,reaction",
        discord_message_id=body.discord_message_id,
        discord_user_id=body.discord_user_id,
        success=success,
        detail=detail,
    )
    return Response({"success": bool(success), "detail": detail or ""})


@api_view(["POST"])
@authentication_classes(_auth)
@permission_classes(_perm)
def reaction_cancel_view(request: Request) -> Response:
    """Wrap events.discord.reactions.handle_reaction_cancel over HTTP."""
    try:
        body = ReactionCancelRequest.model_validate(request.data)
    except ValidationError as exc:
        return _bad_request(exc)
    success, detail = handle_reaction_cancel(
        body.discord_message_id, body.discord_user_id
    )
    log.info(
        "internal_reaction_cancel_processed",
        system="discord",
        subsystem="dispatch",
        tags=["events", "reaction"],
        tags_csv="events,reaction",
        discord_message_id=body.discord_message_id,
        discord_user_id=body.discord_user_id,
        success=success,
        detail=detail,
    )
    return Response({"success": bool(success), "detail": detail or ""})


@api_view(["POST"])
@authentication_classes(_auth)
@permission_classes(_perm)
def legacy_rsvp_set_view(request: Request) -> Response:
    """Create/update a legacy ScheduledEvent RSVP from a reaction emoji."""
    try:
        body = LegacyRsvpSetRequest.model_validate(request.data)
    except ValidationError as exc:
        return _bad_request(exc)
    result = set_legacy_rsvp(**body.model_dump())
    log.info(
        "internal_legacy_rsvp_set_processed",
        system="discord",
        subsystem="dispatch",
        tags=["events", "rsvp"],
        tags_csv="events,rsvp",
        discord_message_id=body.discord_message_id,
        discord_user_id=body.discord_user_id,
        status=body.status,
        success=result.get("success"),
        error=result.get("error"),
    )
    return Response(result)


@api_view(["POST"])
@authentication_classes(_auth)
@permission_classes(_perm)
def legacy_rsvp_remove_view(request: Request) -> Response:
    """Remove a legacy ScheduledEvent RSVP when the reaction is removed."""
    try:
        body = LegacyRsvpRemoveRequest.model_validate(request.data)
    except ValidationError as exc:
        return _bad_request(exc)
    result = remove_legacy_rsvp(**body.model_dump())
    log.info(
        "internal_legacy_rsvp_remove_processed",
        system="discord",
        subsystem="dispatch",
        tags=["events", "rsvp"],
        tags_csv="events,rsvp",
        discord_message_id=body.discord_message_id,
        discord_user_id=body.discord_user_id,
        success=result.get("success"),
        error=result.get("error"),
    )
    return Response(result)


@api_view(["POST"])
@authentication_classes(_auth)
@permission_classes(_perm)
def legacy_event_create_view(request: Request) -> Response:
    """Create a one-shot EventTemplate + ScheduledEvent for /event."""
    try:
        body = LegacyEventCreateRequest.model_validate(request.data)
    except ValidationError as exc:
        return _bad_request(exc)
    result = create_legacy_event(**body.model_dump())
    log.info(
        "internal_legacy_event_create_processed",
        system="discord",
        subsystem="dispatch",
        tags=["events", "admin"],
        tags_csv="events,admin",
        name=body.name,
        channel_id=body.channel_id,
        event_id=result.get("event_id"),
    )
    return Response(result)
