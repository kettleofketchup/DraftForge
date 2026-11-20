- The Discord signup post now follows the event state. Every state change refreshes
  it, including restarts and the hourly auto-close. Outside open signups it shows a
  status line (roll call, in progress, finished, cancelled). Sign Up and Tentative
  appear only while self-serve signups are open, and Decline only until the event
  starts. A failed edit is retried up to `SIGNUP_POST_READ_RETRIES` times. Each
  applied edit logs `signup_post_edit_applied` with `lag_ms`, the time since the
  oldest change it shows, at warning level above 10 seconds (#537).
