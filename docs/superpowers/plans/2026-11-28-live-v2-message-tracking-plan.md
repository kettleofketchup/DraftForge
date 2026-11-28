# Implementation plan for live Discord Components V2 updates

Base the feature branch and PR on `feature/dm-ledger-core` from [#1020](https://github.com/kettleofketchup/DraftForge/pull/1020). Compare the latest main and ledger heads for model, routing and migration drift. Preserve the delivery ledger's idempotency and the public signup-post worker's ownership.

| Step | Change | Verification |
| --- | --- | --- |
| 1. Inventory | Trace subscriber sends, preview, DM claim/finalize, event/signup mutations and Celery's database boundary. | Identify a single sender, renderer and durable owner for each supported destination. |
| 2. Store | Add `LiveDiscordMessage` in `backend/discordbot/models.py`, a forward migration and read-only Django admin. | Migrate a database containing ledger rows. Check destination uniqueness, independent rows for different recipients and migration drift. |
| 3. Render | Add the native V2 reminder builder in `backend/events/discord/embeds.py` and bind `event_signup_reminder` in `backend/discordbot/live_renderers.py`. Switch subscriber sends and preview to the shared builder. | Test open/closed and self-signup settings, seated counts, valid layouts and button IDs, limits and preview parity. |
| 4. Register | Extend the signup reminder context in `backend/discordbot/dm_context.py`. After successful ledger finalization, register both receipt IDs and an initially dirty subject in the same unit of work. | Exercise duplicate finalization, incomplete receipts, legacy, skipped and uncertain sends, and source changes during original delivery. |
| 5. Invalidate | Connect domain signals and mark dirty within source transactions. Explicitly invalidate sources after bulk changes affecting rendered values. | Test targeted fan-out, deletes, rollback and a burst of mutations. |
| 6. Claim and finish | Implement revision coalescing, ownership tokens, expiring leases, successful digest comparison and retry eligibility in `backend/discordbot/live_messages.py`. Expose authenticated internal views. | Test identical renders, concurrent claims, stale finishes, changes during edits, lease expiry, missing sources and invalid requests. |
| 7. Edit | Register a bounded Celery beat task that claims internal work, edits the exact message with suppressed mentions, then reports the outcome. | Use a fake transport for success, absent credentials, retry delays, Discord deletions, permission errors and unavailable internal endpoints. Run Celery settings and app-boundary checks. |
| 8. Deliver | Add contributor documentation, a changelog fragment and tests that run for the stacked PR. | Run targeted tests and applicable CI groups, migration checks, docs and changelog checks. Compare the outgoing diff against the ledger branch and open a draft PR against that same base. |

The stacked PR runs `.github/workflows/live-discord-messages.yml` against its ledger base. It discovers both apps’ `test_live_*.py` modules and also checks the migration graph, delivery choke point and worker app boundaries with Redis.

## Repeatable checks

Run from the repository root in the normal DraftForge test stack.

```bash
just test::run 'python manage.py makemigrations --check --dry-run'
just test::run 'python manage.py test discordbot.tests events.tests app.tests.test_celery_settings --parallel auto'
just test::affected --plan
just test::backend::all
python3 scripts/changelog.py check
just docs::build
```

Inspect the focused test output for an event update through to the destination-specific PATCH. Verify that the unchanged-render case makes zero transport calls, that a restart resumes outstanding work, and that the DM ledger guard still enforces its single send path. Report the commands actually executed and their results in the PR.
