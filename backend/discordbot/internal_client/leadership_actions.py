"""HTTP clients for the internal leadership endpoints (``org/leadership/internal_views.py``)."""

from pydantic import ValidationError

from app.internal_client import transport
from discordbot.schemas import PlannedMessage, ReviewDMPlanBody, ReviewDMPlanResponse
from telemetry.logging import get_logger

log = get_logger(__name__)

_LOG = {"system": "org", "subsystem": "leadership"}


def plan_review_dms(
    event_id: int, snapshot_ids: list[int]
) -> list[PlannedMessage] | None:
    body = ReviewDMPlanBody(event_id=event_id, snapshot_ids=snapshot_ids)
    resp = transport.post("/leadership/review-dms/plan/", body.model_dump(mode="json"))
    if resp is None or resp.status_code != 200:
        log.warning(
            "leadership_review_dm_plan_unavailable",
            **_LOG,
            event_id=event_id,
            http_status_code=None if resp is None else resp.status_code,
        )
        return None
    try:
        return ReviewDMPlanResponse.model_validate(resp.json()).messages
    except (ValueError, ValidationError):
        log.error("leadership_review_dm_plan_bad_response", **_LOG, event_id=event_id)
        return None
