"""HTTP wrappers for the Discord bot's signup-flow callbacks.

The bot process must not touch the ORM (overlay-fs / page-cache divergence
between the bot and Daphne containers means writes from the bot are invisible
to the backend). Every callback that used to call ``events.discord.handle_*``
in-process now POSTs here so the backend is the sole writer.

Each function mirrors the handler's keyword signature and returns the
handler's dict (or an empty dict where the handler returns None / on network
failure). Callers must remain dict-result tolerant.

Responses are validated with ``SignupActionResponse`` — a single pydantic
envelope that covers every action variant — and re-emitted as a plain dict so
existing consumers (which key off ``result["action"]``, ``result.get("subscribed")``,
etc.) are unaffected.
"""

from app.internal_client import _post
from discordbot.schemas import SignupActionResponse


def _validated(resp, default):
    """Coerce an internal-API response through ``SignupActionResponse``.

    Returns ``default`` (a dict) when the HTTP layer failed or the body isn't
    JSON. On success the validated payload is serialised back to a plain dict
    so callers see no behavioural change.
    """
    if resp is None or not resp.ok:
        return default
    try:
        payload = resp.json()
    except ValueError:
        return default
    return SignupActionResponse.model_validate(payload).model_dump()


def signup_button(*, event_id, discord_user_id, discord_username=None):
    payload = {"event_id": event_id, "discord_user_id": discord_user_id}
    if discord_username is not None:
        payload["discord_username"] = discord_username
    return _validated(
        _post("/discord/signup-button/", payload),
        default={"action": "error", "message": "Signup service unavailable."},
    )


def signup_modal_submit(*, event_id, discord_user_id, game_type, values):
    return _validated(
        _post(
            "/discord/signup-modal-submit/",
            {
                "event_id": event_id,
                "discord_user_id": discord_user_id,
                "game_type": game_type,
                "values": values or {},
            },
        ),
        default={"action": "error", "message": "Signup service unavailable."},
    )


def rank_status_select(*, event_id, discord_user_id, rank_status):
    """Original handler returns None — preserve that contract."""
    _post(
        "/discord/rank-status-select/",
        {
            "event_id": event_id,
            "discord_user_id": discord_user_id,
            "rank_status": rank_status,
        },
    )
    return None


def rank_medal_select(*, event_id, discord_user_id, medal):
    return _validated(
        _post(
            "/discord/rank-medal-select/",
            {
                "event_id": event_id,
                "discord_user_id": discord_user_id,
                "medal": medal,
            },
        ),
        default={"action": "error", "message": "Signup service unavailable."},
    )


def previous_rank_submit(*, event_id, discord_user_id, medal, date_text=""):
    return _validated(
        _post(
            "/discord/previous-rank-submit/",
            {
                "event_id": event_id,
                "discord_user_id": discord_user_id,
                "medal": medal,
                "date_text": date_text or "",
            },
        ),
        default={"action": "error", "message": "Signup service unavailable."},
    )


def battle_cup_submit(*, event_id, discord_user_id, tier):
    return _validated(
        _post(
            "/discord/battle-cup-submit/",
            {
                "event_id": event_id,
                "discord_user_id": discord_user_id,
                "tier": tier,
            },
        ),
        default={"action": "error", "message": "Signup service unavailable."},
    )


def screenshot_upload(*, event_id, discord_user_id, screenshot_type, attachment_url):
    return _validated(
        _post(
            "/discord/screenshot-upload/",
            {
                "event_id": event_id,
                "discord_user_id": discord_user_id,
                "screenshot_type": screenshot_type,
                "attachment_url": attachment_url or "",
            },
        ),
        default={"success": False, "message": "Upload service unavailable."},
    )


def notify_button(*, event_id, discord_user_id):
    return _validated(
        _post(
            "/discord/notify-button/",
            {"event_id": event_id, "discord_user_id": discord_user_id},
        ),
        default={"subscribed": False},
    )


def decline_button(*, event_id, discord_user_id):
    return _validated(
        _post(
            "/discord/decline-button/",
            {"event_id": event_id, "discord_user_id": discord_user_id},
        ),
        default={"action": "error", "message": "Decline service unavailable."},
    )


def tentative_button(*, event_id, discord_user_id, discord_username=None):
    payload = {"event_id": event_id, "discord_user_id": discord_user_id}
    if discord_username is not None:
        payload["discord_username"] = discord_username
    return _validated(
        _post("/discord/tentative-button/", payload),
        default={"action": "error", "message": "Tentative service unavailable."},
    )


def save_positions(*, event_id, discord_user_id, positions):
    """Persist Dota position picks. ``positions``: list[int]."""
    return _validated(
        _post(
            "/discord/save-positions/",
            {
                "event_id": event_id,
                "discord_user_id": discord_user_id,
                "positions": list(positions or []),
            },
        ),
        default={"action": "error", "message": "Position service unavailable."},
    )


def set_position(*, event_id, discord_user_id, position):
    """Set a single pos_N=True on the user's Dota profile (legacy per-click flow)."""
    return _validated(
        _post(
            "/discord/set-position/",
            {
                "event_id": event_id,
                "discord_user_id": discord_user_id,
                "position": int(position),
            },
        ),
        default={"action": "error", "message": "Position service unavailable."},
    )


def get_rank_flow_state(*, event_id, discord_user_id):
    """Fetch rank_status / require_screenshot / min_mmr for the pos_confirm view.

    Validated against ``RankFlowStateResponse`` (separate from
    ``SignupActionResponse`` — this endpoint returns rank state, not an
    action). Returns a plain dict so the bot can branch on ``state["error"]``.
    """
    from discordbot.schemas import RankFlowStateResponse

    resp = _post(
        "/discord/rank-flow-state/",
        {"event_id": event_id, "discord_user_id": discord_user_id},
    )
    if resp is None or not resp.ok:
        return {"error": "internal_api_unreachable", "message": "Could not fetch state."}
    try:
        payload = resp.json()
    except ValueError:
        return {"error": "internal_api_unreachable", "message": "Could not fetch state."}
    return RankFlowStateResponse.model_validate(payload).model_dump()
