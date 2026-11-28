# Org API connections

An API connection links one external service to one organization. Org admins manage
them in **Org Settings → API connections** (the `api-access` section). A connection can
do any of four things, each switched on separately:

| Direction | What happens | Needs the feature |
|-----------|--------------|-------------------|
| Inbound | The service calls DraftForge with a DraftForge-issued key (`dfk_…`) and only the operations granted to that connection | the feature of each granted operation |
| MMR push | DraftForge posts each change to a member's assigned MMR to the service | MMR sync API |
| MMR pull | DraftForge fetches members' MMRs from the service, on **Pull now** or on a schedule | MMR sync API |
| Promotion push | DraftForge sends promotion contact receipts to the service | Promotion, plus an operator adoption (see [Promotion](#promotion)) |

Everything starts off. A new connection is disabled, has no inbound key, grants no
operations and has every direction off. Turning a direction on never starts work by
itself: pulls start on **Pull now** or at the next scheduled time, and pushes start with
the next MMR change.

The connection's own **Enabled** switch gates every direction. Turning a connection off
stops inbound calls and outbound work but keeps its configuration, stored credential,
run history and deliveries.

---

## Two separate credentials

A connection holds up to two secrets, and they are never interchangeable:

- **Inbound key.** DraftForge issues it. The service sends it as
  `Authorization: Bearer dfk_<prefix>_<secret>`. DraftForge stores only a hash and shows
  the key once, in the dialog that issued it. It is never put in browser storage or the
  page cache, and closing the dialog, switching org or signing out clears it.
- **Outbound credential.** The service issues it and an org admin types it in.
  DraftForge stores it encrypted, bound to the connection and to the destination origin
  it was entered for. It is write-only: the form always shows an empty field with
  "Credential stored", plus **Replace** and **Clear**. No response, log, run or audit
  entry contains it.

### Inbound keys

| Action | Effect |
|--------|--------|
| Issue key | Creates the connection's key with the connection's current operations. Needs inbound enabled and at least one operation. |
| Rotate key | Revokes the old key at once (no grace period) and returns a new one. The connection, its history and its deliveries keep their identity. The new key starts with fresh per-key rate budgets. |
| Revoke key | Stops inbound access. Outbound directions keep working. |
| Edit operations | Revokes the current key; issue a new one to use the new grants. A live key is never retargeted. |

The admin who issues or rotates a key owns it. Every request re-checks that the owner
is still an admin of the org, so removing their role, deleting their account or merging
it away revokes the key. Another admin takes over by rotating.

Connections migrated from older tokens can hold several legacy keys. The first issue or
rotation replaces all of them with one key that has the connection's full operation
list, and asks for explicit confirmation first; see
[replacing migrated connection keys](org-mmr-sync-api.md#replacing-migrated-connection-keys).

### Operations

| Operation | Allows | Feature |
|-----------|--------|---------|
| `mmr:read` | `GET mmr-sync/` | MMR sync API |
| `mmr:write` | `POST mmr-sync/` | MMR sync API |
| `promotion:read` | `GET integration/v1/contact-receipts/`: a bound event's receipt history | Promotion |
| `promotion:write` | `POST integration/v1/contact-receipts/`: import external contacts and settle promotion points | Promotion |
| `promotion:import` | the same import as `promotion:write`; kept for existing keys | Promotion |

`promotion:write` does not create templates or send messages. A key with only
`promotion:import` gets no read access. An outbound service's own scope names are not
DraftForge grants.

## Outbound destination

| Field | Rule |
|-------|------|
| Base URL | `https://` only, port 443 only, no user name, password or fragment. Hosts that resolve to a private, loopback, link-local, multicast, reserved or cloud-metadata address are refused when DraftForge connects, including IPv6 forms that embed an IPv4 address. |
| Auth | `none`, `bearer` (`Authorization: Bearer …`), `api_key_header` (`X-API-Key: …`) or `api_key_field` (the credential fills one query key or one top-level body key whose value is `{{credential}}`) |
| Credential | Required by every auth mode except `none` before an outbound direction can be turned on |

MMR push and MMR pull use the same base URL and credential. A second service, or a
second credential, needs a second connection.

DraftForge never follows a redirect, never uses an HTTP proxy, and gives each request
15 seconds in total (DNS, connect, TLS and read). Responses are capped at 1 MiB after
decompression.

**Changing the origin.** Saving a different scheme, host or port when a credential is
stored needs a replacement credential or an explicit **Clear** in the same save;
otherwise the save is refused with `credential_required_for_new_origin`. A stored
credential is only ever sent to the origin it was entered for.

### Who authorizes outbound work

Outbound work always runs on one admin's authority:

- With a credential, that admin is the **credential owner**: whoever last saved the
  credential.
- With auth `none`, it is the **outbound authorizer**: the admin who turned on an
  outbound direction, switched auth to `none` with a direction on, or changed the
  origin. Creating or editing a connection for other reasons does not make anyone the
  authorizer.

Switching to a credentialed mode clears the authorizer; switching to `none` scrubs the
credential and makes the acting admin the authorizer. Nobody can name another user.

DraftForge re-checks that this admin is still an active org admin, and that the
feature is still unlocked, when work is queued, before each network request and before
results are written. If they lose the role, are deleted or are merged into another
account, DraftForge clears the credential (or the authorizer), turns the outbound
directions off and records it in the org log. Nothing is transferred: an admin must
enter the credential again, or turn the direction on again, to take over.

## MMR push

When a member's assigned MMR changes, each connection with MMR push on gets a delivery.
Verification-only changes, and members who leave the org, send nothing.

```http
POST {base URL}/api/v1/organizations/{org_id}/mmr
Authorization: Bearer <outbound credential>
Idempotency-Key: 8f3c…
Content-Type: application/json

{"schema_version": 1, "delivery_id": "8f3c…", "org_id": 7, "game_type": 1,
 "entries": [{"org_user_id": 42, "steam_id": "12345", "discord_id": "9876543210",
              "mmr": 4800, "revision": 5}]}
```

- The path is configurable on the **MMR push** tab (`{org_id}` and `{game_type}` are the
  only path slots). IDs are decimal strings.
- `mmr: 0` means the value was cleared.
- `revision` comes from one counter per org and game, so it only increases for a
  player, also across leave/rejoin and account merges. Drop any entry whose revision is
  not newer than the last one you applied for that `(org_id, game_type, player)`.
- A member's identity change (Steam or Discord ID, account claim or merge) sends the
  current value again at a new revision.
- Answer `2xx` with `{"delivery_id": "<same id>", "status": "applied"}` or
  `"unchanged"`. Anything else pauses the delivery.

| Answer | Result |
|--------|--------|
| ack as above | `applied` |
| timeout, network or DNS failure, `408`, `429`, `5xx` | `retry`, backing off from about 30 seconds and doubling up to 30 minutes, with jitter, at most 5 attempts, then `paused` (`retries_exhausted`) |
| `401`, `403` | `paused` (`auth_failed`) |
| any other status | `paused` (`schema_rejected`) |
| `2xx` without a matching ack | `paused` (`invalid_acknowledgement`) |

A retry reuses the same delivery ID. An older unsent revision is superseded by a newer
one and is never sent after it. A timeout can mean the service already applied the
change, so receivers must use the idempotency key and revision; exactly-once delivery
is not promised.

**Loop guard.** A change that came in through a connection (inbound push or pull) is
not pushed back to that same connection; other connections still get it. Services that
transform values can still bounce a change between them, so once one connection has
received 10 deliveries in 10 minutes for the same member that were caused by other
connections, its next delivery for that member pauses with `sync_loop_suspected`.

**Turning off while a request is in flight.** Disabling a connection or direction holds
every queued delivery, but a request already on the wire may still reach the service.

### Recovery

The **Recovery** tab lists paused deliveries with their reasons (counted over every
paused delivery, not just the shown page).

| Action | Use it when |
|--------|-------------|
| **Resume** | The reason is fixed under the current configuration: `auth_failed` after replacing the credential, `schema_rejected` after editing the push settings on the same origin, `sync_loop_suspected` after review. Moves up to 500 deliveries back to retry per call. |
| **Resync current state** (confirmed) | After an origin change (`origin_changed`), or to start over. Cancels every unsent delivery and queues one current-state delivery per member with a value, at new revisions. |

Re-enabling a connection never resumes paused deliveries by itself. Resume never sends a
paused delivery to a new origin. Resync works in transactions of 500 members; if the
configuration changes during a resync it stops with `configuration_changed` after the
chunks already committed, and running it again starts over.

## MMR pull

A pull fetches MMRs for the org's **current members** and writes them as assigned org
MMRs. Rows for people who are not members are reported as unmatched; nobody is ever
added to the org.

### Request

| Setting | Values |
|---------|--------|
| Path | relative to the base URL; `{org_id}` and `{game_type}` are the only path slots |
| Method | `GET`, or `POST` with a JSON body. A POST pull must be read-only on the service side. |
| Query and body | string keys with JSON values; each value is a literal or exactly one placeholder |
| Request mode | `org` (one paginated query), `member_batches` (100 members per request) or `per_member` (one request per member; an estimate above 100 requests needs acknowledgement) |

Placeholders are whole values, not text inside a string:

| Placeholder | Value |
|-------------|-------|
| `{{org.id}}`, `{{game_type}}` | the org and game |
| `{{players.steam_account_ids}}`, `{{players.steam64_ids}}`, `{{players.discord_ids}}` | the batch's IDs: a JSON array of strings in a body, comma-separated in a query |
| `{{player.steam_account_id}}`, `{{player.steam64}}`, `{{player.discord_id}}` | one member's ID (per-member mode) |
| `{{page}}`, `{{page_size}}`, `{{cursor}}` | pagination |
| `{{credential}}` | the stored credential, only in the one designated field of `api_key_field` auth |

Members without the needed ID are left out and counted as `missing_identifier`; a
literal `None` is never sent. Keys that look like secrets (`api_key`, `apikey`, `key`,
`token`, `access_token`, `secret`, `password`, `auth`, `authorization`, `signature`,
`sig`) refuse literal values (`secret_like_literal`): put the secret in the credential.
There are no custom headers, expressions or scripts.

### Response mapping

| Setting | Meaning |
|---------|---------|
| List path | dot path to the array of rows (`data.players`, `results.0.items`); empty means the response is the array |
| Player ID path, ID type | where the player ID is and whether it is a `steam_account_id`, `steam64` or `discord_id`. Steam IDs must be integers or digit strings. |
| MMR path | where the MMR is: a JSON integer within the game's range, or `null` |

Paths have at most 8 segments and 256 characters, with no wildcards. A malformed
envelope fails the run. A bad row is reported (`invalid`, `unmatched`) and the rest are
still applied. If several rows map to one member with the same value it is applied
once; with different values none of them is applied (`ambiguous_duplicate`).

### Pagination

| Kind | Settings | Ends when |
|------|----------|-----------|
| `none` | | after one request |
| `page` | start page 0 or 1, page size 1–500, optional `has_more` path | an empty or short page, or `has_more` is false |
| `cursor` | next-cursor path (a string or number up to 1 KiB) | the cursor is missing, null or empty |

A repeated page or cursor fails with `pagination_loop`. DraftForge never follows a URL
from the response.

### Limits

| Limit | Value |
|-------|-------|
| Requests per run | 100 |
| Rows per run | 10,000 |
| Response per page / per run | 1 MiB / 10 MiB decompressed |
| Time per request | 15 seconds |
| Time per run | 10 minutes |
| Pulls per connection | 1 at a time (a second **Pull now** returns the running one) |
| Outbound requests per org | 2 at a time, across pulls, pushes and tests |
| Configuration | 32 KiB JSON, 100 template values |

If the service still reports more data when a limit is hit, the run fails with
`pull_incomplete`; a truncated pull never shows as successful. A failed request is not
retried inside the run; the run fails and nothing is written.

### How values are written

1. The run snapshots the member list, their IDs and each member's current revision.
   Members who join later wait for the next run; members who leave are skipped.
2. Every page is fetched and staged. Nothing is written until all pages arrived.
3. Staged values are applied in chunks of 500 members. Each chunk locks the members and
   re-reads their value, verification and revision. If anything changed since the
   snapshot (a manual edit, another sync, a verification) the member is a `conflict`
   and keeps its value.
4. The overwrite policy is checked on the re-read value:

| Policy | Replaces |
|--------|----------|
| `missing_only` (default) | only a member whose value is 0 (unset) |
| `unverified_only` | only values that are not verified |
| `replace` | any value |

A refused overwrite is `skipped_policy`. A member missing from the response keeps their
value; a pull never clears an MMR because a row is absent.

The run as a whole is not one transaction: if it stops between chunks it shows as
`partial` and resumes from the next unfinished chunk.

**Mark verified** is off by default. When on, the admin who authorizes the connection's
outbound work (see above) is recorded as the verifier, and unchanged values are
re-verified. The usual verification rules apply (no self-verification, staff members
need an admin reviewer): a value that admin may not verify is still written, unverified.
The run's `verified` counter shows how many were verified. With it off, a changed value
is written unverified and clears any earlier verification.

### Schedule

**Interval** is manual only, or every 15 to 10,080 minutes. Enabling the schedule sets
the first run one interval ahead. A sweep runs every minute, so a run can start up to
about a minute late, and later while the worker is busy; missed intervals are not
replayed. A manual pull and a scheduled pull never overlap.

## Test configuration

**Test configuration** works on a saved connection whose direction is still off, so you
can check it before enabling. It never writes MMRs, deliveries or receipts:

- **MMR pull** fetches the first page and shows a summary of the mapped rows and issue
  codes, not the response itself.
- **MMR push** and **Promotion push** send `GET {base URL}/health` with no member data.
  A passing test shows the destination and credential are accepted; it does not prove
  the service accepts writes.

Archived connections cannot be tested.

## Runs and history

The **Runs** tab lists tests and pulls, newest first, 50 per page, with counters
(updated, unchanged, unmatched, invalid, conflicts, skipped by policy, missing
identifier, verified) and fixed error codes. Each run keeps at most 100 example issues
and the total counts. Runs are kept for 90 days. A run that is queued but not picked up
shows that the worker is waiting or unavailable.

## Promotion

An org has one promotion contact stream. Promotion read and write grants live on that
connection only. Until a site operator adopts the org's deployment promotion setup (see
the [operator guide](../deployment/org-api-connections.md#adopting-legacy-promotion-sync)),
the **Promotion** tab shows "managed by deployment" and promotion push cannot be turned
on (`not_promotion_stream`). After adoption the tab edits the event bindings and
promotion push (bearer auth only).

Sends recorded before an event's binding took effect are held as `backlog_held`.
**Send backlog** shows the count and releases them once confirmed. **Resume** moves
paused receipts back to pending with the same delivery ID and payload.
`reconciliation_required` receipts need an operator. See
[promotion contact sync](promotion-contact-sync.md).

## Rate limits for admins

| Action | Limit |
|--------|-------|
| Create, edit, enable, issue or rotate | 30 per minute per org and per admin |
| **Pull now**, **Test configuration** | 5 per minute per org and per admin |
| Tests | 100 per day per org |

Reading, revoking keys, archiving and turning switches off are never limited.

## Archive

Archiving revokes the inbound key, clears the outbound credential, turns everything off
and cancels queued runs. Runs, deliveries and the org log stay readable.

## Automated tests

The Playwright suite `org-features/org-api-connections.spec.ts` drives the real
management, scheduling and run code, but its external service is simulated in the test
backend: no request leaves the test stack. The safe transport (address pinning, TLS
host checks, redirects, size and time limits) is tested separately against local
sockets. Neither is proof that a particular external service works; check each one with
**Test configuration** and a supervised first pull.

Code: `backend/org/api_connections/`, `backend/org/api_tokens/`,
`frontend/app/features/api-tokens/`.
