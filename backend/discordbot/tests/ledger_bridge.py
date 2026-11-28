"""Route DM ledger and event-DM internal calls into the in-process test client.

Celery-side DM code reaches the ledger over HTTP; in unit tests the rows live
in the test transaction, so this sends those calls to the real internal views.
"""

import json
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any
from unittest import mock

from django.http import HttpResponse
from django.test import override_settings
from rest_framework.test import APIClient

from app.internal_client import transport

BRIDGE_TOKEN = "ledger-bridge-token"
BRIDGED_PREFIXES: tuple[str, ...] = (
    "/discord/dms/",
    "/discord/event-dm/",
    "/discord/live-messages/",
)


class BridgeResponse:
    def __init__(self, resp: HttpResponse) -> None:
        self.status_code: int = resp.status_code
        self.headers = resp.headers
        self.ok: bool = 200 <= resp.status_code < 400
        self.text: str = resp.content.decode(errors="replace")

    def json(self) -> Any:
        return json.loads(self.text)


@contextmanager
def ledger_bridge() -> Iterator[mock.MagicMock]:
    client = APIClient()
    client.credentials(HTTP_X_INTERNAL_TOKEN=BRIDGE_TOKEN)
    real_post = transport.post
    real_patch = transport.patch

    def _post(path: str, data: dict[str, Any]) -> Any:
        if path.startswith(BRIDGED_PREFIXES):
            return BridgeResponse(
                client.post(f"/api/internal{path}", data, format="json")
            )
        return real_post(path, data)

    def _patch(path: str, data: dict[str, Any]) -> Any:
        if path.startswith(BRIDGED_PREFIXES):
            return BridgeResponse(
                client.patch(f"/api/internal{path}", data, format="json")
            )
        return real_patch(path, data)

    with (
        override_settings(INTERNAL_SERVICE_TOKEN=BRIDGE_TOKEN),
        mock.patch.object(transport, "post", side_effect=_post) as post,
        mock.patch.object(transport, "patch", side_effect=_patch),
    ):
        yield post
