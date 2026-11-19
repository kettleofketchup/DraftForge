- The Discord signup post now updates when staff start roll call, reopen signups,
  start the tournament, complete or cancel the event. Each applied edit logs
  `signup_post_edit_applied` with `lag_ms`, the time since the oldest change it shows,
  at warning level above 10 seconds (#537).
