- `just py::migrate`, `py::shell` and `py::test` now really disable the cache: the
  `DISABLE_CACHE=true` prefix applied only to sourcing the venv, not to Python.
- `just db::migrate::all` migrates the dev, prod and test databases. It migrated
  `dev.db.sqlite3` three times: python-dotenv kept the first `NODE_ENV` it loaded, and
  `NODE_ENV` picks the SQLite file.
- `just version::from-env` reads `docker/.env.release` by default (it looked for
  `.env.release` in the repo root).
- The slot guard tests (`just test::slots-unit`) pass again; on main they failed on a
  stale `scripts/version.py` exemption and the compose-file regex in `scripts/test_version.py`.
