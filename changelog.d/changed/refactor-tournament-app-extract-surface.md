- The tournament HTTP and WebSocket surface moved from `app` into the
  `tournament` app. The tournament, team, game, team-log, bracket and draft
  serializers are now in `tournament.serializers`; the tournament, team,
  game, bracket and CSV import views in `tournament.views`; the tournament
  member add view in `tournament.views.members`; the tournament internal
  endpoints in `tournament.views.internal`; the tournament SSR view in
  `tournament.ssr`; the tournament WebSocket consumer and route in
  `tournament.consumers` and `tournament.routing`; and the team log admin in
  `tournament.admin`. `OrganizationsSerializer` is now in `org.serializers`,
  and `LeaguesSerializer` and `LeagueMinimalSerializer` in
  `league.serializers`.
- `app.views.admin_team` is now `app.views.user_search` and holds only
  `search_users`.
- Logger names of the moved views change from `app.*` to `tournament.*`:
  `app.views_main` is now `tournament.views.tournament` and
  `tournament.views.team` (for example `tournament_cache_miss`,
  `team_list_cache_miss`, `team_deleted`, `team_delete_refused`),
  `app.views.bracket` is now `tournament.views.bracket`,
  `app.views.csv_import` is now `tournament.views.csv_import`, and the
  `captain_teams_removed` log now comes from
  `tournament.serializers.tournament` instead of `app.serializers`. Log
  queries that filter on the old names need updating.
- The `view` field of `drf_error_response` logs for the moved views changes
  the same way (for example `app.views_main.TeamView` is now
  `tournament.views.team.TeamView`).
- Tournament HTTP and WebSocket paths, URL names, payloads, models and
  tables are unchanged.
