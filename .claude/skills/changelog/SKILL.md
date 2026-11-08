---
name: changelog
description: DraftForge changelog workflow. Use when writing release notes, adding or fixing a changelog.d/ fragment, editing CHANGELOG.md, handling the changelog:edit label, a failing `changelog` CI check, or cutting a release with just version::set.
---

# Changelog fragments

## Why

`CHANGELOG.md` is written only at release time. A branch that edits the `[Unreleased]`
section of a shared file and merges or rebases after a release applies its bullets as a
clean patch, so they land under the version that was already released, and git reports
no conflict. So each PR adds its own uniquely named file under `changelog.d/`, and
`just version::set X.Y.Z` assembles them into `## [X.Y.Z] - DATE` and removes them in the
version commit.

## Per-PR workflow

1. Decide whether a user or operator would notice the change. Chore, CI and test-only
   work needs no fragment (CI only warns).
2. Pick a section from `changelog.d/sections.json`: `upgrading` (prose: migrations, env
   or config changes operators must apply), `security`, `added`, `changed`,
   `deprecated`, `removed`, `fixed`, `documentation`.
3. Slug = branch name by convention (not enforced): `slug=$(python3 scripts/changelog.py slug)`.
   It must match `^[a-z0-9][a-z0-9._-]*$`. If a release already consumed that path
   (a reused branch name such as `fix/typo`), add a suffix: `fix-typo-2.md`.
4. `mkdir -p changelog.d/<section>` (a release removes emptied section directories,
   since git does not track them), then write `changelog.d/<section>/<slug>.md`:
   - bullet sections: `- ` bullets, continuation lines indented 2 spaces;
   - `upgrading`: paragraphs and fenced code are fine;
   - never `#` headings, HTML comments or link-reference definitions; inline links and
     issue references such as `#303` are fine.
5. Run `python3 scripts/changelog.py check` (exit 0, no output). It also reads files you
   have not `git add`-ed yet (not ignored ones), so run it before or after staging.
   Then commit and push.

Never edit `CHANGELOG.md` in a PR. A note for a PR that already merged without one is
`changelog.d/<section>/pr-<N>.md`, committed on `main` (never `main.md`).

## The CI gate (`changelog` job, `just ci::changelog-check`)

On a pull request to `main`:

| Finding | Result | Fix |
|---------|--------|-----|
| malformed or misnamed fragment (`path:line: msg`) | fails | fix the file as the message says; a bad name comes with a suggested one |
| `CHANGELOG.md:N: [Unreleased] must hold only the pointer comment` | fails, label or not | move those lines into a fragment and revert the hunk |
| `CHANGELOG.md` edited elsewhere, no `changelog:edit` label | fails | move the bullets to a fragment and revert the hunk, or add the label (below) |
| `this path was already released in X.Y.Z` | fails | same note restored: delete it; new note on a reused branch name: rename it, e.g. `<slug>-2.md` |
| `this bullet is identical to one released in X.Y.Z` (or `this note ...` for `upgrading`) | fails | remove or reword that bullet; the rest of the file stays |
| no fragment added | warning only | add one if the change is user- or operator-visible |

The job runs every check before it exits, so one run lists every problem. Every row
except the label check and the warning comes from `python3 scripts/changelog.py check`,
so it fails locally before CI; `just ci::changelog-check` run locally does the same plus
the checker's tests.

## The `changelog:edit` label

For a deliberate correction to a released section. Adding a label does not re-trigger
CI, so re-run the failed job:

```bash
gh pr edit <N> --add-label changelog:edit
gh run rerun <run-id> --failed
```

Merge such a PR with squash or a merge commit, never rebase-merge.

## The push rule (push to `main`)

The push run only reports: the commit is already on `main`. It compares `HEAD~1..HEAD`
only. A `CHANGELOG.md` change there fails unless HEAD is the release commit
(`Updated version to X.Y.Z`), a squash merge (`... (#N)`) or a merge commit
(`Merge pull request #N from ...`). A rebase-merge is not exempt, which is why
`changelog:edit` PRs are never rebase-merged.

## Release assembly (`just version::set X.Y.Z`)

Run on a clean, up-to-date `main`. The preflight refusals, the rollback rules and the
one-time admin setup (label and ruleset) are in `docs/development/changelog.md`; read
it before cutting a release. If the tag push fails after `main` was pushed, there is
no rollback; push the tag by hand with `git push origin refs/tags/X.Y.Z`.
