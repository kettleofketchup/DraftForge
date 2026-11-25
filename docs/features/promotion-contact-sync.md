# Promotion contact sync

DraftForge and an external contact log kept by a partner guild both keep track of who was
invited to an event over Discord DM. This integration connects them for **event promotion only**:

- Contacts the external contact log already recorded for an event show as **ticked** in the
  [Promotion](organization-locked-features.md) tab, so promoters skip people someone
  already messaged.
- Every DM a promoter marks as sent in DraftForge gets its own receipt, kept so that each
  one can become exactly one row in the external contact log once it has a writer that
  can store it (see [Writing to the external contact log is not enabled](#writing-to-the-external-contact-log-is-not-enabled)).
- The adaptor can read DraftForge's contribution totals. Points come from DraftForge's
  ledger, never from the external contact log.

Messaging stays manual. Nothing here sends a Discord message, creates an account or a
membership, or awards points for an imported contact.

The other side of the integration is the adaptor service. Its repository documents the
contact log reads, the adaptor CLI and its intake endpoint (`docs/promotion.md` and
`docs/contributions.md` there).

---

## How data moves

| Direction | What | Credential |
|-----------|------|------------|
| Contact log → adaptor → DraftForge | External contacts for a bound event, imported as receipts that tick candidates | DraftForge app token `dfk_…` with `promotion:read` and `promotion:import` |
| DraftForge → adaptor | Contribution totals, pulled by the adaptor | the same kind of `dfk_…` token with `contributions:read` |
| DraftForge → adaptor → contact log | One receipt per recorded DM, sent by the dispatcher | adaptor API key with only `promotion:write`, limited to the org |

The two credentials are separate on purpose: DraftForge never holds a `dfk_` token for
the adaptor's intake, and the adaptor never holds its own API key for DraftForge.

## Setting it up

### 1. Issue the adaptor's DraftForge token

In **Org Settings → API access**, an org admin creates a token and turns on only the
operations the adaptor needs:

| Operation | Label | Needs the feature |
|-----------|-------|-------------------|
| `promotion:read` | Read promotion recipients | Promotion |
| `promotion:import` | Import external contact history | Promotion |
| `contributions:read` | Read contribution totals | Contributions |
| `mmr:read`, `mmr:write` | Read / update member MMRs | MMR sync API |

New tokens default to the MMR pair, so turn those off for the adaptor token. A token for
the adaptor does **not** need the MMR sync API feature; the API access section is shown
to org admins when any feature with token operations is unlocked. The same request
through the API is `POST /api/organizations/<id>/api-tokens/` with
`{"name": "Contact log adaptor", "operations": ["promotion:read", "promotion:import", "contributions:read"]}`.

Grants are fixed when the token is created. Every request checks, in order: the token,
its org, the operation grant (`403 operation_not_granted`), the operation's feature, that
the owner is still an org admin, and the rate budget. Tokens that existed before grants
were added only have the MMR pair; nothing widens them.

### 2. Bind the org and its events

`PROMOTION_SYNC_BINDINGS` (backend environment, JSON) names the external guild for the org and
the external occasion for each event. It is empty by default, and an org or event without a
binding fails closed (`403 binding_missing`):

```json
[{"org_id": "41", "guild_id": "555000000000000001",
  "events": [{"event_id": "720", "occasion_id": "88"}]}]
```

- IDs are positive decimal strings. Every field is required; unknown fields and
  duplicates (an org, a guild, an event, or an occasion within an org) are rejected at
  startup, and the error never repeats the value.
- `guild_id` must equal the org's own Discord server (`binding_mismatch` otherwise). For
  the partner guild it is that guild's numeric ID.
- Only occasion linkage is supported. Contact log rows that carry only a date are not matched to
  an event; nothing is inferred from event names or dates.
- Keep synthetic or staging bindings and production bindings in separate environment
  files; the adaptor has its own copy of the same bindings and checks them independently.

### 3. Point the dispatcher at the adaptor

The dispatcher is off until configured:

| Variable | Default | Meaning |
|----------|---------|---------|
| `PROMOTION_ADAPTOR_ENABLED` | `false` | While false nothing is sent and the URL and key are not read |
| `PROMOTION_ADAPTOR_BASE_URL` | | `https://host[:port]`, no path, query or credentials (plain `http` only for loopback test hosts) |
| `PROMOTION_ADAPTOR_API_KEY` / `_FILE` | | the adaptor's `promotion:write` key, or a file holding it (not both) |
| `PROMOTION_ADAPTOR_TIMEOUT` | `30` | seconds per request |
| `PROMOTION_ADAPTOR_MAX_ATTEMPTS` | `5` | the last failed attempt leaves the row needing review |
| `PROMOTION_ADAPTOR_RETRY_CAP` | `120` | longest backoff, in seconds |

## Ticks in the Promotion tab

Each imported external contact is stored as a receipt: the external contact ID, event, Discord ID,
time, contact method and linkage, plus a hash of those facts. They never change once
stored. A receipt ticks the candidate with the same Discord ID for that event, even a
guild member who has no DraftForge account yet.

- The tick is read-only: **Contact recorded externally**, its time, and *Delivery not
  verified*. The external contact log recorded an invitation; nobody checked that the DM
  arrived.
- An imported contact has no undo. **Message** and **Mark as sent** are disabled for that
  player, with the reason in their tooltip, and the backend refuses a send with
  `409 contact_already_recorded`.
- **Hide messaged** hides players with either a local send or an external contact.
- A local send and an external contact show side by side. Undoing the local send leaves the
  external tick.
- With the integration configured, the list shows *History may be incomplete* (the
  external contact log may hold contacts that have not been imported yet) and the time of
  the last import. It is a notice, not a block: unticked players can still be messaged.
  The list refreshes every 30 seconds while the page is visible, and an open message
  dialog closes when a refresh shows an external contact for its player.
- Orgs without a binding see no change.

### Import rules

The adaptor imports in batches of up to 100 contacts for one event, after reading the
event's authorized recipients and their `mapping_version`. A batch is all or nothing:

- `applied`: a new contact, stored once.
- `unchanged`: already stored with the same facts. Filling in a missing account or
  membership for the receipt's own Discord ID is allowed and counted in
  `association_updated`.
- `quarantined`: the stored link points at someone else now (the Discord ID changed
  owner, or the membership is another user's). That receipt stops ticking but is kept;
  the rest of the batch still applies.

The same external contact ID with different facts is `409 source_content_conflict` for the
whole batch. A changed recipient universe is `409 mapping_changed`, and the adaptor
re-reads it once.

Imports never create a send, an award, an account or a membership. Merging accounts
moves a receipt only to the account that owns its Discord ID; otherwise the receipt is
quarantined. Deleting an account quarantines its receipts as `account_deleted`.

## Every DM gets a receipt

Each recorded send (**Mark sent** or **Record as sent** in the message dialog) writes one
outbox row in the same transaction as the send, including a repeat send that earns no
points and a send by a second promoter to the same player.
The row holds the org, the local send ID, a delivery UUID and a frozen payload with its
hash; retries resend the same bytes and UUID.

- **Undo** removes the local send and its points but not the receipt: the DM was sent and
  cannot be unsent. `DELETE sends/<id>/` therefore returns `200` with `{writeback}`
  instead of `204`.
- A sender or recipient without a Discord ID gets a row in `reconciliation_required`
  with no payload. The send itself still works.
- After an account merge, open rows point at the kept account, but their payloads keep
  the user ID recorded at send time (the adaptor writes from Discord IDs and only hashes
  user IDs). Deleting the kept account cancels those rows and redacts their payloads.
- Deleting an account cancels its open rows and redacts every payload that names it,
  keeping the hash. A request that was already on its way to the adaptor cannot be
  recalled.

### What the send banner says

After a send is recorded, a configured org shows the external state on its own line, apart from
"Sent to …":

| State | Banner |
|-------|--------|
| `pending` | Waiting to be recorded externally. |
| `in_flight` | Being recorded externally now. |
| `retry` | The adaptor could not take it yet; DraftForge will try recording it externally again. |
| `paused` | External recording is paused. The send is saved in DraftForge and will be recorded once it resumes. |
| `reconciliation_required` | This send needs review before it can be recorded externally. |
| `applied` | Recorded externally. |
| `canceled` | This send will not be recorded externally. |

Only `applied` means the external contact log stored it, and today nothing reaches `applied` (next section).

## Writing to the external contact log is not enabled

The adaptor accepts and validates each receipt, then answers
`409 {"status": "not_applied", "reason": "writeback_disabled", "applied": false, "durable": false}`.
DraftForge records that as `paused`. That answer is **not** a successful sync.

The external contact log's existing contact-recording function cannot store one row per DM: it takes no
original send time or metadata, records the call time instead, and its unique indexes
fold a second invitation to the same person for the same occasion into the first. The
adaptor refuses to start with writeback turned on until a writer exists that keeps the
real promoter, the original time and date, a unique per-send key and a row for every
distinct DM. The contact log's owner has offered an endpoint; it will plug into the adaptor's
writer interface without changing this side. Until then, leave writeback off.

## Running the dispatcher

```bash
python manage.py dispatch_promotion_contacts --limit 100 --dry-run       # count only, changes nothing
python manage.py dispatch_promotion_contacts --limit 100                 # send what is due
python manage.py dispatch_promotion_contacts --limit 100 --resume-paused # paused rows back to pending first
```

There is no Celery task or schedule; an operator or an external scheduler runs it. Each
run prints a JSON report (`due`, `leased`, `counts` per resulting state, `reasons`,
`resumed`, `skipped_unbound`).

| Adaptor answer | Outbox state |
|----------------|--------------|
| `200 applied` with `applied` and `durable` true, a `contact_log_id` and the same delivery ID | `applied` (final) |
| `409 not_applied` (writeback disabled or dry run), `401`, `403` | `paused`, until `--resume-paused` |
| `200 already_contacted`, `409 mapping_required`, `409 idempotency_conflict`, a malformed answer, the last allowed failure | `reconciliation_required` |
| timeout, connection error, `408`, `429`, `5xx` | `retry`, backing off up to the cap and never sooner than `Retry-After` |

Rows are sent only for bound orgs and events; others stay `pending`
(`skipped_unbound`).

## Rolling back

Turn the integration off; do not migrate back over retained data.

1. Set `PROMOTION_ADAPTOR_ENABLED=false`. Rows stay as they are.
2. Revoke the adaptor's `dfk_` token in API access, or clear `PROMOTION_SYNC_BINDINGS`.
   Imports stop and the Promotion tab returns to its local-only behaviour.
3. Receipts and outbox rows stay in the database as evidence.

Migrations `org.0026_api_token_operations` and `org.0027_promotion_sync_receipts` are
additive and reversible on a disposable database, but reversing `0027` drops every
receipt and outbox row. Upgrading again restores the MMR pair on every token, so a
rollback never widens a grant.

## Contribution totals for the adaptor

`GET /api/organizations/<id>/integration/v1/contributions/` lists every org member with
their all-time **contribution** track total (leadership and conduct are not included).
Zero and negative totals are returned as they are; a member without a usable Discord ID
is `"status": "unavailable"` with `"reason": "discord_mapping_missing"` and no points,
which is not the same as zero. Totals are read live per page; a membership change
between pages is `409 mapping_changed`.

## API

All integration endpoints live under `/api/organizations/<org_id>/integration/v1/`, take
only `Authorization: Bearer dfk_…`, and answer errors as
`{"error": {"code", "message", "request_id"}}`. Details are in
[API endpoints](../api/endpoints.md#integration-api).

| Method | Path | Operation |
|--------|------|-----------|
| GET | `events/<event_id>/recipients/?limit=&cursor=` | `promotion:read` |
| POST | `contact-receipts/` | `promotion:import` |
| GET | `contributions/?limit=&cursor=` | `contributions:read` |

## Logs

Log lines use `system=org` and `subsystem=integration` (or `promotion` for the
send path, `api_tokens` for tokens). They carry counts, IDs of DraftForge rows and reason
codes, never message text or tokens.

| Event | When |
|-------|------|
| `integration_recipients_listed`, `integration_contacts_imported`, `integration_contributions_listed` | a successful read or import |
| `integration_request_rejected`, `integration_request_failed` | an integration request answered with an error |
| `integration_contacts_import_conflict` | a batch refused for conflicting source facts |
| `integration_subject_source_unavailable` | the guild member list could not be read (`503`) |
| `integration_subject_identity_conflict` | two subjects resolved to one identity (`409 identity_conflict`) |
| `integration_ledger_unavailable` | the ledger could not be read (`503 ledger_unavailable`) |
| `org_api_operation_denied` | a token used an operation it was not granted |
| `promo_outbox_enqueued` | a send got its outbox row |
| `promo_receipt_quarantined`, `promo_receipts_reconciled_for_merge`, `promo_identity_canceled_for_deletion` | receipts and rows kept honest across merges and deletions |
| `promo_dispatch_run_finished`, `promo_dispatch_attempt_finished`, `promo_adaptor_receipt_answered`, `promo_dispatch_client_failed`, `promo_dispatch_late_outcome_discarded`, `promo_dispatch_resumed`, `promo_dispatch_disabled` | dispatcher runs |

## Testing

All fixtures are synthetic; no test contacts the external contact log, the adaptor or Discord.

- Backend: `org.tests.test_integration_*`, `test_promotion_outbox`, `test_promotion_dispatch`
  (a fake HTTP adaptor), `test_promotion_sync_*` (models, lifecycle, migrations, races).
  `just test::backend::pg-race` reruns the race tests on a throwaway PostgreSQL
  container.
- The hash fixtures in `backend/org/tests/golden/` are byte copies of the adaptor's Go
  fixtures; both sides must produce the same digests.
- `POST /api/tests/org-features/reset/` with `"external_contacts": true` (Playwright:
  `resetOrgFeatures(request, { externalContacts: true })`) binds the features org's upcoming
  event to synthetic occasion 7001 at runtime and stores four receipts: external only, local and
  external, Discord-only, and a non-member. A plain reset removes the binding and the org's
  receipts and outbox rows.
- `frontend/tests/playwright/e2e/19-org-features/18-promotion-integration.spec.ts` covers
  the ticks, a contact imported while the tab is open, the send banner, and issuing a
  promotion token. With `PROMOTION_SCREENSHOT_DIR` set it saves each state at desktop and
  mobile size; the paused, needs-review and applied banners are simulated by rewriting
  the send response in the browser, because no adaptor answers in that test.

Code: `backend/org/integration/`, `backend/config/promotion_sync.py`,
`backend/org/models_promotion_sync.py`,
`backend/org/management/commands/dispatch_promotion_contacts.py`,
`frontend/app/features/promotion/`, `frontend/app/features/api-tokens/`.
