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
3. Slug = branch name by convention (not enforced), lowercased, with `/` and any other
   character outside `a-z 0-9 . _ -` turned into `-`:
   `slug=$(git branch --show-current | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z0-9._-]/-/g; s/^[._-]*//')`.
   It must match `^[a-z0-9][a-z0-9._-]*$`. If a release already consumed that path
   (a reused branch name such as `fix/typo`), add a suffix: `fix-typo-2.md`.
4. Write `changelog.d/<section>/<slug>.md`:
   - bullet sections: `- ` bullets, continuation lines indented 2 spaces;
   - `upgrading`: paragraphs and fenced code are fine;
   - never `#` headings, HTML comments or link-reference definitions; inline links are fine.
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

Run on `main`. In order:

1. Preflight, before any file changes. It refuses: a version that is not `X.Y.Z`;
   `--no-tag-version` without `--no-commit`; a missing `CHANGELOG.md`; a branch other
   than `main`; any staged or unstaged tracked change; untracked files under
   `changelog.d/`; `HEAD` not equal to `origin/main` after `git fetch --tags origin`;
   a tag `X.Y.Z` on `origin` or locally (a leftover local tag from a `--no-commit` run:
   `git tag -d X.Y.Z`). Other untracked files are fine.
2. With zero fragments it asks `Release X.Y.Z with no changelog notes? [y/N]`; anything
   but `y` (or EOF) cancels.
3. Rewrites the version files, writes `## [X.Y.Z] - DATE` into `CHANGELOG.md` and
   `git rm`s the consumed fragments.
4. Commits `Updated version to X.Y.Z` limited to the release paths, tags `X.Y.Z`, pushes
   `main`, then pushes the tag, which builds the release images.

Any failure up to the push of `main` rolls back (`git checkout HEAD --` on the release
paths, or `git reset --keep HEAD~1` and `git tag -d` once committed). A rejected `main`
push means `main` moved or a ruleset rejected you: update `main` and retry. If the tag
push fails after `main` was pushed there is no rollback; push the tag by hand:

```bash
git push origin refs/tags/X.Y.Z
```

`inv version.set X.Y.Z --no-commit` only rewrites the version files (and makes a local
tag unless `--no-tag-version`); it does not touch the changelog.

## One-time admin setup

1. Create the label:
   `gh label create changelog:edit --color D93F0B --description "PR deliberately edits CHANGELOG.md (corrections to released sections)"`
2. Refresh open PRs. GitHub reads the workflow from each PR's merge ref, so a PR opened
   before the workflow landed gets a `changelog` check only after a new push (for
   example, merging `main` into it) or a close and reopen. Re-running old runs does not
   add it.
3. Only then add a ruleset on `main` requiring the `changelog` check, with the release
   role (repository admins, or whoever runs `just version::set`) on its bypass list so
   the release's direct push to `main` is accepted. An unrefreshed PR shows "Expected —
   Waiting for status to be reported" and cannot merge until refreshed.

Until the label and the ruleset exist, the gate reports problems but does not block
merges.
