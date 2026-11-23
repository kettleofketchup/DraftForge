- Tournament backend code started moving from `app` into a new `tournament`
  Django app, ahead of the model move. The tournament, team and game
  permission helpers are now in `tournament.permissions`, the team roster,
  audit, reference, leadership and completion services in
  `tournament.services`, the tournament signal receivers in
  `tournament.signals`, the tournament prefetch plan in `tournament.state`,
  the tournament list helpers in `tournament.listing` and `tournament.buckets`,
  `create_team_from_captain` and `serialize_tournament` in
  `tournament.functions`, the worker-side tournament client in
  `tournament.internal_client` and its schemas in `tournament.schemas`. The
  `audit_team_leadership`, `import_prod_tournament` and
  `sync_prod_tournaments` management commands keep their names.
- `has_event_staff_access` is now in `events.permissions`, the lobby Steam
  league check in `league.permissions`, and `request_user` in
  `app.permissions`.
- Logger names of the moved modules change from `app.*` to `tournament.*`
  (for example `app.signals` is now `tournament.signals` and
  `app.services.team_management` is now
  `tournament.services.team_management`). The INFO level override for
  `app.functions.tournament` now applies to `tournament.functions`. Log
  queries that filter on the old names need updating.
- The `view` field of `drf_error_response` logs for
  `POST /api/tournaments/create-team-from-captain` now reads
  `tournament.functions.WrappedAPIView` instead of
  `app.functions.tournament.WrappedAPIView`.
- `app.schemas` no longer re-exports the Discord and event schemas under
  their old names; import them from `discordbot.schemas` and
  `events.schemas`.
- The bracket app's config class is now `bracket.apps.BracketConfig`.
- Tournament HTTP and WebSocket paths, URL names, payloads, models and
  tables are unchanged.
