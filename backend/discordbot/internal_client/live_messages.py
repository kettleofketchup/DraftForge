"""Worker client for claiming and acknowledging one live Discord edit at a time."""

from app.internal_client import transport
from app.internal_client.transport import InternalAPIUnavailable
from discordbot.schemas import LiveEditClaim, LiveEditFinish


def claim_edit(*, discord_user_id: str | None = None) -> LiveEditClaim | None:
    body = {"discord_user_id": discord_user_id} if discord_user_id is not None else {}
    response = transport.post("/discord/live-messages/claim/", body)
    if response is None or response.status_code not in (200, 204):
        raise InternalAPIUnavailable("live edit claim failed")
    if response.status_code == 204:
        return None
    try:
        return LiveEditClaim.model_validate(response.json())
    except ValueError as exc:
        raise InternalAPIUnavailable("invalid live edit claim") from exc


def finish_edit(pk: int, result: LiveEditFinish) -> bool:
    response = transport.post(
        f"/discord/live-messages/{pk}/finish/", result.model_dump(mode="json")
    )
    if response is None or response.status_code not in (204, 409):
        raise InternalAPIUnavailable("live edit acknowledgement failed")
    return response.status_code == 204
