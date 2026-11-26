"""Integration v1 routes for the event-promotion contact sync.

Each view authorizes through ``gate_token_request`` with its operation
before reading anything else, so wrong-org, missing grant, feature, owner
role and budget checks run first on every request, retries included.
"""

from __future__ import annotations

from collections.abc import Iterable

from rest_framework.request import Request
from rest_framework.response import Response

from org.api_tokens.auth import gate_token_request
from org.api_tokens.operations import Operation
from org.integration.base import IntegrationAPIView
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
    """POST one atomic id range of the bound guild's external contact log."""

    def post(self, request: Request, org_id: int) -> Response:
        org = gate_token_request(request, org_id, operation=Operation.PROMOTION_IMPORT)
        query_params(request, ())
        result = import_contact_receipts(org, json_body(request))
        return Response(result)
