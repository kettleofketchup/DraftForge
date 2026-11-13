import { describe, expect, it, vi } from 'vitest';
import { NO_SLOT_MESSAGE, parseSlotFile, resolveBaseUrl } from '../playwright/fixtures/base-url-resolve';

const slot = (o: Record<string, string> = {}) =>
  Object.entries({ DF_SLOT: '2', DF_BASE_URL: 'https://s2.localhost:12443', DF_WORKTREE: '/wt', DF_SLOT_TOKEN: 'tok', DF_REGISTRY: '/reg', ...o })
    .map(([k, v]) => `${k}=${v}`).join('\n');
const RES = 'owner=/wt\ntoken=tok\nlast_used=1';
const OK = { '/wt/docker/.env.slot': slot(), '/reg/slot-2': RES };
const id = (p: string) => p.replace(/\/+$/, '');
const input = (env: Record<string, string | undefined>, fsMap: Record<string, string> = {}, root = '/wt') => {
  const readFile = vi.fn((p: string) => fsMap[p] ?? null);
  return { env, repoRoot: () => root, readFile, realpath: id };
};

describe('resolveBaseUrl', () => {
  it('env with marker=runner wins and never reads files', () => {
    const i = input({ DF_BASE_URL: 'https://s5.localhost:15443', DF_BASE_URL_SOURCE: 'runner' }, OK);
    expect(resolveBaseUrl(i)).toBe('https://s5.localhost:15443');
    expect(i.readFile).not.toHaveBeenCalled();
  });
  it('marker=container with a disagreeing slot file returns env without reading files', () => {
    const i = input({ DF_BASE_URL: 'https://nginx', DF_BASE_URL_SOURCE: 'container' }, OK);
    expect(resolveBaseUrl(i)).toBe('https://nginx');
    expect(i.readFile).not.toHaveBeenCalled();
  });
  it('env without marker and no slot file returns env', () => {
    const i = input({ DF_BASE_URL: 'https://localhost' }, {});
    expect(resolveBaseUrl(i)).toBe('https://localhost');
    expect(i.readFile.mock.calls).toEqual([['/wt/docker/.env.slot']]);
    expect(i.readFile.mock.results[0].value).toBeNull();
  });
  it('slot file used when env unset', () => {
    expect(resolveBaseUrl(input({}, OK))).toBe('https://s2.localhost:12443');
  });
  it('GITHUB_ACTIONS fallback', () => {
    expect(resolveBaseUrl(input({ GITHUB_ACTIONS: 'true' }, {}))).toBe('https://localhost');
  });
  it('CI=true alone throws NO_SLOT_MESSAGE', () => {
    expect(() => resolveBaseUrl(input({ CI: 'true' }, {}))).toThrow(NO_SLOT_MESSAGE);
  });
  it('DF_WORKTREE mismatch throws', () => {
    const i = input({}, { '/wt/docker/.env.slot': slot({ DF_WORKTREE: '/other' }), '/reg/slot-2': RES });
    expect(() => resolveBaseUrl(i)).toThrow('`.env.slot` was written for /other');
  });
  it('repoRoot with trailing slash still matches', () => {
    expect(resolveBaseUrl(input({}, OK, '/wt/'))).toBe('https://s2.localhost:12443');
  });
  it('registry token mismatch throws "now belongs to"', () => {
    const i = input({}, { '/wt/docker/.env.slot': slot(), '/reg/slot-2': 'owner=/other\ntoken=x\nlast_used=1' });
    expect(() => resolveBaseUrl(i)).toThrow('slot 2 now belongs to /other');
  });
  it('missing reservation throws', () => {
    expect(() => resolveBaseUrl(input({}, { '/wt/docker/.env.slot': slot() }))).toThrow('no reservation for slot 2');
  });
  it('stale DF_BASE_URL without source marker throws "disagrees"', () => {
    expect(() => resolveBaseUrl(input({ DF_BASE_URL: 'https://localhost' }, OK))).toThrow('disagrees');
  });
  it('stale export with matching slot passes', () => {
    expect(resolveBaseUrl(input({ DF_BASE_URL: 'https://s2.localhost:12443' }, OK))).toBe('https://s2.localhost:12443');
  });
  it('slot file without DF_BASE_URL throws', () => {
    const i = input({}, { '/wt/docker/.env.slot': slot({ DF_BASE_URL: '' }), '/reg/slot-2': RES });
    expect(() => resolveBaseUrl(i)).toThrow('has no DF_BASE_URL');
  });
});

it('parseSlotFile ignores comments and blank lines', () => {
  expect(parseSlotFile('# generated\n\nA=1\nB=\n')).toEqual({ A: '1', B: '' });
});
