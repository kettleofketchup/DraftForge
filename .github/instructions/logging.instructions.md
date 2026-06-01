---
applyTo: "backend/**/*.py"
---

# Structured logging (structlog → OpenTelemetry)

Canonical: `.claude/skills/logging/SKILL.md`. Backend logs are structured JSON
exported to Grafana Cloud via OpenTelemetry. Base stdlib `logging` bypasses that
pipeline, so logs never reach Grafana.

## Rules

- **Never `import logging` / `logging.getLogger(__name__)`** (except management
  commands — see "Out of scope" below). Use
  `from telemetry.logging import get_logger` then `log = get_logger(__name__)`.
  This is enforced by ruff (`TID251` bans `logging.getLogger`); Copilot is the
  backup reviewer.
- **Event name first, context in kwargs.** The first positional arg is a
  snake_case event name (`"broadcast_sent"`), not a sentence. **No f-strings or
  `%` formatting** in log calls — pass data as kwargs.
- **Every log needs `system` and `subsystem` kwargs** — the primary Grafana
  filter dimensions. Keep `system` coarse (feature area), `subsystem` functional.
- **Include relevant entity IDs**: `draft_id`, `user_id`/`username`, `event_id`,
  `tournament_id`, `reason` (for skipped/failed actions), `error=str(e)` (never
  the full traceback).
- **Pick the right level**: `DEBUG` (per-request/tick detail, not exported in
  prod), `INFO` (state transitions/lifecycle), `WARNING` (self-recovering
  anomalies), `ERROR` (failures needing attention).

## Out of scope here

- **Management commands** (`backend/**/management/commands/*.py`) are one-off CLI
  tools, not part of the OTEL-exported request/task flow — they may keep stdlib
  `logging` and `self.stdout.write`. They're excluded from the ruff ban too.
- Caching, testing, and migration patterns — see their own `.instructions.md`.

Canonical source: `.claude/skills/logging/SKILL.md` — update there first.
