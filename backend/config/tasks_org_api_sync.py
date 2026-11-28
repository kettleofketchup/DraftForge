"""Light Celery tasks for org API connection syncs.

Tasks carry IDs and fences only; Django claims, executes and records each
bounded step behind the internal API.
"""

from typing import Any

from celery import shared_task

from app.internal_client import org_api_sync
from telemetry.logging import get_logger

log = get_logger(__name__)

BUSY_COUNTDOWN_SECONDS = 5
PROMOTION_CHAIN = 20


@shared_task(ignore_result=True)
def org_api_sync_sweep() -> dict[str, object]:
    claimed = org_api_sync.claim()
    if claimed is None or claimed.get("busy"):
        log.warning(
            "org_api_sync_claim_unavailable", system="org", subsystem="api_connections"
        )
        return {"claimed": 0, "promotion_due": False}
    claims = claimed.get("claims") or []
    for item in claims:
        org_api_sync_step.delay(item["id"], item["fence"], kind=item["kind"])
    due = bool(claimed.get("promotion_due"))
    if due:
        org_api_sync_promotion.delay()
    return {"claimed": len(claims), "promotion_due": due}


@shared_task(ignore_result=True)
def org_api_sync_step(run_id: str, fence: str, kind: str = "run") -> dict[str, object]:
    result: dict[str, Any] | None = org_api_sync.step(kind, run_id, fence)
    if result is None:
        return {
            "run_id": run_id,
            "kind": kind,
            "state": "unavailable",
            "continuation": False,
            "error_code": None,
        }
    if result.get("busy"):
        org_api_sync_step.apply_async(
            args=[run_id, fence],
            kwargs={"kind": kind},
            countdown=BUSY_COUNTDOWN_SECONDS,
        )
        return {
            "run_id": run_id,
            "kind": kind,
            "state": "busy",
            "continuation": True,
            "error_code": "busy",
        }
    summary: dict[str, object] = {
        "run_id": run_id,
        "kind": kind,
        "state": result.get("state"),
        "continuation": bool(result.get("continuation")),
        "error_code": result.get("error_code"),
    }
    following = result.get("fence")
    if summary["continuation"] and following:
        org_api_sync_step.apply_async(
            args=[run_id, following],
            kwargs={"kind": kind},
            countdown=(
                BUSY_COUNTDOWN_SECONDS if result.get("error_code") == "org_busy" else 0
            ),
        )
    return summary


@shared_task(ignore_result=True)
def org_api_sync_promotion(remaining: int = PROMOTION_CHAIN) -> dict[str, object]:
    result = org_api_sync.promotion_step()
    if result is None or result.get("busy"):
        return {"state": "unavailable", "continuation": False}
    more = bool(result.get("continuation")) and remaining > 1
    if more:
        org_api_sync_promotion.delay(remaining - 1)
    return {"state": result.get("state"), "continuation": more}


@shared_task(ignore_result=True)
def org_api_sync_cleanup() -> dict[str, object]:
    result = org_api_sync.cleanup()
    return {"deleted": (result or {}).get("deleted", 0)}
