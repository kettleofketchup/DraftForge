- `just dev::release` now pulls the release images first and stops if the pull fails,
  before it touches the database or the running stack. It then runs
  `makemigrations --check` and stops, with the site still up, if the models have changes
  with no migration. Only then does it stop the release stack, run migrations and start
  the new version, so a release that drops a column no longer
  needs a manual stop-first sequence. The site is down for the migration and container
  start (seconds). It pulls the exact `:VERSION` images the release stack runs instead of
  calling `docker::release::pull`.
