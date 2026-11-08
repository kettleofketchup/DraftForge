- **Changelog process (contributors).** PRs no longer edit `CHANGELOG.md`; they add a
  fragment under `changelog.d/<section>/`, and `just version::set` assembles the
  fragments into the release section. See `docs/development/changelog.md`.
