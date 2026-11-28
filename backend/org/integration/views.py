"""Integration v1 routes for the event-promotion contact sync.

Each view authorizes through ``gate_token_request`` with its operation
before reading anything else, so wrong-org, missing grant, feature, owner
role and budget checks run first on every request, retries included.
"""

from __future__ import annotations

from collections.abc import Iterable

from rest_framework.request import Request
from rest_framework.response import Response

from common.strict_json import parse_canonical_id
from org.api_tokens.auth import gate_token_request
from org.api_tokens.operations import Operation
from org.integration.base import IntegrationAPIView
from org.integration.contact_history import list_contact_history, parse_limit
from org.integration.contacts import import_contact_receipts
from org.integration.errors import invalid
from org.integration.parsers import json_body
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


class ContactReceiptsView(IntegrationAPIView):
    """POST one atomic id range of the bound guild's external contact log;
    GET one bound event's current receipt history."""

    def get(self, request: Request, org_id: int) -> Response:
        org = gate_token_request(request, org_id, operation=Operation.PROMOTION_READ)
        params = query_params(request, ("event_id", "cursor", "limit"))
        if "event_id" not in params:
            raise invalid("event_id", "is required")
        event_id = parse_canonical_id(params["event_id"])
        if event_id is None:
            raise invalid("event_id", "must be a canonical positive decimal string")
        return Response(
            list_contact_history(
                org_id=org.pk,
                event_id=event_id,
                cursor=params.get("cursor"),
                limit=parse_limit(params.get("limit")),
            )
        )

    def post(self, request: Request, org_id: int) -> Response:
        org = gate_token_request(
            request,
            org_id,
            operation=(Operation.PROMOTION_IMPORT, Operation.PROMOTION_WRITE),
        )
        query_params(request, ())
        result = import_contact_receipts(
            org, json_body(request), connection_id=request.auth.connection_id
        )
        return Response(result)
