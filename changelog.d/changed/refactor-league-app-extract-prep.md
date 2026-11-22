- League backend code moved from `app` into the `league` Django app, ahead
  of the model move. The league permission helpers and `IsLeagueAdmin` are
  now in `league.permissions`; tournament, game and lobby checks stay in
  `app.permissions_tournament`. `LeagueView` is now in `league.views`,
  `LeagueSerializer` in `league.serializers`, the league SSR view in
  `league.ssr`, the league admin/staff/member endpoints in
  `league.views_admin_team`, and the rating and match finalization services
  in `league.services`. The unused `IsLeagueStaff` permission class is
  removed.
- The `view` field of `drf_error_response` logs for these endpoints now
  reads `league.views.LeagueView`, `league.views_admin_team.*` and
  `league.ssr.*` instead of `app.views_main.*`, `app.views.admin_team.*` and
  `app.views.ssr.*`. Log queries that filter on it need updating.
- League HTTP paths, URL names, payloads and models are unchanged.
