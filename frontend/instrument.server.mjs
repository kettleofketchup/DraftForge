import * as Sentry from '@sentry/react-router';

Sentry.init({
  dsn: 'https://54c5b2164095f34b34dfb66072ca90f5@o4510850673213440.ingest.us.sentry.io/4510850704867328',
  sendDefaultPii: true,
  enableLogs: true,
  tracesSampleRate: 0.2,
  environment: process.env.NODE_ENV || 'production',
});
