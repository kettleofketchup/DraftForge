// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const warn = vi.fn();
vi.mock('~/lib/logger', () => ({ getLogger: () => ({ warn }) }));

type Utils = typeof import('../utils');

async function load(): Promise<Utils> {
  vi.resetModules();
  return import('../utils');
}

function setCookies(...pairs: string[]): void {
  for (const pair of pairs) document.cookie = `${pair}; path=/`;
}

describe('CSRF cookie name', () => {
  beforeEach(() => {
    warn.mockClear();
    setCookies('csrftoken=slot0', 'csrftoken-s3=slot3');
  });

  afterEach(() => {
    for (const name of ['csrftoken', 'csrftoken-s3']) {
      document.cookie = `${name}=; path=/; max-age=0`;
    }
    vi.unstubAllEnvs();
  });

  it('reads the build-time name until the backend says otherwise', async () => {
    const utils = await load();
    expect(utils.getCsrfCookieName()).toBe('csrftoken');
    expect(utils.getCsrfToken()).toBe('slot0');
  });

  it('switches to the backend name when the build-time name is stale, and warns', async () => {
    const utils = await load();
    utils.syncCsrfCookieName('csrftoken-s3');
    expect(utils.getCsrfToken()).toBe('slot3');
    expect(warn).toHaveBeenCalledTimes(1);

    utils.syncCsrfCookieName('csrftoken-s3');
    expect(warn).toHaveBeenCalledTimes(1);
  });

  it('stays quiet when the backend agrees with the build', async () => {
    vi.stubEnv('VITE_CSRF_COOKIE_NAME', 'csrftoken-s3');
    const utils = await load();
    utils.syncCsrfCookieName('csrftoken-s3');
    expect(utils.getCsrfToken()).toBe('slot3');
    expect(warn).not.toHaveBeenCalled();
  });

  it('ignores a missing or non-string header', async () => {
    const utils = await load();
    utils.syncCsrfCookieName(undefined);
    utils.syncCsrfCookieName('');
    utils.syncCsrfCookieName(['csrftoken-s3']);
    expect(utils.getCsrfCookieName()).toBe('csrftoken');
    expect(warn).not.toHaveBeenCalled();
  });
});
