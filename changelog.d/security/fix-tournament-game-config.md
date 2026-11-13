- Creating a tournament through `/api/tournaments/` checked the league named in `league`
  but saved the one in `league_id_write`, so a league admin could create tournaments in a
  league they don't administer. The saved league is now checked.
