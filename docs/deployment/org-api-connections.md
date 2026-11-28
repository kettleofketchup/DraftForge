# Operating org API connections

This page is for whoever runs a DraftForge deployment. What org admins see is in
[Org API connections](../features/org-api-connections.md).

Run the `python manage.py` commands below in the backend container (`/app/backend`),
not in a Celery container.

---

## What the deployment needs

| Need | Why | Without it |
|------|-----|-----------|
| `ORG_API_CREDENTIAL_KEYS` on the backend | encrypts outbound credentials | outbound credentials cannot be saved or used; inbound keys, legacy tokens and deployment promotion sync keep working |
| Celery worker and beat running `config.celery_light` | the `org-api-sync-sweep` beat entry (every 60 s) claims due pulls, tests and deliveries; `org-api-sync-cleanup-daily` (03:30) purges old runs | runs stay queued and the UI reports the worker as unavailable; nothing is lost |
| `INTERNAL_SERVICE_TOKEN` on backend and workers, worker addresses in `INTERNAL_SERVICE_ALLOWED_IPS` | the light worker has no database; it calls `/api/internal/org-api-sync/…` and Django does the work | sweeps fail with `org_api_sync_claim_unavailable` |
| Public HTTPS egress on port 443 from the backend | outbound requests leave from the backend process, not the worker | tests and runs fail with a network error code |
| `ORG_API_SCHEDULED_PULLS` (optional) | scheduled pulls; default on, except on test stacks | `false` stops scheduled pulls; manual pulls, tests and pushes still run |

### Encryption key ring

`ORG_API_CREDENTIAL_KEYS` is a JSON list of keys, newest first:

```json
[{"id": "2026-11", "key": "<base64 of 32 random bytes>"}]
```

- `id`: 1–64 characters from `A-Z a-z 0-9 _ -`, unique.
- `key`: standard base64 of exactly 32 bytes. Generate one with
  `python3 -c 'import base64, os; print(base64.b64encode(os.urandom(32)).decode())'`.
- The first key encrypts. Every key in the list can decrypt.
- If the value is missing or any entry is malformed, the whole ring is refused
  (`credential_keys_unavailable`). There is no fallback key, and the Django secret key
  is never used.

Credentials are encrypted with AES-GCM. The ciphertext is bound to the org, the
connection, the credential type and the destination origin, so copying it to another
connection or pointing the connection at another host makes it unreadable.

**Where to put it.** It is a server secret. Only the Django backend reads it:

- Docker Compose release stack: add it to `backend/.env` on the host (that file is
  mounted into the backend container). Never put it in `docker/.env.*`: those files are
  committed and are also given to the frontend container.
- Helm: add it to a Secret listed in `extraEnvSecrets`.

The frontend, the Celery worker settings (`config.settings_celery`) and every task
message are kept free of it; a release-gate test checks this. Task messages and
internal API responses carry only run and delivery IDs and lease tokens.

**Back it up.** Store the key ring with the database backup but separately from it. A
database backup without its keys has unreadable outbound credentials; org admins would
have to enter every credential again. A key ring without the database exposes nothing.

### Rotating the key

1. Generate a new key and put it **first**, keeping the old one after it. Restart the
   backend. New and replaced credentials now use the new key.
2. Check every stored credential decrypts:
   `python manage.py reencrypt_org_api_credentials --dry-run`. It prints the connection
   IDs it checked, then the count, and stops with `<id>: <code>` at the first one it
   cannot read. Nothing is written.
3. Re-encrypt: `python manage.py reencrypt_org_api_credentials`. Each connection is
   locked, decrypted, encrypted with the first key, verified and saved in its own
   transaction. Running it again is safe.
4. Confirm nothing still uses the old key:

    ```python
    from org.models import OrgApiConnection
    OrgApiConnection.objects.exclude(outbound_credential_ciphertext="") \
        .exclude(outbound_credential_key_id="<new id>").count()   # must be 0
    ```

5. Remove the old key from the list, restart, and run the dry run again. It must
   finish without an error before the old key is destroyed.

## Workers and load

Each sweep claims at most 20 items. Every step is a separate internal request: one
network attempt (at most 15 seconds) or one commit of at most 500 members, then the
worker queues the next step. The internal client waits 30 seconds per step. A backend
process runs at most 4 steps at once and answers `429 busy` beyond that; the worker
retries 5 seconds later. Each org has at most 2 outbound requests in flight.

A run that holds no live lease is picked up again by the next sweep. A run older than
one hour is failed with `run_abandoned`. Runs, their checkpoints and staged pull rows
are deleted 90 days after they finish (`python manage.py cleanup_org_api_runs
[--dry-run]` does the same on demand). MMR values, deliveries and the org log are kept.

### Logs

All lines carry `system=org`, `subsystem=api_connections`, and only IDs, counts,
directions and fixed error codes: never URLs with query strings, credentials or
response bodies.

| Event | When |
|-------|------|
| `api_connection_lifecycle` | create, edit, enable, disable, issue, rotate, revoke, archive |
| `api_connection_owner_lost` | a credential owner or authorizer lost authority; outbound turned off |
| `api_connection_authority_rejected` | work refused because its authority no longer holds |
| `api_connection_pull_queued`, `api_connection_test_queued` | a run was queued (`scheduled` says which) |
| `api_connection_pull_page`, `api_connection_run_finished` | pull progress and result |
| `api_connection_delivery` | each MMR push attempt and its state |
| `api_connection_deliveries_resumed`, `api_connection_deliveries_resynced` | recovery actions |
| `api_connection_schedule_skipped`, `api_connection_schedule_failed`, `api_connection_schedule_sweep_failed` | a scheduled pull could not be queued |
| `api_connection_runs_abandoned`, `api_connection_runs_purged` | housekeeping |
| `org_api_sync_claim_unavailable` | the worker could not reach the internal API |

Promotion sends over a connection keep the `subsystem=integration` and `promotion`
events listed in [promotion contact sync](../features/promotion-contact-sync.md#logs).

## Upgrading

The `org` migrations `api_connections`, `backfill_api_connections` and the
`api_connection_*` / `promotion_*_actions` migrations after them add the connection
tables and wrap every existing token in a connection:

- A token with only MMR operations gets its own connection, enabled for inbound use.
- Every `promotion:import` token in an org, revoked ones included, goes on one legacy
  promotion connection. Each keeps its own grants until an org admin issues or rotates
  a key there, which needs explicit confirmation of the combined grants.
- No grant is widened, every key keeps working with the same rate budgets and usage
  history, and no delivery is created. Current MMRs get revision 0.

The legacy `api-tokens/` endpoints keep their behaviour, including the MMR-pair default
when `operations` is left out. New connections start empty and off.

Deployment promotion settings (`PROMOTION_SYNC_BINDINGS`, `PROMOTION_ADAPTOR_*`) keep
working unchanged for every org that has not been adopted.

## Adopting legacy promotion sync

An org whose promotion sync is configured in the deployment environment can move it to
its promotion connection, so its admins manage event bindings in Org Settings. Only an
operator can do this.

The deployment `PROMOTION_ADAPTOR_API_KEY` serves every bound org, so it is **never**
copied to an org. Adoption needs a credential the adaptor issued for this org alone. If
the adaptor cannot issue one, leave the org on the deployment settings.

```bash
python manage.py adopt_org_promotion_sync --org 41 --operator <superuser> \
  --base-url https://adaptor.example --credential-file /run/secrets/org41-adaptor --dry-run
python manage.py adopt_org_promotion_sync --org 41 --operator <superuser> \
  --base-url https://adaptor.example --credential-file /run/secrets/org41-adaptor
```

The command checks the org's deployment binding (guild and events), copies only the
non-secret bindings, and attaches the stream to the org's legacy promotion connection,
or to a new disabled one. Receipt and outbox history stay as they are. The operator
becomes the credential owner until an org admin replaces the credential. Promotion push
stays off. Delete the credential file afterwards.

| Refusal | Meaning |
|---------|---------|
| `operator_required` | `--operator` is not a superuser |
| `not_legacy_bound` | the org has no deployment promotion binding |
| `unsafe_destination` | the base URL is not public HTTPS on port 443. Private or loopback adaptor addresses cannot be adopted; keep the org on deployment settings. |
| `binding_mismatch` | the deployment binding does not match the org's Discord server or events |
| `promotion_stream_exists`, `promotion_keys_elsewhere` | another connection already holds the stream or active promotion keys |

After adoption that org only uses its connection. If the connection or its promotion
push is off, sends are held; they never fall back to the deployment adaptor. Sends
recorded before a binding took effect are held as `backlog_held` until an org admin
releases them.

### Before turning promotion push on

Leave promotion push off until the adaptor confirms durable writes for the org. The
echo reconciliation that keeps an imported copy of a DraftForge send from taking the
promotion point is in place and tested in both arrival orders, but the external writer
must also return the applied contact ID and honour the delivery ID as an idempotency
key. While it answers `writeback_disabled`, receipts stay `paused`, which is not
success. `reconciliation_required` rows still need the operator procedure in
[promotion contact sync](../features/promotion-contact-sync.md#running-the-dispatcher).

## Rollout

1. Deploy. Check migrations, that existing tokens still authenticate
   (`GET mmr-sync/` with a known key) and that deployment promotion dispatch behaves as
   before.
2. Provision `ORG_API_CREDENTIAL_KEYS`, restart the backend, and run
   `reencrypt_org_api_credentials --dry-run` (count 0 on a fresh install).
3. Confirm the worker sweep runs: `org-api-sync-sweep` in beat logs, no
   `org_api_sync_claim_unavailable`.
4. With one org: create a connection, save it disabled, run **Test configuration**,
   then **Pull now** with `missing_only` and Mark verified off. Read the run report and
   the org log before turning on a schedule or push.
5. Widen to more orgs. Turn promotion push on only after the section above.

## Rollback

Turn work off; do not reverse migrations once connections have written data.

1. Set `ORG_API_SCHEDULED_PULLS=false` and restart the backend: no new scheduled pulls.
2. Turn connections off. Org admins use the connection's **Enabled** switch (always
   available, even when rate limited). An operator can do it for every connection from
   `python manage.py shell`, with the same audit entry the switch writes:

    ```python
    from app.models import CustomUser
    from org.api_connections.audit import audit_connection
    from org.api_connections.config import apply_config_patch
    from org.api_connections.lifecycle import invalidate_work
    from org.models import OrgApiConnection

    operator = CustomUser.objects.get(username="<superuser>")
    for c in OrgApiConnection.objects.filter(enabled=True, archived_at__isnull=True):
        c = apply_config_patch(c, actor=operator, patch={"enabled": False},
                               expected_version=c.config_version)
        invalidate_work(c)
        audit_connection(c, actor=operator, action="disable_api_connection",
                         fields=["enabled"])
    ```

3. Queued deliveries pause (`configuration_changed`) and are not sent; queued runs are
   canceled. A request already on the wire may still complete.

Configuration, stored credentials, run history, deliveries, revisions and the org log
all stay. Turning a connection back on does not resume paused deliveries; admins use
**Resume** or **Resync** on the Recovery tab. Rolling the code back to a release
without connections leaves the new tables unused; legacy tokens keep working because
their rows are unchanged apart from the added connection link.

## What has and has not been verified

The automated suites cover the transport (address pinning, TLS host checks, redirect,
proxy, size and deadline limits) against local sockets and synthetic certificates,
PostgreSQL races for keys, pulls, deliveries and the promotion stream, both echo
arrival orders, migrations of existing tokens, and the full UI flow in Playwright with a
simulated external service inside the test backend. None of them calls a real external
service. Before relying on a specific service, run **Test configuration** and a
supervised first pull against it, and confirm its acknowledgement and idempotency
behaviour for pushes.
