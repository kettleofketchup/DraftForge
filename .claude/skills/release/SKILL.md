---
name: release
description: Cut a DraftForge release with `just version::set X.Y.Z`. It checks main is clean and current, assembles every changelog.d/ fragment into CHANGELOG.md's `## [X.Y.Z] - DATE` section in the release commit, tags X.Y.Z, pushes, and the tag triggers the GHCR image build. Use when asked to release, bump or increment the version, ship a hotfix, tag a version, or check what notes a release will ship.
---

# Release

A release is one command, `just version::set X.Y.Z` (runs `python -m scripts.version set`,
`scripts/version.py`). It writes the version, turns the pending changelog fragments
into the release's `CHANGELOG.md` section, commits, tags and pushes. The pushed tag
builds the images. Your job: pick the version, check the notes that will ship, run
it on an up-to-date `main`, and report the CI result.

## What `just version::set X.Y.Z` does

1. **Preflight** (`changelog.release_preflight`). It refuses, changing nothing, when:
   - the version is not `MAJOR.MINOR.PATCH` (or `just version::set` got `--no-tag-version`);
   - the current branch is not `main`, or tracked files have uncommitted changes;
   - there are untracked files under `changelog.d/` (they would miss the release);
   - `HEAD` is not `origin/main` after `git fetch --tags origin`;
   - tag `X.Y.Z` already exists on `origin` or locally.
2. If `changelog.d/` holds no fragments, it asks `Release X.Y.Z with no changelog
   notes? [y/N]`. Anything but `y` cancels with nothing changed.
3. Rewrites the version in `pyproject.toml`, `docker/.env.prod`, `docker/.env.release`.
4. **Assembles the changelog.** Every fragment goes into a new `## [X.Y.Z] - DATE`
   section, sections in `changelog.d/sections.json` order, and the consumed fragments
   are `git rm`ed. It refuses if a fragment fails `scripts/changelog.py check`, if
   `[Unreleased]` holds anything but the pointer comment, or if `[X.Y.Z]` already
   exists; then it rolls the version files and `changelog.d/` back.
5. Commits `Updated version to X.Y.Z` (version files, `CHANGELOG.md`, removed
   fragments), tags `X.Y.Z`, pushes `main`, then the tag. If the commit, tag or `main`
   push fails, the commit and tag are undone locally.

## What the tag triggers

A tag matching `[0-9]+.[0-9]+.[0-9]+` (no `v`) runs
`.github/workflows/release-docker-images.yml`, which builds and pushes the backend,
frontend and nginx images to GHCR tagged with the version. No GitHub Release object
is created and nothing deploys automatically.

## Procedure

1. **Pick the version.** Use the user's `X.Y.Z` if given. Otherwise read
   `grep -m1 '^version' pyproject.toml` and bump: patch for a hotfix or "increment",
   minor for features, major for breaking changes. State the number before running.
2. **Sync `main`:**
   ```bash
   git switch main
   git fetch origin && git merge --ff-only origin/main
   ```
   If the fast-forward fails (local commits), stop and ask the user.
3. **Check the notes that will ship:**
   ```bash
   python3 scripts/changelog.py check     # must print nothing and exit 0
   git ls-files 'changelog.d/*/*.md'      # the fragments this release consumes
   ```
   No fragments means a release with no notes. Ask the user before going on, and
   expect the `[y/N]` prompt. A fragment that fails `check` blocks the release; fix
   it in a PR (see the `changelog` skill), not on `main` by hand.
4. **Release:**
   ```bash
   just version::set X.Y.Z
   ```
   Read the output to the end. Success ends with `Released X.Y.Z: pushed main and
   tag X.Y.Z.` and reports how many fragments were assembled.
5. **Watch CI** (see [references/ci-watch.md](references/ci-watch.md)):
   ```bash
   gh run list --workflow=release-docker-images.yml --limit 1
   gh run watch <run-id> --exit-status
   ```
   Report whether the images built and pushed.

## Recovery

- **Preflight refused:** fix what the message names (switch to `main`, commit or
  stash, `git merge --ff-only origin/main`, pick an unused version) and run again.
  Nothing was changed.
- **Assembly failed:** already rolled back. Fix the fragment or `[Unreleased]` in a
  PR, merge, and run again.
- **`main` push rejected:** the commit and tag are already undone. Usually `main`
  moved: sync and retry. A ruleset on `main` also rejects the push unless the
  releaser is on its bypass list.
- **`main` pushed but the tag push failed:** no images were built. Push it by hand:
  `git push origin refs/tags/X.Y.Z`.
- **Wrong commit tagged and pushed:** `CHANGELOG.md` now has `[X.Y.Z]`, so the same
  version cannot be released again. Delete the remote tag only if no images were
  published (`git push origin :refs/tags/X.Y.Z`), then release the next patch version.

## Notes

- Never hand-roll the edits, commit or tag, and never edit `CHANGELOG.md` on `main`:
  the `changelog` CI job fails a push that does, unless it is the release commit.
- For a local bump without releasing, `just version::set X.Y.Z --no-commit` only
  rewrites the version files (and makes a local tag unless `--no-tag-version`).
- No attribution lines; the recipe writes its own commit message.
- Fragment format, sections and the CI gate: the `changelog` skill and
  `docs/development/changelog.md`.
