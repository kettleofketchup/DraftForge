"""HTTP wrappers for the Discord bot's signup-flow callbacks.

The bot process must not touch the ORM (overlay-fs / page-cache divergence
between the bot and Daphne containers means writes from the bot are invisible
to the backend). Every callback that used to call ``events.discord.handle_*``
in-process now POSTs here so the backend is the sole writer.

Each function mirrors the handler's keyword signature and returns the
handler's dict (or an empty dict where the handler returns None / on network
failure). Callers must remain dict-result tolerant.
"""

from app.internal_client import _post


def _result(resp, default=None):
    """Best-effort JSON-decode of an internal-API response.

    Returns ``default or {}`` when the request failed at the network layer
    (``_post`` already logged) or when the body isn't JSON. The bot UI code
    keys off ``result["action"]`` / ``result.get("subscribed")`` etc., so a
    safe empty dict keeps the callback's error branch reachable.
    """
    if resp is None or not resp.ok:
        return default if default is not None else {}
    try:
        return resp.json()
    except ValueError:
        return default if default is not None else {}


def signup_button(*, event_id, discord_user_id, discord_username=None):
    payload = {"event_id": event_id, "discord_user_id": discord_user_id}
    if discord_username is not None:
        payload["discord_username"] = discord_username
    return _result(
        _post("/discord/signup-button/", payload),
        default={"action": "error", "message": "Signup service unavailable."},
    )


def signup_modal_submit(*, event_id, discord_user_id, game_type, values):
    return _result(
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
    return _result(
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
    return _result(
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
    return _result(
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
    return _result(
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
    return _result(
        _post(
            "/discord/notify-button/",
            {"event_id": event_id, "discord_user_id": discord_user_id},
        ),
        default={"subscribed": False},
    )


def decline_button(*, event_id, discord_user_id):
    return _result(
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
    return _result(
        _post("/discord/tentative-button/", payload),
        default={"action": "error", "message": "Tentative service unavailable."},
    )


def save_positions(*, event_id, discord_user_id, positions):
    """Persist Dota position picks. ``positions``: list[int]."""
    return _result(
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
