Org conduct adds three migrations: `org.0013_conduct` (the attendance outcome and conduct
settings tables), `events.0034_event_conduct_finalized_at` (a nullable field on events)
and `app.0109_orglog_conduct_actions` (new org log action choices). They run with the
usual migrate step and need no data backfill: past events have no attendance record, so
tracking starts with the next event that closes after an organization gets the feature.
Reversing the migrations drops the new tables and the `conduct_finalized_at` field.

The feature is locked by default and every enforcement mode is off, so nothing changes
for members until a site admin unlocks it and an organization admin turns a mode on.
