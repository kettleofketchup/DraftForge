"""Test-only liveness probe.

Exposed under `api/tests/` and gated by `isTestEnvironment()` in
`backend/urls.py` — never reachable in prod/release. Used by the
Playwright health-probe reporter (frontend/tests/playwright/reporters/
health-probe-reporter.ts) to detect transient backend hangs during long
test runs.

Touches the DB with a single primary-key SELECT so the response time
reflects backend health (Daphne event-loop + ORM + connection-pool +
DB) rather than just network.
"""
import time

from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response


@api_view(["GET"])
@permission_classes([AllowAny])
def healthz(request):
    from events.models import Event

    t0 = time.perf_counter()
    Event.objects.values_list("id", flat=True).first()
    db_ms = (time.perf_counter() - t0) * 1000
    return Response(
        {
            "ok": True,
            "ts": timezone.now().isoformat(),
            "db_ms": round(db_ms, 2),
        }
    )
