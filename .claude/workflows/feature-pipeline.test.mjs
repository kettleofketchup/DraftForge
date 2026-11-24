import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

const source = (await readFile(new URL('./feature-pipeline.js', import.meta.url), 'utf8'))
  .replace('export const meta =', 'const meta =');
const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor;
const workflow = new AsyncFunction('args', 'agent', 'parallel', 'phase', 'log', source);
const args = {
  worktree: '/tmp/workflow-fixture', branch: 'feature/example', slug: 'example',
  date: '2026-11-24', title: 'Example', request: 'Example', decisions: '', skills: '',
  recon: [], specLenses: [], planLenses: [], finalLenses: ['correctness'],
};
const approved = {
  approved: true, head: 'abc123', title: 'Example', bodyPath: '/tmp/body',
  draft: false, report: 'Approved',
};
const published = {
  status: 'opened', url: 'https://example.invalid/pull/1', number: 1,
  head: 'abc123', screenshotFiles: [], report: 'Opened',
};

async function run(overrides = {}) {
  const calls = [];
  const result = await workflow(args, async (prompt, options) => {
    calls.push({ prompt, ...options });
    if (Object.hasOwn(overrides, options.label)) return overrides[options.label];
    if (options.label === 'plan-revise') return { tasks: [] };
    if (options.label.startsWith('final-review:')) return { findings: [] };
    if (options.label === 'comment-review') return 'Final HEAD receipt';
    if (options.label === 'pr-preflight') return approved;
    if (options.label === 'open-pr') return published;
    return { report: 'Checks passed' };
  }, thunks => Promise.all(thunks.map(fn => fn())), () => {}, () => {});
  return { result, calls };
}

function assertNotPublished(calls) {
  assert.equal(calls.some(call => call.label === 'open-pr'), false);
}

test('opens a PR only after comments and publication preflight', async () => {
  const { result, calls } = await run();
  const labels = calls.map(call => call.label);
  assert(labels.indexOf('comment-review') < labels.indexOf('pr-preflight'));
  assert(labels.indexOf('pr-preflight') < labels.indexOf('open-pr'));
  assert.equal(result.publication.status, 'opened');
  assert.match(result.monitoringHandoff, /parent session/);
  assert.match(result.monitoringHandoff, /invoke \/pr for PR #1/);
  assert.match(result.monitoringHandoff, /30-minute/);
  assert.doesNotMatch(result.monitoringHandoff, /five-minute/);
  assert.equal(result.screenshotsRequired, false);
  assert.match(result.monitoringHandoff, /No screenshots:/);
});

test('hands off required screenshots when non-test frontend code changed', async () => {
  const files = ['frontend/app/lib/logger.ts', 'frontend/app/routes/home.tsx'];
  const { result } = await run({ 'open-pr': { ...published, screenshotFiles: files } });
  assert.equal(result.screenshotsRequired, true);
  assert.match(result.monitoringHandoff, /Screenshots REQUIRED/);
  assert.match(result.monitoringHandoff, /frontend\/app\/lib\/logger\.ts/);
  assert.match(result.monitoringHandoff, /never the skip comment/);
});

test('preflight and publication prompts run the frontend screenshot gate', async () => {
  const { calls } = await run();
  for (const label of ['pr-preflight', 'open-pr']) {
    assert.match(calls.find(call => call.label === label).prompt, /frontend-screenshot-gate\.sh/);
  }
});

for (const label of ['verify:full', 'comment-review', 'final-review:1', 'pr-preflight']) {
  test(`does not publish when ${label} is missing`, async () => {
    const { result, calls } = await run({ [label]: null });
    assertNotPublished(calls);
    assert.equal(result.blocked.stage, 'PR preflight');
  });
}

test('does not publish after rejected sensitive-information review', async () => {
  const { calls } = await run({ 'pr-preflight': { ...approved, approved: false } });
  assertNotPublished(calls);
});

test('does not publish when final findings remain blocked', async () => {
  const { calls } = await run({
    'final-review:1': { findings: [{ severity: 'major', title: 'Defect' }] },
    'final-fix': { status: 'blocked', commits: [], testsRun: '', notes: 'Blocked' },
  });
  assertNotPublished(calls);
});

test('returns an existing open PR without losing the monitoring handoff', async () => {
  const { result } = await run({ 'open-pr': { ...published, status: 'reused' } });
  assert.equal(result.publication.status, 'reused');
  assert.match(result.monitoringHandoff, /parent session/);
});

test('does not hand off monitoring after blocked publication', async () => {
  const { result } = await run({ 'open-pr': { ...published, status: 'blocked' } });
  assert.equal(result.monitoringHandoff, null);
});

test('publication prompt pins approval, prohibits force push and delegates monitoring', async () => {
  const { calls } = await run();
  const prompt = calls.find(call => call.label === 'open-pr').prompt;
  assert.match(prompt, /abc123/);
  assert.match(prompt, /HEAD still equals the approved hash/);
  assert.match(prompt, /Never force-push/);
  assert.match(prompt, /do not start a session-only monitor or capture screenshots inside this short-lived agent/);
});
