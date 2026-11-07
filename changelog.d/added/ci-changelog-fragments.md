- **Changelog.** `CHANGELOG.md` is now written at release time from per-PR fragments
  in `changelog.d/`. `just version::set` assembles them into the release section and
  removes them in the version commit; a `changelog` CI check guards the process.
