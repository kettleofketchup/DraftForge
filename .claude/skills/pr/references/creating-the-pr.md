# Phase 2 — Create the PR

## Pre-flight

Before any `gh pr create`:

```bash
branch=$(git branch --show-current)
[ "$branch" = "main" ] && { echo "refusing: on main"; exit 1; }

# Ensure pushed
git rev-parse --abbrev-ref --symbolic-full-name @{upstream} >/dev/null 2>&1 \
  || git push -u origin "$branch"

# Confirm ahead of main
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

## When NOT to create

- Branch is `main` / `master` / `release/*`.
- No commits ahead of `origin/main`.
- A PR already exists for this `headRefName` (regardless of state). If the existing PR is `MERGED` or `CLOSED`, ask the user before opening a new one.

## Edge cases

- **Pre-commit hook blocked the push earlier** → the working tree is clean but the branch is not pushed. Run `git push -u origin "$branch"` and surface any hook output. Don't bypass hooks.
- **`gh auth status` shows expired token** → tell the user to `gh auth refresh` themselves; don't try to handle auth flow.
- **Force-pushed history** → `gh pr create` will rebuild associations; nothing extra needed.
