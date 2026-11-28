# Live updates for Discord Components V2 messages

## Outcome

A subscriber receives one event reminder. If an organizer changes the start time or closes signups, that same DM shows the new time or stops offering Sign Up. When a signup changes the seated count, reminders for that event refresh. The existing interaction handler continues to enforce admission rules at click time.

This feature starts on the DM ledger core in [PR #1020](https://github.com/kettleofketchup/DraftForge/pull/1020). Subscriber reminders are the first live message type. Signup confirmations acknowledge individual interactions. Historical reminders may contain legacy embeds. Neither provides evidence that a particular sent message enrolled in this renderer. Existing channel signup posts already have their own edit path.

## Ownership

| Component | Responsibility |
| --- | --- |
| DM ledger | Claim the original send, prevent duplicate deliveries, retain the outcome, Discord receipt and click history |
| `LiveDiscordMessage` | Identify one bot-authored destination, its renderer and source, and hold outstanding edit work |
| Django backend | Register a delivered message, invalidate dependent rows in the database transaction, render current domain data and claim or complete edits |
| Celery | Poll the authenticated internal API, PATCH the returned Discord destination through the shared rate limiter and report the outcome |
| Django admin | Inspect delivery and edit state without modifying the history |

A separate edit row lets a source have multiple recipients and lets future channel messages share the same edit worker. Embedding the edit queue in the DM ledger would make channel messages depend on DM-specific fields. Enqueuing a PATCH for every save would introduce duplicate deliveries of work, stale payloads and a gap between database commits and broker availability.

## Lifecycle

1. The subscriber sender opts into `event_signup_reminder` using the allow-listed `live_v2` marker. It sends native Components V2 through the existing ledger. Successfully finalized receipts with both destination IDs register idempotently.
2. Registration starts dirty. A change can commit after the sender renders but before Discord delivers the message. The initial send stores a component digest. The first reconciliation reads the current source, covering that interval without PATCHing an unchanged reminder.
3. Event and signup mutations invalidate only the rows rendering that source. Tenant branding is a dependency where the renderer reads it. A rollback also discards invalidations from the rolled-back write. Writers using bulk ORM operations must explicitly invalidate affected subjects.
4. A worker claims one eligible destination at a time. A lease identifies the render revision being delivered. The backend renders from current committed data and compares the payload digest with the last confirmed send or edit. Equal content can be acknowledged without a Discord request.
5. The worker edits exactly that channel/message pair and supplies an explicit empty mention policy. Finishing the claimed revision leaves newer dirty work pending. A worker crash leaves an expiring lease and the next claim renders again. A lease protects database state. Discord offers no conditional edit operation, so a late success for an obsolete lease triggers a corrective refresh.
6. A deleted source or confirmed missing target ends automatic attempts for that destination. A permissions or payload rejection pauses work until the next matching source change. Transient failures reschedule it. Ambiguous edit outcomes can retry the same message. No edit failure calls the original send path.

The runner stores IDs, progress and a digest. The renderer recreates content from domain tables. Rendered text, button URLs, credentials and personal message content do not belong in claim history or logs.

## Rendering and compatibility

Use one subscriber-reminder builder for the initial send, the existing message preview and later edits. It uses the project's seated signup count, event timing, capacity, display fields and self-service admission policy. Keep the existing signup custom ID and event-page link. Restrict mentions on edits even when an organizer writes mention syntax into an event description.

The migration adds edit state without inferring renderer eligibility from old message contents. Skipped, failed, uncertain and legacy sends do not become edit targets. A successful edit leaves the original DM delivery outcome and click history intact.

## Acceptance

- A delivered opted-in reminder is tracked exactly once. Replaying successful finalization leaves one receipt and one edit target.
- An event write reaches reminders for that event. A different event, a rollback or a rendered no-op sends no PATCH.
- Both sides of a relationship change are invalidated when the change affects the rendered count. A burst of writes coalesces by destination.
- A change committed during a PATCH remains eligible for another render. An abandoned lease recovers, and a stale completion cannot clear newer work.
- A confirmed deletion retires the target. A rate limit or transient outage schedules a retry without creating a replacement DM.
- The Celery task runs with the database-free worker settings. Tests use synthetic IDs and mocked Discord responses.
