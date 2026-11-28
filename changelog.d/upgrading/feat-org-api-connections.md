Migrations wrap every existing org API token in a connection without changing its grants,
budgets or usage; promotion-import tokens in one org share one legacy promotion
connection. No outbound work starts on upgrade.

Outbound credentials need a key ring that only the backend process uses. Add
`ORG_API_CREDENTIAL_KEYS` to `backend/.env` (or a Helm `extraEnvSecrets` Secret), never
to `docker/.env.*`. Both locations also reach the Celery worker, beat and Discord bot
containers, which receive the variable but never read it:

```bash
python3 -c 'import base64, os; print(base64.b64encode(os.urandom(32)).decode())'
# ORG_API_CREDENTIAL_KEYS=[{"id":"2026-11","key":"<that value>"}]
```

Back the key ring up separately from the database. Without it outbound credentials
cannot be saved or used, while inbound keys and deployment promotion sync keep working.
The light Celery worker and beat need `INTERNAL_SERVICE_TOKEN` as before; the new
`org-api-sync-sweep` and `org-api-sync-cleanup-daily` beat entries ship in both Celery
configurations. Set `ORG_API_SCHEDULED_PULLS=false` to stop scheduled pulls. Key
rotation, legacy promotion adoption (`adopt_org_promotion_sync`) and rollback are in
docs/deployment/org-api-connections.md.
