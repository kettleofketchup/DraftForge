# Phase 4 — Monitor CI + Copilot

## Polling loop (single source of truth)

15-min ceiling, 30 s cadence = 30 iterations. Break early when both axes are done.

```bash
PR=$(gh pr view --json number -q .number)
for i in $(seq 1 30); do
  state=$(gh pr view "$PR" --json statusCheckRollup,reviews,reviewRequests --jq '
    {
      checks_total:   (.statusCheckRollup | length),
      checks_pending: (.statusCheckRollup | map(select((.status // "COMPLETED") != "COMPLETED")) | length),
      checks_failed:  (.statusCheckRollup | map(select(.conclusion == "FAILURE")) | length),
      copilot_pending: (.reviewRequests | any((.login // "") | test("copilot"; "i"))),
      copilot_done:    (.reviews        | any((.author.login // "") | test("copilot"; "i")))
    }
  ')
  echo "iter $i/30: $(echo "$state" | jq -c '{checks_pending, checks_failed, copilot_pending, copilot_done}')"

  done=$(echo "$state" | jq -r '(.checks_pending == 0) and (.copilot_pending == false or .copilot_done == true)')
  [ "$done" = "true" ] && break
  sleep 30
done
```

## "Done" rules

| Axis | Done when… |
|------|-----------|
| CI checks | `checks_pending == 0` (every check has `status: COMPLETED`) |
| Copilot review | `copilot_pending == false` OR `copilot_done == true` |

Both axes must be `done` for early-break. If only one is done, keep polling for the other within the 15 min budget.

## Bot-login matching is fuzzy on purpose

`@copilot` resolves to one of:
- `copilot-pull-request-reviewer[bot]` (most common)
- `Copilot` (some org configs)
- a third-party reviewer integration named `*copilot*`

Always match case-insensitively on substring `copilot`. Never hardcode the exact login — it changes and breaks the skill silently.

## Why polling, not `gh pr checks --watch`

`gh pr checks <N> --watch` blocks until checks finish but ignores Copilot review state. We need both axes in one loop, so polling wins. If checks alone are interesting (rare), `gh pr checks <N> --watch --interval 30` is fine.

## Narration rules (what to print to the user)

During polling, output **one short line per iteration** so the user sees progress. Acceptable:

```
iter 4/30: {"checks_pending":3,"checks_failed":0,"copilot_pending":true,"copilot_done":false}
```

NOT acceptable:
- Dumping the full `gh pr view` JSON every iteration.
- Streaming `gh run view --log` output during polling — those go to Phase 5.
- Silent polling (>30 s of no output makes the user think it's hung).

## Timeout behaviour

If the loop exits without `done=true`:

```bash
[ "$i" -eq 30 ] && echo "timeout after 15 min — proceeding to analysis with partial data"
```

Phase 5 still runs against whatever state is available — there's almost always *something* useful (failed checks already visible, Copilot's review may have arrived in the last 30 s, etc.).

## Refresh / re-review

If the user wants to re-trigger Copilot after pushing new commits:

```bash
gh pr edit "$PR" --remove-reviewer @copilot
gh pr edit "$PR" --add-reviewer @copilot
```

The remove-then-add cycle is the most reliable way; just `--add-reviewer` on an already-requested reviewer is a no-op.

## Caveats

- **June 1, 2026:** Copilot review runs consume GitHub Actions minutes. Surface this if the user asks to run `/pr` repeatedly on the same PR — repeated re-reviews are not free.
- **Required-status-check rules** can leave a check in `PENDING` indefinitely if a required external check never runs. The polling loop will time out and the report will list the still-pending checks by name.
