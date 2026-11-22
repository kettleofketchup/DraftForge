- CI: a `prepare` job in the Playwright workflow builds each missing stack image and the
  test DB once and pushes it under its content-hash tag only, so the test jobs pull
  instead of each rebuilding. PR builds never push `:latest` or the registry build cache
  (`docker::buildx --hash-only`, `docker::db::push --hash-only`).
