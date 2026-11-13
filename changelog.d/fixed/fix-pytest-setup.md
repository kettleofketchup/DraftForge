- `just py::test` (pytest) runs the backend suite again. `backend/pytest.ini` used a
  `[tool:pytest]` header that pytest ignores in a `pytest.ini`, so none of its settings
  applied, and the conftest failed to import on the host and in the container. pytest
  now collects the same `test*.py` modules as `manage.py test`, on the same temp-file
  test database and with the same `DOTA_LOBBY_*` defaults. `just py::test` and
  `just test::backend::*` load `docker/.env.test` and keep the cache on, as the test
  container does. The conftest no longer points Django at `backend/test.db.sqlite3` or
  empties it, and `just test::backend::all` no longer resets that file.
- Removed the unused `backend/scripts/run_tests.py`.
