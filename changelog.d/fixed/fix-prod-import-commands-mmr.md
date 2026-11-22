- `sync_prod_users` and `import_prod_tournament` create new users again instead of
  failing on the removed user MMR field (#687). `import_prod_tournament` also reads the
  current tournament API payload (user and team references by id, full datetimes), uses
  its default API URL without `--url`, and takes `--league` / `--organization` to attach
  the tournament to a local league and store new users' MMR as that organization's MMR
  for the tournament's game.
- `sync_prod_tournaments` reads the current tournament API payload: it fetches each
  tournament's detail to resolve users, parses full datetimes, and matches game teams
  by id before name.
- `sync_prod_users` no longer aborts on a database with organization owners: owners are
  kept and updated in place from production instead of deleted, and one user that fails
  to sync no longer discards every other user.
