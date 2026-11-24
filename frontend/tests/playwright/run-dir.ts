import * as path from 'node:path';

/**
 * Where one Playwright run writes its output. `just test::pw::*` sets
 * DF_PW_RUN_DIR to a directory of the run's own (scripts/pw-run-dir.sh), so
 * concurrent runs in one worktree never clean each other's output. Without it
 * (CI, a bare `npx playwright test`) the flat test-results/ and
 * playwright-report/ layout is kept.
 */
const runDir = process.env.DF_PW_RUN_DIR || undefined;

export const OUTPUT_DIR = runDir
  ? path.join(runDir, 'artifacts')
  : 'test-results/';
export const HTML_REPORT_DIR = runDir
  ? path.join(runDir, 'report')
  : 'playwright-report';
export const RUN_LOGS_DIR = path.resolve(
  runDir ? path.join(runDir, 'run-logs') : 'test-results/run-logs',
);
