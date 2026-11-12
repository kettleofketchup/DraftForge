- `populate_all` no longer hangs when Discord is unreachable and no bot token is
  configured. The guild member fetch behind the demo avatars now skips the request
  without a token, and Discord REST calls from the member, guild and voice-activity
  helpers and the rate-limited sender now have a 10-second timeout. The
  voice-activity endpoint returns 503 when no bot token is configured.
