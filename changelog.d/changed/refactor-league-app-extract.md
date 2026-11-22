- The `League`, `LeagueRating`, `LeagueMatch`, `LeagueMatchParticipant` and
  `LeagueLog` models moved from `app` into the `league` Django app. The
  migrations are state-only: the tables keep their `app_league*` names
  (including `app_league_admins` and `app_league_staff`) and no schema
  changes on deploy.
- The five ContentType rows are relabelled from `app` to `league`, so the
  permission labels change from `app.*_league*` to `league.*_league*`.
  Existing user and group grants carry over.
- The cacheops profile key `app.league` is renamed to `league.league`, with
  the same profile.
- No admin URL changes, since none of the five models is registered in
  admin. No logger name, HTTP or WebSocket path, payload or
  `_meta.label`-derived key changes either.
