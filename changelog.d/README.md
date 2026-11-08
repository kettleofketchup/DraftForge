# Changelog fragments

Never edit `CHANGELOG.md` in a PR. Add one file per section you touch instead:

    mkdir -p changelog.d/<section>   # a release removes emptied section directories
    changelog.d/<section>/<slug>.md

- `<section>` is a `dir` from `sections.json`: `upgrading`, `security`, `added`,
  `changed`, `deprecated`, `removed`, `fixed` or `documentation`.
- `<slug>` is by convention your branch name: `python3 scripts/changelog.py slug`
  prints it (`fix/issue #12` becomes `fix-issue-12`). It must match
  `^[a-z0-9][a-z0-9._-]*$`; only that is enforced, not the link to the branch.
- A path a release already consumed cannot be reused: add a suffix (`fix-typo-2.md`).
- A backfill note for an already-merged PR #N, committed on `main`, is `pr-<N>.md`.
- Bullet sections hold `- ` bullets, with continuation lines indented 2 spaces.
- `upgrading` is prose for operators; it also takes paragraphs and fenced code.
- No `#` headings, HTML comments or link-reference definitions. Inline links and issue
  references such as `#303` are fine.

Check your fragments (exit 0 and no output means clean; files not yet `git add`-ed are
checked too, ignored files are not):

    python3 scripts/changelog.py check

`just ci::changelog-check` runs the same check plus the checker's tests (and, in CI,
the label and push rules).

The full reference, including the `changelog:edit` label and releasing, is
`docs/development/changelog.md`.
