# Phase 6 — Analyse and report

## CI failures

### Pull failed runs

```bash
PR=$(gh pr view --json number -q .number)
branch=$(git branch --show-current)
failed=$(gh run list --branch "$branch" --status failure \
  --json databaseId,name,conclusion,url --limit 20)
```

For each failed run, fetch only the failed steps' log:

```bash
echo "$failed" | jq -c '.[]' | while read -r run; do
  id=$(echo "$run" | jq -r .databaseId)
  name=$(echo "$run" | jq -r .name)
  echo "=== $name ($id) ==="
  gh run view "$id" --log-failed 2>/dev/null \
    | grep -E '(FAIL|FAILED|Error|Traceback|AssertionError|^\s*assert|^\s*[A-Za-z_]+Error:|^\s*\w+: error:|\.\w+:[0-9]+:[0-9]*:?\s|::error|##\[error\])' \
    | head -10
done
```

The `grep -E` is intentionally broad — it catches Python tracebacks, pytest `FAIL` lines, Playwright `Error:` lines, TypeScript compiler errors, and shell `exit 1`-driven failures. Cap at 10 lines per step to keep the chat readable.

### Surface root-cause hints

Look for canonical patterns and tag them:

| Pattern in logs | Likely cause | Suggested next step |
|-----------------|--------------|---------------------|
| `OperationalError: no such table` | Migrations not applied in test DB | `just db::reset-test` |
| `cacheops` / `Redis connection refused` | Redis not up in test stack | `just test::up` |
| `Error: page.goto: Timeout` | Frontend not ready before Playwright fired | Check `webServer` block in `playwright.config.ts` |
| `Cannot find module '~/...'` | Path alias broken | Vite/tsconfig path alias regression |
| `Type 'X' is not assignable` | TypeScript error | Run `npm run typecheck` locally |
| `changelog.d/`, `CHANGELOG.md` or `released in` in the `changelog` job | Changelog gate | See the CI-gate table in `.claude/skills/changelog/SKILL.md`: move the bullets to a fragment, rename a reused path (`<slug>-2.md`) or delete a restored one, reword a bullet identical to a released one, or add `changelog:edit` and `gh run rerun <id> --failed` |

This list is starter — extend it whenever a new repeat-offender shows up.

### "Pre-existing vs introduced"

Per repo feedback, **never call a test flaky and never silently skip a pre-existing bug.** If a CI failure looks unrelated to the diff (test name doesn't touch any file in `gh pr diff --name-only`), say so explicitly:

> ⚠ Pre-existing failure: `test_X` failed in `Y.py` but the diff doesn't touch `Y.py` or its dependencies. This is a bug to surface, not flake.

## Output format

Single report, sections in this order:

```
PR #<N>: <title>
URL: <html_url>

## CI ({pending}/{total} pending, {failed} failed)

### ❌ <run name> ({id})
<extracted error lines>

### ❌ <run name> ({id})
<extracted error lines>

(if no failures: ✓ All checks passing)

### Pending at timeout: <check names>   (only if the watch timed out)

## Screenshots

<link to the screenshot comment> — <N> changes, <desktop/mobile>
(or: skipped, no visual changes / pending, no free slot)

## Recommended next steps

1. <highest-severity / most-actionable item>
2. ...
```

## Output discipline

- **No raw JSON dumps in the report.** Use the structured format above.
- **Root-cause hints point at real paths.** Name a `.claude/skills/<name>/` only if it exists locally.
- **End with actionable next steps**, not a flat list of every issue.
