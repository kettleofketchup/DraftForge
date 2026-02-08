import * as Sentry from '@sentry/react';

const DSN =
  'https://54c5b2164095f34b34dfb66072ca90f5@o4510850673213440.ingest.us.sentry.io/4510850704867328';

export function initSentry() {
  // Only initialize in production - skip in dev/test
  if (typeof window === 'undefined') return;
  if (import.meta.env.DEV) return;

  Sentry.init({
    dsn: DSN,
    sendDefaultPii: true,
    integrations: [Sentry.replayIntegration()],
    replaysSessionSampleRate: 0.1,
    replaysOnErrorSampleRate: 1.0,
    environment: process.env.NODE_ENV || 'production',
  });
}

export { Sentry };
