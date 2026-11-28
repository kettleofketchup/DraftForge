# Live Discord messages

New subscriber event reminders are Discord Components V2 messages. If an organizer changes the event time, someone takes a seat, or signups close, DraftForge updates the original DM. Multiple subscribers to the same event each keep their own message. The existing signup button handler enforces the event's current admission rules when a member clicks.

## What enrolls a message

The subscriber sender identifies new V2 reminders with `live_v2: true` in its DM claim context. It also records a SHA-256 digest of the components it sent. On successful finalization, the backend uses the channel and message IDs from Discord to register the reminder for updates. Replaying a receipt is safe. Historical reminders, failed deliveries and one-off signup confirmations retain their original behavior. The [DM ledger](discord-dm-ledger.md) records sends and component clicks.

The `event_signup_reminder` renderer uses the same seated signup count as the event page. The states `rsvp`, `pending_approval`, `approved` and `confirmed` each hold a seat. Waitlisted, tentative, rejected, cancelled and dropped signups do not hold seats. The send, preview and edit paths share the same component builder. Editing leaves the original message ID, delivery outcome and click history intact.

## Follow an edit

1. Find the delivery in Django admin under **Discord DMs**. A delivered subscriber reminder with the V2 marker and both Discord IDs can enroll.
2. Look up its Discord message ID under **Live Discord Messages**. The source ID identifies the event used to render it. Registration starts dirty to reconcile changes made during delivery.
3. A relevant database write marks reminders for that event dirty. Celery beat schedules `discordbot.tasks.refresh_live_messages` every 15 seconds. The worker gets due work from the backend over the authenticated internal API. Worker capacity and Discord rate limits affect when an edit appears.
4. The backend renders current data when it claims a row. When the rendered digest matches the last confirmed send or edit it clears that revision locally. Otherwise the worker sends a PATCH with the new components and explicit mention suppression.
5. A successful completion records the components Discord accepted for the leased revision. Changes that arrived during the edit stay pending. If they render the same components, the next claim advances the revision locally. A late success from an expired worker makes the visible content uncertain and schedules a corrective PATCH.

| Result | What happens to the message |
| --- | --- |
| Discord accepts the edit | Record the successful digest and revision. |
| Discord requests a retry or is unavailable | Leave the row eligible after a delay. A retry edits the original destination. |
| Discord identifies an unknown message or channel | Mark the destination missing and stop trying to edit it. |
| Discord rejects the payload or access | Pause the row. A later matching source change makes the revision eligible for another edit. |
| The source event disappears | Stop refreshing its reminders. |

A global Discord rate limit pauses live workers across the deployment for the reported interval. A rejected bot token pauses them for 60 seconds. The shared pause uses Redis, and each message retains its own retry time in the database. A worker without bot credentials leaves the queue untouched. In a test stack, claims are restricted to the configured test recipient.

The read-only tracking admin exposes queue metadata. Rendered text and button URLs are recreated for each claim. The original DM ledger stays available for delivery history.

## Add a message type

1. Add a stable renderer name in `discordbot.live_renderers` and a builder that accepts a domain subject ID. Resolve all displayed data on the backend. Return current V2 components or indicate that the source is gone. Use deterministic values so an unrelated save does not change the digest.
2. After a successful bot send, register the actual edit destination through `discordbot.live_messages.track_message`. Supply `renderer`, `subject_id`, `channel_id`, and `message_id` as keywords. For a DM, pass its `DiscordDM` row as `dm` and use the ledger's successful-finalization path. A forum message belongs to its thread channel.
3. In the transaction that changes a dependency, call `invalidate_live_messages(renderer, subject_id)` for each affected subject. Use the write path for operations that bypass Django signals, including `QuerySet.update()` and `bulk_update()`. If a child row moves between parents, account for both the old and the new subject.
4. Add tests that go through the real sender and relevant model writes with a mocked Discord transport. Include a second unrelated subject, a rollback, a change during an in-flight edit, and a repeated render that sends no PATCH. Keep credentials and recipient IDs synthetic.

Register a dependency at app startup. For a signup, a partial save can leave an unsaved event assignment on the instance. A stale instance can also point to an old event when the signup is deleted. Resolve the persisted parent after saves, and lock the signup before deletion to keep its parent stable until commit. The signup pre-save receiver also invalidates the former event when a signup moves.

```python
from discordbot.live_signals import watch_live_fields
from events.models import EventSignup

def signup_event_ids(signup):
    return EventSignup.objects.using(signup._state.db).nocache().filter(
        pk=signup.pk
    ).values_list("event_id", flat=True)

watch_live_fields(
    EventSignup,
    renderer="event_signup_reminder",
    fields={"event", "event_id", "status"},
    subject_ids=lambda signup: list(signup_event_ids(signup).select_for_update()),
    saved_subject_ids=signup_event_ids,
)
```

A bulk writer that changes rows for a known event can emit the domain signal inside its transaction. This also applies to application-managed SQL. Writes from a separate process that edits the database directly must invoke an equivalent application hook to schedule a refresh.

```python
from django.db import transaction
from events.live_signals import event_data_changed
from events.models import Event

with transaction.atomic():
    changed = Event.objects.filter(pk=event_id).update(description=new_description)
    if changed:
        event_data_changed.send(sender=Event, event_id=event_id)
```

Worker calls use `POST /api/internal/discord/live-messages/claim/` and `POST /api/internal/discord/live-messages/<pk>/finish/`. A claim returns one lease with HTTP 200. A plain HTTP 204 ends the batch. A 204 with `X-Live-Edit-Scan: limit-reached` tells the worker to keep looking for eligible edits. Each request scans up to 32 rows, and each worker run makes up to 20 claim requests. Each completion carries the lease token.

Discord's API documents which fields can be edited on bot-authored messages and how retry delays are reported. [Edit Message](https://docs.discord.com/developers/resources/message#edit-message) · [Rate Limits](https://docs.discord.com/developers/topics/rate-limits)
