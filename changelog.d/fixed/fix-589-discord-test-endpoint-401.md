- Discord HTTP calls that get a 401 (rejected bot token) now log `discord_auth_failed`.
  The test-only Discord sync and send-notification endpoints return 503
  `discord_auth_failed` right away instead of hanging or reporting "DMs disabled" (#589).
