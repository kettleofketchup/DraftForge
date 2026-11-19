# Operations Notices

An operations notice tells an organization's staff that something in their org or event
needs a look: a member dropped out late, a ready check failed, a task is waiting. Each
notice is a row in `opsnotices.OpsNotice`, created through one registry of notice types
in `backend/opsnotices/`.

Notices are **not**:

- member messages. Anything sent to players goes through the member messaging path, not
  here;
- SRE alerts. Engineering failures (a rejected payload, a crashed task) go to the logs
  and Grafana, never to staff.

This app ships the registry, the storage, the staff API and the event page card. It
registers **no notice types**: until a feature adds one, nothing is emitted and the card
renders nothing. Routing to Discord and delivery come later (#561, #562).

## Notice categories

| Category | Meaning | On the event card | Staff can resolve |
|---|---|---|---|
| `urgent` | needs staff attention now | yes | yes |
| `task` | work with its own lifecycle (#564) | yes | no (`400 task_resolve_unsupported`) |
| `log` | informational record | no | n/a; purged by retention |

Severities are `info` < `warning` < `critical` (`NoticeSeverity.rank`).

## Adding a notice type

Create `backend/<app>/ops_notices.py` and register the type at module top. No central
file changes: `OpsNoticesConfig.ready()` runs `autodiscover_modules("ops_notices")`, and
the TypeScript exporter globs the same files.

```python
from pydantic import BaseModel

from opsnotices.registry import (
    NoticeCategory,
    NoticeSeverity,
    NoticeType,
    register_notice_type,
)


class LateDropPayload(BaseModel):
    member_id: int
    member_name: str
    hours_before_start: int


register_notice_type(
    NoticeType(
        key="rsvp.late_drop",
        label="Late drop",
        description="A confirmed member dropped close to the start.",
        category=NoticeCategory.URGENT,
        default_severity=NoticeSeverity.WARNING,
        payload=LateDropPayload,
        summary=lambda p: f"{p.member_name} dropped {p.hours_before_start}h before start",
        sample_payload=lambda: LateDropPayload(
            member_id=1, member_name="Sample", hours_before_start=2
        ),
        dedupe_key=lambda p: f"member:{p.member_id}",
    )
)
```

Rules, all checked by `validate_registry()` and the registry tests:

- **Key**: `<area>.<name>`, lowercase, matching `^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$`.
  Duplicate keys raise `NoticeRegistryError`.
- **Purity**: an `ops_notices.py` module imports only the standard library, `pydantic`,
  `typing_extensions` and `opsnotices.registry`. No Django, no models, no relative
  imports. The exporter runs without Django, and a test fails on any other import. The
  package's `__init__.py` is imported too, so keep it free of Django imports.
- **Sample payload**: required. It must validate, survive a JSON round trip, and render
  a summary.
- **Summary**: non-empty, at most 150 characters, rendered from the payload.
- **Detail**: optional `detail(payload) -> NoticeDetail` (title, facts, links). Without
  it the detail is `NoticeDetail(title=label)`.
- **Dedupe**: `dedupe_key(payload)` returns the identity of "the same problem". Without
  a hook, every emit creates a new row.
- **Auto-resolve**: `auto_resolves=True` needs a `dedupe_key` hook, because a notice
  without a dedupe key cannot be resolved by identity.
- **No secrets** in payloads. Staff see the raw payload through the API.
- **No input values in validator messages.** Only each error's `loc` and `type` are
  kept; messages are dropped, but do not rely on that.

### Identity and deduplication

A notice's identity is `(organization, key, event_key, dedupe_key)`, unique among open
notices with a non-empty dedupe key. `event_key` is the event's id at create time (`0`
for event-less notices) and never changes, so a notice never moves between events and
the same problem on two events gives two notices.

Emitting an identity that is already open updates that row: `occurrences` goes up by
one, `last_seen_at` moves, the latest payload, actor and subject win, and severity only
escalates. `event`, `event_key` and `delivery_state` never change on a re-emit. After a
notice is resolved, the next emit opens a new row and the old one stays as history.

Deleting an event keeps its notices: `event` becomes null and `event_name` and
`event_key` keep the snapshot.

## Emitting

### Web, Daphne and management commands

Code with database access calls `emit_notice` directly:

```python
from opsnotices.services import emit_notice

emit_notice(
    "rsvp.late_drop",
    LateDropPayload(member_id=user.pk, member_name=user.username, hours_before_start=2),
    organization=event.organization,
    event=event,
    subject_user=user,
    actor=request.user,
)
```

Optional arguments: `dedupe_key` (overrides the type's hook), `severity` (overrides the
default), `emit_id` (idempotency key) and `strict`.

### Celery

Celery workers have no database. `emit_notice` and the resolve functions raise
`RuntimeError` there on the first call, and a test fails if any `tasks.py` or `tasks/`
module imports `opsnotices.services`. Tasks call the internal API through
`app.internal_client` instead:

```python
from uuid import UUID, uuid5

from celery import shared_task

from app.internal_client import OpsNoticeTransientError, emit_ops_notice


@shared_task(
    bind=True,
    autoretry_for=(OpsNoticeTransientError,),
    retry_backoff=True,
    max_retries=5,
)
def notify_late_drop(self, org_id: int, event_id: int, member_id: int) -> None:
    emit_ops_notice(
        "rsvp.late_drop",
        {"member_id": member_id, "member_name": "...", "hours_before_start": 2},
        organization_id=org_id,
        event_id=event_id,
        emit_id=uuid5(UUID(self.request.id), f"rsvp.late_drop:{event_id}:{member_id}"),
    )
```

- Derive `emit_id` from the task id and what makes this emit distinct (key, event,
  member), so it stays the same across retries (`self.request.id` is stable across Celery
  retries) but differs between emits in one run. A retry with the same `emit_id` returns
  the existing notice without counting again.
- A replay only matches a notice with the same key, event and dedupe key, so reusing one
  `emit_id` for different notices does not drop them. Two emits of the same non-deduped
  notice in one run do need distinct ids, or the second is treated as a retry.
- Idempotency only matches the **latest** emit on a notice: a retry that lands after
  another emit touched the same notice counts as a new occurrence. This is a known
  limitation; there is no emit-id ledger.
- `emit_ops_notice` returns the notice id, `None` on a permanent rejection (4xx, already
  logged), and raises `OpsNoticeTransientError` on a network error or 5xx.
- `resolve_ops_notice(key, dedupe_key, organization_id=..., event_id=..., reason=...)`
  returns whether a notice was closed, with the same transient/permanent split.

The endpoints are `POST /api/internal/ops-notices/` and
`POST /api/internal/ops-notices/resolve/` (internal service token required):

| Response | When |
|---|---|
| `201 {id, created: true, occurrences}` | new notice |
| `200 {id, created: false, occurrences}` | re-emit, or replay of the same `emit_id` |
| `400 {error, code}` | `invalid_request` or a validation code (table below) |
| `404` | unknown organization |
| `503 {error, code}` | `database_error` or `event_conflict`: transient, retry |

An unknown `event_id` (the event was deleted after the task was queued) still creates
the notice, with the `event_name` you pass as the snapshot. Unknown user ids become
null and log `ops_notice_internal_user_missing`.

## Failure contract

Every emit runs in its own savepoint, so a failed notice never rolls back the caller's
transaction, and a half-filled notice is never stored or handed off.

| Mode | Setting | On failure |
|---|---|---|
| strict | `OPS_NOTICES_STRICT`, default on under `DEBUG`, `TEST` and test runs | raises `NoticeEmitError` (or `NoticePayloadError`) |
| lenient | production default | logs `ops_notice_emit_failed` at error level and returns `None` |

The database guard for Celery raises in both modes.

| Code | Cause |
|---|---|
| `unknown_notice_type` | key not registered |
| `invalid_payload` | payload fails validation, the validator raises, or serialisation fails; `errors` holds only `loc` and `type` |
| `invalid_severity` | `severity` is not a `NoticeSeverity` value |
| `invalid_dedupe_key` | the dedupe hook raised or returned a non-string |
| `dedupe_key_too_long` | dedupe key over 200 characters (never truncated) |
| `event_org_mismatch` | the event belongs to another organization |
| `event_conflict` | a concurrent write broke the dedupe identity and the retry found no row |
| `database_error` | a `DatabaseError` inside the notice's savepoint |

Grafana alerts on `ops_notice_emit_failed`. No payload values or pydantic messages are
logged.

## Resolving

- `resolve_notice(key, dedupe_key, organization=..., event=..., reason=..., closed_by=...)`
  closes the open notice for that identity, or returns `None`. An empty `dedupe_key`
  raises `ValueError`; resolve by id instead.
- `resolve_notice_by_id(notice, reason=..., closed_by=...)` is idempotent: a closed
  notice comes back unchanged, a deleted one returns `None`.

Both set `state=resolved`, `closed_at`, `close_note` (required, at most 200 characters)
and `closed_by` (null when the system closed it).

## Staff API and event card

| Method | Path | Who |
|---|---|---|
| GET | `/api/organizations/<org_id>/ops-notices/` | org staff |
| GET | `/api/events/<event_id>/ops-notices/` | event staff (includes league staff of a tournament event) |
| POST | `/api/organizations/<org_id>/ops-notices/<notice_id>/resolve/` | org staff |
| POST | `/api/events/<event_id>/ops-notices/<notice_id>/resolve/` | event staff |

Anonymous users and non-staff get 403; an unknown org, event, or a notice outside the
scope gets 404. List parameters: `state=open|resolved|all` (default `open`),
`category=log,urgent,task` (default all), `limit` (default 50, capped at 200). Resolve
takes an optional `reason` (default `"resolved by staff"`).

The event page's details tab shows `OpsNoticesCard` to event staff. It polls open
`urgent` and `task` notices every 15 seconds and renders nothing when there are none.
Its `noticeHref` prop is unused until the notice pages (#563) exist.

## Hand-off seams

`opsnotices.signals` defines two signals with no receivers in this app:

- `notice_emitted(notice_id, created, occurrences)`: sent with `send_robust` after the
  transaction commits. Emits of one notice inside one transaction are coalesced into a
  single call; `created` is true if any of them created the row, and `occurrences` is
  the committed count. A re-emit sends `created=False` and leaves `delivery_state`
  alone.
- `notice_resolved(notice_id)`: sent after a resolve commits.

Receivers connect in their own app's `ready()`. A failing receiver is logged
(`ops_notice_handoff_receiver_failed`) and never reaches the producer.

The signal is in-process and best-effort: if the process dies after commit, the row
stays `pending`. `delivery_state` values are `pending` (no router has processed it yet),
`sent`, `partial`, `failed` and `unrouted`; only the router and dispatcher (#561, #562)
write them, and they own reconciling `pending` rows that are older than a few seconds
(the `(delivery_state, last_seen_at)` index exists for that).

Coalescing reads Django's `connection.run_on_commit`; a test pins that behaviour so a
Django upgrade that changes it fails CI.

## Retention

`opsnotices.retention.RETENTION` declares the contract for the retention job (#499):

- `purge_notices(older_than=..., organization=None)` deletes closed notices whose
  `closed_at` is older than the cutoff, and `log` notices whose `last_seen_at` is older,
  open or not. Open `urgent` and `task` notices are never purged.
- `older_than` below 365 days raises `ValueError`.

Nothing calls it yet, so notices are kept indefinitely until #499 wires it in.

## Extending the states (#564)

`OPEN_STATES = ("open",)` in `opsnotices/models.py` drives the check constraint
`opsnotice_state_closed_at_consistent`: open states have no `closed_at`, every other
state has one. Adding a state such as `in_progress` to `OPEN_STATES` changes the
constraint, so it needs a **constraint migration** (remove and re-add), not just a
choices change. `state` is 24 characters wide to leave room for new values. The dedupe
constraint is keyed on `closed_at`, so it does not change when states widen.

## Generated TypeScript types

`frontend/app/lib/opsnotices/noticeTypes.generated.ts` holds the categories, severities,
states, delivery states and per-type metadata (not payload schemas). Regenerate it after
adding or changing a type:

```bash
just py::gen-notice-types
```

`just py::notice-types-check` exits 1 with a diff when the file is stale; the `unit` job
in CI runs it. The exporter imports pydantic, so it runs with the poetry venv's Python
(`python -I backend/opsnotices/export_schema.py`). That is why the recipes live in the
`py::` module: `ci::` recipes run with bare `python3` and no venv. Backend tests cannot
check the committed file because the test container mounts only `backend/`.

## Discord guard

`opsnotices/tests/test_discord_guard.py` parses the notice modules and fails if any of
them imports `discordbot`, `events.discord`, `discord` or `aiohttp`, calls a DM or send
helper, or mentions a Discord host. A runtime test also patches the Discord helpers and
`requests` and checks that emit and resolve call none of them. The future dispatcher
(#562) is added to `ALLOWED_SENDERS` in that test.
