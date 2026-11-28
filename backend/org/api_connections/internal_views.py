import threading
from collections.abc import Callable
from uuid import UUID

from django.utils import timezone
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
)
from rest_framework.request import Request
from rest_framework.response import Response

from app.auth import InternalServiceAuth, IsInternalService
from org.api_connections.orchestration import (
    claim_work,
    promotion_due,
    purge_expired_runs,
    step_delivery,
    step_promotion,
    step_run,
)
from org.api_connections.types import StepResult

MAX_CLAIMS = 50
STEP_CONCURRENCY = 4
STEP_SLOTS = threading.BoundedSemaphore(STEP_CONCURRENCY)


def _code(code: str, status: int) -> Response:
    return Response({"code": code}, status=status)


def _result(result: StepResult) -> Response:
    if result.error_code == "not_found":
        return _code("not_found", 404)
    return Response(
        {
            "state": result.state,
            "continuation": result.continuation,
            "error_code": result.error_code,
            "fence": str(result.fence) if result.fence else None,
        }
    )


def _bounded(step: Callable[[], StepResult]) -> Response:
    if not STEP_SLOTS.acquire(blocking=False):
        return _code("busy", 429)
    try:
        return _result(step())
    finally:
        STEP_SLOTS.release()


def _fence(request: Request) -> UUID | None:
    if type(request.data) is not dict or set(request.data) != {"fence"}:
        return None
    try:
        return UUID(str(request.data["fence"]))
    except ValueError:
        return None


@api_view(["POST"])
@authentication_classes([InternalServiceAuth])
@permission_classes([IsInternalService])
def claim(request: Request) -> Response:
    body = request.data
    if type(body) is not dict or set(body) - {"limit"}:
        return _code("invalid_request", 400)
    limit = body.get("limit", 20)
    if type(limit) is not int or not 1 <= limit <= MAX_CLAIMS:
        return _code("invalid_request", 400)
    now = timezone.now()
    claims = claim_work(now=now, limit=limit)
    return Response(
        {
            "claims": [
                {"kind": item.kind, "id": str(item.run_id), "fence": str(item.fence)}
                for item in claims
            ],
            "promotion_due": promotion_due(now=now),
        }
    )


@api_view(["POST"])
@authentication_classes([InternalServiceAuth])
@permission_classes([IsInternalService])
def run_step(request: Request, run_id: UUID) -> Response:
    fence = _fence(request)
    if fence is None:
        return _code("invalid_request", 400)
    return _bounded(lambda: step_run(run_id, fence=fence))


@api_view(["POST"])
@authentication_classes([InternalServiceAuth])
@permission_classes([IsInternalService])
def delivery_step(request: Request, delivery_id: UUID) -> Response:
    fence = _fence(request)
    if fence is None:
        return _code("invalid_request", 400)
    return _bounded(lambda: step_delivery(delivery_id, fence=fence))


@api_view(["POST"])
@authentication_classes([InternalServiceAuth])
@permission_classes([IsInternalService])
def promotion_step(request: Request) -> Response:
    if type(request.data) is not dict or request.data:
        return _code("invalid_request", 400)
    return _bounded(step_promotion)


@api_view(["POST"])
@authentication_classes([InternalServiceAuth])
@permission_classes([IsInternalService])
def cleanup(request: Request) -> Response:
    if type(request.data) is not dict or request.data:
        return _code("invalid_request", 400)
    return Response({"deleted": purge_expired_runs(now=timezone.now())})
