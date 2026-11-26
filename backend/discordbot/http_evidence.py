from __future__ import annotations

from typing import Any

import requests

from .delivery_types import DeliveryFailure, FailureCategory, FailurePhase


def response_json(response: requests.Response | None) -> Any:
    if response is None:
        return None
    try:
        return response.json()
    except ValueError:
        return None


def discord_error_code(response: requests.Response | None) -> int | None:
    body = response_json(response)
    if not isinstance(body, dict):
        return None
    code = body.get("code")
    if isinstance(code, int) and not isinstance(code, bool):
        return code
    return None


def failure_from_response(
    response: requests.Response | None, phase: FailurePhase
) -> DeliveryFailure:
    if response is None:
        return DeliveryFailure(phase, FailureCategory.TRANSPORT)
    status = response.status_code
    if status == 401:
        category = FailureCategory.AUTH
    elif status == 429:
        category = FailureCategory.RATE_LIMITED
    else:
        category = FailureCategory.HTTP_ERROR
    return DeliveryFailure(phase, category, status, discord_error_code(response))


def failure_from_exception(exc: BaseException, phase: FailurePhase) -> DeliveryFailure:
    return failure_from_response(getattr(exc, "response", None), phase)
