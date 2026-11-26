# Promotion contact sync

DraftForge and an external contact log kept by a partner guild both keep track of who was
contacted over Discord DM and who earned the promotion point for inviting a player to an
event. This integration keeps two ledgers in step, for **event promotion only**:

- **The contact ledger.** Every contact the external contact log holds for players of the
  bound guild is imported, whatever its reason, occasion or date, and kept current when
  the external row is later edited or deleted. Every DM a promoter marks as sent in
  DraftForge gets its own receipt, kept so that each one can become exactly one row in the
  external contact log once it has a writer that can store it (see
  [Writing to the external contact log is not enabled](#writing-to-the-external-contact-log-is-not-enabled)).
- **The promotion ledger.** An event has one promotion point per player. An imported
  invitation on an occasion bound to a DraftForge event holds that point and credits the
  external promoter. If DraftForge had already given the point for a local send, the
  external entry wins and the local point is voided by a reversal entry that stays in the
  ledger. See [Promotion points](#promotion-points).

Each side computes its own totals from its own ledgers. Totals are never exchanged:
there is no contribution-totals export.

Messaging stays manual. Nothing here sends a Discord message or creates an account, a
membership or a send.

The other side of the integration is the adaptor service. Its repository documents the
contact log reads, the adaptor CLI and its intake endpoint (`docs/promotion.md` there).

---

## How data moves

| Direction | What | Credential |
|-----------|------|------------|
| Contact log → adaptor → DraftForge | Every contact of the bound guild, posted in id-range batches; DraftForge stores, updates or retracts each one and settles its promotion point | DraftForge app token `dfk_…` with `promotion:import` |
| DraftForge → adaptor → contact log | One receipt per recorded DM, sent by the dispatcher | adaptor API key with only `promotion:write`, limited to the org |

The two credentials are separate on purpose: DraftForge never holds a `dfk_` token for
the adaptor's intake, and the adaptor never holds its own API key for DraftForge.

## Setting it up

### 1. Issue the adaptor's DraftForge token

In **Org Settings → API access**, an org admin creates a token with the operations the
adaptor needs:

| Operation | Label | Needs the feature |
|-----------|-------|-------------------|
| `promotion:import` | Import external contact history and promotion points | Promotion |
| `mmr:read`, `mmr:write` | Read / update member MMRs | MMR sync API |

`promotion:import` records external contacts and awards and voids promotion points. The
adaptor uses one token for both jobs, so it also needs the MMR pair when it syncs MMRs;
an adaptor that only imports contacts needs `promotion:import` alone. The API access
section is shown to org admins when the MMR sync API or Promotion is unlocked, so a
promotion-only token can be issued without the MMR sync API feature. The same request
through the API is `POST /api/organizations/<id>/api-tokens/` with
`{"name": "Contact log adaptor", "operations": ["promotion:import"]}`.

Grants are fixed when the token is created. Every request checks, in order: the token,
its org, the operation grant (`403 operation_not_granted`), the operation's feature, that
the owner is still an org admin, and the rate budget. Tokens that existed before grants
were added only have the MMR pair; nothing widens them. The operations are exactly
`mmr:read`, `mmr:write` and `promotion:import`; any other name is rejected as unknown.

### 2. Bind the org and its events

`PROMOTION_SYNC_BINDINGS` (backend environment, JSON) names the external guild for the org and
the external occasion for each event. It is empty by default, and an org without a
binding fails closed (`403 binding_missing`):

```json
[{"org_id": "41", "guild_id": "555000000000000001",
  "events": [{"event_id": "720", "occasion_id": "88"}]}]
```

- IDs are positive decimal strings. Every field is required; unknown fields and
  duplicates (an org, a guild, an event, or an occasion within an org) are rejected at
  startup, and the error never repeats the value.
- `guild_id` must equal the org's own Discord server, and every import must name the
  same guild (`403 binding_mismatch` otherwise). For the partner guild it is that
  guild's numeric ID.
- The `events` entries map external occasions to DraftForge events. A contact on an
  occasion with no entry is still stored, but it ticks nobody and holds no point. A
  contact linked only by date is never matched to an event; nothing is inferred from
  event names or dates.
- **After changing a binding, run a full adaptor import** (`promotion contacts --full`).
  A changed occasion → event mapping reaches a stored contact only when that row is
  posted again, and the adaptor's incremental runs re-post only recent rows. The full
  run moves each contact, and its point, to the event the new binding gives it.
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

## The imported contact ledger

Each external contact is stored once per external contact ID as a receipt. It keeps the
external facts (contact time, New York contact date, contact method, reason
`EVENT_INVITE`, `FOLLOW_UP` or `GENERAL`, the occasion or the date it is linked to, and
whether it was forced) plus a hash of those facts. It also keeps two Discord IDs the
adaptor derives from the external people's current accounts: the contacted player and
the promoter (empty when the adaptor could not resolve one). The event comes from
DraftForge's own binding, never from the request.

Only an `EVENT_INVITE` on a bound occasion ticks a candidate or holds a point. Every
other contact is stored for later frequency views and has no effect today.

### Batches and ranges

The adaptor reads the external log in id order and posts batches of up to 100 contacts.
Each batch names a range `{after, through}`: the adaptor read every external row with
`after < id ≤ through` in one snapshot, and each one is either in the batch or listed
in `skipped_ids` (up to 1000 rows it saw but did not post, such as players outside the
guild or rows that failed validation). An invalid row is skipped by the adaptor, so it
never blocks its batch; DraftForge still refuses a malformed batch as a whole with
`400`.

Each answer reports `max_source_contact_id`, the highest external ID DraftForge holds.
The adaptor starts its next incremental run a little below it, so rows committed late
with lower IDs are not missed; a `--full` run starts from the beginning.

### Updates and retractions

The external log's operators can edit or delete rows directly, so DraftForge compares
each posted contact with the one it holds:

| Result | When | What happens |
|--------|------|--------------|
| `applied` | a new external ID | stored, then its point is settled |
| `unchanged` | same facts, same Discord IDs, same event | nothing rewritten; a missing account or membership link may be filled in (`association_updated`), and an uncredited point is settled again in case the promoter became a member |
| `updated` | the facts, either Discord ID or the bound event changed | the receipt's revision goes up, an `update_external_contact` org log entry records the old and new hash and the changed field names (never Discord IDs), its old point effects are reversed and the point is settled again |
| `reinstated` | a retracted ID is posted again | the retraction is cleared and the contact is settled again |
| `quarantined` | the stored account link now points at someone else | the receipt is kept; see [Quarantine and points](#quarantine-and-points) |

A live contact whose ID falls inside a posted range but is neither posted nor skipped
was deleted externally: DraftForge **retracts** it (`retracted` in the answer). A
retracted contact stays stored, never ticks and never holds a point. A contact first
imported less than 5 minutes before the batch's `scan_started_at` is left for the next
run.

Each contact also retains the latest accepted `scan_started_at`, including unchanged
observations, reinstatements and repeated deletion observations. A batch from an older
scan cannot update, reinstate or retract newer state; its posted entries answer
`unchanged` with the stored point status. The timestamp is the source snapshot's start,
not the request's arrival time, so overlapping imports may finish out of order safely.
DraftForge also retains the newest scan time for each committed source-ID range, except
skipped IDs. If a newer scan covered a source ID that is not stored, an older scan cannot
create that contact or give it a point.

An account merge records which externally held Discord IDs now belong to each moved
send, including sends already voided by a previous merge. Releasing any of those IDs
reconsiders the send, but its point is restored only after no held ID remains for the
recipient and no other local send for that recipient earns the point.

## Promotion points

The promotion point for an (event, player) pair, where the player is a Discord ID, is
held by at most one source.

### What an imported invitation does

When an imported `EVENT_INVITE` on a bound event is settled:

1. **Echo.** If the contact is the external copy of a DraftForge send (an applied
   receipt wrote it), it is an echo: it holds nothing, so a DraftForge send is never
   counted twice. No echo can happen while writeback is disabled.
2. **Duplicate.** If another imported contact already holds the point for that pair, it
   is a duplicate and holds nothing.
3. Otherwise it **holds the point**:
   - **credited**: the promoter's Discord ID belongs to a DraftForge account that is a
     member of the org, and that member gets a `promo_message` entry ("Recorded in the
     external contact log") worth the org's current promotion point value, dated at the
     external contact time. No promoter role and no Contributions feature is needed,
     just as for a local send.
   - **uncredited**: the point is held but nobody in DraftForge is credited, because the
     promoter was not resolved, contacted themselves, has no account, or is not a member.
     The next import that sees the contact again tries to credit them.
4. If DraftForge had already given the point for a local send to that player, the local
   point is **voided**: a `promo_void` entry ("Voided: the external contact log holds
   this point") reverses the send's entry, and the send stops earning. The send, its
   receipt and its tick stay. The void matches the player by the Discord ID recorded at
   send time, so a later relink does not hide it.

### Void and restore

No void or retraction deletes history. Each change is a new ledger entry that points at
the entry it reverses, plus an org log entry:

| Ledger kind | Label | Org log action | Written when |
|-------------|-------|----------------|--------------|
| `promo_void` | Promotion point voided | `void_promo_point` | an external contact takes the point from a local send, or an external credit is reversed because its contact changed or was removed |
| `promo_restore` | Promotion point restored | `restore_promo_point` | the external contact that voided a local point no longer holds it and no other external contact takes over |

When the holder of a point is edited onto another key or retracted, the next duplicate
for that pair (lowest external ID) takes the point over, and the local void stays. Only
when no imported contact is left to hold it is the local point restored, with the send
earning again. A promoter change on a credited contact voids the old credit and credits
the new promoter. A local void freezes the external point's Discord ID, so restoration
also finds sends voided during an account merge, even if the receipt's target later
changes. A replacement duplicate or any remaining holder for the merged recipient keeps
the send's point voided; restoration never creates a second earning local point.

A void carries the reversed entry's date, so all-time and monthly totals net to zero in
the right month, and voided entries and reversal rows do not count as leaderboard
`entries`. The member contribution breakdown and the admin ledger show each entry with
its sign: an external credit as `+1`, a void as `-1`.

### What a local send does now

- A send is refused with `409 contact_already_recorded` when an imported contact ticks
  the player or an imported contact holds the point, so a send is never accepted and
  then silently denied its point. The send dialog's "earns a point" note uses the same
  rule.
- Undoing a voided send deletes its entry, and the reversals go with it, so the net stays
  zero.
- Merging Discord accounts, or approving a claim request, voids the kept account's
  earning send for an event where an imported contact holds the point for either
  Discord ID, so the merged player has one live point.
- Deleting an event releases the points its contacts held; the ledger entries keep their
  points, as they do today.
- Changing the promotion point value with **apply to past** also rescores voids and
  restores, so each one still equals its entry. A local send still reads the point value
  without a lock, as before.

### Quarantine and points

Quarantine is about which DraftForge account a contact ticks, not about whether the
external point exists. A quarantined contact that holds the point still ticks the
candidate with its Discord ID, still blocks sends to that Discord ID, and still voids the
local point. A quarantined contact that does not hold the point never ticks.

## Ticks in the Promotion tab

An imported invitation for the event ticks the candidate with the same Discord ID, even
a guild member who has no DraftForge account yet. Echoes and retracted contacts never
tick.

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

Imports never create a send, an account or a membership. Merging accounts moves a
receipt only to the account that owns its Discord ID; otherwise the receipt is
quarantined. Deleting an account quarantines its receipts as `account_deleted`; a
receipt that holds a point keeps it.

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

**Gate before enabling writeback.** Once DraftForge sends can reach the external log,
an import can see a DraftForge send's external copy before the dispatcher marks the
outbox row applied. That copy would be imported as the point holder instead of an echo.
Before writeback is turned on, the dispatcher must reconcile when it marks a row applied,
under the event lock: reclassify an already imported copy as an echo, void its credit and
restore the local point. This is not built yet, because writeback is disabled.

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
   Imports stop and the Promotion tab returns to its local-only behaviour. Credits,
   voids and restores already written stay in the ledger.
3. Receipts and outbox rows stay in the database as evidence.

Migrations `org.0026_api_token_operations` through `org.0030_promotion_observations_and_keys`
are additive and reversible on a disposable database, but reversing `0027` drops every
receipt and outbox row. Upgrading again restores the MMR pair on every token, so a
rollback never widens a grant.

## API

The only integration endpoint is `POST /api/organizations/<org_id>/integration/v1/contact-receipts/`
(operation `promotion:import`). It takes only `Authorization: Bearer dfk_…` and answers
errors as `{"error": {"code", "message", "request_id"}}`. The request and response
shapes are in [API endpoints](../api/endpoints.md#integration-api).

There is no event recipients read and no contribution-totals export, and no grant for
either: the adaptor imports the whole guild instead of asking who may be reported, and
each side computes its own totals.

## Logs

Log lines use `system=org` and `subsystem=integration` (or `promotion` for the
send path, `api_tokens` for tokens). They carry counts, IDs of DraftForge rows and reason
codes, never message text, Discord IDs or tokens.

| Event | When |
|-------|------|
| `integration_contacts_imported` | a successful import, with its counts |
| `integration_request_rejected`, `integration_request_failed` | an integration request answered with an error |
| `integration_contacts_import_conflict` | a batch rolled back with `409 import_conflict_retry` |
| `org_api_operation_denied` | a token used an operation it was not granted |
| `promo_point_voided`, `promo_point_restored` | a promotion point voided or restored |
| `promo_points_settled_after_merge` | local points voided after an account merge |
| `promo_outbox_enqueued` | a send got its outbox row |
| `promo_receipt_quarantined`, `promo_receipts_reconciled_for_merge`, `promo_identity_canceled_for_deletion` | receipts and rows kept honest across merges and deletions |
| `promo_dispatch_run_finished`, `promo_dispatch_attempt_finished`, `promo_adaptor_receipt_answered`, `promo_dispatch_client_failed`, `promo_dispatch_late_outcome_discarded`, `promo_dispatch_resumed`, `promo_dispatch_disabled` | dispatcher runs |

## Testing

All fixtures are synthetic; no test contacts the external contact log, the adaptor or Discord.

- Backend: `org.tests.test_integration_*` (auth, bindings, contacts, protocol),
  `test_promotion_ledger` (settle, void, restore, supersede, retract, local guards,
  rescoring, event deletion), `test_promotion_merge`, `test_promotion_outbox`,
  `test_promotion_dispatch` (a fake HTTP adaptor), and `test_promotion_sync_*` (models,
  lifecycle, migrations, races). `just test::backend::pg-race` reruns the race tests on a
  throwaway PostgreSQL container.
- The fixtures in `backend/org/tests/golden/` (`import_source_hash.json`,
  `import_rules.json`, `receipt_hash.json`) are byte copies of the adaptor's Go fixtures.
  Both sides must produce the same digests and accept or reject the same import rows.
- `POST /api/tests/org-features/reset/` with `"external_contacts": true` (Playwright:
  `resetOrgFeatures(request, { externalContacts: true })`) binds the features org's
  upcoming event to synthetic occasion 7001 at runtime and posts one guild-wide batch
  through the real import: external only (credited to the features promoter), local and
  external (which voids that send's local point), Discord-only, and a non-member. A plain
  reset removes the binding and the org's receipts and outbox rows.
- `frontend/tests/playwright/e2e/org-features/promotion-integration.spec.ts` covers
  the ticks, a contact imported while the tab is open, the send banner, the promoter's
  breakdown with the external credit and the voided local point, and issuing a
  promotion token. With `PROMOTION_SCREENSHOT_DIR` set it saves each state at desktop and
  mobile size; the paused, needs-review and applied banners are simulated by rewriting
  the send response in the browser, because no adaptor answers in that test.

Code: `backend/org/integration/` (`contacts.py`, `points.py`, `ticks.py`),
`backend/config/promotion_sync.py`, `backend/org/models_promotion_sync.py`,
`backend/org/management/commands/dispatch_promotion_contacts.py`,
`frontend/app/features/promotion/`, `frontend/app/features/api-tokens/`,
`frontend/app/features/contributions/`.
