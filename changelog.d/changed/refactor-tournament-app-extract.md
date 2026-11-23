- The `Tournament`, `Team`, `Game` and `TeamLog` models (with
  `LeadershipProblem`, `TeamLogVia` and `TeamLogAction`) moved from `app`
  into the `tournament` Django app, and the tournament enums (`GameMode`,
  `DotaLobbyMode`, `DotaLobbyLaunch`, `DraftStyles`) into
  `tournament.choices`. The migrations are state-only: the tables keep their
  `app_tournament`, `app_team`, `app_game` and `app_teamlog` names (and the
  `app_tournament_users`, `app_team_members`, `app_team_dropin_members`,
  `app_team_left_members` and `app_team_league_users` join tables), and no
  schema changes on deploy.
- The four ContentType rows are relabelled from `app` to `tournament`, so
  permission labels change from `app.*` to `tournament.*` (for example
  `app.change_team` is now `tournament.change_team`). Existing user and group
  grants carry over.
- The team log admin moved from `/admin/app/teamlog/` to
  `/admin/tournament/teamlog/`.
- The cacheops profile keys `app.tournament`, `app.team` and `app.game` are
  renamed to `tournament.tournament`, `tournament.team` and
  `tournament.game`, with the same profiles.
- Team usage and reference payloads (the `team_in_use` 409 on team delete
  and the draft reset responses) now name the models `tournament.Game` and
  `tournament.Tournament`, and their keys `tournament.Game.radiant_team`,
  `tournament.Game.dire_team` and so on, instead of `app.*`. Because `usage`
  is sorted by model label, `tournament.Game` entries now come after
  `bracket.BracketSlot` entries.
- `TOURNAMNET_TYPE_CHOICES` is renamed `TOURNAMENT_TYPE_CHOICES`.
- HTTP and WebSocket paths, URL names, Redis keys and table names are
  unchanged.
