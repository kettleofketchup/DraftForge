# Phase 4 — Watch CI

## Watch

PR CI (Playwright shards, backend tests, lint, changelog, preview images) usually
finishes in 10–25 min. Watch with a 30 min ceiling:

```bash
PR=$(gh pr view --json number -q .number)
timeout 30m gh pr checks "$PR" --watch --interval 60
```

`--watch` exits once no check is pending; its exit code is non-zero when any check
failed, which is a result to analyse, not an error to retry.

Run it with a Bash timeout above 30 min, or in the background and wait for the exit
notification. Checks that have not registered yet (a push seconds ago) show as "no
checks reported": wait a minute and re-run.

## Narration

One short line per change in state, e.g. `CI: 14 pass, 3 pending, 1 fail (Playwright shard 2/4)`.
No full JSON, and no `gh run view --log` output during the watch (that is Phase 5).

For a compact snapshot at any point:

```bash
gh pr view "$PR" --json statusCheckRollup --jq '
  {total:   (.statusCheckRollup | length),
   pending: (.statusCheckRollup | map(select((.status // "COMPLETED") != "COMPLETED")) | length),
   failed:  (.statusCheckRollup | map(select(.conclusion == "FAILURE")) | length)}'
```

## Timeout

If `timeout` ends the watch (exit 124), list the still-pending checks by name and run
Phase 5 on what completed. Required-status rules can leave an external check pending
forever; the pending list in the report makes that visible. The user can re-run `/pr`
to pick up the rest.
