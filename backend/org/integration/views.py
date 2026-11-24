"""Integration v1 routes for the SFG event-promotion sync.

Each view authorizes through ``gate_token_request`` with its operation
before reading anything else, so wrong-org, missing grant, feature, owner
role and budget checks run first on every request, retries included.
"""

from __future__ import annotations

from collections.abc import Iterable

from django.shortcuts import get_object_or_404
from rest_framework.request import Request
from rest_framework.response import Response

from events.models import Event
from org.api_tokens.auth import gate_token_request
from org.api_tokens.operations import Operation
from org.integration.base import IntegrationAPIView
from org.integration.errors import invalid
from org.integration.parsers import parse_limit
from org.integration.subjects import list_event_recipients
from telemetry.logging import get_logger

log = get_logger(__name__)


def query_params(request: Request, allowed: Iterable[str]) -> dict[str, str]:
    """Single-valued query parameters, refusing unknown or repeated names."""
    names = set(allowed)
    params: dict[str, str] = {}
    for name in request.query_params:
        if name not in names:
            raise invalid("query", "has an unknown parameter")
        values = request.query_params.getlist(name)
        if len(values) != 1:
            raise invalid(name, "must be given once")
        params[name] = values[0]
    return params


class EventRecipientsView(IntegrationAPIView):
    """GET one page of an event's authorized promotion subjects."""

    def get(self, request: Request, org_id: int, event_id: int) -> Response:
        org = gate_token_request(request, org_id, operation=Operation.PROMOTION_READ)
        params = query_params(request, ("limit", "cursor"))
        limit = parse_limit(params.get("limit"))
        event = get_object_or_404(
            Event.objects.nocache(), pk=event_id, organization=org
        )
        page = list_event_recipients(
            org, event, limit=limit, cursor=params.get("cursor")
        )
        log.info(
            "integration_recipients_listed",
            system="org",
            subsystem="integration",
            org_id=org.pk,
            event_id=event.pk,
            token_id=request.auth.pk,
            count=len(page["recipients"]),
            continued="cursor" in params,
            has_more=page["next_cursor"] is not None,
        )
        return Response(page)
