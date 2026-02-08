import type * as SentryType from '@sentry/react-router';

const DSN =
  'https://54c5b2164095f34b34dfb66072ca90f5@o4510850673213440.ingest.us.sentry.io/4510850704867328';

// Holds the Sentry namespace once loaded; starts as a no-op stub
let _sentry: typeof SentryType | null = null;

export async function initSentry() {
  if (typeof window === 'undefined') return;
  if (import.meta.env.DEV) return;

  try {
    const Sentry = await import(/* @vite-ignore */ '@sentry/react-router');
    _sentry = Sentry;

    Sentry.init({
      dsn: DSN,
      sendDefaultPii: true,
      enableLogs: true,
      integrations: [
        Sentry.reactRouterTracingIntegration(),
        Sentry.replayIntegration(),
      ],
      tracesSampleRate: 0.2,
      tracePropagationTargets: [/^\//, /^https:\/\/dota\.kettle\.sh\/api/],
      replaysSessionSampleRate: 0.1,
      replaysOnErrorSampleRate: 1.0,
      environment: import.meta.env.MODE,
    });
  } catch {
    // @sentry/react-router not available — expected in dev/test Docker images
  }
}

/**
 * No-op-safe Sentry proxy. All calls are silently ignored if Sentry
 * failed to load or hasn't been initialized.
 */
export const Sentry = new Proxy({} as typeof SentryType, {
  get(_target, prop) {
    if (_sentry) return (_sentry as Record<string | symbol, unknown>)[prop];
    // Return a no-op function for any method call
    if (prop === 'captureException' || prop === 'captureMessage') {
      return () => {};
    }
    return undefined;
  },
});
