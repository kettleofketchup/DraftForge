Org conduct adds three migrations: `org.0013_conduct` (the attendance outcome and conduct
settings tables), `events.0034_event_conduct_finalized_at` (a nullable field on events)
and `app.0108_orglog_conduct_actions` (new org log action choices). They run with the
usual migrate step and need no data backfill: past events have no attendance record, so
tracking starts with the next event that closes after an organization gets the feature.
Reversing the migrations drops the new tables and the `conduct_finalized_at` field.

The feature is locked by default. A site admin unlocks it per organization from the
organization's locked features; until then no attendance is recorded and nothing changes
for members.
