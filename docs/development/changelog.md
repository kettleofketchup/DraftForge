# Changelog

`CHANGELOG.md` is written at release time, never by hand in a PR. Each PR adds a small
fragment file under `changelog.d/`, and `just version::set X.Y.Z` assembles the
fragments into a `## [X.Y.Z] - DATE` section and removes them in the version commit.

!!! info "Why fragments"
    A branch that edits the `[Unreleased]` section of one shared file and merges after
    a release applies its bullets as a clean patch, so they land under the version that
    was already released, and git reports no conflict. A new, uniquely named file per
    PR cannot end up under an old version.

## Adding a fragment

1. Pick a section (table below).
2. Name the file after your branch: `python3 scripts/changelog.py slug` prints the
   conventional slug (lowercased; each run of characters outside `a-z 0-9 . _ -`
   becomes `-`). `feat/event-reminders` becomes
   `changelog.d/added/feat-event-reminders.md`. The name is a convention, not a rule: if
   a release already used that path (a reused branch name such as `fix/typo`), add a
   suffix, e.g. `fix-typo-2.md`.
3. Create the section directory if it is missing (`mkdir -p changelog.d/added`; a
   release removes emptied section directories because git does not track them),
   write the file and check it (it reads new files before `git add` too), then commit
   it with your change:

    ```bash
    python3 scripts/changelog.py check
    ```

Chore, CI and test-only PRs can skip the fragment; the `changelog` check only warns.
This page is the full reference;
[changelog.d/README.md](https://github.com/kettleofketchup/DraftForge/blob/main/changelog.d/README.md)
is the short version next to the fragments.

| Section | Heading | Use it for |
|---------|---------|------------|
| `upgrading` | Upgrading | Migrations, env or config changes operators must apply (prose) |
| `security` | Security | Vulnerability fixes and hardening |
| `added` | Added | New features |
| `changed` | Changed | Changes to existing behaviour |
| `deprecated` | Deprecated | Features that will be removed |
| `removed` | Removed | Features removed in this release |
| `fixed` | Fixed | Bug fixes |
| `documentation` | Documentation | Notable docs changes |

### Examples

A bullet section (`changelog.d/fixed/fix-bracket-seeding.md`):

```markdown
- **Bracket seeding.** Byes now go to the top seeds instead of the last teams
  added to the tournament.
```

An `upgrading` note (`changelog.d/upgrading/feat-event-reminders.md`) can hold
paragraphs and fenced code:

````markdown
Two new migrations add the reminder schedule tables. Apply them before starting the
new backend image:

```bash
just db::migrate::all
```

Set `REMINDER_LEAD_MINUTES` in `docker/.env.prod` (default `30`).
````

Fragments take no headings (`#` lines, or a text line underlined with `===` or `---`),
HTML comments or link-reference definitions. Inline links, issue references such as
`#303` and `#` comments inside fenced or indented code are fine. Trailing whitespace
and a UTF-8 byte-order mark are stripped when the release is assembled.

## The `changelog` check

The `changelog` CI job runs on every PR to `main` and every push to `main`.

| Situation | Result |
|-----------|--------|
| A fragment is malformed or misnamed | Fails |
| `CHANGELOG.md`'s `[Unreleased]` holds anything but the pointer comment | Fails, even with the label |
| A PR edits `CHANGELOG.md` without the `changelog:edit` label | Fails |
| A fragment sits at a path a release already consumed | Fails: delete it if it is the same note, rename it (`<slug>-2.md`) if it is new |
| A bullet of 40 or more characters is identical to one already released | Fails: remove or reword that bullet (short stock bullets such as `- Updated dependencies.` may recur) |
| A PR adds no fragment | Warning only |
| A direct push to `main` edits `CHANGELOG.md` outside a release commit | Fails (report only; the commit is already on `main`) |

Squash merges (`... (#N)`), merge commits and the release commit are exempt on push.
A note for a PR that already merged without one goes in
`changelog.d/<section>/pr-<N>.md`.

### Deliberate edits to `CHANGELOG.md`

To correct a released section, add the `changelog:edit` label to the PR. Adding a
label does not re-run CI, so re-run the failed job:

```bash
gh pr edit <N> --add-label changelog:edit
gh run rerun <run-id> --failed
```

Squash-merge such a PR or merge it with a merge commit. A rebase-merge turns the push
check on `main` red.

## Releasing

`just version::set X.Y.Z` (on an up-to-date, clean `main`):

1. Refuses, before any file changes: a version that is not `X.Y.Z`;
   `--no-tag-version` without `--no-commit`; a missing `CHANGELOG.md`; a branch other
   than `main`; any staged or unstaged tracked change; untracked files under
   `changelog.d/`; `HEAD` not equal to `origin/main` after `git fetch --tags origin`;
   a tag `X.Y.Z` on `origin` or locally (a leftover local tag from a `--no-commit`
   run: `git tag -d X.Y.Z`). Other untracked files are fine.
2. Asks for confirmation when there are no fragments.
3. Rewrites the version files, assembles `CHANGELOG.md` and `git rm`s the fragments.
4. Commits `Updated version to X.Y.Z` (release paths only), tags `X.Y.Z`, pushes `main`,
   then pushes the tag, which builds the release images.

Any failure before the push of `main` rolls everything back (`git checkout HEAD --`
on the release paths, or `git reset --keep HEAD~1` and `git tag -d` once committed).
A rejected `main` push means `main` moved or a ruleset rejected you: update `main` and
retry. If the tag push fails after `main` was pushed, push the tag by hand:

```bash
git push origin refs/tags/X.Y.Z
```

`just version::set X.Y.Z --no-commit` only rewrites the version files (and
makes a local tag unless `--no-tag-version`).

## One-time admin setup

1. The `changelog:edit` label (already created on the repository; recreate it with
   `gh label create changelog:edit --color D93F0B` if it is ever deleted).
2. Refresh open PRs. A PR opened before the workflow landed gets its first `changelog`
   check only on its next push (for example, merging `main` into it) or a close and
   reopen. Re-running its old runs does not add the check.
3. Only then add a ruleset on `main` that requires the `changelog` check, with the
   release role (repository admins, or whoever runs `just version::set`) on its bypass
   list, so the release's direct push to `main` is accepted. A PR that was not
   refreshed shows "Expected — Waiting for status to be reported" until it is.

Until the label and the ruleset exist, the check reports problems but does not block
merges.
