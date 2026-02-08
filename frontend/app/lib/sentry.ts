import * as Sentry from '@sentry/react-router';

const DSN =
  'https://54c5b2164095f34b34dfb66072ca90f5@o4510850673213440.ingest.us.sentry.io/4510850704867328';

export function initSentry() {
  if (typeof window === 'undefined') return;
  if (import.meta.env.DEV) return;

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
}

export { Sentry };
