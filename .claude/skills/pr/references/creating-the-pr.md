# Phase 2 — Create the PR

## Pre-flight

Before any `gh pr create`:

```bash
branch=$(git branch --show-current)
[ "$branch" = "main" ] && { echo "refusing: on main"; exit 1; }

# Changelog fragment (.claude/skills/changelog/SKILL.md). If the diff is user- or
# operator-visible and has no fragment yet, write and commit it first.
# Branches that predate the checker skip this until they merge main.
slug=$(printf '%s' "$branch" | tr '[:upper:]/' '[:lower:]-')
echo "fragment path: changelog.d/<section>/$slug.md"
if [ -f scripts/changelog.py ]; then
  python3 scripts/changelog.py check || { echo "fix changelog.d/ fragments first"; exit 1; }
fi

# Push when there is no upstream, or when local commits are not on it yet
# (a fragment committed after the first push would otherwise stay local).
if ! git rev-parse --abbrev-ref --symbolic-full-name @{upstream} >/dev/null 2>&1; then
  git push -u origin "$branch"
elif [ -n "$(git rev-list @{upstream}..HEAD)" ]; then
  git push
fi

# Confirm ahead of main (after the push)
ahead=$(git rev-list --count "origin/main..$branch")
[ "$ahead" -eq 0 ] && { echo "no commits ahead of main"; exit 1; }
```

If push fails (auth, pre-push hook), surface the error and stop — do not retry blindly.

## Title and body

### Autofill from commits (1–3 commits ahead)

```bash
commits=$(git log --format='%s' "origin/main..$branch")
n=$(echo "$commits" | wc -l)
if [ "$n" -le 3 ]; then
  title=$(echo "$commits" | head -1)
  summary_bullets=$(echo "$commits" | awk '{print "- " $0}')
fi
```

If `n > 3`, ask the user once for a title rather than guessing.

### Body template (HEREDOC, always)

```bash
gh pr create --base main --head "$branch" --title "$title" --body "$(cat <<EOF
## Summary

$summary_bullets

## Test plan

- [ ] [fill in based on what changed]
EOF
)"
```

For trivial chore branches (one-liner docs / config), still include a `## Test plan` checklist — leave it empty if nothing to test, but the section must exist (project convention).

## After creation

Capture the PR number for later phases:

```bash
PR=$(gh pr view --json number -q .number)
url=$(gh pr view --json url -q .url)
```

Then output one user-facing line: `Opened PR #<N>: <url>` — do not paste the full PR JSON.

If the PR edits `CHANGELOG.md` on purpose (a correction to a released section), label it
and re-run the failed `changelog` job, because adding a label does not re-trigger CI:

```bash
gh pr edit "$PR" --add-label changelog:edit
gh run rerun <run-id> --failed
```

## When NOT to create

- Branch is `main` / `master` / `release/*`.
- No commits ahead of `origin/main`.
- A PR already exists for this `headRefName` (regardless of state). If the existing PR is `MERGED` or `CLOSED`, ask the user before opening a new one.

## Edge cases

- **Pre-commit hook blocked the push earlier** → the working tree is clean but the branch is not pushed. Run `git push -u origin "$branch"` and surface any hook output. Don't bypass hooks.
- **`gh auth status` shows expired token** → tell the user to `gh auth refresh` themselves; don't try to handle auth flow.
- **Force-pushed history** → `gh pr create` will rebuild associations; nothing extra needed.
