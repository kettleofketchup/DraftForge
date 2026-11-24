# Monitor PR conflicts with main and CI/CD failures

Start this monitor as soon as Phase 1 finds an open PR (or Phase 2 creates one).
Run alongside coverage, screenshots and CI; keep it after CI goes green until the
PR is merged/closed, the user stops it, or the session ends. Do not merge the PR.

## Arm the monitor

Use `Monitor`, not a cron job or a blocking foreground loop. Set `timeout_ms` to
1800000 (the Monitor cap) and a description naming the PR. Each window is one
30-minute tick: the command checks once when armed, then sleeps 1800 seconds until
the window expires. Re-arm on every expiry while the PR is open; the expiry notice
is the cue for the next check, not the end of monitoring. Tell the user this is
session-only and checks every 30 minutes.

Dedup state must survive re-arms. Create one per-PR state directory with
`mktemp -d` on first arm, record its path, and pass the same path to every
re-armed command; read the last reported head/base OIDs, conflict state, CI
summary and failure keys from it before emitting and write them back after.

Resolve and pin the repository (`gh repo view --json nameWithOwner`), PR number,
head branch, base branch and owning worktree before starting. Pass explicit
`--repo OWNER/REPO` and the PR number on every `gh` call. Reject an unexpected
base rather than silently substituting main; this procedure is for main-based PRs.

Each tick (on arm, then every re-arm) runs these read-only checks:

1. Read `gh pr view NUMBER --repo OWNER/REPO --json state,mergeable,headRefOid,baseRefOid,headRefName,baseRefName`.
2. Emit a terminal event and exit when state is `MERGED` or `CLOSED`.
3. Emit an actionable event for `mergeable == CONFLICTING`, including both OIDs.
   Suppress duplicate conflict events for the same head/base pair.
4. Treat `UNKNOWN` as unresolved, not clean. Retry next tick and emit an event
   if it remains unknown for two consecutive ticks.
5. Emit API/auth/network failures instead of treating them as no conflicts;
   keep polling after transient failures. Emit recovery once after an error.
6. Emit a base-change event only when the base OID changes, otherwise stay quiet.
7. On every tick, also read `gh pr checks NUMBER --repo OWNER/REPO --json name,state,bucket,link,workflow` and `gh pr view NUMBER --repo OWNER/REPO --json statusCheckRollup,headRefOid`. Pin results to the current head; ignore runs for superseded commits. Use the check URLs to identify runs, and inspect run attempts before deduplicating failures.
8. Emit changed CI summaries (pending/pass/fail counts) and actionable events for new failures, cancellations, timeouts, action-required or startup failures. Do not treat every non-zero `gh pr checks` exit as an API error: failed/pending checks have documented non-zero exit codes. Distinguish valid JSON results from transport/auth failures. Surface missing checks that persist for two ticks; no checks is not success.
9. Deduplicate CI failure events by head OID, check/run identity and run attempt, not just check name. Emit recovery and new-head events so previous green checks never stand in for the current head. Keep polling after green CI; later workflows or reruns can still fail.

Query mergeability every tick even if main's OID is unchanged: the PR head can
change independently. Keep all git mutations out of the monitor process; its
only job is to notify this session. A base-change event with no conflict needs
no merge. `BEHIND` or failing CI alone is not a merge conflict.

## Handle a conflict event

Handle events serially in this session, never in concurrent background writers.

1. Re-read PR state, branch names and mergeability. Stop for merged/closed PRs;
   ignore a conflict that has already cleared. Verify the event belongs to the
   pinned repository and PR, not whichever branch is currently checked out.
2. Locate the PR's existing worktree. Check peer sessions with `ListAgents`;
   coordinate with its owner before changing a peer-owned branch. Never switch
   branches in the shared main checkout or change another session's worktree
   without coordination.
3. In the owning worktree, verify the branch matches the PR head, the worktree
   and index are clean, no merge/rebase/cherry-pick is in progress, and there are
   no unpushed commits or divergent remote head. If blocked, report why and
   pause repair; never auto-stash, reset, force-push, or discard work.
4. Fetch origin and revalidate the PR head against `origin/<head>`. Verify origin
   belongs to the pinned repository. Merge `refs/remotes/origin/main` into the
   PR branch, **not** the PR branch into main; use a merge, not a rebase.
5. Resolve conflicts semantically, preserving both changes. Inspect surrounding
   code and moved modules; do not blindly pick ours/theirs. Ask the user when
   intent cannot be determined safely. Leave any unresolved merge clearly
   reported and pause further repair instead of repeating merges.
6. Update migration numbering and `max_migration.txt` if affected. Run targeted
   tests; for backend changes run `manage.py check` and the app-boundary tests
   using project `just` recipes. Follow the existing verification requirements
   for the touched code. Report failures and do not push a known-broken merge.
7. Commit the resolved merge with a clean, unattributed message, then push only
   the PR branch (no force) when authorized. `/pr`'s conflict-repair scope includes
   this merge commit and push; still honor any explicit no-commit/no-push request
   or required tool approval. If the remote moved, stop and reassess.
8. Restart Phase 5 for the new head and report the merge, resolution and tests.
   Keep the main monitor active; a green result for the previous head does not
   verify the new head. Notify the user of conflicts needing intervention.

Use `cd <worktree> && ...` in every worktree Bash call; do not rely on a previous
call's cwd. Never merge, close, approve or enable auto-merge on the PR itself.

## Progressive CI/CD repair loop

For each CI failure event, re-read the PR head and fetch the exact failed run's
logs using [analyzing-results.md](analyzing-results.md). Never diagnose an old
head's result as a failure of the current branch. Track failure signatures and
attempted fixes for this PR so duplicate events do not trigger duplicate work.

1. Serialize CI repair with conflict repair. Apply the same worktree ownership,
   clean-tree, branch, in-progress-operation and remote-head checks above.
2. Diagnose from failed steps and reproduce with the project's targeted test or
   validation recipes. Read relevant skills before changing code. Do not simply
   rerun a failed job, loosen assertions or disable checks to get green.
3. Fix failures introduced by this PR, run relevant verification, then commit
   and push the targeted fix when authorized. Honor explicit no-commit/no-push
   instructions and tool approvals. Do not deploy, change secrets or permissions,
   or bypass protection rules as part of CI repair.
4. For pre-existing failures, follow Phase 7's user-choice requirement rather
   than silently expanding the PR. For infrastructure/auth/approval blockers,
   report evidence and the required intervention; do not retry indefinitely.
5. After each push, discard the prior head's CI summary and watch checks for the
   new head. Handle new failures through this same loop; check main conflicts
   every 30 minutes throughout. A fix push does not wait for the next tick:
   re-arm immediately so the new head gets checked now. Re-run coverage/screenshots if fixes change
   behaviour or visuals. A report is a checkpoint, not a reason to stop watching.
6. If the same failure survives two verified repair attempts, or intent is
   ambiguous, pause automatic repair and ask the user with logs and attempted
   fixes. Keep read-only monitoring active without repeating the blocked action.

Stop and notify the user on an actionable blocker. Announce verified recovery
once per head, not on every tick. Never label an unexplained failure flaky.

## Stop and cleanup

Record the monitor task ID. Stop it with `TaskStop` when the PR closes/merges,
the user cancels, or the branch is handed off. Reusing `/pr` for the same PR
must reuse its active monitor rather than starting a duplicate. Do not claim
monitoring continues after session exit or after expiry without re-arming.
