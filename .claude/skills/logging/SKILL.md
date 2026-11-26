---
name: logging
description: Structured logging conventions for DraftForge backend (Django/Celery/Daphne) and frontend (React). This skill should be used when adding log statements, creating new modules, debugging with logs, or reviewing logging patterns. Covers structlog usage, system/subsystem taxonomy, required fields, log levels, and Grafana query patterns.
---

# Structured Logging

DraftForge uses **structlog** (backend) for structured JSON logging exported to Grafana Cloud via OpenTelemetry. All logs use a `system`/`subsystem` taxonomy for filtering.

## Backend: Quick Start

```python
from telemetry.logging import get_logger
log = get_logger(__name__)

# Structured log — event name first, then kwargs
log.info("order_created", system="tournament", subsystem="registration", draft_id=5, user_id=42)
```

**Never use f-strings or `%` formatting in log messages.** The first argument is always an event name (snake_case). All context goes in kwargs.

## System / Subsystem Taxonomy

Every log MUST include `system` and `subsystem` kwargs. These are the primary Grafana filter dimensions.

> **Two-axis taxonomy:** `system` / `subsystem` answer *where the code lives* (single value, label-friendly). `tags: list[str]` is an optional secondary axis answering *what domains this log concerns* (multi-value, for cross-cutting queries like "show me everything related to signups"). When tags are set, also set `tags_csv` (comma-joined string) for clean LogQL `=~` filtering (Loki's `| json` flattens lists as `tags_0`, `tags_1` which is awkward to filter). Bind tags via `discord_log_context` for interaction-flow logs, or pass explicitly for one-off cross-cutting logs.

| system | subsystem | tags | Where | What |
|--------|-----------|------|-------|------|
| `herodraft` | `connection` | — | `draft/consumers/hero.py` | WS connect/disconnect, captain state (kicks now under websocket/connection) |
| `herodraft` | `heartbeat` | — | `draft/tasks/hero_tick.py` | Heartbeat staleness checks, heartbeat-triggered pauses |
| `herodraft` | `timer` | — | `draft/tasks/hero_tick.py` (driver) + `draft/tasks/draft_tick.py` (loop) | Tick loop lifecycle, tick broadcast, timeout auto-pick, resume |
| `websocket` | `heartbeat` | — | `draft/consumers/base.py` | Heartbeat receive, captain register/unregister (generic WS infra) |
| `websocket` | `connection` | — | `telemetry/websocket.py`, `draft/consumers/base.py` | Generic WS connect/disconnect/receive instrumentation; captain kick send/failure (captain_kicked, captain_kick_failed) |
| `websocket` | `timer` | — | `draft/tasks/draft_tick.py` | Shared tick runner: connection counts (connection_count_incremented, connection_count_decremented), registry shutdown (tick_broadcasters_shutdown) |
| `teamdraft` | `connection` | — | `draft/consumers/team.py` (DraftConsumer) | Team-draft WS connect/disconnect, heartbeat frames, malformed messages; captain presence (teamdraft_captain_connected, teamdraft_captain_disconnected, teamdraft_captain_presence_restored, captain_conn_count_negative) |
| `teamdraft` | `timer` | — | `draft/tasks/team_tick.py`, `draft/services/team.py`, `draft/services/team_timeout.py`, `draft/tasks/draft_tick.py` (evaluate_client_pick_time), `draft/views/team_picks.py` | Team-draft tick loop, round activation, pick timing, timeout skip; client pick-time rejects (pick_time_naive_datetime, pick_time_in_future, pick_time_too_old) |
| `teamdraft` | `heartbeat` | — | `draft/tasks/team_tick.py` | Active-captain heartbeat staleness → auto-pause |
| `teamdraft` | `view` | — | `draft/views/team.py` | ready/start/pause/resume HTTP actions |
| `herodraft` | `view` | — | `draft/views/hero.py` | HeroDraft HTTP actions: create, roll, choice/pick submit, abandon, reset |
| `celery` | `task` | — | `telemetry/celery.py` | Generic Celery task lifecycle bookends (started/completed/failed) |
| `events` | `discord` | — | `events/tasks.py` (cron sync, non-interaction tasks like `sync_discord_events`) | Cron-driven event sync to Discord that isn't triggered by an interaction |
| `events` | `voice_presence` | — | `events/voice_presence.py` | State/snapshot applied, channel missing, heartbeat unavailable, manual set, confirm skipped |
| `discord` | `voice` | — | `discordbot/voice_feed.py`, `discordbot/bot.py` | Watched refresh, state reports, snapshots posted/skipped, queue full, worker failures |
| `events` | `scheduling` | — | `events/tasks.py`, `events/management/` | Event generation, signup opening, repeaters |
| `events` | `eligibility` | — | `events/eligibility/evaluate.py` | `eligibility_evaluated`: reason `codes` and `admissible` for every signup evaluation |
| `tournament` | `discord` | — | `discordbot/tasks.py` | Tournament DMs, bracket notifications |
| `avatars` | `endpoint` | — | `user/internal/avatar.py` | Internal endpoints: list-linked-users, list-guild-ids, bulk-update + invalidate |
| `avatars` | `refresh` | — | `user/tasks/avatar_refresh.py::refresh_avatars_batched` | Daily Celery beat: read guild-member cache, diff against DB, POST bulk-update |
| `avatars` | `single` | — | `user/tasks/avatar_refresh.py::refresh_single_user_avatar` + helpers | Single-user refresh: Discord API fetch + per-user `update_user_avatar` |
| `avatars` | `legacy` | — | `user/tasks/avatar_refresh.py::refresh_discord_avatars` / `refresh_all_discord_data` | Older per-user fanout tasks (predates the batched path) |
| `discord` | `lease` | — | `discordbot/tasks.py`, `app/views/internal.py` | DiscordMessageLog stale-lease sweep (pending NULL >5min, failed >1h) |
| `discord` | `interaction` | `["events","signup"]` | `discordbot/components/{base,dota,deadlock,default,registry}.py`, `discordbot/signup_responses.py`, `discordbot/log_context.py`, `events/discord/providers/`, `events/discord/handlers.py`, `events/discord/_shared.py` | Discord-bot UI plumbing (per-game provider modules) + response delivery + signup-flow business logic: button/modal/select callbacks and their handlers. Per-game flows are tag-differentiated, NOT new subsystems. |
| `discord` | `dispatch` | `["events","signup"]` | `events/discord/dispatch.py`, `events/signup_post_lock.py` (mark/clear pending), `discordbot/internal_voice_views.py` | `notify_*` dispatch visibility (queued vs skipped); threads `interaction_id` to Celery |
| `discord` | `celery` | `["events","signup"]` | `events/tasks.py` (Discord-dispatching tasks), `events/signup_post_lock.py` (acquire/release lock) | `celery_task_started/finished/failed/retry` bookend logs |
| `cache` | `invalidate` | — | `app/cache_utils.py` | Per-object cacheops invalidation fired from `transaction.on_commit` |
| `websocket` | `broadcast` | — | `draft/services/team_broadcast.py`, `draft/services/hero_broadcast.py` | Draft / herodraft event + state broadcast to channel groups (`kind` field distinguishes draft/herodraft/herodraft_state) |
| `auth` | `internal` | — | `app/auth.py` | Internal-service auth (X-Internal-Token): IP-allowlist rejects, invalid-token failures |
| `auth` | `social` | — | `user/pipelines.py` | Discord OAuth social-auth pipeline: account reclaim/merge, username matching |
| `auth` | `merge` | — | `user/discord_accounts.py` | Discord account de-dup / merge |
| `tournament` | `draft`, `registration`, `user` | — | `app/models.py`, `tournament/functions.py`, `user/views_avatar.py`, `draft/models/team.py`, `draft/views/team_setup.py`, `draft/views/team_picks.py` | Draft build/pick/rebuild, captain/team registration, per-user avatar refresh |
| `api` | `serializer`, `routing`, `main`, `csv_import` | — | `user/serializers.py`, `user/views_account.py`, `app/views*.py`, `tournament/serializers/*.py`, `tournament/views/*.py`, `tournament/views/csv_import.py`, `backend/urls.py` | DRF serializer mutations, view cache-miss, CSV import, env/routing |
| `user` | `functions` | — | `user/views_profile.py` | Profile-update request/validate/apply |
| `app` | `signals` | — | `tournament/signals.py`, `draft/signals.py` | Model signal handlers (org/league user create, herodraft cleanup) |
| `internal_client` | `http` | — | `app/internal_client/` (`transport.py` and per-domain modules) | Internal HTTP client errors and JSON-parse failures |
| `discord` | `bot`, `utils`, `views`, `channels`, `roles`, `users` | — | `discordbot/**` | Bot lifecycle, message utils, slash views, channel/role/user services |
| `events` | `tasks`, `services`, `views`, `dispatch` | — | `events/**` | Event task lifecycle, signup services, manual fire, tournament-link dispatch, `event_staff_deduped` (host/helper dedupe after merges) |
| `events` | `services` | — | `events/admission.py` | Self sign-up refusals: event closed or self-serve off (`signup_self_serve_refused`, with `reason`), and blocking eligibility reasons such as conduct's block (`signup_eligibility_refused`, with `codes`) |
| `events` | `overrides` | — | `events/overrides.py` | Staff override policy check (`override_checked`) and blocks (`override_blocked`) |
| `steam` | `api`, `game_linking`, `match`, `mmr`, `stats`, `model`, `league_sync`, `retry`, `ingest` | — | `steam/**` | Steam API, account/game linking, match fetch/store, MMR/stats (league recompute skips staff-verified rows: `league_mmr_recompute_skipped_verified`), league sync, retry, internal store_match ingest |
| `bracket` | `generate`, `model` | — | `bracket/**` | Bracket generation + model-level cache logging |
| `org` | `views` | — | `org/views.py` | Org admin actions (user delete/merge) |
| `org` | `features` | — | `org/features.py` | Locked feature switch writes (`org_feature_set`, after commit) |
| `org` | `settings` | — | `org/settings_service.py` | OrgSettings lazy create and admin updates |
| `org` | `promoters` | — | `org/views_features.py` | Promoter add/remove (`org_promoter_added`, `org_promoter_removed`) |
| `org` | `contributions` | — | `org/contributions/services.py` | Ledger writes: awards, host/helper sync, manual award edit/delete, point values and rescores, merge reassign, user-delete cleanup |
| `org` | `standing` | — | `org/standing/periods.py` | Invalid org timezone fallback (`org_timezone_invalid`) |
| `org` | `promotion` | — | `org/promotion/services.py`, `org/promotion/views.py`, `org/promotion/starter.py` | Promo send record/undo, merge demotions, template create/update/delete, starter template seeding. Never message text |
| `org` | `conduct` | — | `org/conduct/{capture,lifecycle,finalize,sources,services}.py` | Attendance outcomes: late-cancel capture/ignore (`conduct_late_cancel_captured`, `conduct_late_cancel_ignored`), staff edits (`conduct_outcomes_set`), finalize (`conduct_event_finalized`, `conduct_auto_source_skipped`), void/delete/reopen (`conduct_event_voided`, `conduct_event_deleted`, `conduct_event_reopened`), settings (`conduct_settings_updated`), merge reassign (`conduct_member_reassigned`). Never staff reasons |
| `org` | `leadership` | — | `org/leadership/{lifecycle,reviews,maintenance,settings,traits}.py` | Captain snapshots and review lifecycle: close/void/delete (`leadership_event_snapshotted`, `leadership_event_voided`, `leadership_event_rows_deleted`, warning `leadership_duplicate_captain`), reviews (`captain_review_submitted`, `captain_review_withdrawn`, `captain_review_voided`, `captain_review_unvoided`, `captain_rating_upserted`; the rater id only on debug `captain_review_rater`), settings and traits after commit (`leadership_settings_updated`, `leadership_traits_updated`, `leadership_trait_deleted`), merge and user delete (`leadership_member_reassigned`, `leadership_deleted_for_user`). Never a rater id at info, never void reasons |
| `org` | `mmr` | — | `org/mmr.py`, `org/mmr_official.py` | Per-game org MMR writes, claim merge, unprefetched-read tripwire, verification markers (`org_mmr_set`, `org_mmr_merged`, `org_mmr_unprefetched`, `org_mmr_marked_verified`, `org_mmr_reverified`) |
| `org` | `mmr_requests` | — | `org/mmr_requests/*.py`, `org/mmr_official.py` | MMR change requests: create/cancel/approve/reject/staff set (`mmr_request_created`, `mmr_request_cancelled`, `mmr_request_approved`, `mmr_request_rejected`, `mmr_request_staff_set`), supersede/repoint/membership-delete cancel (`mmr_requests_superseded`, `mmr_requests_repointed`, `mmr_requests_cancelled_membership_deleted`), upload guard and screenshot sanitizer refusals (`mmr_upload_body_too_large`, `mmr_screenshot_sanitizer_busy`, `mmr_screenshot_storage_full`, `mmr_screenshot_storage_unavailable`). Never notes, rejection reasons or file paths |
| `league` | `mmr` | — | `league/mmr.py` | League MMR writes and membership merges (`league_mmr_set`, `league_mmr_merged`) |
| `org` | `mmr` | — | `org/mmr.py` | Per-game org MMR writes, claim merge, unprefetched-read tripwire, cache-invalidation failures (`org_mmr_set`, `org_mmr_merged`, `org_mmr_unprefetched`, warning `org_mmr_invalidate_failed`) |
| `lobby` | `client` | — | `lobby/client.py` | dota_lobby API calls: failed requests with the problem `code`, `retryable` and retry attempt (never bodies, passwords or the API key) |
| `lobby` | `api`, `webhook`, `events`, `broadcast`, `signals` | — | `lobby/views_internal.py`, `lobby/events.py`, `lobby/broadcast.py`, `lobby/signals.py` | Internal lobby API (claim/accepted/conflict), webhook receiver (bad signature, ignored, applied), event application (`lobby_gameid_conflict`), websocket broadcast failures, auto-create/close/flip triggers. Never the lobby password |
| `lobby` | `views` | — | `lobby/views.py` | Organizer and player lobby API: create/close/launch/invite requests and dota_lobby errors they hit (problem `code`, upstream status). Never the lobby password |
| `lobby` | `tasks`, `reconcile` | — | `lobby/tasks.py` | Create/close/flip/backfill tasks with the dota_lobby problem `code`; the 60 s reconcile sweep (`lobby_reconcile_summary` counts) |
| `lobby` | `bot_access` | — | `lobby/bot_access/` | Bot league access reads and refreshes: upstream failure `code`/status, refresh counts (`bot_access_refreshed`), provider fallback (`bot_access_provider_fallback`), unknown bot states, throttled requests (`bot_access_throttled`). Never bot names, usernames or Steam IDs; failed per-bot calls log `lobby/client` `http_path` as the template `/v1/bots/{name}/leagues` |
| `common` | `utils` | — | `common/utils.py` | Shared utility warnings (CI/IP detection) |

Add new systems/subsystems as features grow. Keep systems coarse (feature area), subsystems functional (what role the code plays).

## Cross-System Correlation

Logs that span multiple systems carry an `interaction_id` (Discord interaction) or `request_id` (web request) so a single user action can be traced across processes.

For Discord interactions, the `discord_log_context` async CM in `discordbot/log_context.py` binds:
- `interaction_id` — primary correlation key (Discord-generated, unique per click)
- `discord_user_id`, `discord_username`, `channel_id`, `guild_id`
- `custom_id`, `event_id`, `interaction_type`
- `tags=["events","signup"]` (or other prefix-derived tags)
- `tags_csv="events,signup"` (flat string for clean LogQL filtering)

These propagate via `structlog.contextvars.merge_contextvars` through `await` and `sync_to_async`. They also propagate across Celery `.delay()` calls when the dispatch site passes `interaction_id` as a kwarg and the task calls `bind_contextvars(interaction_id=...)` at entry.

OTel `trace_id` and `span_id` are injected automatically by the `_add_otel_trace_context` processor in `telemetry/logging.py`. At a 10% sample rate, the `trace_id` is in every log line for that 10%; for the other 90%, rely on `interaction_id` for log-side correlation.

### Grafana query patterns

```logql
# Single user click
{service_name="backend"} | json | interaction_id="<id>"

# Cross-cutting: anything signup-related
{service_name="backend"} | json | tags_csv=~".*signup.*"

# Discord code that touches events
{service_name="backend"} | json | system="discord" | tags_csv=~".*events.*"
```

## Log Levels

| Level | When | Exported to Grafana? |
|-------|------|---------------------|
| `DEBUG` | Per-request/per-tick detail, heartbeat received | No (prod=INFO) |
| `INFO` | State transitions, lifecycle events, periodic health | Yes |
| `WARNING` | Anomalies that self-recover (stale heartbeat, slow tick) | Yes |
| `ERROR` | Failures requiring attention (broadcast failed, API error) | Yes |

## Required Fields

Beyond `system` and `subsystem`, include relevant entity IDs:

- `draft_id` — for anything draft-related
- `user_id` / `username` — for user-scoped actions
- `event_id` — for event system logs
- `duration_s` / `elapsed_ms` — for timing-sensitive operations
- `reason` — for skipped/stopped/failed actions
- `error` — for exception context (`str(e)`, never the full traceback)

## References

- Backend patterns (structlog config, OTel export, Celery/Daphne logging, middleware): [references/backend.md](references/backend.md)
- Frontend console logging conventions: [references/frontend.md](references/frontend.md)
- Querying/parsing logs from the CLI with `gcx` (error breakdown, mixed JSON+plain-text, silence detection, request/trace correlation): [references/grafana-loki.md](references/grafana-loki.md)

## Grafana Queries

```logql
# All herodraft heartbeat logs
{service_name="backend"} | json | system="herodraft" | subsystem="heartbeat"

# Slow ticks
{service_name="backend"} | json | event="tick_slow"

# All errors across systems
{service_name="backend"} | json | level="error"

# Filter by draft
{service_name="backend"} | json | draft_id="42"
```

Run these from the CLI with `gcx` (context `draftforge` → kettle.grafana.net). **Pass
`--agent=false`** or Claude Code's auto agent-mode suppresses the output:

```bash
gcx logs query '{service_name="backend"} | json | level="error"' --since 24h -o raw --agent=false
```

The `discord` service mixes structlog JSON with plain-text `discord.py` lines, so `| json`
drops half of them — use line filters (`|= "ERROR"`) there. Full examples (error breakdown,
silence detection, request/trace correlation): [references/grafana-loki.md](references/grafana-loki.md).
