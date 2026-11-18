- Discord signup post edits are now debounced and run one at a time per event,
  so a burst of signups no longer leaves the post showing an older list. When
  the signup list cannot be read, an edit retries a few times
  (`SIGNUP_POST_READ_RETRIES`) and then leaves the post unchanged instead of
  emptying it; the next signup change refreshes it (#573).
- When the signup list cannot be read, event announcements, attendance and
  profile reminders (including a reminder fired by hand from the admin) and
  subscriber DMs are skipped instead of sent with an empty list. They go out on
  the next scheduler pass; a reminder fired by hand does nothing in that case.
