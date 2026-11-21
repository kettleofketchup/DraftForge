---
name: pr
description: DraftForge PR lifecycle. Use when the user runs /pr, opens or reuses a pull request, wants before/after screenshots of UI changes posted on a PR, or asks to watch CI on a branch.
---

# /pr — PR lifecycle workflow

Drive a PR from "branch pushed" to an actionable report without the user babysitting it:

1. Resolve PR state (reuse the open PR or create one).
2. Post before/after screenshots of visual changes as a PR comment, or a one-line comment saying there are none.
3. Watch GitHub Actions checks until none are pending (up to 30 min).
4. Pull the failed jobs' error lines and report findings with next steps.
5. Offer pre-existing problems the branch found as GitHub issues and separate fix PRs.

## When to trigger

- User types `/pr`, or says "open / create a PR" on the current branch.
- User says "watch CI" / "monitor checks" on a branch with an open PR.
- User asks for screenshots of a PR's UI changes.
- A push just happened and the user asks what's next.

Ask first when a branch merely has uncommitted work.

## Workflow

### Phase 1 — Resolve state

```bash
branch=$(git branch --show-current)
pr_json=$(gh pr view --json number,state,headRefName,baseRefName,url,comments 2>/dev/null || echo "")
```

- Empty `pr_json` → Phase 2 (create).
- `OPEN` → Phase 3.
- `MERGED` / `CLOSED` → report and stop; ask whether to open a new one.

### Phase 2 — Create the PR (if missing)

Title/body from commits when the branch has 1–3 commits; otherwise ask the user once for a title. HEREDOC body with `## Summary` and `## Test plan`. Add a `changelog.d/` fragment first if the change is user- or operator-visible ([changelog skill](../changelog/SKILL.md)). Exact commands: [references/creating-the-pr.md](references/creating-the-pr.md).

### Phase 3 — Screenshots

Runs for a new PR, for a reused PR with no screenshot comment yet (no comment body starting `## Screenshots` or `No screenshots:`; a `Screenshots pending:` comment does not count), and after new commits that change the UI. Gate on the diff:

```bash
gh pr diff "$PR" --name-only | grep -E '^frontend/app/(components|routes|features)/|^frontend/app/app\.css$|tokens'
```

- No match → `gh pr comment "$PR" --body "No screenshots: this PR has no visual changes (<what it touches instead>)."` and go to Phase 4.
- Match → follow [references/screenshots.md](references/screenshots.md) end to end: before from the merge-base, after from the PR head, same pages/states/data/viewport, headless capture on each worktree's own test stack slot, every PNG viewed, images on the `pr-assets/<n>` branch, one comment with a before/after table per change, stacks down and slots released.

Every `just` call in that phase is one Bash call of the form `cd <worktree> && just <recipe>  # allow-cd`. A bare `cd` does not carry over to the next call, and a populate recipe that runs in the main checkout wipes its test DB.

Phase 3 is done when the PR has a new screenshot comment (or the skip / pending comment) and `just test::slots` shows no slot held by this PR's worktrees.

### Phase 4 — Watch CI

```bash
timeout 30m gh pr checks "$PR" --watch --interval 60
```

Narrate in single lines. Polling detail and timeout handling: [references/monitoring-ci.md](references/monitoring-ci.md).

### Phase 5 — Analyse and report

For each failed run, `gh run view <id> --log-failed`, keep the error lines (max 10 per failed step), tag likely causes, and flag failures in files the diff doesn't touch as pre-existing bugs (never "flaky"). Report format: [references/analyzing-results.md](references/analyzing-results.md).

### Phase 6 — Pre-existing problems

Always run this, even when CI is green. Collect every problem the branch's work found that was already on `main` (tests failing there, "reported only" bugs from spec/review/verification, deferred items), confirm each on `origin/main` with `file:line`, and present them to the user. Offer per problem: GitHub issue only; issue plus a subagent fix in its own worktree/branch/PR (a workflow for larger fixes); fix in this PR; or skip. File nothing without the user's pick. Review every issue body for sensitive information before `gh issue create`, and every fix PR body must contain `Closes #<issue>` so merging it closes the issue. Procedure and checklist: [references/preexisting-problems.md](references/preexisting-problems.md).

## Scope

- Pushes only through the creation pre-flight; a dirty or unpushed branch is reported to the user.
- Reports CI failures with next steps; fixing them is a separate request.
- Extracts error lines; raw `--log-failed` output stays out of the chat.

## References

- [creating-the-pr.md](references/creating-the-pr.md) — `gh pr create` pre-flight, title/body autofill
- [screenshots.md](references/screenshots.md) — before/after capture, test stack slots, `pr-assets/<n>` branch, comment format
- [monitoring-ci.md](references/monitoring-ci.md) — watch/poll loop, timeout
- [analyzing-results.md](references/analyzing-results.md) — CI log extraction, root-cause table, report format
- [preexisting-problems.md](references/preexisting-problems.md) — pre-existing bugs → reviewed GitHub issues and `Closes #N` fix PRs
