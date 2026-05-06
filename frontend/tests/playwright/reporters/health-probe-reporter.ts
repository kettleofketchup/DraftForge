import * as fs from 'node:fs';
import * as path from 'node:path';
import * as https from 'node:https';
import type { Reporter, TestCase, TestResult } from '@playwright/test/reporter';

/**
 * Playwright reporter that pings `/api/healthz` after every test and writes a
 * JSONL line per test with:
 *   - test title / file / outcome / duration
 *   - probe HTTP status, total roundtrip ms, and the backend's reported
 *     internal db_ms (a single Event.id SELECT)
 *
 * Purpose: surface cumulative test-stack pressure. Late-suite tests
 * sometimes time out on first attempt and pass on retry — we suspected
 * accumulated DB / Celery / Redis state. With this reporter every run
 * produces a timeseries we can correlate with failures.
 *
 * Output: `frontend/test-results/run-logs/health-probe-<stamp>.jsonl`.
 *
 * Pair with `playwright.config.ts` `trace: 'retain-on-failure'` and
 * `just test::pw::headless-with-logs` (which streams backend logs to the
 * same directory) for a complete failure-evidence package.
 */

interface ProbeResult {
  ok: boolean;
  status: number;
  totalMs: number;
  dbMs: number | null;
  error?: string;
}

// Test-only endpoint, gated by `isTestEnvironment()` in backend/urls.py —
// lives under `api/tests/` alongside the other test-only login + reset
// helpers. NOT reachable in prod/release.
const HEALTH_URL = process.env.PLAYWRIGHT_HEALTH_URL ?? 'https://localhost/api/tests/healthz/';
const HEALTH_TIMEOUT_MS = 5000;

function probeOnce(): Promise<ProbeResult> {
  return new Promise((resolve) => {
    const start = Date.now();
    const url = new URL(HEALTH_URL);
    const req = https.request(
      {
        hostname: url.hostname,
        port: url.port || 443,
        path: url.pathname,
        method: 'GET',
        rejectUnauthorized: false,
        timeout: HEALTH_TIMEOUT_MS,
      },
      (res) => {
        const chunks: Buffer[] = [];
        res.on('data', (c) => chunks.push(c));
        res.on('end', () => {
          const totalMs = Date.now() - start;
          const body = Buffer.concat(chunks).toString('utf-8');
          let dbMs: number | null = null;
          try {
            const parsed = JSON.parse(body);
            dbMs = typeof parsed.db_ms === 'number' ? parsed.db_ms : null;
          } catch {
            // ignore parse error — probe still recorded
          }
          resolve({ ok: (res.statusCode ?? 0) < 400, status: res.statusCode ?? 0, totalMs, dbMs });
        });
      },
    );
    req.on('timeout', () => {
      req.destroy();
      resolve({ ok: false, status: 0, totalMs: Date.now() - start, dbMs: null, error: 'timeout' });
    });
    req.on('error', (err) => {
      resolve({ ok: false, status: 0, totalMs: Date.now() - start, dbMs: null, error: String(err) });
    });
    req.end();
  });
}

class HealthProbeReporter implements Reporter {
  private logFile = '';
  private testIndex = 0;

  onBegin() {
    const dir = path.resolve('test-results/run-logs');
    fs.mkdirSync(dir, { recursive: true });
    const stamp = new Date().toISOString().replace(/[:.]/g, '-');
    this.logFile = path.join(dir, `health-probe-${stamp}.jsonl`);
    fs.writeFileSync(
      this.logFile,
      JSON.stringify({ event: 'begin', timestamp: new Date().toISOString() }) + '\n',
    );
  }

  async onTestEnd(test: TestCase, result: TestResult) {
    this.testIndex += 1;
    const probe = await probeOnce();
    const line = JSON.stringify({
      event: 'test-end',
      idx: this.testIndex,
      timestamp: new Date().toISOString(),
      title: test.title,
      file: path.relative(process.cwd(), test.location.file),
      status: result.status,
      retry: result.retry,
      durationMs: result.duration,
      probeStatus: probe.status,
      probeMs: probe.totalMs,
      probeDbMs: probe.dbMs,
      probeError: probe.error,
    });
    fs.appendFileSync(this.logFile, line + '\n');
  }

  onEnd() {
    fs.appendFileSync(
      this.logFile,
      JSON.stringify({ event: 'end', timestamp: new Date().toISOString(), totalTests: this.testIndex }) + '\n',
    );
  }
}

export default HealthProbeReporter;
