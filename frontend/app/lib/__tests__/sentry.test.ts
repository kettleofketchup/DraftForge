// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest';
import { DEFAULT_SENTRY_DSN, initSentry, resolveSentryDsn } from '~/lib/sentry';

const sentryInit = vi.fn();
vi.mock('@sentry/react-router', () => ({
  init: (...args: unknown[]) => sentryInit(...args),
  reactRouterTracingIntegration: () => ({}),
  replayIntegration: () => ({}),
}));

describe('resolveSentryDsn', () => {
  it('is off when VITE_SENTRY_ENABLED is unset (dev servers, tests)', () => {
    expect(resolveSentryDsn({})).toBeNull();
    expect(resolveSentryDsn({ VITE_SENTRY_DSN: 'https://k@example.test/1' })).toBeNull();
  });

  it('is off for any value other than true', () => {
    expect(resolveSentryDsn({ VITE_SENTRY_ENABLED: 'false' })).toBeNull();
    expect(resolveSentryDsn({ VITE_SENTRY_ENABLED: '1' })).toBeNull();
    expect(resolveSentryDsn({ VITE_SENTRY_ENABLED: '' })).toBeNull();
  });

  it('uses the project DSN when enabled without an override', () => {
    expect(resolveSentryDsn({ VITE_SENTRY_ENABLED: 'true' })).toBe(DEFAULT_SENTRY_DSN);
    expect(resolveSentryDsn({ VITE_SENTRY_ENABLED: 'TRUE', VITE_SENTRY_DSN: ' ' })).toBe(
      DEFAULT_SENTRY_DSN,
    );
  });

  it('uses VITE_SENTRY_DSN when enabled with an override', () => {
    expect(
      resolveSentryDsn({ VITE_SENTRY_ENABLED: 'true', VITE_SENTRY_DSN: 'https://k@example.test/1' }),
    ).toBe('https://k@example.test/1');
  });
});

describe('initSentry', () => {
  afterEach(() => {
    vi.unstubAllEnvs();
    sentryInit.mockClear();
  });

  it('does not initialise Sentry when the build does not enable it', async () => {
    vi.stubEnv('VITE_SENTRY_ENABLED', '');
    await initSentry();
    expect(sentryInit).not.toHaveBeenCalled();
  });

  it('initialises Sentry with the resolved DSN when enabled', async () => {
    vi.stubEnv('VITE_SENTRY_ENABLED', 'true');
    vi.stubEnv('VITE_SENTRY_DSN', 'https://k@example.test/1');
    await initSentry();
    expect(sentryInit).toHaveBeenCalledWith(
      expect.objectContaining({ dsn: 'https://k@example.test/1' }),
    );
  });
});
