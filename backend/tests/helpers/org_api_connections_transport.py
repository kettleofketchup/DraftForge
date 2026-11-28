"""Test-only fake outbound transport for the org API connection E2E fixtures.

This is process-local test patching. ``install_fake_transport`` swaps the
safe-transport entry points the pull, push, test and promotion callers
imported for a fake that answers only the synthetic ``.test`` origins in
tests.data.org_api_connections. Every other destination still goes through
the real safe transport. It also makes the internal sweep endpoints skip the
fixture orgs, so only ``drive_connection_work`` steps their runs and
deliveries and the beat sweep cannot race the spec's assertions. It refuses
to install outside the test environment, and nothing persisted on a
connection selects it, so production cannot reach it through a request body
or org config.

The fake keeps the real URL canonicalization and credential rendering: an
unsafe URL or a credential bound to another origin fails exactly as it would
against the network.
"""

import base64
import hashlib
import json
import threading
from collections.abc import Callable
from functools import partial
from types import ModuleType
from typing import Any, Final
from urllib.parse import urlsplit

from django.conf import settings
from django.db.models import Q
from django.utils import timezone

from common.game import GameType
from common.utils import isTestEnvironment
from org.api_connections import internal_views, orchestration, pull, push
from org.api_connections.crypto import canonical_origin
from org.api_connections.orchestration import step_delivery, step_run
from org.api_connections.push import acquire_delivery_lease
from org.api_connections.runs import ACTIVE_STATES, acquire_lease
from org.api_connections.safe_http import _render, canonical_url
from org.api_connections.types import (
    SafeHttpRawResponse,
    SafeHttpRequest,
    SafeHttpResponse,
)
from org.integration import adaptor_client
from org.mmr import set_org_mmr
from org.models import (
    OrgApiMmrDelivery,
    OrgApiRunCheckpoint,
    OrgApiSyncRun,
    OrgUser,
)
from tests.data.org_api_connections import (
    API_CONNECTIONS_ORGS,
    FAKE_GOOD_CREDENTIAL,
    FAKE_ORIGINS,
    FAKE_PULL_PATH,
    FAKE_PULL_ROWS,
)

TEST_KEY_ID: Final[str] = "e2e-fixture"
CALL_LOG_LIMIT: Final[int] = 200

_TARGETS: Final[tuple[tuple[ModuleType, str], ...]] = (
    (pull, "request_json"),
    (push, "request_json"),
    (orchestration, "request_json"),
    (orchestration, "request_bytes"),
    (adaptor_client, "request_bytes"),
)

FIXTURE_ORG_IDS: Final[frozenset[int]] = frozenset(
    org.pk for org in API_CONNECTIONS_ORGS if org.pk is not None
)

_SWEEP_TARGETS: Final[tuple[str, ...]] = (
    "claim_work",
    "promotion_due",
    "step_promotion",
)

_FAKE_ORIGINS: Final[frozenset[str]] = frozenset(
    canonical_origin(origin) for origin in FAKE_ORIGINS
)

_lock = threading.Lock()
_originals: dict[tuple[str, str], Callable[..., Any]] = {}
_saved_key_ring: str | None = None
_calls: list[dict[str, Any]] = []


class FakeTransportUnavailable(RuntimeError):
    pass


def _require_test_environment() -> None:
    if not isTestEnvironment():
        raise FakeTransportUnavailable("fake transport is test-only")


def fixture_key_ring() -> str:
    """A deterministic synthetic key ring; never a deployment key."""
    key = hashlib.sha256(b"draftforge-e2e-org-api-connections").digest()
    return json.dumps([{"id": TEST_KEY_ID, "key": base64.b64encode(key).decode()}])


def _record(request: SafeHttpRequest, url: str, status: int) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "method": request.method,
        "host": urlsplit(url).hostname,
        "path": urlsplit(url).path,
        "status": status,
    }
    if request.body is not None and request.method == "POST":
        entries = request.body.get("entries")
        if isinstance(entries, list):
            entry["mmrs"] = [
                item.get("mmr") for item in entries if isinstance(item, dict)
            ]
    with _lock:
        _calls.append(entry)
        del _calls[:-CALL_LOG_LIMIT]
    return entry


def _answer(request: SafeHttpRequest, url: str) -> tuple[int, Any]:
    _render(request, url)
    if request.auth != "none" and request.credential != FAKE_GOOD_CREDENTIAL:
        return 401, {"error": "unauthorized"}
    path = urlsplit(url).path
    if request.method == "GET" and path.endswith("/health"):
        return 200, {"status": "ok"}
    if request.method == "GET" and path == FAKE_PULL_PATH:
        return 200, {"players": [dict(row) for row in FAKE_PULL_ROWS]}
    if request.method == "POST" and path.startswith("/api/v1/organizations/"):
        return 200, {"delivery_id": request.idempotency_key, "status": "applied"}
    return 404, {"error": "not_found"}


def _fake(original: Callable[..., Any], raw: bool) -> Callable[..., Any]:
    def send(request: SafeHttpRequest, *, deadline: float, max_bytes: int = 0) -> Any:
        url = canonical_url(request.url)
        if canonical_origin(url) not in _FAKE_ORIGINS:
            kwargs = {"deadline": deadline}
            if max_bytes:
                kwargs["max_bytes"] = max_bytes
            return original(request, **kwargs)
        status, data = _answer(request, url)
        _record(request, url, status)
        if raw:
            return SafeHttpRawResponse(
                status=status, body=json.dumps(data).encode(), retry_after=None
            )
        return SafeHttpResponse(
            status=status, data=data, bytes_received=len(json.dumps(data))
        )

    send.fake_transport = True  # type: ignore[attr-defined]
    return send


def install_fake_transport() -> None:
    """Route the synthetic origins to the fake; idempotent, test-only."""
    global _saved_key_ring
    _require_test_environment()
    with _lock:
        for module, name in _TARGETS:
            current = getattr(module, name)
            if getattr(current, "fake_transport", False):
                continue
            _originals[(module.__name__, name)] = current
            setattr(module, name, _fake(current, raw=name == "request_bytes"))
        for name in _SWEEP_TARGETS:
            current = getattr(internal_views, name)
            if getattr(current, "fake_transport", False):
                continue
            _originals[(internal_views.__name__, name)] = current
            skipping = partial(current, skip_org_ids=FIXTURE_ORG_IDS)
            skipping.fake_transport = True  # type: ignore[attr-defined]
            setattr(internal_views, name, skipping)
        if not settings.ORG_API_CREDENTIAL_KEYS and _saved_key_ring is None:
            _saved_key_ring = settings.ORG_API_CREDENTIAL_KEYS
            settings.ORG_API_CREDENTIAL_KEYS = fixture_key_ring()


def uninstall_fake_transport() -> None:
    """Put the real transport and the original key ring setting back."""
    global _saved_key_ring
    with _lock:
        for module, name in _TARGETS:
            original = _originals.pop((module.__name__, name), None)
            if original is not None:
                setattr(module, name, original)
        for name in _SWEEP_TARGETS:
            original = _originals.pop((internal_views.__name__, name), None)
            if original is not None:
                setattr(internal_views, name, original)
        if _saved_key_ring is not None:
            settings.ORG_API_CREDENTIAL_KEYS = _saved_key_ring
            _saved_key_ring = None
        _calls.clear()


def fake_transport_installed() -> bool:
    return all(
        getattr(getattr(module, name), "fake_transport", False)
        for module, name in _TARGETS
    ) and all(
        getattr(getattr(internal_views, name), "fake_transport", False)
        for name in _SWEEP_TARGETS
    )


def fake_calls() -> list[dict[str, Any]]:
    _require_test_environment()
    with _lock:
        return [dict(call) for call in _calls]


def clear_fake_calls() -> None:
    with _lock:
        _calls.clear()


def drive_connection_work(
    org_ids: list[int],
    *,
    edit_after_stage: tuple[int, int] | None = None,
    max_steps: int = 200,
) -> dict[str, Any]:
    """Run the due runs and deliveries of ``org_ids`` through the real step
    services, without waiting for the beat sweep. Other orgs' work is untouched.

    ``edit_after_stage`` is (user pk, MMR): once a pull run has staged its
    targets, that member's MMR is edited before the commit step, so the run
    reports a deterministic revision conflict.
    """
    _require_test_environment()
    install_fake_transport()
    steps = 0
    runs: dict[str, str] = {}
    deliveries: dict[str, str] = {}
    pending_edit = edit_after_stage
    while steps < max_steps:
        now = timezone.now()
        progressed = False
        run_ids = list(
            OrgApiSyncRun.objects.filter(
                organization_id__in=org_ids, state__in=ACTIVE_STATES
            )
            .filter(Q(lease_token__isnull=True) | Q(lease_expires_at__lte=now))
            .order_by("created_at")
            .values_list("pk", flat=True)
        )
        for run_id in run_ids:
            fence = acquire_lease(run_id, now=now)
            while fence is not None and steps < max_steps:
                result = step_run(run_id, fence=fence)
                steps += 1
                progressed = True
                runs[str(run_id)] = result.state
                if (
                    pending_edit is not None
                    and result.continuation
                    and OrgApiRunCheckpoint.objects.filter(
                        run_id=run_id, phase="commit"
                    ).exists()
                ):
                    _edit_member_mmr(run_id, *pending_edit)
                    pending_edit = None
                fence = result.fence if result.continuation else None
        delivery_ids = list(
            OrgApiMmrDelivery.objects.filter(connection__organization_id__in=org_ids)
            .filter(
                Q(state__in=("pending", "retry"), due_at__lte=now)
                | Q(state="in_flight", lease_expires_at__lte=now)
            )
            .order_by("due_at", "pk")
            .values_list("delivery_id", flat=True)
        )
        for delivery_id in delivery_ids:
            if steps >= max_steps:
                break
            fence = acquire_delivery_lease(delivery_id, now=now)
            if fence is None:
                continue
            result = step_delivery(delivery_id, fence=fence)
            steps += 1
            progressed = True
            deliveries[str(delivery_id)] = result.state
        if not progressed:
            break
    return {"steps": steps, "runs": runs, "deliveries": deliveries}


def _edit_member_mmr(run_id: Any, user_pk: int, mmr: int) -> None:
    run = OrgApiSyncRun.objects.get(pk=run_id)
    member = OrgUser.objects.nocache().get(
        organization_id=run.organization_id, user_id=user_pk
    )
    set_org_mmr(member, GameType.DOTA2, mmr, mark_verified=False)
