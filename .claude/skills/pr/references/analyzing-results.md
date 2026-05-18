# Phase 5 — Analyse and report

Two pulls happen in parallel; one merged report goes to the user.

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
    | grep -E '(FAIL|FAILED|Error|Traceback|AssertionError|^\s*assert|^\s*[A-Za-z_]+Error:|^\s*\w+: error:|\.\w+:[0-9]+:[0-9]*:?\s)' \
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

This list is starter — extend it whenever a new repeat-offender shows up.

### "Pre-existing vs introduced"

Per repo feedback, **never call a test flaky and never silently skip a pre-existing bug.** If a CI failure looks unrelated to the diff (test name doesn't touch any file in `gh pr diff --name-only`), say so explicitly:

> ⚠ Pre-existing failure: `test_X` failed in `Y.py` but the diff doesn't touch `Y.py` or its dependencies. This is a bug to surface, not flake.

## Copilot inline comments

### Pull comments

```bash
comments=$(gh api "repos/{owner}/{repo}/pulls/$PR/comments" \
  --jq '[.[] | select((.user.login // "") | test("copilot"; "i"))
       | {path, line, body, html_url}]')
top_review=$(gh api "repos/{owner}/{repo}/pulls/$PR/reviews" \
  --jq '[.[] | select((.user.login // "") | test("copilot"; "i"))
       | {state, body, submitted_at}] | last')
```

### Match each comment to a skill

For every comment, walk each `.github/instructions/*.instructions.md` file, parse its `applyTo` glob, and check whether the comment's `path` matches. A comment can match multiple files (e.g., a frontend component file matches both `react.instructions.md` and `brand.instructions.md`).

```bash
# Pseudocode — implement inline in the skill turn
for c in comments:
  matched_skills = []
  for inst_file in .github/instructions/*.instructions.md:
    applyTo = parse_frontmatter(inst_file).applyTo  # comma-separated globs
    if any(fnmatch(c.path, g) for g in applyTo.split(',')):
      matched_skills.append(basename(inst_file).removesuffix('.instructions.md'))
  c.skills = matched_skills
```

Tag each comment with its matched skill(s) so the user knows which canonical source to consult.

### Severity heuristic

Copilot doesn't expose a severity field. Infer from the comment body:

| Keywords | Severity |
|----------|----------|
| "must", "should not", "never", "incorrect", "broken", "wrong" | **block** |
| "consider", "you may want", "could improve", "suggestion" | **nit** |
| Everything else | **warn** |

Don't be precious about it — this is a hint to the user, not a contract.

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

## Copilot review ({comment count} comments, top-level state: {state})

Top-level: <one-line summary of top_review.body>

### <path>:<line>  [skills: brand, react]  severity: block
<comment.body trimmed to ~3 lines>
→ canonical: .claude/skills/<skill>/SKILL.md

(repeat per comment, grouped by file)

## Recommended next steps

1. <highest-severity / most-actionable item>
2. ...
```

## Output discipline

- **No raw JSON dumps in the report.** Use the structured format above.
- **No more than ~10 inline comments shown.** If Copilot left more, summarise the rest as "+N more in <files>".
- **Skill-pointer lines must be valid paths.** If `.claude/skills/<name>/` doesn't exist locally, drop the pointer rather than print a broken path.
- **End with actionable next steps**, not a flat list of every issue.
