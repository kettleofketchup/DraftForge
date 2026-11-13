- Backend tests: the SQLite test database is now a uniquely named temp file set up by the
  test runner (and the pytest `conftest`) instead of in `settings.py`, so production
  processes no longer touch the temp dir at import. Its WAL sidecars and parallel clones
  are removed on teardown, files from killed runs are swept after a day, and
  `manage.py test --parallel` works under the `spawn` start method (macOS).
