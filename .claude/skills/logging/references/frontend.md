# Frontend Logging Reference

## Overview

Frontend uses browser `console` methods. No structured logging library — Sentry captures errors and replays. Console logs are for development debugging only; they don't ship to Grafana.

## Console Usage

```typescript
// Use console methods matching severity
console.debug('WebSocket message received', { type, draftId });
console.info('Draft connected', { draftId, isCaptain });
console.warn('Heartbeat interval already running');
console.error('WebSocket connection failed', { draftId, error });
```

## Conventions

- Use **object context** as second argument, not string interpolation
- Prefix with component/system name for grep-ability in devtools
- Never log sensitive data (tokens, passwords, PII)

```typescript
// Good
console.info('[HeroDraft] Captain connected', { draftId, userId });
console.warn('[WebSocket] Reconnecting', { attempt: 3, url });

// Bad
console.log('connected');
console.log(`Draft ${draftId} user ${userId} connected`);
```

## Sentry Integration

Errors captured by Sentry (`Sentry.captureException`) include replay session data. Sentry Replay is configured with `maskAllText: false` and `blockAllMedia: false` (see `frontend/app/lib/sentry.ts`).

For intentional error reporting:

```typescript
import { Sentry } from '~/lib/sentry';

try {
  await riskyOperation();
} catch (err) {
  Sentry.captureException(err, {
    tags: { system: 'herodraft', subsystem: 'connection' },
    extra: { draftId, userId },
  });
}
```

Use the same `system`/`subsystem` taxonomy as backend when tagging Sentry events for cross-stack filtering.

## WebSocket Store Logging

The `heroDraftStore` uses a module-level logger pattern:

```typescript
const log = {
  debug: (...args: unknown[]) => console.debug('[HeroDraft]', ...args),
  warn: (...args: unknown[]) => console.warn('[HeroDraft]', ...args),
  error: (...args: unknown[]) => console.error('[HeroDraft]', ...args),
};
```

Follow this pattern for new stores/features that need namespaced console output.

## Log Levels in Practice

| Method | When |
|--------|------|
| `console.debug` | WS messages, state updates, render cycles — noisy |
| `console.info` | Connection lifecycle, user actions, feature activation |
| `console.warn` | Unexpected state that self-recovers (reconnect, retry) |
| `console.error` | Failures — also send to Sentry |
