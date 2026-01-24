# Playwright Performance Optimization Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Optimize Playwright test execution speed through CI sharding, reduced waits, and better parallelization.

**Architecture:** Add GitHub Actions matrix sharding, replace arbitrary timeouts with explicit waits, and improve test isolation for higher parallelism.

**Tech Stack:** Playwright, GitHub Actions, TypeScript

---

## Task 1: Add CI Sharding to GitHub Actions

**Files:**
- Modify: `.github/workflows/playwright.yml`

**Step 1: Read the current workflow file**

```bash
cat .github/workflows/playwright.yml
```

**Step 2: Add matrix strategy for sharding**

Update the playwright job to use a matrix strategy:

```yaml
jobs:
  playwright:
    runs-on: ubuntu-latest
    strategy:
      fail-fast: false
      matrix:
        shard: [1, 2, 3, 4]
    # ... existing config ...
```

**Step 3: Update the test run command to use shard**

```yaml
    - name: Run Playwright tests
      run: |
        poetry run inv test.playwright.headless -- --shard=${{ matrix.shard }}/${{ strategy.job-total }}
```

**Step 4: Update artifact upload to include shard number**

```yaml
    - name: Upload Playwright report
      if: failure()
      uses: actions/upload-artifact@v4
      with:
        name: playwright-report-${{ matrix.shard }}
        path: frontend/playwright-report/
```

**Step 5: Commit**

```bash
git add .github/workflows/playwright.yml
git commit -m "perf(ci): add 4-way sharding for Playwright tests"
```

---

## Task 2: Update Invoke Task to Support Sharding Args

**Files:**
- Modify: `scripts/tests.py`

**Step 1: Read the current tests.py file**

Find the `playwright_headless` task definition.

**Step 2: Add passthrough args support**

Update the headless task to accept additional Playwright args:

```python
@task
def playwright_headless(ctx, args=""):
    """Run Playwright tests in headless mode.

    Args:
        args: Additional arguments to pass to Playwright (e.g., --shard=1/4)
    """
    with ctx.cd("frontend"):
        ctx.run(f"npx playwright test --project=chromium --project=mobile-chrome {args}")
```

**Step 3: Verify the task works**

```bash
inv test.playwright.headless -- --shard=1/4
```

**Step 4: Commit**

```bash
git add scripts/tests.py
git commit -m "feat(invoke): add passthrough args to playwright tasks"
```

---

## Task 3: Replace waitForTimeout with Explicit Waits in Shuffle Draft Tests

**Files:**
- Modify: `frontend/tests/playwright/e2e/08-shuffle-draft/01-full-draft.spec.ts`
- Modify: `frontend/tests/playwright/e2e/08-shuffle-draft/02-roll.spec.ts`

**Step 1: Identify all waitForTimeout calls**

```bash
grep -n "waitForTimeout" frontend/tests/playwright/e2e/08-shuffle-draft/*.spec.ts
```

**Step 2: Replace with explicit waits**

Pattern replacements:

| Before | After |
|--------|-------|
| `await page.waitForTimeout(1000)` after click | `await page.waitForLoadState('networkidle')` |
| `await page.waitForTimeout(500)` before assertion | Remove (expect already waits) |
| `await page.waitForTimeout(2000)` for dialog | `await dialog.waitFor({ state: 'visible' })` |

Example replacement in `01-full-draft.spec.ts`:

```typescript
// Before
await page.locator('[data-testid="teamsTab"]').click({ force: true });
await page.waitForTimeout(1000);

// After
await page.locator('[data-testid="teamsTab"]').click({ force: true });
await page.waitForLoadState('networkidle');
```

**Step 3: Run tests to verify**

```bash
cd frontend && npx playwright test tests/playwright/e2e/08-shuffle-draft --project=chromium
```

**Step 4: Commit**

```bash
git add frontend/tests/playwright/e2e/08-shuffle-draft/
git commit -m "perf(tests): replace waitForTimeout with explicit waits in shuffle-draft"
```

---

## Task 4: Replace waitForTimeout with Explicit Waits in Draft Tests

**Files:**
- Modify: `frontend/tests/playwright/e2e/07-draft/01-captain-pick.spec.ts`
- Modify: `frontend/tests/playwright/e2e/07-draft/02-undo-pick.spec.ts`

**Step 1: Identify all waitForTimeout calls**

```bash
grep -n "waitForTimeout" frontend/tests/playwright/e2e/07-draft/*.spec.ts
```

**Step 2: Apply same replacement pattern as Task 3**

**Step 3: Run tests to verify**

```bash
cd frontend && npx playwright test tests/playwright/e2e/07-draft --project=chromium
```

**Step 4: Commit**

```bash
git add frontend/tests/playwright/e2e/07-draft/
git commit -m "perf(tests): replace waitForTimeout with explicit waits in draft tests"
```

---

## Task 5: Replace waitForTimeout with Explicit Waits in Bracket Tests

**Files:**
- Modify: `frontend/tests/playwright/e2e/09-bracket/01-bracket-badges.spec.ts`
- Modify: `frontend/tests/playwright/e2e/09-bracket/02-bracket-match-linking.spec.ts`
- Modify: `frontend/tests/playwright/e2e/09-bracket/03-bracket-winner-advancement.spec.ts`

**Step 1: Identify all waitForTimeout calls**

```bash
grep -n "waitForTimeout" frontend/tests/playwright/e2e/09-bracket/*.spec.ts
```

**Step 2: Apply same replacement pattern**

**Step 3: Run tests to verify**

```bash
cd frontend && npx playwright test tests/playwright/e2e/09-bracket --project=chromium
```

**Step 4: Commit**

```bash
git add frontend/tests/playwright/e2e/09-bracket/
git commit -m "perf(tests): replace waitForTimeout with explicit waits in bracket tests"
```

---

## Task 6: Replace waitForTimeout with Explicit Waits in League Tests

**Files:**
- Modify: `frontend/tests/playwright/e2e/10-leagues/01-tabs.spec.ts`

**Step 1: Identify all waitForTimeout calls**

```bash
grep -n "waitForTimeout" frontend/tests/playwright/e2e/10-leagues/*.spec.ts
```

**Step 2: Apply same replacement pattern**

**Step 3: Run tests to verify**

```bash
cd frontend && npx playwright test tests/playwright/e2e/10-leagues --project=chromium
```

**Step 4: Commit**

```bash
git add frontend/tests/playwright/e2e/10-leagues/
git commit -m "perf(tests): replace waitForTimeout with explicit waits in league tests"
```

---

## Task 7: Add Merge Job for Sharded Test Results

**Files:**
- Modify: `.github/workflows/playwright.yml`

**Step 1: Add a merge job that runs after all shards complete**

```yaml
  merge-reports:
    needs: playwright
    if: always()
    runs-on: ubuntu-latest
    steps:
      - name: Download all shard reports
        uses: actions/download-artifact@v4
        with:
          pattern: playwright-report-*
          path: all-reports

      - name: Merge reports
        run: |
          npx playwright merge-reports --reporter=html all-reports

      - name: Upload merged report
        uses: actions/upload-artifact@v4
        with:
          name: playwright-report-merged
          path: playwright-report/
          retention-days: 30
```

**Step 2: Commit**

```bash
git add .github/workflows/playwright.yml
git commit -m "feat(ci): add merged report job for sharded Playwright tests"
```

---

## Task 8: Add Global Setup for Shared Data Fetching

**Files:**
- Create: `frontend/tests/playwright/global-setup.ts`
- Modify: `frontend/playwright.config.ts`

**Step 1: Create global setup file**

This fetches shared test data once before all tests run:

```typescript
// frontend/tests/playwright/global-setup.ts
import { chromium, FullConfig } from '@playwright/test';

async function globalSetup(config: FullConfig) {
  const browser = await chromium.launch();
  const context = await browser.newContext({ ignoreHTTPSErrors: true });

  // Pre-fetch commonly used test data
  const tournamentsResponse = await context.request.get('https://localhost/api/tests/tournaments/');
  const leaguesResponse = await context.request.get('https://localhost/api/leagues/');

  // Store in environment for tests to access
  process.env.TEST_TOURNAMENTS = JSON.stringify(await tournamentsResponse.json());
  process.env.TEST_LEAGUES = JSON.stringify(await leaguesResponse.json());

  await browser.close();
}

export default globalSetup;
```

**Step 2: Add globalSetup to playwright.config.ts**

```typescript
export default defineConfig({
  globalSetup: require.resolve('./tests/playwright/global-setup.ts'),
  // ... rest of config
});
```

**Step 3: Update helpers to use cached data when available**

In `helpers/tournament.ts` and `helpers/league.ts`, check for env var first:

```typescript
export async function getTournamentByKey(context: BrowserContext, key: string): Promise<TournamentData | null> {
  // Check cached data first
  if (process.env.TEST_TOURNAMENTS) {
    const tournaments = JSON.parse(process.env.TEST_TOURNAMENTS);
    const found = tournaments.find((t: any) => t.key === key);
    if (found) return found;
  }

  // Fall back to API call
  const response = await context.request.get(`${API_URL}/tests/tournament-by-key/${key}/`);
  // ...
}
```

**Step 4: Run full test suite to verify**

```bash
cd frontend && npx playwright test
```

**Step 5: Commit**

```bash
git add frontend/tests/playwright/global-setup.ts frontend/playwright.config.ts frontend/tests/playwright/helpers/
git commit -m "perf(tests): add global setup for shared data caching"
```

---

## Task 9: Update Documentation

**Files:**
- Modify: `.claude/CLAUDE.md`

**Step 1: Add performance testing section**

Add to the Testing section:

```markdown
### Playwright Performance

**Local parallel execution:**
```bash
# Run with 50% of CPUs (default)
inv test.playwright.headless

# Run with specific worker count
inv test.playwright.headless -- --workers=4
```

**CI sharding:**
Tests are automatically sharded across 4 runners in CI for ~4x speedup.

**Run specific shard locally:**
```bash
inv test.playwright.headless -- --shard=1/4
```
```

**Step 2: Commit**

```bash
git add .claude/CLAUDE.md
git commit -m "docs: add Playwright performance documentation"
```

---

## Expected Results

| Metric | Before | After |
|--------|--------|-------|
| Local execution | Serial/slow | ~2-4x faster (50% CPU workers) |
| CI execution | Single runner | ~4x faster (4 shards) |
| Test reliability | waitForTimeout flakiness | Explicit waits = more stable |
| Data fetching | Per-test API calls | Cached in global setup |

---

## Verification Checklist

- [ ] CI sharding runs 4 parallel jobs
- [ ] All shards complete successfully
- [ ] Merged report is generated
- [ ] Local tests run with multiple workers
- [ ] No waitForTimeout calls remain in modified files
- [ ] Global setup caches test data
- [ ] Documentation updated
