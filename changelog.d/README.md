# Changelog fragments

Never edit `CHANGELOG.md` in a PR. Add one file per section you touch instead:

    changelog.d/<section>/<slug>.md

- `<section>` is a `dir` from `sections.json`: `upgrading`, `security`, `added`,
  `changed`, `deprecated`, `removed`, `fixed` or `documentation`.
- `<slug>` is your branch name, lowercased, with `/` turned into `-`
  (`feat/Event-Reminders` becomes `added/feat-event-reminders.md`). It must match
  `^[a-z0-9][a-z0-9._-]*$`.
- A backfill note for an already-merged PR #N, committed on `main`, is `pr-<N>.md`.
  Never `main.md`.
- Bullet sections hold `- ` bullets, with continuation lines indented 2 spaces.
- `upgrading` is prose for operators: migrations, env or config changes they must
  apply. It also takes paragraphs and fenced code.
- No `#` headings, HTML comments or link-reference definitions. Inline links are fine.

Check your fragments locally:

    python3 scripts/changelog.py check

`just version::set X.Y.Z` assembles every fragment into the new `## [X.Y.Z]` section of
`CHANGELOG.md` and removes them in the version commit. CI runs the `changelog` check as
`just ci::changelog-check`; run locally it does only the fragment checks.

A PR that deliberately edits `CHANGELOG.md` (a correction to a released section) needs
the `changelog:edit` label and must be squash-merged or merged with a merge commit,
never rebase-merged. See `.claude/skills/changelog/SKILL.md`.
