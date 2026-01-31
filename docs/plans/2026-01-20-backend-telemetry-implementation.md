# Backend Telemetry Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add structured logging with structlog, optional OpenTelemetry tracing, and consistent context propagation across HTTP requests, WebSockets, and Celery tasks.

**Architecture:** A `backend/telemetry/` module provides centralized configuration. Middleware binds request context (request_id, user_id, URL-based labels) to structlog. OTel tracing is opt-in via environment variables with safe no-op behavior when disabled.

**Tech Stack:** structlog, opentelemetry-sdk, opentelemetry-instrumentation-django, opentelemetry-instrumentation-requests, opentelemetry-instrumentation-system-metrics

---

## CRITICAL FIXES (Review Findings)

The following fixes MUST be applied during implementation:

### 1. Task Ordering: config.py References Non-Existent Modules

**Problem:** Task 2 creates `config.py` with `init_telemetry()` that imports `logging.py` and `tracing.py` which don't exist yet.

**Fix:** In Task 2, create `config.py` with ONLY the helper functions (`env_bool`, `is_dev`, `get_service_name`). Add `init_telemetry()` function AFTER Task 3 (logging.py) and Task 6 (tracing.py) are complete.

### 2. Test Capture Pattern Won't Work

**Problem:** Tests mock `sys.stdout` but structlog captures stdout at configuration time.

**Fix:** Use `structlog.testing.capture_logs` instead:

```python
from structlog.testing import capture_logs

def test_configure_logging_json_format(self):
    configure_logging(level="INFO", format="json")
    log = get_logger("test")

    with capture_logs() as cap_logs:
        log.info("test_event", key="value")

    self.assertEqual(cap_logs[0]["event"], "test_event")
    self.assertEqual(cap_logs[0]["key"], "value")
```

### 3. Test Isolation: Structlog Global State

**Problem:** Tests modify global structlog configuration without reset.

**Fix:** Add tearDown to ALL test classes:

```python
def setUp(self):
    from telemetry import logging as telem_logging
    telem_logging._configured = False
    structlog.reset_defaults()

def tearDown(self):
    structlog.reset_defaults()
    structlog.contextvars.clear_contextvars()
```

### 4. Deprecated asyncio Pattern

**Problem:** `asyncio.get_event_loop().run_until_complete()` is deprecated in Python 3.10+.

**Fix:** Use `asyncio.run()`:

```python
def test_connect_generates_connection_id(self):
    consumer = MockConsumer()
    asyncio.run(consumer.telemetry_connect())
    self.assertIsNotNone(consumer.ws_conn_id)
```

### 5. ASGI Security: Preserve AllowedHostsOriginValidator

**Problem:** Plan removes `AllowedHostsOriginValidator` security wrapper.

**Fix:** Preserve existing security in Task 10:

```python
from channels.security.websocket import AllowedHostsOriginValidator

application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        "websocket": AllowedHostsOriginValidator(
            URLRouter(websocket_urlpatterns)
        ),
    }
)
```

### 6. Duplicate env_bool Function

**Problem:** `env_bool` is defined in both `config.py` and `tracing.py`.

**Fix:** In `tracing.py`, import from config:

```python
from telemetry.config import env_bool
```

Remove the local `_env_bool` definition.

### 7. WebSocket Path Mismatch (Singular vs Plural)

**Problem:** WebSocket paths use singular (`/ws/draft/5/`) but labels.py expects plural (`/drafts/`).

**Fix:** Add WebSocket-specific patterns to `labels.py`:

```python
RESOURCE_PATTERNS = [
    # WebSocket singular paths (check before API plural paths)
    (r"/draft/(\d+)", "draft"),
    (r"/tournament/(\d+)", "tournament"),
    # API plural paths...
    (r"/drafts/(\d+)", "draft"),
    (r"/tournaments/(\d+)", "tournament"),
    # ...
]
```

### 8. Middleware Position: Can't Get user.id

**Problem:** Middleware runs before `AuthenticationMiddleware`, so `request.user` is not set.

**Fix:** In Task 9, place middleware AFTER `AuthenticationMiddleware`:

```python
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "telemetry.middleware.TelemetryMiddleware",  # AFTER AuthenticationMiddleware
    # ...
]
```

### 9. Docker Networking: Observability Stack Isolated

**Problem:** Jaeger runs on separate network, backend can't reach it.

**Fix:** Update Task 13 documentation to use localhost:

```yaml
# Usage: docker compose -f docker/docker-compose.observability.yaml up -d
#
# Then set in your .env (use localhost, not container name):
#   OTEL_ENABLED=true
#   OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317
```

### 10. OTel Version Coupling

**Problem:** Caret ranges (`^`) may pull incompatible versions.

**Fix:** Use tilde ranges in Task 1:

```toml
structlog = "~24.0"
opentelemetry-api = "~1.20"
opentelemetry-sdk = "~1.20"
opentelemetry-exporter-otlp = "~1.20"
opentelemetry-instrumentation-django = "~0.41"
opentelemetry-instrumentation-requests = "~0.41"
opentelemetry-instrumentation-system-metrics = "~0.41"
opentelemetry-instrumentation-celery = "~0.41"
```

---

## Phase 1: Dependencies and Module Structure

### Task 1: Add Python Dependencies

**Files:**
- Modify: `pyproject.toml`

**Step 1: Add telemetry dependencies to pyproject.toml**

Add to `[tool.poetry.dependencies]`:

```toml
structlog = "^24.0"
opentelemetry-api = "^1.20"
opentelemetry-sdk = "^1.20"
opentelemetry-exporter-otlp = "^1.20"
opentelemetry-instrumentation-django = "^0.41"
opentelemetry-instrumentation-requests = "^0.41"
opentelemetry-instrumentation-system-metrics = "^0.41"
opentelemetry-instrumentation-celery = "^0.41"
```

**Step 2: Install dependencies**

Run: `cd /home/kettle/git_repos/website/.worktrees/backend-telemetry && source .venv/bin/activate && poetry install`

Expected: Dependencies install successfully

**Step 3: Verify import works**

Run: `cd /home/kettle/git_repos/website/.worktrees/backend-telemetry && source .venv/bin/activate && python -c "import structlog; print(structlog.__version__)"`

Expected: Version number printed (e.g., `24.x.x`)

**Step 4: Commit**

```bash
cd /home/kettle/git_repos/website/.worktrees/backend-telemetry
git add pyproject.toml poetry.lock
git commit -m "deps: add structlog and opentelemetry packages"
```

---

### Task 2: Create Telemetry Module Structure

**Files:**
- Create: `backend/telemetry/__init__.py`
- Create: `backend/telemetry/config.py`

**Step 1: Create module directory and __init__.py**

Create `backend/telemetry/__init__.py`:

```python
"""
DTX Backend Telemetry Module

Provides structured logging (structlog) and optional distributed tracing (OpenTelemetry)
with consistent context propagation across HTTP requests, WebSockets, and Celery tasks.

Usage:
    from telemetry.config import init_telemetry
    init_telemetry()  # Call once at Django startup
"""

from telemetry.config import init_telemetry

__all__ = ["init_telemetry"]
```

**Step 2: Create config.py with environment helpers**

Create `backend/telemetry/config.py`:

```python
"""Central telemetry configuration and initialization."""

import os
import logging

# Use stdlib logging until structlog is configured
_bootstrap_log = logging.getLogger("telemetry.config")


def env_bool(key: str, default: bool = False) -> bool:
    """Parse boolean environment variable."""
    value = os.environ.get(key, "").lower()
    if value in ("true", "1", "yes"):
        return True
    if value in ("false", "0", "no"):
        return False
    return default


def is_dev() -> bool:
    """Check if running in development environment."""
    node_env = os.environ.get("NODE_ENV", "dev")
    return node_env in ("dev", "development")


def get_service_name() -> str:
    """Get the service name for telemetry."""
    return os.environ.get("OTEL_SERVICE_NAME", "dtx-backend")


def init_telemetry() -> None:
    """
    Initialize telemetry subsystems.

    Call once at Django startup (in settings.py or wsgi/asgi.py).
    Safe to call multiple times - subsequent calls are no-ops.
    """
    # Import here to avoid circular imports
    from telemetry.logging import configure_logging, get_logger
    from telemetry.tracing import init_tracing

    # Check master switch
    if not env_bool("TELEMETRY_ENABLED", True):
        _bootstrap_log.info("Telemetry disabled via TELEMETRY_ENABLED=false")
        return

    # Configure structlog
    log_level = os.environ.get("LOG_LEVEL", "INFO")
    log_format = os.environ.get("LOG_FORMAT", "pretty" if is_dev() else "json")
    configure_logging(level=log_level, format=log_format)

    # Get a logger now that structlog is configured
    log = get_logger(__name__)

    # Initialize OTel tracing (no-op if not configured)
    init_tracing()

    # Log startup summary
    log.info(
        "telemetry_initialized",
        otel_enabled=env_bool("OTEL_ENABLED", False),
        log_format=log_format,
        log_level=log_level,
        service_name=get_service_name(),
    )
```

**Step 3: Verify module imports**

Run: `cd /home/kettle/git_repos/website/.worktrees/backend-telemetry/backend && source ../.venv/bin/activate && python -c "from telemetry.config import env_bool, is_dev; print(env_bool('TEST', False), is_dev())"`

Expected: `False True` (or similar based on env)

**Step 4: Commit**

```bash
cd /home/kettle/git_repos/website/.worktrees/backend-telemetry
git add backend/telemetry/
git commit -m "feat(telemetry): add module structure and config helpers"
```

---

## Phase 2: Structured Logging

### Task 3: Implement Logging Configuration

**Files:**
- Create: `backend/telemetry/logging.py`
- Create: `backend/telemetry/tests/__init__.py`
- Create: `backend/telemetry/tests/test_logging.py`

**Step 1: Write failing test for logging configuration**

Create `backend/telemetry/tests/__init__.py`:

```python
"""Telemetry module tests."""
```

Create `backend/telemetry/tests/test_logging.py`:

```python
"""Tests for telemetry logging configuration."""

import io
import json
import sys
from unittest import TestCase, mock

from telemetry.logging import configure_logging, get_logger


class ConfigureLoggingTest(TestCase):
    """Tests for configure_logging function."""

    def test_configure_logging_json_format(self):
        """JSON format outputs valid JSON lines."""
        configure_logging(level="INFO", format="json")
        log = get_logger("test")

        # Capture stdout
        captured = io.StringIO()
        with mock.patch("sys.stdout", captured):
            log.info("test_event", key="value")

        output = captured.getvalue().strip()
        data = json.loads(output)

        self.assertEqual(data["event"], "test_event")
        self.assertEqual(data["key"], "value")
        self.assertEqual(data["level"], "info")
        self.assertIn("timestamp", data)

    def test_configure_logging_pretty_format(self):
        """Pretty format outputs human-readable logs."""
        configure_logging(level="INFO", format="pretty")
        log = get_logger("test")

        # Capture stdout
        captured = io.StringIO()
        with mock.patch("sys.stdout", captured):
            log.info("test_event", key="value")

        output = captured.getvalue()

        # Pretty format should contain the event and key
        self.assertIn("test_event", output)
        self.assertIn("key", output)
        self.assertIn("value", output)


class GetLoggerTest(TestCase):
    """Tests for get_logger function."""

    def test_get_logger_returns_bound_logger(self):
        """get_logger returns a structlog logger."""
        configure_logging(level="INFO", format="json")
        log = get_logger("mymodule")

        # Should have standard logging methods
        self.assertTrue(hasattr(log, "info"))
        self.assertTrue(hasattr(log, "warning"))
        self.assertTrue(hasattr(log, "error"))
```

**Step 2: Run test to verify it fails**

Run: `cd /home/kettle/git_repos/website/.worktrees/backend-telemetry/backend && source ../.venv/bin/activate && DISABLE_CACHE=true python -m pytest telemetry/tests/test_logging.py -v`

Expected: FAIL with import error (logging.py doesn't exist yet)

**Step 3: Implement logging.py**

Create `backend/telemetry/logging.py`:

```python
"""Structured logging configuration using structlog."""

import logging
import sys
from typing import Literal

import structlog
from structlog.typing import Processor

# Track if logging has been configured
_configured = False


def _add_logger_name(
    logger: logging.Logger, method_name: str, event_dict: dict
) -> dict:
    """Add logger name to event dict."""
    record = event_dict.get("_record")
    if record:
        event_dict["logger"] = record.name
    return event_dict


def configure_logging(
    level: str = "INFO",
    format: Literal["json", "pretty"] = "json",
) -> None:
    """
    Configure structlog for the application.

    Args:
        level: Minimum log level (DEBUG, INFO, WARNING, ERROR)
        format: Output format - 'json' for production, 'pretty' for development
    """
    global _configured

    # Shared processors for all output formats
    shared_processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso", key="timestamp"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
    ]

    if format == "json":
        # JSON output for production
        renderer: Processor = structlog.processors.JSONRenderer()
    else:
        # Pretty console output for development
        renderer = structlog.dev.ConsoleRenderer(
            colors=True,
            exception_formatter=structlog.dev.plain_traceback,
        )

    # Configure structlog
    structlog.configure(
        processors=shared_processors + [
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # Configure stdlib logging to use structlog formatter
    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.handlers = [handler]
    root_logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Quiet noisy third-party loggers
    for logger_name in ["urllib3", "requests", "httpx", "httpcore"]:
        logging.getLogger(logger_name).setLevel(logging.WARNING)

    _configured = True


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """
    Get a structlog logger for the given module name.

    Args:
        name: Logger name (typically __name__)

    Returns:
        A bound structlog logger
    """
    return structlog.get_logger(name)
```

**Step 4: Run tests to verify they pass**

Run: `cd /home/kettle/git_repos/website/.worktrees/backend-telemetry/backend && source ../.venv/bin/activate && DISABLE_CACHE=true python -m pytest telemetry/tests/test_logging.py -v`

Expected: All tests PASS

**Step 5: Commit**

```bash
cd /home/kettle/git_repos/website/.worktrees/backend-telemetry
git add backend/telemetry/logging.py backend/telemetry/tests/
git commit -m "feat(telemetry): add structlog configuration"
```

---

## Phase 3: Label Extraction

### Task 4: Implement URL Label Extraction

**Files:**
- Create: `backend/telemetry/labels.py`
- Create: `backend/telemetry/tests/test_labels.py`

**Step 1: Write failing tests for label extraction**

Create `backend/telemetry/tests/test_labels.py`:

```python
"""Tests for URL-based label extraction."""

from unittest import TestCase

from telemetry.labels import extract_labels


class ExtractLabelsTest(TestCase):
    """Tests for extract_labels function."""

    def test_tournament_root(self):
        """Extract labels from /api/tournaments/{id}/"""
        result = extract_labels("/api/tournaments/5/")
        self.assertEqual(result["labels"], ["tournament"])
        self.assertEqual(result["tournament.id"], 5)

    def test_tournament_draft(self):
        """Extract labels from /api/tournaments/{id}/draft/{id}/"""
        result = extract_labels("/api/tournaments/5/draft/12/")
        self.assertEqual(result["labels"], ["tournament", "draft"])
        self.assertEqual(result["tournament.id"], 5)
        self.assertEqual(result["draft.id"], 12)

    def test_draft_root(self):
        """Extract labels from /api/drafts/{id}/"""
        result = extract_labels("/api/drafts/42/")
        self.assertEqual(result["labels"], ["draft"])
        self.assertEqual(result["draft.id"], 42)

    def test_league_standings(self):
        """Extract labels from /api/leagues/{id}/standings/"""
        result = extract_labels("/api/leagues/3/standings/")
        self.assertEqual(result["labels"], ["league", "standings"])
        self.assertEqual(result["league.id"], 3)

    def test_organization(self):
        """Extract labels from /api/organizations/{id}/"""
        result = extract_labels("/api/organizations/7/")
        self.assertEqual(result["labels"], ["organization"])
        self.assertEqual(result["organization.id"], 7)

    def test_match(self):
        """Extract labels from /api/matches/{id}/"""
        result = extract_labels("/api/matches/99/")
        self.assertEqual(result["labels"], ["match"])
        self.assertEqual(result["match.id"], 99)

    def test_users(self):
        """Extract labels from /api/users/"""
        result = extract_labels("/api/users/")
        self.assertEqual(result["labels"], ["user"])
        self.assertNotIn("user.id", result)

    def test_users_me(self):
        """Extract labels from /api/users/me/"""
        result = extract_labels("/api/users/me/")
        self.assertEqual(result["labels"], ["user"])

    def test_unknown_path(self):
        """Unknown paths return empty dict."""
        result = extract_labels("/api/unknown/path/")
        self.assertEqual(result, {})

    def test_nested_resources(self):
        """Deeply nested paths extract all labels."""
        result = extract_labels("/api/leagues/1/tournaments/2/games/3/")
        self.assertEqual(result["labels"], ["league", "tournament", "game"])
        self.assertEqual(result["league.id"], 1)
        self.assertEqual(result["tournament.id"], 2)
        self.assertEqual(result["game.id"], 3)

    def test_games(self):
        """Extract labels from /api/games/{id}/"""
        result = extract_labels("/api/games/15/")
        self.assertEqual(result["labels"], ["game"])
        self.assertEqual(result["game.id"], 15)

    def test_teams(self):
        """Extract labels from /api/teams/{id}/"""
        result = extract_labels("/api/teams/8/")
        self.assertEqual(result["labels"], ["team"])
        self.assertEqual(result["team.id"], 8)

    def test_non_api_path(self):
        """Non-API paths return empty dict."""
        result = extract_labels("/static/css/style.css")
        self.assertEqual(result, {})
```

**Step 2: Run test to verify it fails**

Run: `cd /home/kettle/git_repos/website/.worktrees/backend-telemetry/backend && source ../.venv/bin/activate && DISABLE_CACHE=true python -m pytest telemetry/tests/test_labels.py -v`

Expected: FAIL with import error

**Step 3: Implement labels.py**

Create `backend/telemetry/labels.py`:

```python
"""URL-based label extraction for telemetry context."""

import re
from typing import Any

# Known resource patterns and their label names
# Order matters: more specific patterns should come first
RESOURCE_PATTERNS = [
    # Plural resources with IDs
    (r"/tournaments/(\d+)", "tournament"),
    (r"/drafts/(\d+)", "draft"),
    (r"/leagues/(\d+)", "league"),
    (r"/organizations/(\d+)", "organization"),
    (r"/matches/(\d+)", "match"),
    (r"/games/(\d+)", "game"),
    (r"/teams/(\d+)", "team"),
    (r"/users/(\d+)", "user"),
    # Plural resources without IDs (list endpoints)
    (r"/tournaments/?$", "tournament"),
    (r"/drafts/?$", "draft"),
    (r"/leagues/?$", "league"),
    (r"/organizations/?$", "organization"),
    (r"/matches/?$", "match"),
    (r"/games/?$", "game"),
    (r"/teams/?$", "team"),
    (r"/users/?", "user"),  # Includes /users/me/
    # Sub-resources (no ID, just label)
    (r"/standings/?$", "standings"),
    (r"/bracket/?$", "bracket"),
    (r"/stats/?$", "stats"),
]


def extract_labels(path: str) -> dict[str, Any]:
    """
    Extract contextual labels from a URL path.

    Parses URL patterns to produce metadata for logging and tracing.
    Uses OTel semantic conventions for field names.

    Args:
        path: URL path (e.g., "/api/tournaments/5/draft/12/")

    Returns:
        Dict with 'labels' list and resource IDs, e.g.:
        {"labels": ["tournament", "draft"], "tournament.id": 5, "draft.id": 12}

        Returns empty dict for unrecognized paths.

    Examples:
        >>> extract_labels("/api/tournaments/5/")
        {"labels": ["tournament"], "tournament.id": 5}

        >>> extract_labels("/api/tournaments/5/draft/12/")
        {"labels": ["tournament", "draft"], "tournament.id": 5, "draft.id": 12}
    """
    # Only process API paths
    if not path.startswith("/api/"):
        return {}

    labels: list[str] = []
    result: dict[str, Any] = {}

    # Track which resources we've already matched to avoid duplicates
    matched_resources: set[str] = set()

    for pattern, resource_name in RESOURCE_PATTERNS:
        match = re.search(pattern, path)
        if match:
            # Avoid duplicate labels
            if resource_name not in matched_resources:
                labels.append(resource_name)
                matched_resources.add(resource_name)

            # Extract ID if present in capture group
            if match.groups():
                try:
                    resource_id = int(match.group(1))
                    result[f"{resource_name}.id"] = resource_id
                except (ValueError, IndexError):
                    pass

    if labels:
        result["labels"] = labels

    return result
```

**Step 4: Run tests to verify they pass**

Run: `cd /home/kettle/git_repos/website/.worktrees/backend-telemetry/backend && source ../.venv/bin/activate && DISABLE_CACHE=true python -m pytest telemetry/tests/test_labels.py -v`

Expected: All tests PASS

**Step 5: Commit**

```bash
cd /home/kettle/git_repos/website/.worktrees/backend-telemetry
git add backend/telemetry/labels.py backend/telemetry/tests/test_labels.py
git commit -m "feat(telemetry): add URL-based label extraction"
```

---

## Phase 4: Request Middleware

### Task 5: Implement Telemetry Middleware

**Files:**
- Create: `backend/telemetry/middleware.py`
- Create: `backend/telemetry/tests/test_middleware.py`

**Step 1: Write failing tests for middleware**

Create `backend/telemetry/tests/test_middleware.py`:

```python
"""Tests for telemetry middleware."""

import uuid
from unittest import TestCase, mock

from django.http import HttpRequest, HttpResponse
from django.test import RequestFactory

from telemetry.middleware import TelemetryMiddleware


class TelemetryMiddlewareTest(TestCase):
    """Tests for TelemetryMiddleware."""

    def setUp(self):
        """Set up test fixtures."""
        self.factory = RequestFactory()
        self.get_response = mock.Mock(return_value=HttpResponse("OK"))
        self.middleware = TelemetryMiddleware(self.get_response)

    def test_generates_request_id(self):
        """Middleware generates request_id if not provided."""
        request = self.factory.get("/api/tournaments/")

        response = self.middleware(request)

        # Response should have X-Request-ID header
        self.assertIn("X-Request-ID", response)
        # Should be a valid UUID
        uuid.UUID(response["X-Request-ID"])

    def test_accepts_request_id_header(self):
        """Middleware accepts X-Request-ID from client."""
        request_id = "client-provided-id-123"
        request = self.factory.get(
            "/api/tournaments/",
            HTTP_X_REQUEST_ID=request_id,
        )

        response = self.middleware(request)

        self.assertEqual(response["X-Request-ID"], request_id)

    def test_binds_context_for_request(self):
        """Middleware binds context to structlog."""
        import structlog

        request = self.factory.get("/api/tournaments/5/")

        # Track what context was bound
        bound_context = {}

        def capture_response(req):
            # Capture context during request
            ctx = structlog.contextvars.get_contextvars()
            bound_context.update(ctx)
            return HttpResponse("OK")

        middleware = TelemetryMiddleware(capture_response)
        middleware(request)

        # Verify context was bound
        self.assertIn("request.id", bound_context)
        self.assertEqual(bound_context["labels"], ["tournament"])
        self.assertEqual(bound_context["tournament.id"], 5)

    def test_clears_context_after_request(self):
        """Middleware clears context after request completes."""
        import structlog

        request = self.factory.get("/api/tournaments/5/")

        self.middleware(request)

        # Context should be cleared
        ctx = structlog.contextvars.get_contextvars()
        self.assertNotIn("tournament.id", ctx)

    def test_binds_user_id_when_authenticated(self):
        """Middleware binds user.id for authenticated requests."""
        import structlog

        request = self.factory.get("/api/tournaments/")
        request.user = mock.Mock()
        request.user.is_authenticated = True
        request.user.pk = 42

        bound_context = {}

        def capture_response(req):
            ctx = structlog.contextvars.get_contextvars()
            bound_context.update(ctx)
            return HttpResponse("OK")

        middleware = TelemetryMiddleware(capture_response)
        middleware(request)

        self.assertEqual(bound_context["user.id"], 42)

    def test_handles_anonymous_user(self):
        """Middleware handles anonymous users gracefully."""
        import structlog

        request = self.factory.get("/api/tournaments/")
        request.user = mock.Mock()
        request.user.is_authenticated = False

        bound_context = {}

        def capture_response(req):
            ctx = structlog.contextvars.get_contextvars()
            bound_context.update(ctx)
            return HttpResponse("OK")

        middleware = TelemetryMiddleware(capture_response)
        middleware(request)

        # user.id should not be present for anonymous users
        self.assertNotIn("user.id", bound_context)
```

**Step 2: Run test to verify it fails**

Run: `cd /home/kettle/git_repos/website/.worktrees/backend-telemetry/backend && source ../.venv/bin/activate && DISABLE_CACHE=true python -m pytest telemetry/tests/test_middleware.py -v`

Expected: FAIL with import error

**Step 3: Implement middleware.py**

Create `backend/telemetry/middleware.py`:

```python
"""Django middleware for telemetry context binding."""

import time
import uuid
from typing import Callable

import structlog
from django.http import HttpRequest, HttpResponse

from telemetry.labels import extract_labels
from telemetry.logging import get_logger

log = get_logger(__name__)


class TelemetryMiddleware:
    """
    Middleware that binds telemetry context to each request.

    Responsibilities:
    - Generate or accept request_id (from X-Request-ID header)
    - Extract user_id from authenticated session
    - Extract labels from URL path
    - Bind all context to structlog for request duration
    - Add X-Request-ID to response headers
    - Log request completion with timing
    """

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]):
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        # Start timing
        start_time = time.perf_counter()

        # Get or generate request ID
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())

        # Extract user ID if authenticated
        user_id = None
        if hasattr(request, "user") and request.user.is_authenticated:
            user_id = request.user.pk

        # Extract labels from URL
        labels = extract_labels(request.path)

        # Build context dict
        context: dict = {
            "request.id": request_id,
            **labels,
        }
        if user_id is not None:
            context["user.id"] = user_id

        # Bind context to structlog
        structlog.contextvars.bind_contextvars(**context)

        try:
            # Process request
            response = self.get_response(request)

            # Calculate duration
            duration_ms = (time.perf_counter() - start_time) * 1000

            # Log request completion
            log.info(
                "request_completed",
                **{
                    "http.method": request.method,
                    "http.route": request.path,
                    "http.status_code": response.status_code,
                    "duration_ms": round(duration_ms, 2),
                }
            )

            # Add request ID to response
            response["X-Request-ID"] = request_id

            return response

        except Exception as e:
            # Log error
            duration_ms = (time.perf_counter() - start_time) * 1000
            log.error(
                "request_failed",
                **{
                    "http.method": request.method,
                    "http.route": request.path,
                    "duration_ms": round(duration_ms, 2),
                    "error": str(e),
                },
                exc_info=True,
            )
            raise

        finally:
            # Always clear context
            structlog.contextvars.clear_contextvars()
```

**Step 4: Run tests to verify they pass**

Run: `cd /home/kettle/git_repos/website/.worktrees/backend-telemetry/backend && source ../.venv/bin/activate && DISABLE_CACHE=true python -m pytest telemetry/tests/test_middleware.py -v`

Expected: All tests PASS

**Step 5: Commit**

```bash
cd /home/kettle/git_repos/website/.worktrees/backend-telemetry
git add backend/telemetry/middleware.py backend/telemetry/tests/test_middleware.py
git commit -m "feat(telemetry): add request context middleware"
```

---

## Phase 5: OpenTelemetry Tracing

### Task 6: Implement OTel Tracing Configuration

**Files:**
- Create: `backend/telemetry/tracing.py`
- Create: `backend/telemetry/tests/test_tracing.py`

**Step 1: Write failing tests for tracing**

Create `backend/telemetry/tests/test_tracing.py`:

```python
"""Tests for OpenTelemetry tracing configuration."""

import os
from unittest import TestCase, mock

from telemetry.tracing import init_tracing


class InitTracingTest(TestCase):
    """Tests for init_tracing function."""

    def test_disabled_when_otel_enabled_false(self):
        """Tracing is no-op when OTEL_ENABLED is false."""
        with mock.patch.dict(os.environ, {"OTEL_ENABLED": "false"}, clear=False):
            # Should not raise
            init_tracing()

    def test_disabled_when_no_endpoint(self):
        """Tracing is no-op when no OTLP endpoint configured."""
        env = {
            "OTEL_ENABLED": "true",
            # No OTEL_EXPORTER_OTLP_ENDPOINT
        }
        with mock.patch.dict(os.environ, env, clear=False):
            # Remove endpoint if it exists
            os.environ.pop("OTEL_EXPORTER_OTLP_ENDPOINT", None)
            # Should not raise
            init_tracing()

    def test_initializes_with_valid_config(self):
        """Tracing initializes when properly configured."""
        env = {
            "OTEL_ENABLED": "true",
            "OTEL_EXPORTER_OTLP_ENDPOINT": "http://localhost:4317",
            "OTEL_SERVICE_NAME": "test-service",
        }
        with mock.patch.dict(os.environ, env, clear=False):
            # Should not raise
            init_tracing()

    def test_idempotent(self):
        """Tracing can be initialized multiple times safely."""
        env = {
            "OTEL_ENABLED": "true",
            "OTEL_EXPORTER_OTLP_ENDPOINT": "http://localhost:4317",
        }
        with mock.patch.dict(os.environ, env, clear=False):
            # Should not raise on multiple calls
            init_tracing()
            init_tracing()
```

**Step 2: Run test to verify it fails**

Run: `cd /home/kettle/git_repos/website/.worktrees/backend-telemetry/backend && source ../.venv/bin/activate && DISABLE_CACHE=true python -m pytest telemetry/tests/test_tracing.py -v`

Expected: FAIL with import error

**Step 3: Implement tracing.py**

Create `backend/telemetry/tracing.py`:

```python
"""OpenTelemetry tracing configuration."""

import logging
import os
from typing import Optional

# Use stdlib logging for bootstrap messages
_log = logging.getLogger("telemetry.tracing")

# Track initialization state
_initialized = False


def _env_bool(key: str, default: bool = False) -> bool:
    """Parse boolean environment variable."""
    value = os.environ.get(key, "").lower()
    if value in ("true", "1", "yes"):
        return True
    if value in ("false", "0", "no"):
        return False
    return default


def init_tracing() -> None:
    """
    Initialize OpenTelemetry tracing.

    Configures OTLP exporter if OTEL_ENABLED=true and endpoint is configured.
    Safe to call multiple times - subsequent calls are no-ops.

    Environment Variables:
        OTEL_ENABLED: Enable tracing (default: false)
        OTEL_SERVICE_NAME: Service name (default: dtx-backend)
        OTEL_EXPORTER_OTLP_ENDPOINT: OTLP endpoint URL
        OTEL_EXPORTER_OTLP_HEADERS: Optional auth headers
        OTEL_TRACES_SAMPLER_ARG: Sample rate (default: 0.1 = 10%)
    """
    global _initialized

    if _initialized:
        return

    # Check if OTel is enabled
    if not _env_bool("OTEL_ENABLED", False):
        _log.info("OpenTelemetry disabled (OTEL_ENABLED not set or false)")
        _initialized = True
        return

    # Check for endpoint
    endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")
    if not endpoint:
        _log.info("OpenTelemetry disabled (no OTLP endpoint configured)")
        _initialized = True
        return

    try:
        # Import OTel modules
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.resources import Resource, SERVICE_NAME
        from opentelemetry.sdk.trace.sampling import TraceIdRatioBased

        # Get configuration
        service_name = os.environ.get("OTEL_SERVICE_NAME", "dtx-backend")
        sample_rate = float(os.environ.get("OTEL_TRACES_SAMPLER_ARG", "0.1"))
        headers = os.environ.get("OTEL_EXPORTER_OTLP_HEADERS", "")

        # Parse headers (format: "key1=value1,key2=value2")
        header_dict: dict[str, str] = {}
        if headers:
            for pair in headers.split(","):
                if "=" in pair:
                    key, value = pair.split("=", 1)
                    header_dict[key.strip()] = value.strip()

        # Create resource
        resource = Resource.create({
            SERVICE_NAME: service_name,
        })

        # Create sampler
        sampler = TraceIdRatioBased(sample_rate)

        # Create tracer provider
        provider = TracerProvider(
            resource=resource,
            sampler=sampler,
        )

        # Create exporter
        exporter = OTLPSpanExporter(
            endpoint=endpoint,
            headers=header_dict or None,
        )

        # Add processor
        provider.add_span_processor(BatchSpanProcessor(exporter))

        # Set global tracer provider
        trace.set_tracer_provider(provider)

        # Instrument Django
        try:
            from opentelemetry.instrumentation.django import DjangoInstrumentor
            DjangoInstrumentor().instrument()
        except Exception as e:
            _log.warning(f"Failed to instrument Django: {e}")

        # Instrument requests (for outbound HTTP)
        try:
            from opentelemetry.instrumentation.requests import RequestsInstrumentor
            RequestsInstrumentor().instrument()
        except Exception as e:
            _log.warning(f"Failed to instrument requests: {e}")

        # Instrument system metrics
        try:
            from opentelemetry.instrumentation.system_metrics import SystemMetricsInstrumentor
            SystemMetricsInstrumentor().instrument()
        except Exception as e:
            _log.warning(f"Failed to instrument system metrics: {e}")

        _log.info(
            f"OpenTelemetry initialized: endpoint={endpoint}, "
            f"service={service_name}, sample_rate={sample_rate}"
        )

    except ImportError as e:
        _log.warning(f"OpenTelemetry packages not available: {e}")
    except Exception as e:
        _log.error(f"Failed to initialize OpenTelemetry: {e}")

    _initialized = True
```

**Step 4: Run tests to verify they pass**

Run: `cd /home/kettle/git_repos/website/.worktrees/backend-telemetry/backend && source ../.venv/bin/activate && DISABLE_CACHE=true python -m pytest telemetry/tests/test_tracing.py -v`

Expected: All tests PASS

**Step 5: Commit**

```bash
cd /home/kettle/git_repos/website/.worktrees/backend-telemetry
git add backend/telemetry/tracing.py backend/telemetry/tests/test_tracing.py
git commit -m "feat(telemetry): add OpenTelemetry tracing configuration"
```

---

## Phase 6: WebSocket Telemetry

### Task 7: Implement WebSocket Consumer Mixin

**Files:**
- Create: `backend/telemetry/websocket.py`
- Create: `backend/telemetry/tests/test_websocket.py`

**Step 1: Write failing tests for WebSocket mixin**

Create `backend/telemetry/tests/test_websocket.py`:

```python
"""Tests for WebSocket telemetry mixin."""

from unittest import TestCase, mock
from unittest.mock import AsyncMock, MagicMock

import structlog

from telemetry.websocket import TelemetryConsumerMixin


class MockConsumer(TelemetryConsumerMixin):
    """Mock consumer for testing."""

    def __init__(self):
        self.scope = {
            "path": "/ws/draft/5/",
            "user": MagicMock(),
            "client": ("127.0.0.1", 12345),
        }
        self.scope["user"].is_authenticated = True
        self.scope["user"].pk = 42
        self.channel_layer = MagicMock()
        self.channel_name = "test_channel"


class TelemetryConsumerMixinTest(TestCase):
    """Tests for TelemetryConsumerMixin."""

    def test_connect_generates_connection_id(self):
        """Connect generates ws_conn_id."""
        consumer = MockConsumer()

        # Call connect (sync wrapper for test)
        import asyncio
        asyncio.get_event_loop().run_until_complete(consumer.telemetry_connect())

        self.assertIsNotNone(consumer.ws_conn_id)
        # Should be a string (UUID)
        self.assertIsInstance(consumer.ws_conn_id, str)

    def test_connect_extracts_labels(self):
        """Connect extracts labels from WebSocket path."""
        consumer = MockConsumer()

        import asyncio
        asyncio.get_event_loop().run_until_complete(consumer.telemetry_connect())

        self.assertEqual(consumer.ws_labels["labels"], ["draft"])
        self.assertEqual(consumer.ws_labels["draft.id"], 5)

    def test_connect_binds_user_context(self):
        """Connect binds user context when authenticated."""
        consumer = MockConsumer()

        import asyncio

        # Capture bound context
        bound_context = {}

        async def run_test():
            await consumer.telemetry_connect()
            ctx = structlog.contextvars.get_contextvars()
            bound_context.update(ctx)

        asyncio.get_event_loop().run_until_complete(run_test())

        self.assertEqual(bound_context.get("user.id"), 42)

    def test_disconnect_clears_context(self):
        """Disconnect clears structlog context."""
        consumer = MockConsumer()

        import asyncio

        async def run_test():
            await consumer.telemetry_connect()
            await consumer.telemetry_disconnect(1000)

        asyncio.get_event_loop().run_until_complete(run_test())

        # Context should be cleared
        ctx = structlog.contextvars.get_contextvars()
        self.assertNotIn("ws.conn_id", ctx)
```

**Step 2: Run test to verify it fails**

Run: `cd /home/kettle/git_repos/website/.worktrees/backend-telemetry/backend && source ../.venv/bin/activate && DISABLE_CACHE=true python -m pytest telemetry/tests/test_websocket.py -v`

Expected: FAIL with import error

**Step 3: Implement websocket.py**

Create `backend/telemetry/websocket.py`:

```python
"""WebSocket telemetry mixin for Django Channels consumers."""

import uuid
from typing import Any, Optional

import structlog

from telemetry.labels import extract_labels
from telemetry.logging import get_logger

log = get_logger(__name__)


class TelemetryConsumerMixin:
    """
    Mixin for Django Channels consumers that provides telemetry context.

    Add to your consumer class:
        class DraftConsumer(TelemetryConsumerMixin, AsyncWebsocketConsumer):
            async def connect(self):
                await self.telemetry_connect()
                await super().connect()

            async def disconnect(self, close_code):
                await self.telemetry_disconnect(close_code)
                await super().disconnect(close_code)

    Features:
    - Generates unique connection ID (ws_conn_id)
    - Extracts labels from WebSocket path
    - Binds context for all logs during connection
    - Logs connect/disconnect events
    """

    # These will be set during connect
    ws_conn_id: str
    ws_labels: dict[str, Any]

    # Expected to be provided by the consumer class
    scope: dict[str, Any]

    async def telemetry_connect(self) -> None:
        """
        Initialize telemetry context for WebSocket connection.

        Call this at the start of your connect() method.
        """
        # Generate connection ID
        self.ws_conn_id = str(uuid.uuid4())

        # Extract labels from WebSocket path
        path = self.scope.get("path", "")
        self.ws_labels = extract_labels(path.replace("/ws/", "/api/"))

        # Get user info if authenticated
        user = self.scope.get("user")
        user_id: Optional[int] = None
        if user and getattr(user, "is_authenticated", False):
            user_id = user.pk

        # Get client info
        client = self.scope.get("client", ("unknown", 0))
        client_ip = client[0] if client else "unknown"

        # Build context
        context: dict[str, Any] = {
            "ws.conn_id": self.ws_conn_id,
            **self.ws_labels,
        }
        if user_id is not None:
            context["user.id"] = user_id

        # Bind context to structlog
        structlog.contextvars.bind_contextvars(**context)

        # Log connection
        log.info("ws_connected", client_ip=client_ip)

    async def telemetry_disconnect(self, close_code: int) -> None:
        """
        Clean up telemetry context for WebSocket disconnection.

        Call this at the start of your disconnect() method.

        Args:
            close_code: WebSocket close code
        """
        log.info("ws_disconnected", close_code=close_code)

        # Clear context
        structlog.contextvars.clear_contextvars()

    async def telemetry_receive(self, text_data: Optional[str] = None) -> None:
        """
        Log received WebSocket message.

        Call this at the start of your receive() method if you want to log messages.

        Args:
            text_data: The received text data (truncated in logs)
        """
        # Log with truncated data to avoid huge log entries
        preview = text_data[:100] if text_data else None
        log.debug("ws_receive", data_preview=preview)
```

**Step 4: Run tests to verify they pass**

Run: `cd /home/kettle/git_repos/website/.worktrees/backend-telemetry/backend && source ../.venv/bin/activate && DISABLE_CACHE=true python -m pytest telemetry/tests/test_websocket.py -v`

Expected: All tests PASS

**Step 5: Commit**

```bash
cd /home/kettle/git_repos/website/.worktrees/backend-telemetry
git add backend/telemetry/websocket.py backend/telemetry/tests/test_websocket.py
git commit -m "feat(telemetry): add WebSocket consumer mixin"
```

---

## Phase 7: Celery Telemetry

### Task 8: Implement Celery Base Task

**Files:**
- Create: `backend/telemetry/celery.py`
- Create: `backend/telemetry/tests/test_celery.py`

**Step 1: Write failing tests for Celery task**

Create `backend/telemetry/tests/test_celery.py`:

```python
"""Tests for Celery telemetry base task."""

from unittest import TestCase, mock

import structlog

from telemetry.celery import TelemetryTask


class MockRequest:
    """Mock Celery request object."""
    id = "task-123"


class TelemetryTaskTest(TestCase):
    """Tests for TelemetryTask."""

    def test_binds_task_context(self):
        """Task binds task.id and task.name to context."""
        task = TelemetryTask()
        task.name = "test_task"
        task.request = MockRequest()

        bound_context = {}

        def capture_context():
            ctx = structlog.contextvars.get_contextvars()
            bound_context.update(ctx)
            return "result"

        with mock.patch.object(task, "run", capture_context):
            task()

        self.assertEqual(bound_context.get("task.id"), "task-123")
        self.assertEqual(bound_context.get("task.name"), "test_task")

    def test_accepts_propagated_request_id(self):
        """Task accepts _request_id from kwargs."""
        task = TelemetryTask()
        task.name = "test_task"
        task.request = MockRequest()

        bound_context = {}

        def capture_context():
            ctx = structlog.contextvars.get_contextvars()
            bound_context.update(ctx)
            return "result"

        with mock.patch.object(task, "run", capture_context):
            task(_request_id="propagated-123")

        self.assertEqual(bound_context.get("request.id"), "propagated-123")

    def test_accepts_propagated_user_id(self):
        """Task accepts _user_id from kwargs."""
        task = TelemetryTask()
        task.name = "test_task"
        task.request = MockRequest()

        bound_context = {}

        def capture_context():
            ctx = structlog.contextvars.get_contextvars()
            bound_context.update(ctx)
            return "result"

        with mock.patch.object(task, "run", capture_context):
            task(_user_id=42)

        self.assertEqual(bound_context.get("user.id"), 42)

    def test_clears_context_after_task(self):
        """Task clears context after completion."""
        task = TelemetryTask()
        task.name = "test_task"
        task.request = MockRequest()

        with mock.patch.object(task, "run", return_value="result"):
            task()

        ctx = structlog.contextvars.get_contextvars()
        self.assertNotIn("task.id", ctx)

    def test_clears_context_on_error(self):
        """Task clears context even on error."""
        task = TelemetryTask()
        task.name = "test_task"
        task.request = MockRequest()

        def raise_error():
            raise ValueError("test error")

        with mock.patch.object(task, "run", raise_error):
            with self.assertRaises(ValueError):
                task()

        ctx = structlog.contextvars.get_contextvars()
        self.assertNotIn("task.id", ctx)
```

**Step 2: Run test to verify it fails**

Run: `cd /home/kettle/git_repos/website/.worktrees/backend-telemetry/backend && source ../.venv/bin/activate && DISABLE_CACHE=true python -m pytest telemetry/tests/test_celery.py -v`

Expected: FAIL with import error

**Step 3: Implement celery.py**

Create `backend/telemetry/celery.py`:

```python
"""Celery telemetry base task with context binding."""

import uuid
from typing import Any, Optional

import structlog
from celery import Task

from telemetry.logging import get_logger

log = get_logger(__name__)


class TelemetryTask(Task):
    """
    Celery base task that binds telemetry context.

    Usage:
        @app.task(base=TelemetryTask)
        def my_task(arg1, arg2):
            log.info("doing work")
            return result

    Context Propagation:
        When calling the task, you can propagate context from a request:

        my_task.delay(
            arg1,
            arg2,
            _request_id=structlog.contextvars.get_contextvars().get("request.id"),
            _user_id=request.user.pk,
        )

    Bound Context:
        - task.id: Celery task ID
        - task.name: Task function name
        - request.id: Propagated or generated request ID
        - user.id: Propagated user ID (if provided)
    """

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        """Execute task with telemetry context."""
        # Extract telemetry kwargs (pop so they don't go to task)
        request_id = kwargs.pop("_request_id", None) or str(uuid.uuid4())
        user_id = kwargs.pop("_user_id", None)

        # Build context
        context: dict[str, Any] = {
            "task.id": self.request.id,
            "task.name": self.name,
            "request.id": request_id,
        }
        if user_id is not None:
            context["user.id"] = user_id

        # Bind context
        structlog.contextvars.bind_contextvars(**context)

        log.info("task_started")

        try:
            result = self.run(*args, **kwargs)
            log.info("task_completed")
            return result
        except Exception as e:
            log.error("task_failed", error=str(e), exc_info=True)
            raise
        finally:
            structlog.contextvars.clear_contextvars()
```

**Step 4: Run tests to verify they pass**

Run: `cd /home/kettle/git_repos/website/.worktrees/backend-telemetry/backend && source ../.venv/bin/activate && DISABLE_CACHE=true python -m pytest telemetry/tests/test_celery.py -v`

Expected: All tests PASS

**Step 5: Commit**

```bash
cd /home/kettle/git_repos/website/.worktrees/backend-telemetry
git add backend/telemetry/celery.py backend/telemetry/tests/test_celery.py
git commit -m "feat(telemetry): add Celery context-aware base task"
```

---

## Phase 8: Django Integration

### Task 9: Integrate Telemetry into Django Settings

**Files:**
- Modify: `backend/backend/settings.py`

**Step 1: Add telemetry initialization to settings.py**

Add at the end of `backend/backend/settings.py` (before any existing telemetry code):

```python
# =============================================================================
# Telemetry Configuration
# =============================================================================

# Initialize telemetry (structured logging + optional OTel tracing)
from telemetry.config import init_telemetry
init_telemetry()
```

**Step 2: Add TelemetryMiddleware to MIDDLEWARE**

In `backend/backend/settings.py`, add the middleware early in the MIDDLEWARE list (after SecurityMiddleware, before SessionMiddleware):

```python
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "telemetry.middleware.TelemetryMiddleware",  # Add this line
    "django.contrib.sessions.middleware.SessionMiddleware",
    # ... rest of middleware
]
```

**Step 3: Verify Django starts successfully**

Run: `cd /home/kettle/git_repos/website/.worktrees/backend-telemetry/backend && source ../.venv/bin/activate && DISABLE_CACHE=true python manage.py check`

Expected: `System check identified no issues.`

**Step 4: Verify logs are structured**

Run: `cd /home/kettle/git_repos/website/.worktrees/backend-telemetry/backend && source ../.venv/bin/activate && DISABLE_CACHE=true python -c "from telemetry.logging import get_logger; log = get_logger('test'); log.info('test_event', key='value')"`

Expected: Structured log output with timestamp, level, event, key

**Step 5: Commit**

```bash
cd /home/kettle/git_repos/website/.worktrees/backend-telemetry
git add backend/backend/settings.py
git commit -m "feat(telemetry): integrate into Django settings"
```

---

### Task 10: Integrate Telemetry into ASGI

**Files:**
- Modify: `backend/backend/asgi.py`

**Step 1: Add telemetry initialization to asgi.py**

Modify `backend/backend/asgi.py` to ensure telemetry is initialized for WebSocket workers:

```python
"""
ASGI config for backend project.
"""

import os

from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter, URLRouter
from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.settings")

# Initialize Django ASGI application early to ensure settings are loaded
django_asgi_app = get_asgi_application()

# Initialize telemetry for WebSocket workers
from telemetry.config import init_telemetry
init_telemetry()

# Import routing after Django is initialized
from app.routing import websocket_urlpatterns

application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        "websocket": AuthMiddlewareStack(URLRouter(websocket_urlpatterns)),
    }
)
```

**Step 2: Verify ASGI loads**

Run: `cd /home/kettle/git_repos/website/.worktrees/backend-telemetry/backend && source ../.venv/bin/activate && DISABLE_CACHE=true python -c "from backend.asgi import application; print('ASGI loaded')"`

Expected: `ASGI loaded`

**Step 3: Commit**

```bash
cd /home/kettle/git_repos/website/.worktrees/backend-telemetry
git add backend/backend/asgi.py
git commit -m "feat(telemetry): integrate into ASGI for WebSocket workers"
```

---

### Task 11: Update WebSocket Consumers

**Files:**
- Modify: `backend/app/consumers.py`

**Step 1: Add mixin to DraftConsumer**

Update `backend/app/consumers.py` to use the telemetry mixin:

```python
# Add import at top
from telemetry.websocket import TelemetryConsumerMixin

# Update DraftConsumer class
class DraftConsumer(TelemetryConsumerMixin, AsyncWebsocketConsumer):
    async def connect(self):
        await self.telemetry_connect()  # Add this line
        # ... existing connect code ...

    async def disconnect(self, close_code):
        await self.telemetry_disconnect(close_code)  # Add this line
        # ... existing disconnect code ...
```

**Step 2: Add mixin to TournamentConsumer**

```python
class TournamentConsumer(TelemetryConsumerMixin, AsyncWebsocketConsumer):
    async def connect(self):
        await self.telemetry_connect()  # Add this line
        # ... existing connect code ...

    async def disconnect(self, close_code):
        await self.telemetry_disconnect(close_code)  # Add this line
        # ... existing disconnect code ...
```

**Step 3: Verify consumers still work**

Run: `cd /home/kettle/git_repos/website/.worktrees/backend-telemetry/backend && source ../.venv/bin/activate && DISABLE_CACHE=true python -c "from app.consumers import DraftConsumer, TournamentConsumer; print('Consumers loaded')"`

Expected: `Consumers loaded`

**Step 4: Commit**

```bash
cd /home/kettle/git_repos/website/.worktrees/backend-telemetry
git add backend/app/consumers.py
git commit -m "feat(telemetry): add telemetry mixin to WebSocket consumers"
```

---

## Phase 9: Environment Configuration

### Task 12: Update Environment Files

**Files:**
- Modify: `backend/.env.example`
- Modify: `docker/.env.dev`
- Modify: `docker/.env.test`
- Modify: `docker/.env.prod`

**Step 1: Create/update backend/.env.example**

Create or update `backend/.env.example`:

```bash
# Existing secrets (not shown for security)
# client_id=...
# discord_secret=...
# discord_token=...
# STEAM_API_KEY=...

# =============================================================================
# Telemetry Configuration
# =============================================================================

# Master switch for telemetry (default: true for logging)
TELEMETRY_ENABLED=true

# Logging configuration
LOG_LEVEL=INFO
LOG_FORMAT=pretty  # 'pretty' for dev, 'json' for prod

# OpenTelemetry (disabled by default - enable when collector available)
OTEL_ENABLED=false
OTEL_SERVICE_NAME=dtx-backend
# OTEL_EXPORTER_OTLP_ENDPOINT=https://otlp-gateway-prod-us-central-0.grafana.net/otlp
# OTEL_EXPORTER_OTLP_HEADERS=Authorization=Basic <base64-encoded-credentials>
# OTEL_TRACES_SAMPLER_ARG=0.1
```

**Step 2: Update docker/.env.dev**

Add to `docker/.env.dev`:

```bash
# Telemetry
LOG_FORMAT=pretty
LOG_LEVEL=DEBUG
OTEL_ENABLED=false
```

**Step 3: Update docker/.env.test**

Add to `docker/.env.test`:

```bash
# Telemetry
LOG_FORMAT=json
LOG_LEVEL=INFO
OTEL_ENABLED=false
```

**Step 4: Update docker/.env.prod**

Add to `docker/.env.prod`:

```bash
# Telemetry
LOG_FORMAT=json
LOG_LEVEL=ERROR
OTEL_ENABLED=false
```

**Step 5: Commit**

```bash
cd /home/kettle/git_repos/website/.worktrees/backend-telemetry
git add backend/.env.example docker/.env.dev docker/.env.test docker/.env.prod
git commit -m "config(telemetry): add environment variables"
```

---

### Task 13: Add Local Observability Stack

**Files:**
- Create: `docker/docker-compose.observability.yaml`

**Step 1: Create observability compose file**

Create `docker/docker-compose.observability.yaml`:

```yaml
# Optional local observability stack for development
# Usage: docker compose -f docker/docker-compose.observability.yaml up -d
#
# Then set in your .env:
#   OTEL_ENABLED=true
#   OTEL_EXPORTER_OTLP_ENDPOINT=http://jaeger:4317

services:
  jaeger:
    image: jaegertracing/all-in-one:latest
    container_name: jaeger
    ports:
      - "16686:16686"  # Jaeger UI
      - "4317:4317"    # OTLP gRPC
      - "4318:4318"    # OTLP HTTP
    environment:
      COLLECTOR_OTLP_ENABLED: "true"
    networks:
      - observability

networks:
  observability:
    name: observability
```

**Step 2: Verify compose file is valid**

Run: `cd /home/kettle/git_repos/website/.worktrees/backend-telemetry && docker compose -f docker/docker-compose.observability.yaml config`

Expected: Valid YAML output

**Step 3: Commit**

```bash
cd /home/kettle/git_repos/website/.worktrees/backend-telemetry
git add docker/docker-compose.observability.yaml
git commit -m "config(telemetry): add local Jaeger observability stack"
```

---

## Phase 10: Documentation

### Task 14: Create Telemetry Documentation

**Files:**
- Create: `docs/dev/telemetry/index.md`
- Create: `docs/dev/telemetry/architecture.md`
- Create: `docs/dev/telemetry/logging.md`
- Create: `docs/dev/telemetry/tracing.md`
- Create: `docs/dev/telemetry/context.md`
- Create: `docs/dev/telemetry/local-observability.md`
- Create: `docs/dev/telemetry/reference.md`
- Modify: `mkdocs.yml`

**Step 1: Create docs/dev/telemetry/ directory**

Run: `mkdir -p /home/kettle/git_repos/website/.worktrees/backend-telemetry/docs/dev/telemetry`

**Step 2: Create index.md**

Create `docs/dev/telemetry/index.md`:

```markdown
# Telemetry

DTX uses structured logging and optional distributed tracing for observability.

## Quick Start

### Logging in Your Code

```python
from telemetry.logging import get_logger

log = get_logger(__name__)

def my_function():
    log.info("processing_request", user_id=42, action="create")
```

### What Gets Logged Automatically

- All HTTP requests with timing, status, and context
- WebSocket connections and disconnections
- Celery task lifecycle (start, complete, fail)

## Features

| Feature | Status | Description |
|---------|--------|-------------|
| Structured Logging | ✅ Enabled | JSON logs in prod, pretty in dev |
| Request Context | ✅ Enabled | request.id, user.id, URL labels |
| WebSocket Context | ✅ Enabled | Connection tracking |
| Celery Context | ✅ Enabled | Task tracking |
| OpenTelemetry | ⚡ Opt-in | Distributed tracing |

## Documentation

- [Architecture](architecture.md) - Design decisions and data flow
- [Logging Guide](logging.md) - How to add logging to code
- [Tracing Guide](tracing.md) - OpenTelemetry setup
- [Context Guide](context.md) - Adding context to new endpoints
- [Local Observability](local-observability.md) - Running Jaeger locally
- [Reference](reference.md) - Environment variable reference
```

**Step 3: Create architecture.md**

Create `docs/dev/telemetry/architecture.md`:

```markdown
# Telemetry Architecture

## Overview

The telemetry system provides consistent observability across all backend components.

```
┌─────────────────────────────────────────────────────────────────┐
│                        Django Application                        │
├─────────────────────────────────────────────────────────────────┤
│  HTTP Request    │  WebSocket     │  Celery Task               │
│  ↓               │  ↓             │  ↓                          │
│  Middleware      │  Mixin         │  Base Task                  │
│  ↓               │  ↓             │  ↓                          │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │              Context Binding (structlog.contextvars)      │  │
│  │  request.id │ user.id │ labels │ tournament.id │ etc.    │  │
│  └───────────────────────────────────────────────────────────┘  │
│                              ↓                                   │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │                    structlog Processors                    │  │
│  │  timestamp │ level │ logger name │ format (JSON/pretty)   │  │
│  └───────────────────────────────────────────────────────────┘  │
│                              ↓                                   │
│  ┌─────────────────────┐  ┌────────────────────────────────┐   │
│  │  stdout (logs)       │  │  OTLP Exporter (traces)        │   │
│  │  JSON in prod        │  │  If OTEL_ENABLED=true          │   │
│  │  Pretty in dev       │  │  → Grafana Cloud / Jaeger      │   │
│  └─────────────────────┘  └────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

## Components

### 1. Label Extraction (`telemetry/labels.py`)

Parses URL paths to extract contextual metadata:

```python
extract_labels("/api/tournaments/5/draft/12/")
# → {"labels": ["tournament", "draft"], "tournament.id": 5, "draft.id": 12}
```

### 2. Request Middleware (`telemetry/middleware.py`)

Binds context to every HTTP request:

- Generates or accepts `request.id`
- Extracts `user.id` from session
- Extracts labels from URL
- Logs request completion with timing

### 3. WebSocket Mixin (`telemetry/websocket.py`)

Adds context to WebSocket connections:

- Generates `ws.conn_id`
- Extracts labels from path
- Logs connect/disconnect events

### 4. Celery Base Task (`telemetry/celery.py`)

Binds context to background tasks:

- Accepts propagated `request.id` and `user.id`
- Logs task lifecycle events

## Design Principles

1. **Safe by default**: No crashes if telemetry misconfigured
2. **Opt-in tracing**: OTel disabled unless explicitly enabled
3. **Consistent context**: Same fields everywhere
4. **OTel conventions**: Field names follow semantic conventions
```

**Step 4: Create remaining documentation files**

Create `docs/dev/telemetry/logging.md`:

```markdown
# Logging Guide

## Getting a Logger

```python
from telemetry.logging import get_logger

log = get_logger(__name__)
```

## Logging Events

```python
# Basic event
log.info("user_created", user_id=42)

# With context
log.info("tournament_started", tournament_id=5, player_count=10)

# Errors with exception info
try:
    risky_operation()
except Exception as e:
    log.error("operation_failed", error=str(e), exc_info=True)
```

## Log Levels

| Level | Use For |
|-------|---------|
| `debug` | Detailed debugging info (dev only) |
| `info` | Normal operations, business events |
| `warning` | Unexpected but handled situations |
| `error` | Failures that need attention |

## Context Fields

These are automatically added by middleware:

| Field | Source |
|-------|--------|
| `request.id` | Generated or from X-Request-ID header |
| `user.id` | From authenticated session |
| `labels` | Extracted from URL path |
| `tournament.id` | From URL `/api/tournaments/{id}/` |
| `draft.id` | From URL `/api/drafts/{id}/` |
| etc. | Other resource IDs from URL |

## Output Formats

**Dev (pretty):**
```
2026-01-20 14:32:15 [info] user_created
    user_id=42 request.id=abc-123
```

**Prod (JSON):**
```json
{"timestamp":"2026-01-20T14:32:15Z","level":"info","event":"user_created","user_id":42,"request.id":"abc-123"}
```
```

Create `docs/dev/telemetry/tracing.md`:

```markdown
# Tracing Guide

## Overview

OpenTelemetry tracing is opt-in. When enabled, it sends trace data to an OTLP-compatible collector.

## Enabling Tracing

Set these environment variables:

```bash
OTEL_ENABLED=true
OTEL_EXPORTER_OTLP_ENDPOINT=https://your-collector-url
OTEL_EXPORTER_OTLP_HEADERS=Authorization=Basic xxx
```

## What Gets Traced

When enabled:

- Django HTTP requests (automatic)
- Outbound HTTP calls (automatic)
- System metrics (CPU, memory)

## Sample Rate

Control trace sampling with:

```bash
OTEL_TRACES_SAMPLER_ARG=0.1  # 10% of traces
```

## Local Development

See [Local Observability](local-observability.md) for running Jaeger locally.
```

Create `docs/dev/telemetry/context.md`:

```markdown
# Adding Context Guide

## Adding Labels for New URL Patterns

Edit `backend/telemetry/labels.py`:

```python
RESOURCE_PATTERNS = [
    # Add your new pattern
    (r"/myresource/(\d+)", "myresource"),
    # ...
]
```

## Adding Context in Views

```python
from telemetry.logging import get_logger
import structlog

log = get_logger(__name__)

def my_view(request, pk):
    # Add custom context for this request
    structlog.contextvars.bind_contextvars(
        custom_field="value",
    )

    log.info("view_action")  # Will include custom_field
```

## Propagating Context to Celery

```python
import structlog
from myapp.tasks import my_task

def my_view(request):
    ctx = structlog.contextvars.get_contextvars()

    my_task.delay(
        arg1,
        _request_id=ctx.get("request.id"),
        _user_id=request.user.pk,
    )
```
```

Create `docs/dev/telemetry/local-observability.md`:

```markdown
# Local Observability

## Running Jaeger Locally

Start the local observability stack:

```bash
docker compose -f docker/docker-compose.observability.yaml up -d
```

Access Jaeger UI at: http://localhost:16686

## Connecting Your App

Set environment variables:

```bash
OTEL_ENABLED=true
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317
```

## Stopping

```bash
docker compose -f docker/docker-compose.observability.yaml down
```
```

Create `docs/dev/telemetry/reference.md`:

```markdown
# Environment Variable Reference

## Logging

| Variable | Default | Description |
|----------|---------|-------------|
| `TELEMETRY_ENABLED` | `true` | Master switch for telemetry |
| `LOG_LEVEL` | `INFO` | Minimum log level |
| `LOG_FORMAT` | auto | `json` or `pretty` (auto-detected from NODE_ENV) |

## OpenTelemetry

| Variable | Default | Description |
|----------|---------|-------------|
| `OTEL_ENABLED` | `false` | Enable distributed tracing |
| `OTEL_SERVICE_NAME` | `dtx-backend` | Service name in traces |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | — | OTLP collector URL |
| `OTEL_EXPORTER_OTLP_HEADERS` | — | Auth headers (format: `key=value,key2=value2`) |
| `OTEL_TRACES_SAMPLER_ARG` | `0.1` | Sample rate (0.1 = 10%) |

## Per-Environment Defaults

| Variable | Dev | Test | Prod |
|----------|-----|------|------|
| `LOG_FORMAT` | `pretty` | `json` | `json` |
| `LOG_LEVEL` | `DEBUG` | `INFO` | `ERROR` |
| `OTEL_ENABLED` | `false` | `false` | `false` |
```

**Step 5: Update mkdocs.yml**

Add to the `nav` section of `mkdocs.yml`:

```yaml
nav:
  # ... existing nav items ...
  - Development:
    # ... existing dev items ...
    - Telemetry:
      - Overview: dev/telemetry/index.md
      - Architecture: dev/telemetry/architecture.md
      - Logging Guide: dev/telemetry/logging.md
      - Tracing Guide: dev/telemetry/tracing.md
      - Context Guide: dev/telemetry/context.md
      - Local Observability: dev/telemetry/local-observability.md
      - Reference: dev/telemetry/reference.md
```

**Step 6: Verify docs build**

Run: `cd /home/kettle/git_repos/website/.worktrees/backend-telemetry && source .venv/bin/activate && mkdocs build`

Expected: Builds without errors

**Step 7: Commit**

```bash
cd /home/kettle/git_repos/website/.worktrees/backend-telemetry
git add docs/dev/telemetry/ mkdocs.yml
git commit -m "docs(telemetry): add comprehensive documentation"
```

---

## Phase 11: Final Verification

### Task 15: Run All Tests

**Step 1: Run all telemetry tests**

Run: `cd /home/kettle/git_repos/website/.worktrees/backend-telemetry/backend && source ../.venv/bin/activate && DISABLE_CACHE=true python -m pytest telemetry/tests/ -v`

Expected: All tests PASS

**Step 2: Run all backend tests**

Run: `cd /home/kettle/git_repos/website/.worktrees/backend-telemetry/backend && source ../.venv/bin/activate && DISABLE_CACHE=true python manage.py test app.tests -v 2 --parallel`

Expected: All existing tests still PASS

**Step 3: Verify Django starts**

Run: `cd /home/kettle/git_repos/website/.worktrees/backend-telemetry/backend && source ../.venv/bin/activate && DISABLE_CACHE=true timeout 5 python manage.py runserver 0.0.0.0:8001 || true`

Expected: Server starts, logs show structured output

---

### Task 16: Final Commit and Summary

**Step 1: Ensure all changes are committed**

Run: `cd /home/kettle/git_repos/website/.worktrees/backend-telemetry && git status`

Expected: Nothing to commit (working tree clean)

**Step 2: View commit history**

Run: `cd /home/kettle/git_repos/website/.worktrees/backend-telemetry && git log --oneline -15`

Expected: Series of well-organized commits

---

## Summary

After completing all tasks, the backend telemetry system provides:

1. **Structured Logging** - JSON in prod, pretty in dev
2. **Request Context** - Automatic binding of request.id, user.id, URL labels
3. **WebSocket Telemetry** - Connection lifecycle tracking
4. **Celery Telemetry** - Task context propagation
5. **OpenTelemetry Tracing** - Opt-in distributed tracing
6. **System Metrics** - CPU/memory when OTel enabled
7. **Documentation** - Comprehensive guides in MkDocs

Files created/modified:
- `backend/telemetry/` - New module (8 files)
- `backend/backend/settings.py` - Integration
- `backend/backend/asgi.py` - WebSocket integration
- `backend/app/consumers.py` - Mixin added
- `docker/` - Environment configs
- `docs/dev/telemetry/` - Documentation (7 files)
