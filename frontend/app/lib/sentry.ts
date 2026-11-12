// The project's Sentry DSN. Production images enable reporting with
// VITE_SENTRY_ENABLED=true (a build arg in frontend/Dockerfile); dev servers,
// test stacks and vitest leave it unset, so they never send events.
export const DEFAULT_SENTRY_DSN =
  'https://54c5b2164095f34b34dfb66072ca90f5@o4510850673213440.ingest.us.sentry.io/4510850704867328';

// import.meta.env, or any map of build variables.
type SentryEnv = Readonly<Record<string, unknown>>;

const text = (value: unknown): string => (typeof value === 'string' ? value.trim() : '');

/** The DSN to report to, or null when Sentry stays off for this build. */
export function resolveSentryDsn(env: SentryEnv): string | null {
  if (text(env.VITE_SENTRY_ENABLED).toLowerCase() !== 'true') return null;
  return text(env.VITE_SENTRY_DSN) || DEFAULT_SENTRY_DSN;
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
let _sentry: any = null;

export async function initSentry() {
  if (typeof window === 'undefined') return;
  const dsn = resolveSentryDsn(import.meta.env);
  if (!dsn) return;

  try {
    const Sentry = await import('@sentry/react-router');
    _sentry = Sentry;

    Sentry.init({
      dsn,
      sendDefaultPii: true,
      enableLogs: true,
      integrations: [
        Sentry.reactRouterTracingIntegration(),
        Sentry.replayIntegration({
          maskAllText: false,
          blockAllMedia: false,
        }),
      ],
      tracesSampleRate: 0.2,
      tracePropagationTargets: [/^\//, /^https:\/\/dota\.kettle\.sh\/api/],
      replaysSessionSampleRate: 0.1,
      replaysOnErrorSampleRate: 1.0,
      environment: import.meta.env.MODE,
    });
  } catch {
    // @sentry/react-router not available in test images
  }
}

/**
 * No-op-safe Sentry proxy. All calls are silently ignored if Sentry
 * failed to load or hasn't been initialized.
 */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export const Sentry: any = new Proxy(
  {},
  {
    get(_target, prop) {
      if (_sentry) return _sentry[prop];
      if (prop === 'captureException' || prop === 'captureMessage') {
        return () => {};
      }
      return undefined;
    },
  },
);
